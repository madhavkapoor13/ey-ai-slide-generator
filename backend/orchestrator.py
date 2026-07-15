"""
backend/orchestrator.py
========================
Phase 2 Orchestrator — the single component aware of the full pipeline.

Architecture
------------
The orchestrator coordinates the Phase 2 modules in a fixed sequential
order. It is the ONLY place in the codebase that knows the pipeline
topology. Every other component (modules, renderers, routes) is isolated
from this knowledge.

Pipeline
--------
::

    User Request (title, content)
         │
         ▼
    [1] extract_intent()        ─── Intent Module
         │  IntentResult
         ▼
    [2] plan_presentation()     ─── Narrative Planner
         │  DeckSpec
         ▼
    [3] analyze_information()   ─── Information Analyzer
         │  InformationResult
         ▼
    [4] generate_clarifications() ─── Clarification Engine (if needed)
         │  ClarificationResult
         ▼
    [5] build_context()         ─── Enterprise Context Builder (only if enough info)
         │  EnterpriseContext
         ▼
    [6] identify_process()      ─── Process Mapper
         │  ProcessResult
         ▼
    [7] execute_deck()          ─── Deck Executor
         │  DeckExecutionResult
         ▼
    Caller (slide_service_v2 → renderer)

The orchestrator returns a ``PipelineResult`` wrapper. If clarification is
required, downstream generation steps (context, process mapping, deck
execution) are skipped. Each user response is treated as a fresh pipeline
execution; no partial state is persisted.

Enterprise context and process mapping are computed exactly once and reused
by the Deck Executor for every slide.

Design constraints
------------------
- The orchestrator must NOT know about renderers, Office.js, or python-pptx.
- The orchestrator must NOT call the LLM directly.
- Each module boundary is a typed schema — no raw dicts cross boundaries
  except inside ``SlideSpec.raw_spec`` (renderer contract).
- All errors propagate upward; the orchestrator does not swallow exceptions.
"""

from __future__ import annotations

import logging

from backend.modules.clarification import generate_clarifications
from backend.modules.context import build_context
from backend.modules.deck_executor import execute_deck
from backend.modules.information_analyzer import analyze_information
from backend.modules.intent import extract_intent
from backend.modules.presentation_planner import plan_presentation
from backend.modules.process_mapper import identify_process
from schemas.deck_execution import DeckExecutionResult
from schemas.pipeline_result import PipelineResult
from schemas.presentation import DeckSpec

logger = logging.getLogger(__name__)


def run_pipeline(title: str, content: str) -> PipelineResult:
    """
    Execute the full Phase 2 AI orchestration pipeline.

    This is the single entry point for Phase 2 deck generation. The calling
    layer (``slide_service.generate_slide_v2``) consumes the returned
    ``PipelineResult`` and either renders the deck or a clarification
    placeholder deck.

    Parameters
    ----------
    title:
        Raw slide title from the user request. Passed unchanged into the
        pipeline; each module decides how much of it to use.
    content:
        Raw slide content / description from the user request.

    Returns
    -------
    PipelineResult
        Aggregate outcome. ``status`` is ``WAITING_FOR_USER`` when
        clarification is required, otherwise ``COMPLETED``.

    Raises
    ------
    Exception
        Any unhandled exception from a module propagates upward.
        The caller (FastAPI route) is responsible for HTTP error handling.

    Example
    -------
    ::

        result = run_pipeline("Current State", "Procure-to-Pay process...")
        if result.status == "COMPLETED":
            for slide_spec in result.deck_execution_result.successful_slides:
                renderer.render(slide_spec.raw_spec, output_path, presentation=prs)
    """
    logger.info("orchestrator: pipeline started — title=%r", title)

    # ── Step 1: Intent ────────────────────────────────────────────────────
    # Classify what the user wants to generate. No LLM call yet.
    intent = extract_intent(title, content)
    logger.info(
        "orchestrator: intent extracted — slide_type=%s confidence=%.2f",
        intent.slide_type,
        intent.confidence,
    )

    # ── Step 2: Narrative Planning ─────────────────────────────────────────
    # Plan the consulting deck. DeckSpec is kept local to the orchestrator.
    deck_spec: DeckSpec = plan_presentation(content, intent)
    logger.info(
        "orchestrator: deck planned — presentation_type=%s slides=%d",
        deck_spec.presentation_type,
        len(deck_spec.slides),
    )

    # ── Step 3: Information Analysis ───────────────────────────────────────
    # Determine whether enough information exists to generate a credible deck.
    information_result = analyze_information(content, intent, deck_spec)
    logger.info(
        "orchestrator: information analyzed — has_enough=%s missing=%s confidence=%s",
        information_result.has_enough_information,
        information_result.missing_fields,
        information_result.confidence,
    )

    if not information_result.has_enough_information:
        # ── Step 4a: Clarification ────────────────────────────────────────
        # Stop the pipeline and return structured questions. Context building,
        # process mapping, and deck execution are intentionally skipped.
        clarification_result = generate_clarifications(content, deck_spec, information_result)
        logger.info(
            "orchestrator: clarification required — content=%d visualization=%d",
            len(clarification_result.content_questions),
            len(clarification_result.visualization_questions),
        )

        return PipelineResult(
            status="WAITING_FOR_USER",
            needs_clarification=True,
            clarification_result=clarification_result,
            deck_execution_result=None,
            warnings=[information_result.analysis],
        )

    # ── Step 4b: Context ──────────────────────────────────────────────────
    # Enrich the intent with enterprise knowledge and industry signals.
    # Computed once and reused for every slide generated by the Deck Executor.
    context = build_context(intent)
    logger.info(
        "orchestrator: context built — industry=%s domain=%s facts=%d",
        context.industry,
        context.domain,
        len(context.facts),
    )

    # ── Step 5: Process Mapping ───────────────────────────────────────────
    # Map the intent onto a structured business process representation.
    # Computed once and reused for every slide generated by the Deck Executor.
    process_result = identify_process(intent, context)
    logger.info(
        "orchestrator: process identified — process=%s family=%s confidence=%.2f",
        process_result.process_name,
        process_result.process_family,
        process_result.confidence,
    )

    # ── Step 6: Deck Execution ────────────────────────────────────────────
    # Generate and validate each slide independently. Per-slide failures do
    # not abort the deck; the Deck Executor records them and continues.
    deck_result: DeckExecutionResult = execute_deck(deck_spec, intent, context, process_result)
    logger.info(
        "orchestrator: deck executed — total=%d successful=%d failed=%d",
        len(deck_result.deck_spec.slides),
        len(deck_result.successful_slides),
        len(deck_result.failed_slides),
    )

    logger.info("orchestrator: pipeline complete — title=%r", title)
    return PipelineResult(
        status="COMPLETED",
        needs_clarification=False,
        clarification_result=None,
        deck_execution_result=deck_result,
        warnings=[],
    )

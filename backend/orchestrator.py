"""
backend/orchestrator.py
========================
Phase 2 Orchestrator — the single component aware of the full pipeline.

Architecture
------------
The orchestrator coordinates the five Phase 2 modules in a fixed
sequential order. It is the ONLY place in the codebase that knows the
pipeline topology. Every other component (modules, renderers, routes) is
isolated from this knowledge.

Pipeline
--------
::

    User Request (title, content)
         │
         ▼
    [1] extract_intent()        ─── Intent Module
         │  IntentResult
         ▼
    [2] build_context()         ─── Enterprise Context Builder
         │  EnterpriseContext
         ▼
    [3] identify_process()      ─── Process Mapper
         │  process_map: dict
         ▼
    [4] generate_content()      ─── Content Generator (only LLM caller)
         │  SlideSpec
         ▼
    [5] validate_content()      ─── Validation Module
         │  ValidationResult
         ▼
    Caller (slide_service_v2 → renderer)

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

from backend.modules.content_generator import generate_content
from backend.modules.context import build_context
from backend.modules.intent import extract_intent
from backend.modules.process_mapper import identify_process
from backend.modules.validator import validate_content
from schemas.validation import ValidationResult

logger = logging.getLogger(__name__)


def run_pipeline(title: str, content: str) -> ValidationResult:
    """
    Execute the full Phase 2 AI orchestration pipeline.

    This is the single entry point for Phase 2 slide generation. The
    calling layer (``slide_service.generate_slide_v2``) is responsible for
    passing the ``ValidationResult.validated_spec`` to the appropriate
    renderer.

    Parameters
    ----------
    title:
        Raw slide title from the user request. Passed unchanged into the
        pipeline; each module decides how much of it to use.
    content:
        Raw slide content / description from the user request.

    Returns
    -------
    ValidationResult
        The terminal output of the pipeline. Callers must check
        ``ValidationResult.is_valid`` before passing
        ``validated_spec`` to a renderer.

        If ``is_valid=False``, ``validated_spec`` may be ``None`` and
        ``issues`` will describe what went wrong.

    Raises
    ------
    Exception
        Any unhandled exception from a module propagates upward.
        The caller (FastAPI route) is responsible for HTTP error handling.

    Example
    -------
    ::

        result = run_pipeline("Current State", "Procure-to-Pay process...")
        if result.is_valid:
            renderer.render(result.validated_spec.raw_spec, output_path)
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

    # ── Step 2: Context ───────────────────────────────────────────────────
    # Enrich the intent with enterprise knowledge and industry signals.
    context = build_context(intent)
    logger.info(
        "orchestrator: context built — industry=%s domain=%s facts=%d",
        context.industry,
        context.domain,
        len(context.facts),
    )

    # ── Step 3: Process Mapping ───────────────────────────────────────────
    # Map the intent onto a structured business process representation.
    process_map = identify_process(intent, context)
    logger.info(
        "orchestrator: process identified — map_keys=%s",
        list(process_map.keys()),
    )

    # ── Step 4: Content Generation ────────────────────────────────────────
    # Produce the renderer-ready SlideSpec. This is the only step that
    # invokes an LLM (via content_generator, via Phase 1 planner for now).
    spec = generate_content(intent, context, process_map)
    logger.info(
        "orchestrator: content generated — slide_type=%s version=%s generated_by=%s",
        spec.slide_type,
        spec.version,
        spec.generated_by,
    )

    # ── Step 5: Validation ────────────────────────────────────────────────
    # Quality-gate the spec before it reaches the renderer.
    result = validate_content(spec)
    logger.info(
        "orchestrator: validation complete — is_valid=%s issues=%d",
        result.is_valid,
        len(result.issues),
    )

    if not result.is_valid:
        logger.warning(
            "orchestrator: pipeline produced invalid spec — issues=%s",
            result.issues,
        )

    logger.info("orchestrator: pipeline complete — title=%r", title)
    return result

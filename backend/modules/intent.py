"""
backend/modules/intent.py
=========================
Intent Module — Phase 2.

Responsibility
--------------
Classify the user's raw request into a normalised ``IntentResult`` that
downstream modules can act on without re-parsing the raw strings.

Public API
----------
::

    result: IntentResult = extract_intent(title, content)

Design constraints
------------------
- Must NOT call any LLM directly (that is the content_generator's job).
- Must NOT have any knowledge of renderers, Office.js, or python-pptx.
- Must produce a valid ``IntentResult`` regardless of input quality.
"""

from __future__ import annotations

import logging

from backend.llm.prompt_loader import get_prompt
from schemas.intent import IntentResult

logger = logging.getLogger(__name__)

# Pre-loaded for Sprint 1 LLM classifier; keyword heuristic does not use it yet.
INTENT_PROMPT = get_prompt("intent")

# ---------------------------------------------------------------------------
# Keyword signal sets — mirrors Phase 1 heuristic in slide_service.py so
# that the intent classification is consistent across both pipelines until
# Sprint 1 replaces this with an LLM classifier.
# ---------------------------------------------------------------------------

_OPERATING_MODEL_SIGNALS: frozenset[str] = frozenset(
    [
        "operating model",
        "current state",
        "business stages",
        "detailed business activities",
        "executive summary",
        "value leakage",
        "kpis",
        "pain points, business risks",
        "risks, and inefficiencies",
    ]
)

_PROCESS_FLOW_SIGNALS: frozenset[str] = frozenset(
    [
        "process flow",
        "workflow",
        "step by step",
        "pipeline",
        "sequence",
        "flow",
    ]
)

_COMPARISON_SIGNALS: frozenset[str] = frozenset(
    [
        "comparison",
        "compare",
        "versus",
        "vs",
        "side by side",
    ]
)

_CURRENT_FUTURE_SIGNALS: frozenset[str] = frozenset(
    [
        "current future",
        "as-is to-be",
        "as is to be",
        "before after",
        "transformation",
        "future state",
    ]
)


def extract_intent(title: str, content: str) -> IntentResult:
    """
    Classify the user's raw request into a normalised ``IntentResult``.

    This implementation uses keyword heuristics (Phase 1 parity) as a
    placeholder. In Sprint 1 this will be replaced by an LLM-based
    classifier using ``backend/ai/prompts/intent.md`` via ``prompt_loader``.

    Parameters
    ----------
    title:
        Raw slide title provided by the user.
    content:
        Raw slide content / description provided by the user.

    Returns
    -------
    IntentResult
        Populated with the classified ``slide_type`` and a ``confidence``
        of 0.0 to signal that this is a heuristic result (TODO: Sprint 1).

    TODO — Sprint 1
    ---------------
    - Replace keyword heuristic with LLM classifier.
    - Load system prompt from ``backend/ai/prompts/intent.md`` via ``prompt_loader``.
    - Set ``confidence`` based on LLM response logprobs or self-rating.
    - Populate ``metadata`` with detected industry / tone signals.
    """
    combined = f"{title} {content}".lower()

    slide_type = _classify(combined)
    logger.info("intent extracted: slide_type=%s title=%s", slide_type, title)

    return IntentResult(
        slide_type=slide_type,
        raw_title=title,
        raw_content=content,
        confidence=0.0,  # TODO Sprint 1: replace with LLM confidence
        metadata={},     # TODO Sprint 1: populate with industry/tone signals
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _classify(combined_text: str) -> str:
    """
    Map a lowercased combined text to a slide type using keyword signals.

    Returns ``"unknown"`` if no signals match — the orchestrator should
    handle this gracefully by defaulting to ``"process_flow"``.
    """
    if any(signal in combined_text for signal in _OPERATING_MODEL_SIGNALS):
        return "operating_model"
    if any(signal in combined_text for signal in _COMPARISON_SIGNALS):
        return "comparison"
    if any(signal in combined_text for signal in _CURRENT_FUTURE_SIGNALS):
        return "current_future"
    if any(signal in combined_text for signal in _PROCESS_FLOW_SIGNALS):
        return "process_flow"
    # Default — process flow is the most general layout
    return "process_flow"

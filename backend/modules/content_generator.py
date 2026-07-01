"""
backend/modules/content_generator.py
=====================================
Content Generator — Phase 2.

Responsibility
--------------
Produce a renderer-ready ``SlideSpec`` from the classified intent,
enriched context, and process map. This is the only module that is
permitted to invoke an LLM.

Public API
----------
::

    spec: SlideSpec = generate_content(intent, context, process_map)

Design constraints
------------------
- This is the ONLY module allowed to call an LLM.
- Must NOT call renderers or have Office.js knowledge.
- Must return a ``SlideSpec`` whose ``raw_spec`` dict is compatible
  with the existing Phase 1 renderers.
"""

from __future__ import annotations

import logging
from typing import Any

from backend.llm.planner import create_operating_model_spec, create_slide_spec
from schemas.context import EnterpriseContext
from schemas.intent import IntentResult
from schemas.slide_spec import SlideSpec

logger = logging.getLogger(__name__)


def generate_content(
    intent: IntentResult,
    context: EnterpriseContext,  # noqa: ARG001  (used by Sprint 4 implementation)
    process_map: dict[str, Any],  # noqa: ARG001  (used by Sprint 3 implementation)
) -> SlideSpec:
    """
    Generate a renderer-ready ``SlideSpec`` from the pipeline inputs.

    Current implementation delegates to the Phase 1 LLM planner functions
    so that ``/generate/v2`` is end-to-end runnable from day one. Sprint 4
    will replace this delegation with a context-aware, prompt-engineered
    generation step that uses ``context`` and ``process_map``.

    Parameters
    ----------
    intent:
        Classified user intent from ``extract_intent()``.
    context:
        Enriched enterprise context from ``build_context()``.
        Currently unused — preserved for Sprint 4 integration.
    process_map:
        Process structure mapping from ``identify_process()``.
        Currently unused — preserved for Sprint 3 integration.

    Returns
    -------
    SlideSpec
        A fully populated spec whose ``raw_spec`` dict is compatible
        with the existing Phase 1 renderers (``ProcessFlowRenderer`` and
        ``OperatingModelRenderer``).

    TODO — Sprint 4
    ---------------
    - Replace Phase 1 planner delegation with a context-aware generation
      prompt loaded from ``backend/prompts/content.txt``.
    - Inject ``context.facts`` into the LLM prompt to ground the content.
    - Inject ``process_map`` canonical steps to constrain the structure.
    - Validate LLM JSON output against the appropriate Phase 1 schema
      before wrapping in a ``SlideSpec``.
    """
    logger.info(
        "generating content: slide_type=%s (delegating to Phase 1 planner)",
        intent.slide_type,
    )

    raw_spec = _call_phase1_planner(intent)

    return SlideSpec(
        slide_type=intent.slide_type,
        raw_spec=raw_spec,
        version="2.0",
        generated_by="content_generator_v2_placeholder",
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _call_phase1_planner(intent: IntentResult) -> dict[str, Any]:
    """
    Delegate to the Phase 1 LLM planners to produce a renderer-ready dict.

    This keeps ``/generate/v2`` end-to-end runnable while Sprint 4 builds
    the context-aware generation layer.

    Parameters
    ----------
    intent:
        Classified intent carrying raw title, content, and slide type.

    Returns
    -------
    dict
        Raw spec dict from the Phase 1 planner, compatible with existing
        renderers.
    """
    if intent.slide_type == "operating_model":
        logger.info("content_generator: invoking Phase 1 operating model planner")
        return create_operating_model_spec(intent.raw_title, intent.raw_content)

    # Default: process flow covers process_flow, comparison, current_future,
    # and unknown until dedicated generators are built in later sprints.
    logger.info("content_generator: invoking Phase 1 process flow planner")
    return create_slide_spec(intent.raw_title, intent.raw_content)

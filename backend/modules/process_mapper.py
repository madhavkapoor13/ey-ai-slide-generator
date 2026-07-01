"""
backend/modules/process_mapper.py
==================================
Process Mapper — Phase 2.

Responsibility
--------------
Given an ``IntentResult`` and an ``EnterpriseContext``, identify and
structure the business process that the slide should represent. The output
is a dict that the ``content_generator`` will use to scaffold its LLM
prompt and constrain the generated spec.

Public API
----------
::

    process_map: dict = identify_process(intent, context)

Design constraints
------------------
- Must NOT call the renderer or have Office.js knowledge.
- Must NOT produce slide content — only process structure metadata.
- Input schemas must be respected; do not modify them.
"""

from __future__ import annotations

import logging
from typing import Any

from schemas.context import EnterpriseContext
from schemas.intent import IntentResult

logger = logging.getLogger(__name__)


def identify_process(
    intent: IntentResult,
    context: EnterpriseContext,
) -> dict[str, Any]:
    """
    Identify the underlying business process structure for the slide.

    This is a placeholder implementation that returns an empty process map.
    In Sprint 3 this will use the enterprise context and industry signals
    to map user requests onto known business process templates.

    Parameters
    ----------
    intent:
        Classified user intent from ``extract_intent()``.
    context:
        Enriched enterprise context from ``build_context()``.

    Returns
    -------
    dict
        Process mapping metadata consumed by ``generate_content()``.
        Keys will be defined in Sprint 3 but should include at minimum:
        ``process_name``, ``canonical_steps``, ``reference_model``.

    TODO — Sprint 3
    ---------------
    - Map ``intent.slide_type`` to an industry process taxonomy
      (e.g. APQC, SCOR, custom EY frameworks).
    - Use ``context.industry`` and ``context.domain`` to select the
      right reference process model.
    - Load process mapping prompt from ``backend/prompts/process.txt``.
    - Return a structured dict with ``process_name``, ``canonical_steps``,
      ``kpi_candidates``, and ``risk_taxonomy``.
    """
    logger.info(
        "identifying process: slide_type=%s industry=%s domain=%s (placeholder — empty map)",
        intent.slide_type,
        context.industry,
        context.domain,
    )

    # TODO Sprint 3: replace with real process taxonomy mapping
    return {}  # TODO: populate with process_name, canonical_steps, kpi_candidates

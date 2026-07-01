"""
backend/modules/context.py
==========================
Enterprise Context Builder — Phase 2.

Responsibility
--------------
Enrich the classified ``IntentResult`` with industry-level knowledge,
research facts, and domain signals. The resulting ``EnterpriseContext``
gives downstream modules the grounding data needed to produce
enterprise-quality slide content.

Public API
----------
::

    context: EnterpriseContext = build_context(intent)

Design constraints
------------------
- Must NOT call renderers or have Office.js knowledge.
- Must NOT modify the ``IntentResult`` it receives.
- Must return a valid ``EnterpriseContext`` even with no enrichment data.
"""

from __future__ import annotations

import logging

from schemas.context import EnterpriseContext
from schemas.intent import IntentResult

logger = logging.getLogger(__name__)


def build_context(intent: IntentResult) -> EnterpriseContext:
    """
    Build an enriched ``EnterpriseContext`` from the classified intent.

    This is a placeholder implementation that returns an empty context.
    In Sprint 2 this will be replaced by a RAG-backed enrichment pipeline
    using ``backend/prompts/context.txt``.

    Parameters
    ----------
    intent:
        The ``IntentResult`` produced by ``extract_intent()``.

    Returns
    -------
    EnterpriseContext
        Populated with ``industry``, ``domain``, ``facts``, and
        ``enrichment_metadata``. Currently returns sensible empty defaults.

    TODO — Sprint 2
    ---------------
    - Use ``intent.raw_title`` and ``intent.raw_content`` to detect industry
      and domain via LLM or taxonomy lookup.
    - Retrieve relevant research facts from a vector store / RAG pipeline.
    - Load enrichment prompt from ``backend/prompts/context.txt``.
    - Populate ``enrichment_metadata`` with source provenance and latency.
    """
    logger.info(
        "building context: slide_type=%s (placeholder — no enrichment yet)",
        intent.slide_type,
    )

    # TODO Sprint 2: replace with real industry/domain detection and RAG lookup
    return EnterpriseContext(
        industry="Unknown",      # TODO: detect from intent signals
        domain="Unknown",        # TODO: detect from intent signals
        facts=[],                # TODO: retrieve from vector store
        enrichment_metadata={},  # TODO: populate with provenance data
    )

"""
backend/modules/knowledge_manager.py
====================================
Sprint F — Enterprise Knowledge Manager.

Provides deterministic access to curated consulting knowledge stored in
backend/knowledge/consulting_knowledge.json. The API is intentionally simple
in Sprint F: match by business function against canonical domain names and
aliases. If no match is found, return a generic enterprise default.

The knowledge layer is consumed by the Content Generator as a grounding source
ranked below EnterpriseContext and ProcessResult.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from schemas.knowledge import DomainKnowledge

logger = logging.getLogger(__name__)

_KNOWLEDGE_PATH = Path(__file__).resolve().parents[1] / "knowledge" / "consulting_knowledge.json"


class _KnowledgeCache:
    """Simple cache for the parsed consulting knowledge base."""

    def __init__(self) -> None:
        self._data: dict[str, Any] | None = None

    def load(self) -> dict[str, Any]:
        if self._data is None:
            self._data = json.loads(_KNOWLEDGE_PATH.read_text(encoding="utf-8"))
        return self._data


_knowledge_cache = _KnowledgeCache()


def get_knowledge(industry: str | None, business_function: str | None) -> DomainKnowledge:
    """
    Retrieve curated consulting knowledge for a business function.

    Parameters
    ----------
    industry:
        Industry vertical. Accepted for future extensibility but not used as
        the primary matching key in Sprint F.
    business_function:
        Business function or process name to match against domain knowledge.
        This is the primary matching key.

    Returns
    -------
    DomainKnowledge
        Curated knowledge for the matched domain, or a generic enterprise
        default if no match is found.
    """
    knowledge = _knowledge_cache.load()
    domains = knowledge.get("domains", {})
    normalized_function = _normalize(business_function)

    for domain_name, domain_data in domains.items():
        if _matches_domain(normalized_function, domain_name, domain_data):
            logger.info(
                "knowledge matched domain=%s for business_function=%r",
                domain_name,
                business_function,
            )
            # The canonical domain name lives in the JSON key; inject it into
            # the data before constructing the typed model.
            data_with_domain = {**domain_data, "domain": domain_name}
            return DomainKnowledge(**data_with_domain)

    logger.info(
        "no knowledge match for business_function=%r; returning generic default",
        business_function,
    )
    return _default_knowledge()


def _matches_domain(
    normalized_function: str, domain_name: str, domain_data: dict[str, Any]
) -> bool:
    """Check whether the normalized function matches the domain or an alias."""
    if not normalized_function:
        return False
    if normalized_function == _normalize(domain_name):
        return True
    aliases = [_normalize(alias) for alias in domain_data.get("aliases", [])]
    return normalized_function in aliases


def _normalize(value: str | None) -> str:
    """Normalize a matching key: lowercase, strip, treat '&' as 'and'."""
    if not value:
        return ""
    return value.lower().strip().replace("&", "and")


def _default_knowledge() -> DomainKnowledge:
    """Return a minimal, safe default when no domain match exists."""
    return DomainKnowledge(
        domain="General Enterprise",
        aliases=[],
        common_kpis=[],
        common_pain_points=[
            "Fragmented processes across organizational silos",
            "Limited visibility into end-to-end performance",
            "Manual workarounds and spreadsheet-based controls",
        ],
        transformation_themes=[
            "Process standardization and automation",
            "Data-driven decision making",
            "Cross-functional alignment and governance",
        ],
        common_risks=[
            "Low adoption of new ways of working",
            "Data quality issues from legacy systems",
            "Inability to sustain transformation benefits",
        ],
    )

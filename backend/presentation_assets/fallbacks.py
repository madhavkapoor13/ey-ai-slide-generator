"""
backend/presentation_assets/fallbacks.py
=======================================
Family-aware fallback asset resolution for production generation.
"""

from __future__ import annotations

from backend.presentation_assets import asset_registry


FAMILY_FALLBACK_IDS = {
    "executive_summary": "FALLBACK-EXEC-SUMMARY-001",
    "summary": "FALLBACK-EXEC-SUMMARY-001",
    "roadmap": "FALLBACK-ROADMAP-001",
    "timeline": "FALLBACK-TIMELINE-001",
    "process": "FALLBACK-PROCESS-001",
    "process_flow": "FALLBACK-PROCESS-001",
    "comparison": "FALLBACK-COMPARISON-001",
    "kpi": "FALLBACK-KPI-001",
}

GENERAL_FALLBACK_ID = "FALLBACK-GENERAL-TEXT-001"


def fallback_asset_ids_for_family(family: str | None) -> list[str]:
    """Return family fallback first, then the general fallback."""
    ids: list[str] = []
    normalized = (family or "").strip().lower()
    family_id = FAMILY_FALLBACK_IDS.get(normalized)
    if family_id:
        ids.append(family_id)
    ids.append(GENERAL_FALLBACK_ID)
    return ids


def resolve_fallback_asset_id(family: str | None, *, require_certified: bool = True) -> str | None:
    """
    Return the first available fallback asset for ``family``.

    In production, callers should keep ``require_certified=True``. Development
    tools may pass False to exercise draft fallback assets.
    """
    for asset_id in fallback_asset_ids_for_family(family):
        manifest = asset_registry.get(asset_id)
        if manifest is None:
            continue
        if require_certified and not manifest.certification.certified:
            continue
        return asset_id
    return None

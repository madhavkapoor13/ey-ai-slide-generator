"""
backend/presentation_assets/asset_selector.py
==============================================
Presentation Asset Selector — deterministic, metadata-only asset retrieval.

Selection order in the per-slide Deck Executor loop (Sprint C wiring):

  1. Visual Planner      → VisualPatternSelection (family signal source)
  2. Asset Selector     → AssetSelection             [this module]
  3. Content Generator  → SlideSpec (content shaped to the asset's manifest)

The Selector resolves the consulting ``family`` from the Visual Planner's
``pattern_id`` via a *data* map (``visual_pattern_family_map.json``), builds
an :class:`AssetSelectionQuery` from signals already in scope at the Deck
Executor call site (SlidePlan role/purpose, Intent audience, explicit or
inferred UserPreferences), filters the registry by family, and scores the
survivors with a small stable weighted sum. No embeddings, no model calls.

When no candidate is found for the requested family, the Selector returns a
synthetic fallback AssetSelection (the produced deck stays continuous;
Sprint E authors a real EY-branded fallback asset — for now a deterministic
fallback manifest is embedded inline so the Selector works in isolation).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from backend.presentation_assets import asset_registry
from schemas.presentation_asset import (
    AssetManifest,
    AssetPlaceholder,
    AssetSelection,
    AssetSelectionQuery,
    PlaceholderBinding,
    PlaceholderKind,
)

logger = logging.getLogger(__name__)

_FAMILY_MAP_PATH = (
    Path(__file__).resolve().parent / "visual_pattern_family_map.json"
)
_family_map_cache: dict[str, str] | None = None

_SCORING_WEIGHTS = {
    "audience": 0.20,
    "style": 0.20,
    "capacity": 0.25,
    "keyword": 0.20,
    "recommended_for": 0.10,
    "message_type": 0.15,
    "information_shape": 0.15,
    "avoid_for": 0.25,   # penalty when an avoid_for tag hits
}
_MAX_RAW_SCORE = (
    _SCORING_WEIGHTS["audience"]
    + _SCORING_WEIGHTS["style"]
    + _SCORING_WEIGHTS["capacity"]
    + _SCORING_WEIGHTS["keyword"]
    + _SCORING_WEIGHTS["recommended_for"]
    + _SCORING_WEIGHTS["message_type"]
    + _SCORING_WEIGHTS["information_shape"]
)
_TOP_N_CANDIDATES = 5

_FALLBACK_ASSET_ID = "FALLBACK-001"


# ---------------------------------------------------------------------------
# Family resolution (data-driven, never a code switch on pattern_id)
# ---------------------------------------------------------------------------


def load_family_map() -> dict[str, str]:
    """
    Load and cache the ``pattern_id → family`` data map.

    Falls back to an empty dict if the file is missing; callers then use
    the map's ``_default_for_unknown`` value or a hard fallback.
    """
    global _family_map_cache
    if _family_map_cache is not None:
        return _family_map_cache
    data: dict[str, str] = {}
    if _FAMILY_MAP_PATH.exists():
        with _FAMILY_MAP_PATH.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        default = raw.pop("_default_for_unknown", None)
        for k, v in raw.items():
            if k.startswith("_"):
                continue
            data[k] = str(v)
        if default is not None:
            data["__default__"] = str(default)
    _family_map_cache = data
    return data


def clear_family_map_cache() -> None:
    """Clear the cached family map. Useful for tests."""
    global _family_map_cache
    _family_map_cache = None


def family_for_pattern(pattern_id: str) -> str:
    """
    Resolve the consulting family for a Visual Planner ``pattern_id``.

    The lookup is data-driven (the JSON map); unknown ids fall back to the
    map's ``_default_for_unknown`` value (or ``"executive_summary"`` as a
    last resort). This is the only bridge between the Visual Planner and
    the Presentation Asset Library — extending either side is a JSON edit.
    """
    fm = load_family_map()
    if pattern_id in fm:
        return fm[pattern_id]
    return fm.get("__default__", "executive_summary")


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def _overlap(query_tags: list[str], asset_tags: list[str]) -> float:
    """Jaccard-style overlap; 0.0 when either side is empty."""
    if not query_tags or not asset_tags:
        return 0.0
    q = {t.lower() for t in query_tags}
    a = {t.lower() for t in asset_tags}
    if not q or not a:
        return 0.0
    return len(q & a) / len(q)


def _capacity_fit(query: AssetSelectionQuery, manifest: AssetManifest) -> float:
    """1.0 when content_count falls inside density_range; penalty by distance otherwise."""
    if query.content_count is None:
        return 0.5  # neutral when the caller has no count signal
    lo, hi = manifest.density_range
    n = query.content_count
    if lo <= n <= hi:
        return 1.0
    # Distance outside the range, normalised to [0, 1] over a 4-step window.
    distance = (lo - n) if n < lo else (n - hi)
    return max(0.0, 1.0 - (distance / 4.0))


def _avoid_for_hit(query: AssetSelectionQuery, manifest: AssetManifest) -> float:
    """Return 1.0 if any query keyword/purpose overlaps manifest.avoid_for; else 0.0."""
    if not manifest.avoid_for:
        return 0.0
    avoid_lower = {a.lower() for a in manifest.avoid_for}
    q_lower = {k.lower() for k in query.keywords}
    return 1.0 if (q_lower & avoid_lower) else 0.0


def _score(manifest: AssetManifest, query: AssetSelectionQuery) -> tuple[float, dict[str, float]]:
    """Return (raw_score, score_breakdown)."""
    audience = _overlap(query.audience, manifest.audience_tags)
    style = _overlap(query.style, manifest.style_tags)
    capacity = _capacity_fit(query, manifest)
    keyword = _overlap(
        query.keywords,
        [manifest.purpose]
        + list(manifest.family_aliases)
        + list(manifest.fits_content_kinds),
    )
    recommended = _overlap(
        [k for k in query.keywords] + query.audience,
        manifest.recommended_for,
    )
    avoid = _avoid_for_hit(query, manifest)
    message_type = (
        1.0
        if query.message_type
        and manifest.message_type
        and query.message_type.lower() == manifest.message_type.lower()
        else 0.0
    )
    information_shape = (
        1.0
        if query.information_shape
        and manifest.information_shape
        and query.information_shape.lower() == manifest.information_shape.lower()
        else 0.0
    )

    # Direct hint match between the caller's content kind hints and the
    # asset's declared fits_content_kinds is a strong relevance signal.
    content_kind_bonus = (
        0.15
        if query.content_kind_hints
        and _overlap(query.content_kind_hints, list(manifest.fits_content_kinds)) > 0
        else 0.0
    )

    raw = (
        _SCORING_WEIGHTS["audience"] * audience
        + _SCORING_WEIGHTS["style"] * style
        + _SCORING_WEIGHTS["capacity"] * capacity
        + _SCORING_WEIGHTS["keyword"] * keyword
        + _SCORING_WEIGHTS["recommended_for"] * recommended
        + _SCORING_WEIGHTS["message_type"] * message_type
        + _SCORING_WEIGHTS["information_shape"] * information_shape
        + content_kind_bonus
        - _SCORING_WEIGHTS["avoid_for"] * avoid
    )
    breakdown = {
        "audience": round(audience, 4),
        "style": round(style, 4),
        "capacity": round(capacity, 4),
        "keyword": round(keyword, 4),
        "recommended_for": round(recommended, 4),
        "message_type": round(message_type, 4),
        "information_shape": round(information_shape, 4),
        "avoid_for": round(avoid, 4),
        "raw": round(raw, 4),
    }
    return raw, breakdown


def _fallback_selection(query: AssetSelectionQuery) -> AssetSelection:
    """
    Build a synthetic fallback AssetSelection for the requested family.

    Sprint E authors a real EY-branded fallback asset (FALLBACK-001) and
    registers it in the library; the Selector will then prefer the real
    fallback manifest from the registry when present. This inline fallback
    keeps the Selector working in isolation / before Sprint E.
    """
    fallback_manifest = AssetManifest(
        asset_id=_FALLBACK_ASSET_ID,
        schema_version="1.0.0",
        family=query.family,
        family_aliases=[],
        purpose="Fallback asset: simple title + body bullets when no Slidefox asset matches.",
        audience_tags=[],
        style_tags=[],
        recommended_for=[],
        avoid_for=[],
        density=1,
        density_range=[1, 6],
        fits_content_kinds=[],
        supports_images=False,
        placeholders=[
            AssetPlaceholder(
                id="title",
                role="title",
                kind=PlaceholderKind.TITLE,
                binding=PlaceholderBinding(native_placeholder_idx=0),
            ),
            AssetPlaceholder(
                id="body",
                role="body",
                kind=PlaceholderKind.BODY,
                cardinality="N",
                required=False,
                binding=PlaceholderBinding(shape_name="Body"),
            ),
        ],
        repeating=None,
    )
    return AssetSelection(
        asset_id=_FALLBACK_ASSET_ID,
        family=query.family,
        manifest=fallback_manifest,
        confidence=0.0,
        score_breakdown={"fallback": 1.0},
        reasoning="No registered asset matched the requested family; using fallback.",
        candidate_ids=[],
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def select(
    query: AssetSelectionQuery,
    *,
    assets_dir: Path | str | None = None,
) -> AssetSelection:
    """
    Deterministically select the best Presentation Asset for ``query``.

    Parameters
    ----------
    query:
        Selection inputs (family, audience, style, keywords, content_count).
    assets_dir:
        Optional explicit assets directory (test isolation); when omitted,
        the registry's cached default-dir index is used.

    Returns
    -------
    AssetSelection
        The best-scoring asset, or a synthetic fallback when no candidate
        matches the requested family.
    """
    assets = asset_registry.load_assets(assets_dir)

    candidates = asset_registry.by_family(query.family, assets_dir=assets_dir)
    exact_family_candidates = [
        m for m in candidates if m.family.lower() == query.family.lower()
    ]
    if exact_family_candidates:
        candidates = exact_family_candidates
    if query.require_certified:
        certified = [m for m in candidates if m.certification.certified]
        candidates = certified
    if not candidates:
        logger.info(
            "asset_selector: no candidates for family=%r — returning fallback",
            query.family,
        )
        return _fallback_selection(query)

    scored: list[tuple[float, dict[str, float], AssetManifest]] = []
    for manifest in candidates:
        raw, breakdown = _score(manifest, query)
        scored.append((raw, breakdown, manifest))

    # Sort: highest raw score first; tie-break by lower asset_id (stable).
    scored.sort(key=lambda entry: (-entry[0], entry[2].asset_id))

    best_raw, best_breakdown, best_manifest = scored[0]

    confidence = min(best_raw / _MAX_RAW_SCORE, 1.0) if _MAX_RAW_SCORE > 0 else 0.0
    confidence = max(confidence, 0.0)

    candidates_top = [m.asset_id for _, _, m in scored[:_TOP_N_CANDIDATES]]

    return AssetSelection(
        asset_id=best_manifest.asset_id,
        family=best_manifest.family,
        manifest=best_manifest,
        confidence=round(confidence, 4),
        score_breakdown=best_breakdown,
        reasoning=(
            f"Selected {best_manifest.asset_id} (family={best_manifest.family}) "
            f"with raw score {best_raw:.3f}."
        ),
        candidate_ids=candidates_top,
    )

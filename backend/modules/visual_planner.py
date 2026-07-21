"""
backend/modules/visual_planner.py
=================================
Sprint V2 — Visual Planner.

Deterministic reasoning module that selects the most appropriate visual
pattern for a slide from the Visual Pattern Library.

The Visual Planner does NOT render slides and does NOT create PowerPoint
objects. It only returns a VisualPatternSelection describing which reusable
pattern should be used.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

from backend.llm.config import MODEL_ROUTING, PROVIDER_CONFIG
from schemas.presentation import SlidePlan
from schemas.slide_spec import SlideSpec
from schemas.visual import VisualPatternSelection

logger = logging.getLogger(__name__)

_VISUAL_PATTERNS_DIR = Path(__file__).resolve().parents[1] / "visual_patterns"
_PATTERN_FILES = {
    "creative_listing": "creative_patterns.json",
    "infographic": "infographic_patterns.json",
}

# Weighted scoring signals. A perfect match on all signals yields 1.0.
_WEIGHT_ROLE = 0.25
_WEIGHT_PURPOSE = 0.15
_WEIGHT_VISUALIZATION_TYPE = 0.30
_WEIGHT_CONTENT_KEY = 0.20
_WEIGHT_ITEM_COUNT = 0.10
_MAX_RAW_SCORE = (
    _WEIGHT_ROLE
    + _WEIGHT_PURPOSE
    + _WEIGHT_VISUALIZATION_TYPE
    + _WEIGHT_CONTENT_KEY
    + _WEIGHT_ITEM_COUNT
)

# Fallback pattern used when no strong match is found.
_FALLBACK_PATTERN_ID = "CL-06"
_FALLBACK_CATEGORY = "creative_listing"
_FALLBACK_NAME = "Executive Summary Cards"
_CONFIDENCE_THRESHOLD = 0.25

# Product-quality guardrail: several slide roles have a correct consulting
# visual family independent of generated content. Apply these before generic
# scoring so broad words like "implementation" do not push risk, process, or
# decision slides into the roadmap/KPI family.
_ROLE_PATTERN_OVERRIDES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("executive summary",), "CL-06"),
    (("current procurement process", "current state", "as-is", "process"), "IG-03"),
    (("case for change", "case_for_change", "why change", "change imperative"), "IG-16"),
    (("future-state operating model", "future state", "operating model", "capability"), "IG-06"),
    (("ai use case", "use case portfolio", "use cases"), "CL-02"),
    (("business benefit", "benefits", "value case", "value realization"), "IG-14"),
    (("implementation roadmap", "roadmap", "rollout plan"), "IG-02"),
    (("transformation timeline", "timeline", "milestone"), "IG-01"),
    (("kpi", "success metric", "metric framework"), "CL-03"),
    (("implementation risk", "risk", "mitigation"), "IG-12"),
    (("opportunity matrix", "opportunities", "growth levers", "market opportunity"), "IG-13"),
    (("next steps", "action register", "decision required", "actions"), "IG-15"),
    (("board decision", "board update", "board readout"), "CL-06"),
)

# Opt-in flag for the hybrid LLM refinement path. When the deterministic score
# is below the confidence threshold, the Visual Planner can ask the LLM router
# to choose among the top candidate patterns. Default OFF keeps behavior fully
# deterministic (and offline-safe for tests); set to "1" to enable in production.
_LLM_REFINE_ENV_FLAG = "VISUAL_PLANNER_LLM_REFINE"
_LLM_REFINE_MODULE = "visual_planner"

# Keywords associated with each pattern. Keep these conservative and explicit.
_PATTERN_KEYWORDS: dict[str, dict[str, list[str]]] = {
    # Creative Listings
    "CL-01": {
        "roles": [
            "insight", "trend", "benefit", "risk", "theme", "recommendation", "pillar", "driver",
            "benefits", "business benefits", "key business benefits",
        ],
        "visualization": ["cards", "insight cards", "four cards"],
        "purpose": ["insight", "trend", "benefit", "risk", "theme", "recommendation", "driver", "pillar"],
        "content_keys": ["cards", "insights", "themes"],
        "count_key": "cards",
    },
    "CL-02": {
        "roles": [
            "strategy", "strategic", "option", "pillar", "theme", "priority", "approach",
            "use cases", "ai use cases", "initiative",
        ],
        "visualization": ["strategy cards", "cards", "pillars"],
        "purpose": ["strategy", "strategic", "option", "pillar", "theme", "priority", "approach"],
        "content_keys": ["cards", "pillars", "strategies"],
        "count_key": "cards",
    },
    "CL-03": {
        "roles": [
            "kpi", "metric", "performance", "dashboard", "measure", "benefit",
            "kpis", "kpi for success", "success metrics", "success",
        ],
        "visualization": ["kpi", "metrics", "dashboard", "scorecard"],
        "purpose": ["kpi", "metric", "performance", "dashboard", "measure", "target", "success"],
        "content_keys": ["kpis", "metrics"],
        "count_key": "kpis",
    },
    "CL-04": {
        "roles": ["comparison", "compare", "versus", "vs", "before", "after", "current", "future", "scenario", "benchmark"],
        "visualization": ["comparison", "compare", "versus"],
        "purpose": ["comparison", "compare", "versus", "before", "after", "current", "future", "scenario", "benchmark"],
        "content_keys": ["columns", "comparison", "items"],
        "count_key": "columns",
    },
    "CL-05": {
        "roles": ["listing", "list", "drivers", "enablers", "challenges", "opportunities", "pros", "cons"],
        "visualization": ["listing", "list", "two column"],
        "purpose": ["listing", "list", "drivers", "enablers", "challenges", "opportunities", "pros", "cons"],
        "content_keys": ["columns", "items", "list"],
        "count_key": "columns",
    },
    "CL-06": {
        "roles": [
            "executive summary", "summary", "key finding", "takeaway", "recommendation", "decision",
            "next steps", "board update", "board readout", "board",
        ],
        "visualization": ["executive summary", "summary", "takeaways"],
        "purpose": ["executive summary", "summary", "key finding", "takeaway", "recommendation", "decision", "next steps"],
        "content_keys": ["cards", "takeaways", "findings"],
        "count_key": "cards",
    },
    "CL-07": {
        "roles": ["capability", "service", "tool", "theme", "grid"],
        "visualization": ["grid", "icon grid"],
        "purpose": ["capability", "service", "tool", "theme", "grid"],
        "content_keys": ["items", "grid", "capabilities"],
        "count_key": "items",
    },
    "CL-08": {
        "roles": ["image", "photo", "gallery", "use case", "snapshot", "initiative"],
        "visualization": ["image grid", "gallery", "images"],
        "purpose": ["image", "photo", "gallery", "use case", "snapshot", "initiative"],
        "content_keys": ["cards", "images"],
        "count_key": "cards",
    },
    # Infographics
    "IG-01": {
        "roles": ["timeline", "milestone", "history", "chronology", "transformation timeline"],
        "visualization": ["timeline"],
        "purpose": ["timeline", "milestone", "history", "chronology"],
        "content_keys": ["events", "timeline"],
        "count_key": "events",
    },
    "IG-02": {
        "roles": ["roadmap", "implementation", "plan", "schedule", "phase", "rollout"],
        "visualization": ["roadmap"],
        "purpose": ["roadmap", "implementation", "plan", "schedule", "phase", "rollout"],
        "content_keys": ["phases", "roadmap", "activities"],
        "count_key": "phases",
    },
    "IG-03": {
        "roles": [
            "process", "flow", "stage", "step", "workflow", "overview",
            "current state", "current procurement challenges", "challenges",
            "digital baseline", "baseline",
        ],
        "visualization": ["process flow", "flow"],
        "purpose": ["process", "flow", "stage", "step", "workflow", "overview", "current state", "challenges", "baseline"],
        "content_keys": ["steps", "stages", "process"],
        "count_key": "steps",
    },
    "IG-04": {
        "roles": [
            "matrix", "grid", "priority", "risk", "impact",
            "opportunities", "opportunity", "implementation risks", "risks",
            "investment", "maturity",
        ],
        "visualization": ["matrix"],
        "purpose": ["matrix", "priority", "risk", "impact", "comparison", "maturity"],
        "content_keys": ["rows", "matrix", "cells"],
        "count_key": "rows",
    },
    "IG-05": {
        "roles": ["journey", "customer journey", "experience", "touchpoint"],
        "visualization": ["journey"],
        "purpose": ["journey", "experience", "touchpoint"],
        "content_keys": ["stages", "journey", "touchpoints"],
        "count_key": "stages",
    },
    "IG-06": {
        "roles": [
            "capability map", "capabilities", "domain", "taxonomy",
            "future state", "future-state operating model", "target state",
            "vision", "future operating model",
        ],
        "visualization": ["capability map"],
        "purpose": ["capability map", "capabilities", "domain", "taxonomy", "future state", "vision", "target state"],
        "content_keys": ["domains", "capabilities", "map"],
        "count_key": "domains",
    },
    "IG-07": {
        "roles": ["pyramid", "maturity", "hierarchy", "stack", "layer"],
        "visualization": ["pyramid"],
        "purpose": ["pyramid", "maturity", "hierarchy", "stack", "layer"],
        "content_keys": ["levels", "pyramid"],
        "count_key": "levels",
    },
    "IG-08": {
        "roles": ["cycle", "circular", "loop", "feedback", "continuous"],
        "visualization": ["circular flow", "cycle"],
        "purpose": ["cycle", "circular", "loop", "feedback", "continuous"],
        "content_keys": ["stages", "cycle"],
        "count_key": "stages",
    },
    "IG-09": {
        "roles": ["value chain", "supply chain", "value stream", "chain"],
        "visualization": ["value chain"],
        "purpose": ["value chain", "supply chain", "value stream", "chain"],
        "content_keys": ["activities", "chain", "value_chain"],
        "count_key": "activities",
    },
    "IG-10": {
        "roles": ["hub", "spoke", "ecosystem", "platform", "core", "modules"],
        "visualization": ["hub and spoke", "ecosystem"],
        "purpose": ["hub", "spoke", "ecosystem", "platform", "core", "modules"],
        "content_keys": ["center", "spokes", "hub"],
        "count_key": "spokes",
    },
    "IG-11": {
        "roles": ["annotated", "diagram", "illustration", "callout", "hero"],
        "visualization": ["annotated visual", "callout", "diagram"],
        "purpose": ["annotated", "diagram", "illustration", "callout", "hero"],
        "content_keys": ["image", "annotations", "callouts"],
        "count_key": "annotations",
    },
    "IG-12": {
        "roles": [
            "risk", "risks", "implementation risk", "risk assessment", "risk matrix",
            "mitigation", "risk register", "risk heat map",
        ],
        "visualization": ["matrix", "risk matrix", "heat map"],
        "purpose": ["risk", "assessment", "mitigation", "likelihood", "impact"],
        "content_keys": ["risks", "matrix", "rows"],
        "count_key": "risks",
    },
    "IG-13": {
        "roles": [
            "opportunity", "opportunities", "opportunity matrix", "growth levers",
            "market opportunity", "value creation", "business plan validation",
        ],
        "visualization": ["matrix", "opportunity matrix"],
        "purpose": ["opportunity", "growth", "market", "value creation"],
        "content_keys": ["categories", "opportunities", "matrix"],
        "count_key": "categories",
    },
    "IG-14": {
        "roles": [
            "business benefit", "benefits", "value case", "value realization",
            "success factors", "value drivers", "key benefits",
        ],
        "visualization": ["list", "benefits list"],
        "purpose": ["benefit", "value", "success factor", "driver"],
        "content_keys": ["factors", "benefits", "items"],
        "count_key": "factors",
    },
    "IG-15": {
        "roles": [
            "next steps", "action register", "initiative tracker", "implementation plan",
            "actions", "next step", "action tracker",
        ],
        "visualization": ["register", "table", "action register"],
        "purpose": ["next steps", "actions", "tracker", "register", "ownership"],
        "content_keys": ["actions", "rows", "register"],
        "count_key": "actions",
    },
}


def load_pattern_registry() -> dict[str, dict[str, Any]]:
    """
    Load the visual pattern registry from ``backend/visual_patterns/``.

    Returns a flat mapping of ``pattern_id`` to pattern metadata, combining
    both creative listing and infographic pattern files.
    """
    registry: dict[str, dict[str, Any]] = {}
    for category, filename in _PATTERN_FILES.items():
        path = _VISUAL_PATTERNS_DIR / filename
        if not path.exists():
            raise FileNotFoundError(f"Visual pattern file not found: {path}")
        with path.open("r", encoding="utf-8") as f:
            patterns = json.load(f)
        for pattern in patterns:
            pattern["category"] = category
            registry[pattern["pattern_id"]] = pattern
    return registry


def _contains_keyword(text: str, keywords: list[str]) -> bool:
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def _role_override_pattern_id(slide_role: str, visualization_type: str) -> str | None:
    """Return a deterministic pattern id when the slide role is unambiguous."""
    role_text = slide_role.lower()
    visualization_text = visualization_type.lower()

    # Prefer role text over visualization text; visualization hints are often
    # taxonomy defaults, while explicit slide roles carry the user contract.
    for keywords, pattern_id in _ROLE_PATTERN_OVERRIDES:
        if any(keyword in role_text for keyword in keywords):
            return pattern_id
    for keywords, pattern_id in _ROLE_PATTERN_OVERRIDES:
        if any(keyword in visualization_text for keyword in keywords):
            return pattern_id
    return None


def _selection_for_pattern(
    pattern: dict[str, Any],
    confidence: float,
    reasoning: str,
) -> VisualPatternSelection:
    return VisualPatternSelection(
        pattern_id=pattern["pattern_id"],
        category=pattern["category"],
        confidence=round(confidence, 2),
        reasoning=reasoning,
        recommended_variant=None,
    )


def _fallback_selection() -> VisualPatternSelection:
    """Deterministic fallback used when no strong match is found and LLM
    refinement is disabled or unavailable."""
    return VisualPatternSelection(
        pattern_id=_FALLBACK_PATTERN_ID,
        category=_FALLBACK_CATEGORY,
        confidence=round(0.5, 2),
        reasoning=(
            "No strong visual pattern match; defaulting to a flexible "
            "executive-summary layout."
        ),
        recommended_variant=None,
    )


def _llm_refine_enabled() -> bool:
    """True only when the opt-in flag is set AND a provider API key exists."""
    if os.getenv(_LLM_REFINE_ENV_FLAG, "0").lower() not in ("1", "true", "yes", "on"):
        return False
    return _provider_key_configured()


def _provider_key_configured() -> bool:
    for provider in MODEL_ROUTING.get(_LLM_REFINE_MODULE, []):
        spec = PROVIDER_CONFIG.get(provider, {})
        key_env = spec.get("api_key_env")
        if isinstance(key_env, str) and os.getenv(key_env):
            return True
        if isinstance(key_env, list) and any(os.getenv(name) for name in key_env):
            return True
    return False


def _llm_refine_pattern(
    slide_plan: SlidePlan,
    slide_spec: SlideSpec,
    candidates: list[dict[str, Any]],
) -> VisualPatternSelection:
    """
    Ask the LLM router to pick the best pattern from the top candidates when
    deterministic scoring is inconclusive.

    Raises on any failure so the caller can fall back to the deterministic
    default. Never called unless ``_llm_refine_enabled()`` is True.
    """
    load_dotenv()
    from backend.llm import router

    candidate_payload = [
        {
            "pattern_id": c.get("pattern_id"),
            "name": c.get("name", c.get("pattern_id")),
            "category": c.get("category", _FALLBACK_CATEGORY),
            "description": c.get("description", ""),
        }
        for c in candidates
    ]
    user_input = json.dumps(
        {
            "slide_role": slide_plan.slide_role,
            "purpose": slide_plan.purpose,
            "visualization_type": slide_plan.visualization_type,
            "content_keys": sorted(slide_spec.raw_spec.keys()),
            "candidate_patterns": candidate_payload,
        },
        ensure_ascii=True,
    )
    prompt = (
        "You are a consulting presentation design expert. Choose the single "
        "best visual pattern id for the slide below, drawing only from the "
        "candidate list. Consider the slide role, purpose, and the semantic "
        "visualization type. Respond ONLY with a JSON object of the form "
        '{"pattern_id": "<id>", "reasoning": "<short reason>"}.\n\n' + user_input
    )
    payload = router.generate_json(_LLM_REFINE_MODULE, prompt, temperature=0.1)
    if not isinstance(payload, dict):
        raise ValueError("LLM refine response was not a JSON object.")
    pattern_id = payload.get("pattern_id")
    if not isinstance(pattern_id, str) or not pattern_id:
        raise ValueError("LLM refine response did not include a pattern_id.")

    match = next((c for c in candidates if c.get("pattern_id") == pattern_id), None)
    category = match["category"] if match else _FALLBACK_CATEGORY
    raw_reasoning = payload.get("reasoning")
    reasoning = raw_reasoning.strip() if isinstance(raw_reasoning, str) else "Refined via LLM."
    return VisualPatternSelection(
        pattern_id=pattern_id,
        category=category,
        confidence=0.6,
        reasoning=reasoning,
        recommended_variant=None,
    )


def _item_count(raw_spec: dict[str, Any], count_key: str) -> Optional[int]:
    """Extract the number of items for a pattern if the relevant key exists."""
    value = raw_spec.get(count_key)
    if isinstance(value, list):
        return len(value)
    # Some patterns store items under nested keys (e.g. columns -> items).
    if count_key == "columns" and isinstance(value, list):
        return sum(len(col.get("items", [])) for col in value if isinstance(col, dict))
    return None


def score_pattern(
    pattern: dict[str, Any],
    slide_role: str,
    purpose: str,
    visualization_type: str,
    raw_spec: dict[str, Any],
) -> tuple[float, list[str]]:
    """
    Score a single pattern against the slide inputs.

    Returns the raw score (0.0-1.0) and a list of reasoning fragments.
    """
    pattern_id = pattern["pattern_id"]
    keywords = _PATTERN_KEYWORDS.get(pattern_id, {})
    score = 0.0
    reasons: list[str] = []

    if keywords.get("roles") and _contains_keyword(slide_role, keywords["roles"]):
        score += _WEIGHT_ROLE
        reasons.append(f"slide role '{slide_role}' matches")

    if keywords.get("purpose") and _contains_keyword(purpose, keywords["purpose"]):
        score += _WEIGHT_PURPOSE
        reasons.append(f"purpose '{purpose}' matches")

    if keywords.get("visualization") and _contains_keyword(
        visualization_type, keywords["visualization"]
    ):
        score += _WEIGHT_VISUALIZATION_TYPE
        reasons.append(f"visualization type '{visualization_type}' matches")

    content_keys = keywords.get("content_keys", [])
    matched_keys = [key for key in content_keys if key in raw_spec]
    if matched_keys:
        score += _WEIGHT_CONTENT_KEY
        reasons.append(f"content keys {matched_keys} present")

    count_key = keywords.get("count_key")
    if count_key:
        count = _item_count(raw_spec, count_key)
        if count is not None:
            min_items = pattern.get("min_items", 0)
            max_items = pattern.get("max_items", 999)
            if min_items <= count <= max_items:
                score += _WEIGHT_ITEM_COUNT
                reasons.append(f"item count {count} fits {min_items}-{max_items}")

    return score, reasons


def plan_visual_pattern(
    slide_plan: SlidePlan,
    slide_spec: SlideSpec,
    exclude_category: Optional[str] = None,
) -> VisualPatternSelection:
    """
    Select the best visual pattern for a slide plan and its generated content.

    The selection is deterministic: it scores every registered pattern against
    the slide role, purpose, visualization type, and SlideSpec content, then
    returns the highest-scoring pattern. If no pattern crosses the confidence
    threshold, a graceful fallback is returned.

    ``exclude_category`` is used by callers (e.g. the deck executor) to avoid
    repeating the same visual family on consecutive slides. Patterns in the
    excluded category receive a large score penalty so a different family wins
    when one is available.
    """
    registry = load_pattern_registry()
    raw_spec = slide_spec.raw_spec

    slide_role = slide_plan.slide_role or ""
    purpose = slide_plan.purpose or ""
    visualization_type = slide_plan.visualization_type or ""

    override_id = _role_override_pattern_id(slide_role, visualization_type)
    if override_id and override_id in registry:
        pattern = registry[override_id]
        logger.info(
            "visual_planner: selected %s via role override for role=%r visualization=%r",
            override_id,
            slide_role,
            visualization_type,
        )
        return _selection_for_pattern(
            pattern,
            0.9,
            (
                f"Selected '{pattern['name']}' because slide role "
                f"'{slide_role}' requires the {visualization_type or pattern['name']} visual family."
            ),
        )

    _RHYTHM_GUARD_PENALTY = 0.30

    # Compute raw scores, then a separate penalized copy for rhythm-guard logic.
    scored_raw: list[tuple[float, list[str], dict[str, Any]]] = []
    scored: list[tuple[float, list[str], dict[str, Any]]] = []
    for pattern in registry.values():
        raw_score, reasons = score_pattern(
            pattern, slide_role, purpose, visualization_type, raw_spec
        )
        scored_raw.append((raw_score, list(reasons), pattern))
        if exclude_category and pattern.get("category") == exclude_category:
            penalized_score = max(raw_score - _RHYTHM_GUARD_PENALTY, 0.0)
            reasons.append("rhythm guard penalty applied")
            scored.append((penalized_score, reasons, pattern))
        else:
            scored.append((raw_score, reasons, pattern))

    # Sort by score descending, then by pattern_id ascending for deterministic ties.
    scored_raw.sort(key=lambda entry: (-entry[0], entry[2]["pattern_id"]))
    scored.sort(key=lambda entry: (-entry[0], entry[2]["pattern_id"]))

    # Diagnostic logging for scoring decisions (enable DEBUG to audit selections).
    logger.debug(
        "visual_planner: scoring inputs — role=%r visualization=%r purpose=%r spec_keys=%s exclude_category=%r",
        slide_role,
        visualization_type,
        purpose,
        sorted(raw_spec.keys()),
        exclude_category,
    )
    logger.debug(
        "visual_planner: top candidates before rhythm guard — %s",
        ", ".join(f"{entry[2]['pattern_id']}={entry[0]:.2f}" for entry in scored_raw[:5]),
    )
    logger.debug(
        "visual_planner: top candidates after rhythm guard — %s",
        ", ".join(f"{entry[2]['pattern_id']}={entry[0]:.2f}" for entry in scored[:5]),
    )
    if scored_raw and scored:
        winner_before = scored_raw[0][2]["pattern_id"]
        winner_after = scored[0][2]["pattern_id"]
        logger.debug(
            "visual_planner: rhythm guard changed result=%s (before=%s after=%s)",
            winner_before != winner_after,
            winner_before,
            winner_after,
        )

    if not scored or scored[0][0] < _CONFIDENCE_THRESHOLD:
        logger.info("visual_planner: no strong match; considering fallback %s", _FALLBACK_PATTERN_ID)
        if _llm_refine_enabled():
            top_candidates = [entry[2] for entry in scored[:3]] or [
                registry[k] for k in sorted(registry)[:3]
            ]
            try:
                refined = _llm_refine_pattern(slide_plan, slide_spec, top_candidates)
                logger.info(
                    "visual_planner: LLM refinement selected %s",
                    refined.pattern_id,
                )
                return refined
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "visual_planner: LLM refinement failed; using deterministic "
                    "fallback %s: %s",
                    _FALLBACK_PATTERN_ID,
                    exc,
                )
        return _fallback_selection()

    best_score, best_reasons, best_pattern = scored[0]
    normalized_confidence = min(best_score / _MAX_RAW_SCORE, 1.0)

    reasoning = (
        f"Selected '{best_pattern['name']}' based on "
        + "; ".join(best_reasons)
        + "."
    )

    logger.info(
        "visual_planner: selected %s (score=%.2f, confidence=%.2f)",
        best_pattern["pattern_id"],
        best_score,
        normalized_confidence,
    )

    return VisualPatternSelection(
        pattern_id=best_pattern["pattern_id"],
        category=best_pattern["category"],
        confidence=round(normalized_confidence, 2),
        reasoning=reasoning,
        recommended_variant=None,
    )

"""
Template-first visual variant resolver for the pilot EY asset library.

This is an additive layer over the existing Presentation Asset registry. The
pilot architecture treats each certified asset as a hardcoded editable visual
variant: AI still owns story and content, while PowerPoint owns layout.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.presentation_assets import asset_registry
from schemas.presentation_asset import AssetManifest, AssetSelection
from schemas.presentation import SlidePlan
from schemas.visual import VisualBrief


_INVESTMENT_TERMS = (
    "investment",
    "investment case",
    "business case",
    "funding",
    "funding request",
    "budget",
    "roi",
    "return on investment",
    "payback",
    "value case",
    "economics",
)

_VALUE_REALIZATION_TERMS = (
    "value realization",
    "value realisation",
    "value realization roadmap",
    "value realisation roadmap",
    "value capture",
    "benefit capture",
    "benefit pools",
    "benefit pool",
    "benefits roadmap",
    "benefit roadmap",
    "time-phased value",
    "time phased value",
)


@dataclass(frozen=True)
class VisualVariant:
    variant_id: str
    asset_id: str
    slide_type: str
    user_label: str
    default: bool = False
    source_slide_index: int | None = None
    aliases: tuple[str, ...] = ()


_VARIANTS: tuple[VisualVariant, ...] = (
    VisualVariant(
        "EXEC_SUMMARY_3POINT",
        "EXEC-SUMMARY-3PRIORITY-CARD-001",
        "executive_summary",
        "Executive summary with three priority cards",
        default=True,
        aliases=("executive_summary_3priority", "exec_summary_3priority_card"),
    ),
    VisualVariant(
        "CURRENT_PROCESS_5STEP",
        "CURRENT-STATE-PROCESS-5STEP-001",
        "current_state",
        "Current process with five stages",
        default=True,
        aliases=("current_state_process", "current_process"),
    ),
    VisualVariant(
        "CURRENT_PROCESS_6STEP",
        "CURRENT-STATE-PROCESS-6STEP-001",
        "current_state",
        "Current process with six stages",
        aliases=("current_process_6step", "current_state_6step", "six_step_process"),
    ),
    VisualVariant(
        "CURRENT_FUTURE_COMPARISON",
        "CURRENT-FUTURE-COMPARISON-5SHIFT-001",
        "current_future_comparison",
        "Current state versus future state with five shifts",
        default=True,
        aliases=("current_state_vs_future_state", "from_to_comparison", "transformation_shifts"),
    ),
    VisualVariant(
        "CASE_FOR_CHANGE_3DRIVERS",
        "CASE-FOR-CHANGE-3DRIVER-001",
        "case_for_change",
        "Case for change with three drivers",
        default=True,
        aliases=("case_for_change", "three_drivers"),
    ),
    VisualVariant(
        "OPERATING_MODEL_4CAPABILITY",
        "FUTURE-STATE-OPERATING-MODEL-4CAPABILITY-001",
        "future_state_operating_model",
        "Future-state operating model with four capabilities",
        default=True,
        aliases=("future_state", "target_operating_model", "capability_map"),
    ),
    VisualVariant(
        "GOVERNANCE_MODEL",
        "GOVERNANCE-MODEL-001",
        "governance_model",
        "Governance model with forums, decision rights, and workstreams",
        default=True,
        aliases=("program_governance", "decision_rights", "governance"),
    ),
    VisualVariant(
        "USE_CASES_5CARD",
        "AI-USECASES-5PRIORITY-001",
        "ai_use_cases",
        "Five priority AI use cases",
        default=True,
        aliases=("ai_use_cases", "use_case_portfolio"),
    ),
    VisualVariant(
        "AI_USE_CASE_PRIORITIZATION_MATRIX",
        "AI-USECASE-PRIORITIZATION-MATRIX-001",
        "ai_use_cases",
        "AI use case prioritization matrix",
        aliases=("ai_use_case_matrix", "use_case_prioritization", "prioritization_matrix"),
    ),
    VisualVariant(
        "BENEFITS_6FACTOR",
        "BENEFITS-6FACTOR-V2-001",
        "business_benefits",
        "Six-factor business benefits",
        default=True,
        aliases=("business_benefits", "value_drivers"),
    ),
    VisualVariant(
        "INVESTMENT_CASE",
        "INVESTMENT-CASE-SUMMARY-001",
        "investment_case",
        "Investment case summary with value, timing, and economics",
        default=True,
        aliases=("business_case", "funding_request", "value_case"),
    ),
    VisualVariant(
        "OPPORTUNITY_6AREA",
        "OPPORTUNITY-6AREA-001",
        "opportunities",
        "Six-area opportunity grid with issues, opportunities, and value unlocked",
        default=True,
        aliases=("opportunity_6area", "opportunities", "value_drivers", "improvement_opportunities"),
    ),
    VisualVariant(
        "ROADMAP_3PHASE",
        "ROADMAP-3PHASE-ACTIVITY-001",
        "roadmap",
        "Three-phase roadmap with activities",
        default=True,
        aliases=("implementation_roadmap", "simple_roadmap"),
    ),
    VisualVariant(
        "ROADMAP_3PHASE_WORKSTREAM",
        "ROADMAP-3PHASE-4WORKSTREAM-V2-001",
        "roadmap",
        "Three-phase roadmap by workstream",
        aliases=("workstream_roadmap", "roadmap_workstream"),
    ),
    VisualVariant(
        "VALUE_REALIZATION_ROADMAP",
        "VALUE-REALIZATION-ROADMAP-001",
        "roadmap",
        "Value realization roadmap with benefit pools and owners",
        aliases=("value_roadmap", "benefit_capture_roadmap", "benefits_roadmap"),
    ),
    VisualVariant(
        "KPI_6METRIC",
        "KPI-6PRIORITY-METRICS-001",
        "kpi_dashboard",
        "Six priority KPI metrics",
        default=True,
        aliases=("kpi_dashboard", "success_metrics"),
    ),
    VisualVariant(
        "KPI_SCORECARD_TABLE",
        "KPI-SCORECARD-TABLE-001",
        "kpi_dashboard",
        "KPI scorecard table with performance summary",
        aliases=("kpi_scorecard", "metric_table", "performance_scorecard"),
    ),
    VisualVariant(
        "RISK_MATRIX",
        "RISK-MATRIX-HEATMAP-001",
        "risks",
        "Likelihood-impact risk matrix",
        default=True,
        aliases=("risk_matrix", "risk_heatmap", "implementation_risks"),
    ),
    VisualVariant(
        "RISK_REGISTER",
        "RISK-REGISTER-7ITEM-001",
        "risks",
        "Risk register with mitigation, owner, and status",
        aliases=("risk_register", "risk_log", "mitigation_register"),
    ),
    VisualVariant(
        "ACTION_REGISTER",
        "NEXTSTEPS-ACTION-REGISTER-7ITEM-001",
        "next_steps",
        "Action register with owners and timing",
        default=True,
        aliases=("next_steps", "board_decisions", "action_register"),
    ),
    VisualVariant(
        "DECISION_REQUEST",
        "DECISION-REQUEST-3CARD-001",
        "next_steps",
        "Board decision request with three decision cards",
        aliases=("decision_request", "board_approval_request", "funding_decision"),
    ),
    VisualVariant(
        "SECTION_DIVIDER_STANDARD",
        "SECTION-NEXT-STEPS-001",
        "section_divider",
        "Standard section divider",
        default=True,
        aliases=("section_divider", "section_break", "next_steps_section"),
    ),
    VisualVariant(
        "SECTION_DIVIDER_DARK",
        "SECTION-DIVIDER-DARK-001",
        "section_divider",
        "Dark EY section divider",
        aliases=("dark_section_divider", "section_break_dark", "chapter_divider_dark"),
    ),
)


def resolve_variant_for_slide(
    slide_plan: SlidePlan,
    visual_brief: VisualBrief,
    *,
    user_preferences: Any = None,
    require_certified: bool = False,
) -> AssetSelection | None:
    """Resolve a pilot slide to a certified visual variant selection."""
    slide_type = slide_type_for_plan(slide_plan, visual_brief)
    if not slide_type:
        return None

    explicit = _explicit_variant_id(slide_type, user_preferences)
    variant = _variant_by_id(explicit) if explicit else _default_variant(slide_type, slide_plan, visual_brief)
    if variant is None:
        return None

    manifest = asset_registry.get(variant.asset_id)
    if manifest is None:
        raise ValueError(f"visual variant {variant.variant_id!r} maps to missing asset {variant.asset_id!r}")
    if require_certified and not manifest.certification.certified:
        raise ValueError(f"visual variant {variant.variant_id!r} is not certified")

    return AssetSelection(
        asset_id=manifest.asset_id,
        family=manifest.family,
        manifest=manifest,
        confidence=1.0 if explicit else 0.95,
        score_breakdown={
            "visual_variant": 1.0,
            "user_override": 1.0 if explicit else 0.0,
        },
        reasoning=(
            f"Resolved slide_type={slide_type!r} to visual variant "
            f"{variant.variant_id} ({variant.asset_id})."
        ),
        candidate_ids=[v.asset_id for v in variants_for_slide_type(slide_type)],
    )


def variants_for_slide_type(slide_type: str) -> list[VisualVariant]:
    normalized = _normalize(slide_type)
    return [v for v in _VARIANTS if _normalize(v.slide_type) == normalized]


def variant_for_asset_id(asset_id: str | None) -> VisualVariant | None:
    normalized = _normalize(asset_id or "")
    for variant in _VARIANTS:
        if _normalize(variant.asset_id) == normalized:
            return variant
    return None


def slide_type_for_plan(slide_plan: SlidePlan, visual_brief: VisualBrief) -> str | None:
    role_text = str(slide_plan.slide_role or "").lower()
    text = " ".join(
        str(part or "")
        for part in (
            slide_plan.slide_role,
            slide_plan.purpose,
            slide_plan.visualization_type,
            visual_brief.message_type,
            visual_brief.information_shape,
        )
    ).lower()
    message_type = _normalize(visual_brief.message_type)
    information_shape = _normalize(visual_brief.information_shape)

    if "section" in role_text and ("divider" in role_text or "break" in role_text):
        return "section_divider"
    if "current" in role_text and "future" in role_text:
        return "current_future_comparison"
    if "from" in role_text and "to" in role_text:
        return "current_future_comparison"
    if "governance" in role_text or "decision right" in role_text:
        return "governance_model"
    if _contains_any(role_text, _INVESTMENT_TERMS):
        return "investment_case"
    if "opportunit" in role_text or "value driver" in role_text:
        return "opportunities"
    if "next step" in role_text or "decision" in role_text or "action" in role_text:
        return "next_steps"
    if "risk" in role_text or "mitigation" in role_text:
        return "risks"
    if "scorecard" in role_text and ("kpi" in role_text or "metric" in role_text or "performance" in role_text):
        return "kpi_dashboard"
    if "kpi" in role_text or "metric" in role_text:
        return "kpi_dashboard"
    if _contains_any(role_text, _VALUE_REALIZATION_TERMS):
        return "roadmap"
    if "roadmap" in role_text or "rollout" in role_text:
        return "roadmap"
    if "business benefit" in role_text or "benefit" in role_text or "value case" in role_text:
        return "business_benefits"
    if "use case" in role_text or "ai use" in role_text:
        return "ai_use_cases"
    if "future state" in role_text or "target operating model" in role_text or "operating model" in role_text:
        return "future_state_operating_model"
    if "case for change" in role_text or "change imperative" in role_text or "why change" in role_text:
        return "case_for_change"
    if (
        "current state" in role_text
        or "current process" in role_text
        or ("current" in role_text and "process" in role_text)
        or "procurement process" in role_text
        or "as-is" in role_text
        or "as is" in role_text
    ):
        return "current_state"
    if "executive summary" in role_text:
        return "executive_summary"

    if "section" in text and ("divider" in text or "break" in text):
        return "section_divider"
    if "executive summary" in text:
        return "executive_summary"
    if (
        ("current" in text and "future" in text)
        or ("from" in text and "to" in text)
        or message_type in {"comparison", "current_future_comparison"}
        or information_shape in {"comparison", "current_future_comparison"}
    ):
        return "current_future_comparison"
    if "governance" in text or "decision right" in text:
        return "governance_model"
    if _contains_any(text, _INVESTMENT_TERMS) or message_type in {"investment_case", "business_case", "funding_request"}:
        return "investment_case"
    if (
        "opportunit" in text
        or "value driver" in text
        or message_type in {"opportunities", "value_drivers", "improvement_opportunities"}
        or information_shape in {"opportunity_grid", "opportunity_matrix"}
    ):
        return "opportunities"
    if (
        "current state" in text
        or "current process" in text
        or ("current" in text and "process" in text)
        or "procurement process" in text
        or "as-is" in text
        or "as is" in text
        or (message_type == "process_flow" and "process" in text)
    ):
        return "current_state"
    if "case for change" in text or "change imperative" in text or "why change" in text:
        return "case_for_change"
    if "future state" in text or "target operating model" in text or "operating model" in text:
        return "future_state_operating_model"
    if "use case" in text or "ai use" in text:
        return "ai_use_cases"
    if _contains_any(text, _VALUE_REALIZATION_TERMS):
        return "roadmap"
    if "roadmap" in text or "rollout" in text:
        return "roadmap"
    if "business benefit" in text or "benefit" in text:
        return "business_benefits"
    if (
        "kpi" in text
        or "metric" in text
        or message_type in {"kpi_dashboard", "kpi_scorecard", "success_metrics"}
        or information_shape in {"metrics", "scorecard_table"}
    ):
        return "kpi_dashboard"
    if (
        "risk" in text
        or "mitigation" in text
        or message_type in {"risk_matrix", "risk_register", "implementation_risks"}
        or information_shape in {"risk_matrix", "risk_table"}
    ):
        return "risks"
    if (
        "next step" in text
        or "decision" in text
        or "action" in text
        or message_type in {"board_decisions", "next_steps"}
        or information_shape in {"actions", "action_register"}
    ):
        return "next_steps"
    return None


def _default_variant(
    slide_type: str,
    slide_plan: SlidePlan,
    visual_brief: VisualBrief,
) -> VisualVariant | None:
    text = " ".join(
        str(part or "")
        for part in (
            slide_plan.slide_role,
            slide_plan.purpose,
            slide_plan.visualization_type,
            visual_brief.message_type,
            visual_brief.information_shape,
        )
    ).lower()
    if _normalize(slide_type) == "section_divider" and "dark" in text:
        return _variant_by_id("SECTION_DIVIDER_DARK")
    if _normalize(slide_type) == "current_state" and (
        "6" in text or "six" in text or visual_brief.content_units >= 6
    ):
        return _variant_by_id("CURRENT_PROCESS_6STEP")
    if _normalize(slide_type) == "ai_use_cases" and ("priorit" in text or "matrix" in text or "feasibility" in text):
        return _variant_by_id("AI_USE_CASE_PRIORITIZATION_MATRIX")
    if _normalize(slide_type) in {"investment_case", "business_benefits"} and _contains_any(text, _INVESTMENT_TERMS):
        return _variant_by_id("INVESTMENT_CASE")
    if _normalize(slide_type) == "roadmap" and "workstream" in text:
        return _variant_by_id("ROADMAP_3PHASE_WORKSTREAM")
    if _normalize(slide_type) == "roadmap" and (
        _contains_any(text, _VALUE_REALIZATION_TERMS)
        or "value" in text
        or "benefit" in text
        or "realization" in text
        or "realisation" in text
    ):
        return _variant_by_id("VALUE_REALIZATION_ROADMAP")
    if _normalize(slide_type) == "kpi_dashboard" and ("scorecard" in text or "table" in text or "performance overview" in text):
        return _variant_by_id("KPI_SCORECARD_TABLE")
    if _normalize(slide_type) == "risks" and (
        "register" in text
        or "log" in text
        or "owner" in text
        or "status" in text
        or "risk_register" in text
        or "risk_table" in text
    ):
        return _variant_by_id("RISK_REGISTER")
    if _normalize(slide_type) == "next_steps" and ("decision" in text or "approve" in text or "funding" in text or "request" in text):
        return _variant_by_id("DECISION_REQUEST")
    candidates = variants_for_slide_type(slide_type)
    for variant in candidates:
        if variant.default:
            return variant
    return candidates[0] if candidates else None


def _explicit_variant_id(slide_type: str, user_preferences: Any) -> str | None:
    preferences = getattr(user_preferences, "user_visual_preferences", None) or {}
    if not isinstance(preferences, dict):
        return None
    normalized_type = _normalize(slide_type)
    for raw_key, raw_value in preferences.items():
        if _normalize(str(raw_key)) == normalized_type and raw_value:
            return str(raw_value)
    return None


def _variant_by_id(variant_id: str | None) -> VisualVariant | None:
    if not variant_id:
        return None
    normalized = _normalize(variant_id)
    for variant in _VARIANTS:
        names = [variant.variant_id, variant.asset_id, *variant.aliases]
        if any(_normalize(name) == normalized for name in names):
            return variant
    raise ValueError(f"unknown visual variant override: {variant_id}")


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    normalized = str(text or "").lower()
    return any(term in normalized for term in terms)


def _normalize(value: str) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")

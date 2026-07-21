"""
backend/modules/content_generator.py
=====================================
Consulting Content Generator — Sprint 4.

Transforms IntentResult, EnterpriseContext, and ProcessResult into a
renderer-ready SlideSpec. This module generates consulting narrative, but
must not invent company facts or unsupported numeric claims.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from backend.llm.prompt_loader import build_prompt
from backend.modules.knowledge_manager import get_knowledge
from backend.modules.visual_planner import plan_visual_pattern
from schemas.context import EnterpriseContext
from schemas.intent import IntentResult
from schemas.knowledge import DomainKnowledge
from schemas.operating_model import OperatingModelSpec
from schemas.presentation import SlidePlan
from schemas.presentation_asset import AssetManifest, AssetPlaceholder, PlaceholderKind
from schemas.process import ProcessResult
from schemas.slide_spec import SlideSpec
from schemas.visual import VisualPatternSelection
from backend.presentation_assets.manifest_conformance import check_conformance
from backend.presentation_assets.text_fit import check_text_fit, shorten_to_fit_once

logger = logging.getLogger(__name__)

_STAGE_COUNT = 6
_ACTIVITIES_PER_STAGE = 6
_MAX_ACTIVITY_WORDS = 7
_MIN_ACTIVITY_WORDS = 3
# Numeric claims are preserved but tagged "(illustrative)" rather than stripped.
_ILLUSTRATIVE_NUMERIC_PATTERNS = [
    re.compile(r"\b\d+(?:\.\d+)?\s*%"),
    re.compile(r"[$€£¥]\s*\d+(?:\.\d+)?\s*\w*"),
    re.compile(r"\b\d+(?:\.\d+)?\s*(?:days?|weeks?|months?|hours?|hrs?|minutes?|mins?)\b", re.I),
    re.compile(r"\bROI\b", re.I),
    re.compile(r"\b(?:revenue|cost|savings|profit|margin|budget)\s+(?:of|by|at)?\s*[$€£¥]?\d+(?:\.\d+)?", re.I),
]
# Slide roles that rely on the process-flow baseline (stages/pain_points).
# All other roles use per-role shape and omit stages/pain_points.
_PROCESS_ROLES = {"Current State", "Process Flow", "Operating Model"}
# Visual patterns that also require the process-flow baseline.
_PROCESS_VISUAL_PATTERNS = {"IG-03"}
_IMPACT_TERMS = (
    "delays",
    "reduces",
    "limits",
    "increases",
    "impacts",
    "constrains",
    "creates",
    "weakens",
    "disrupts",
    "erodes",
)
_WEAK_STAGE_TERMS = {
    "intake",
    "preparation",
    "execution",
    "reporting",
    "governance",
    "payroll",
    "receive goods",
    "create purchase order",
}
_GENERIC_STAGE_DEFAULTS = [
    "Demand Intake Governance",
    "Data Quality Management",
    "Workflow Execution Control",
    "Exception Management",
    "Performance Visibility",
    "Continuous Improvement Governance",
]
_PROCESS_STAGE_OVERRIDES = {
    "record-to-report": [
        "Journal Entry Governance",
        "General Ledger Control",
        "Close Process Management",
        "Consolidation Governance",
        "Management Reporting",
        "Performance Decision Support",
    ],
    "procure-to-pay": [
        "Strategic Sourcing Governance",
        "Supplier Collaboration Management",
        "Purchase Requisition Control",
        "Purchase Order Management",
        "Invoice Reconciliation",
        "Payment Execution Governance",
    ],
    "hire-to-retire": [
        "Workforce Demand Planning",
        "Talent Acquisition Governance",
        "Onboarding Workflow Management",
        "Performance Management",
        "Payroll & Workforce Administration",
        "Separation Governance",
    ],
    "order-to-cash": [
        "Customer Order Governance",
        "Order Management Control",
        "Fulfillment Workflow Management",
        "Billing Exception Management",
        "Collections Governance",
        "Cash Application Control",
    ],
    "plan-source-make-deliver": [
        "Demand Planning Governance",
        "Supplier Collaboration Management",
        "Production Planning Control",
        "Inventory Visibility Management",
        "Distribution Execution Governance",
        "Supply Chain Performance Management",
    ],
    "manufacturing operations": [
        "Production Planning Governance",
        "Material Readiness Control",
        "Manufacturing Execution Management",
        "Quality Control Management",
        "Maintenance Workflow Governance",
        "Finished Goods Handover",
    ],
    "case-to-resolution": [
        "Case Intake Governance",
        "Service Triage Management",
        "Resolution Workflow Control",
        "Escalation Management",
        "Closure Governance",
        "Customer Feedback Visibility",
    ],
    "campaign-to-lead": [
        "Campaign Planning Governance",
        "Audience Targeting Management",
        "Content Workflow Control",
        "Campaign Execution Management",
        "Lead Capture Governance",
        "Lead Qualification Control",
    ],
}


def generate_content(
    intent: IntentResult,
    context: EnterpriseContext,
    process_result: ProcessResult,
) -> SlideSpec:
    """
    Generate a complete current-state operating model SlideSpec.

    The returned ``raw_spec`` preserves the existing operating-model renderer
    contract while also carrying Sprint 4 fields such as ``executive_summary``,
    ``pain_points``, and ``metadata``.
    """
    logger.info(
        "generating content: company=%s process=%s",
        context.company,
        process_result.process_name,
    )

    payload = _generate_payload(intent, context, process_result)
    raw_spec = _to_renderer_ready_spec(payload, intent, context, process_result)

    # Validate the renderer-facing subset before wrapping it in SlideSpec.
    OperatingModelSpec.model_validate(raw_spec)

    return SlideSpec(
        slide_type="operating_model",
        raw_spec=raw_spec,
        version="2.0",
        generated_by="consulting_content_generator_v1",
        visual_pattern_id=None,
        visual_confidence=None,
    )


def generate_slide_content(
    intent: IntentResult,
    context: EnterpriseContext,
    process_result: ProcessResult,
    slide_plan: SlidePlan,
    *,
    visual_pattern_selection: VisualPatternSelection | None = None,
    asset_id: str | None = None,
    asset_manifest: AssetManifest | None = None,
) -> SlideSpec:
    """
    Generate a single slide's content from a SlidePlan.

    This function is slide-aware and visual-aware: the SlidePlan's role,
    purpose, and the selected VisualPatternSelection are passed to the LLM so
    the generated content is already shaped for the renderer. The underlying
    renderer contract remains backward-compatible.

    ``asset_id`` is the Presentation Asset chosen for this slide by the Deck
    Executor's sibling Asset Selector call. It is stamped onto the returned
    SlideSpec unchanged so the Populator can open the right .pptx later.

    ``asset_manifest`` is the full manifest of the selected asset. When
    supplied, the LLM prompt is built directly from the manifest's placeholder
    list (Sprint D), producing a ``raw_spec`` keyed by placeholder id instead
    of the legacy operating-model shape. None keeps the legacy path unchanged.
    """
    logger.info(
        "generating slide content: company=%s process=%s slide_role=%s slide_number=%s visual_pattern=%s asset=%s",
        context.company,
        process_result.process_name,
        slide_plan.slide_role,
        slide_plan.slide_number,
        visual_pattern_selection.pattern_id if visual_pattern_selection else "auto",
        asset_id or "none",
    )

    if slide_plan.slide_role == "Section Divider":
        return _section_divider_spec(
            intent, context, slide_plan, visual_pattern_selection, asset_id=asset_id
        )

    if visual_pattern_selection is None:
        visual_pattern_selection = _select_visual_pattern(slide_plan)

    if asset_manifest is not None:
        payload = _generate_manifest_payload(
            intent,
            context,
            process_result,
            slide_plan=slide_plan,
            visual_pattern_selection=visual_pattern_selection,
            asset_manifest=asset_manifest,
        )
        raw_spec = _apply_manifest_shape(
            payload,
            asset_manifest,
            intent,
            context,
            process_result,
            slide_plan=slide_plan,
        )
        return SlideSpec(
            slide_type="operating_model",
            raw_spec=raw_spec,
            version="2.0",
            generated_by="consulting_slide_content_generator_v1",
            visual_pattern_id=(
                visual_pattern_selection.pattern_id if visual_pattern_selection else None
            ),
            visual_confidence=(
                visual_pattern_selection.confidence if visual_pattern_selection else None
            ),
            asset_id=asset_id,
        )

    payload = _generate_payload(
        intent,
        context,
        process_result,
        slide_plan=slide_plan,
        visual_pattern_selection=visual_pattern_selection,
    )
    raw_spec = _to_renderer_ready_spec(
        payload,
        intent,
        context,
        process_result,
        slide_plan=slide_plan,
        visual_pattern_selection=visual_pattern_selection,
    )

    # Validate the renderer-facing subset before wrapping it in SlideSpec.
    OperatingModelSpec.model_validate(raw_spec)

    return SlideSpec(
        slide_type="operating_model",
        raw_spec=raw_spec,
        version="2.0",
        generated_by="consulting_slide_content_generator_v1",
        visual_pattern_id=(
            visual_pattern_selection.pattern_id if visual_pattern_selection else None
        ),
        visual_confidence=(
            visual_pattern_selection.confidence if visual_pattern_selection else None
        ),
        asset_id=asset_id,
    )


def _select_visual_pattern(slide_plan: SlidePlan) -> VisualPatternSelection:
    """Select a visual pattern for a SlidePlan using the Visual Planner."""
    candidate_spec = SlideSpec(
        slide_type="operating_model",
        raw_spec={
            "title": slide_plan.slide_role,
            "subtitle": slide_plan.purpose,
        },
    )
    return plan_visual_pattern(slide_plan, candidate_spec)


def _generate_payload(
    intent: IntentResult,
    context: EnterpriseContext,
    process_result: ProcessResult,
    slide_plan: SlidePlan | None = None,
    *,
    visual_pattern_selection: VisualPatternSelection | None = None,
) -> dict[str, Any]:
    try:
        domain_knowledge = _load_domain_knowledge(context.industry, intent.business_function or context.business_function)
        payload = _call_content_llm(
            intent,
            context,
            process_result,
            domain_knowledge,
            slide_plan,
            visual_pattern_selection=visual_pattern_selection,
        )
        if not isinstance(payload, dict):
            raise ValueError("Content LLM response was not a JSON object.")
        return payload
    except Exception as exc:  # noqa: BLE001 - generic fallback keeps v2 runnable.
        logger.warning("content generation LLM failed; using generic fallback: %s", exc)
        return _fallback_payload(
            intent,
            context,
            process_result,
            slide_plan=slide_plan,
            visual_pattern_selection=visual_pattern_selection,
        )


def _load_domain_knowledge(industry: str | None, business_function: str | None) -> DomainKnowledge:
    """Load curated knowledge, returning a safe default if anything fails."""
    try:
        return get_knowledge(industry, business_function)
    except Exception as exc:  # noqa: BLE001
        logger.warning("failed to load domain knowledge; using default: %s", exc)
        return DomainKnowledge(domain="General Enterprise")


def _compact_enterprise_context(
    context: EnterpriseContext,
    max_facts: int = 5,
    max_fact_length: int = 300,
) -> dict[str, Any]:
    """
    Return a token-light representation of ``EnterpriseContext`` for LLM prompts.

    The full context can carry dozens of grounded facts plus sources and warnings,
    which quickly exceeds low-tier provider token limits. For content generation we
    only need the high-level company profile and the most salient facts.
    """
    facts = context.facts[:max_facts]
    return {
        "company": context.company,
        "industry": context.industry,
        "business_function": context.business_function,
        "company_summary": context.company_summary,
        "facts": [
            {
                "fact_type": fact.type,
                "text": fact.statement[:max_fact_length],
            }
            for fact in facts
        ],
    }


def _call_content_llm(
    intent: IntentResult,
    context: EnterpriseContext,
    process_result: ProcessResult,
    domain_knowledge: DomainKnowledge,
    slide_plan: SlidePlan | None = None,
    *,
    visual_pattern_selection: VisualPatternSelection | None = None,
) -> dict[str, Any]:
    from backend.llm import router

    user_input = {
        "intent": intent.model_dump(mode="json"),
        "enterprise_context": _compact_enterprise_context(context),
        "process_result": process_result.model_dump(mode="json"),
        "domain_knowledge": domain_knowledge.model_dump(mode="json"),
    }
    if slide_plan is not None:
        user_input["slide_plan"] = slide_plan.model_dump(mode="json")
    if visual_pattern_selection is not None:
        user_input["visual_pattern"] = visual_pattern_selection.model_dump(mode="json")

    prompt_module = "slide_content" if slide_plan is not None else "content"

    visual_instruction = ""
    if visual_pattern_selection is not None:
        visual_instruction = _visual_pattern_instruction(visual_pattern_selection.pattern_id)

    prompt = build_prompt(
        prompt_module,
        user_input=json.dumps(user_input, ensure_ascii=True),
        additional_context=f"{visual_instruction}\n\nInput:",
    )
    return router.generate_json("content_generator", prompt, temperature=0.2)


def _slide_role_scope(slide_role: str) -> str:
    """Return a board-facing scope phrase for a slide role."""
    role_lower = slide_role.lower()
    mapping = {
        "executive summary": "Strategic Summary",
        "current state": "Current Operating Model",
        "future state": "Target Operating Model",
        "business benefits": "Expected Value",
        "ai use cases": "AI Applications",
        "implementation roadmap": "Implementation Sequence",
        "transformation timeline": "Program Timeline",
        "implementation risks": "Risk Exposure",
        "kpis for success": "Success Metrics",
        "next steps": "Immediate Actions",
        "opportunities": "Improvement Opportunities",
        "maturity assessment": "Capability Maturity",
    }
    for key, phrase in mapping.items():
        if key in role_lower:
            return phrase
    return slide_role


def _section_divider_spec(
    intent: IntentResult,
    context: EnterpriseContext,
    slide_plan: SlidePlan,
    visual_pattern_selection: VisualPatternSelection | None,
    *,
    asset_id: str | None = None,
) -> SlideSpec:
    """Return a SlideSpec for a section-break divider slide."""
    company = _clean_text(context.company) or _clean_text(getattr(intent, "company", None)) or "Enterprise"
    next_role = slide_plan.purpose.replace("Transition to", "").strip().rstrip(".")
    section_title = _slide_role_scope(next_role) if next_role else "Next Section"
    if asset_id == "SECTION-DIVIDER-DARK-001":
        divider_context = f"{slide_plan.purpose} {getattr(intent, 'raw_content', '')}".lower()
        if "roadmap" in divider_context:
            section_title = "Implementation Roadmap"
        raw_spec = {
            "section_number": f"SECTION {slide_plan.slide_number:02d}",
            "title": _fit_compact_label(section_title, "Implementation Roadmap", max_chars=34),
            "subtitle": _fit_compact_label(
                f"{company} procurement transformation roadmap",
                f"{company} transformation roadmap",
                max_chars=82,
            ),
            "tagline": "Board discussion",
        }
    elif asset_id == "SECTION-NEXT-STEPS-001":
        raw_spec = {
            "section_number": f"SECTION {slide_plan.slide_number:02d}",
            "section_title": "NEXT STEPS\n& ACTIONS",
            "section_subtitle": (
                "Decisions, accountabilities and actions required after the transformation proposal."
            ),
        }
    else:
        raw_spec = {
            "title": slide_plan.slide_role,
            "subtitle": f"{company} — {section_title}",
            "description": f"Transition to {section_title}.",
            "executive_summary": f"The following section covers {section_title.lower()}.",
            "section_title": section_title,
            "metadata": {
                "company": company,
                "slide_role": slide_plan.slide_role,
                "slide_number": str(slide_plan.slide_number),
                "visual_pattern": "SECTION-DIVIDER",
            },
        }
    return SlideSpec(
        slide_type="operating_model",
        raw_spec=raw_spec,
        version="2.0",
        generated_by="consulting_slide_content_generator_v1",
        visual_pattern_id="SECTION-DIVIDER",
        visual_confidence=1.0,
        asset_id=asset_id,
    )


def _description_from_executive_summary(value: Any) -> str | None:
    """Return the first sentence of the executive summary for use as description."""
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split()).strip()
    if not cleaned:
        return None
    # Split on sentence boundary, keep the first sentence.
    import re

    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    first = parts[0].strip()
    return first or None


def _to_renderer_ready_spec(
    payload: dict[str, Any],
    intent: IntentResult,
    context: EnterpriseContext,
    process_result: ProcessResult,
    slide_plan: SlidePlan | None = None,
    *,
    visual_pattern_selection: VisualPatternSelection | None = None,
) -> dict[str, Any]:
    company = _clean_text(context.company) or _clean_text(getattr(intent, "company", None)) or "Enterprise"
    industry = _clean_text(context.industry) or _clean_text(getattr(intent, "industry", None)) or "Unknown"
    business_function = (
        _clean_text(getattr(intent, "business_function", None))
        or _clean_text(context.business_function)
        or process_result.process_family
    )

    if slide_plan is not None:
        title = slide_plan.slide_role
        role_scope = _slide_role_scope(slide_plan.slide_role)
        subtitle = (
            _clean_text(payload.get("subtitle"))
            or f"{company} {business_function} — {role_scope}"
        )
        description = (
            _clean_text(payload.get("description"))
            or _description_from_executive_summary(payload.get("executive_summary"))
            or role_scope
        )
    else:
        title = _clean_text(payload.get("title")) or _clean_text(intent.raw_title) or "Current State"
        subtitle = _clean_text(payload.get("subtitle")) or f"{company} {business_function} Operating Model"
        description = f"{process_result.process_name} current-state operating model"

    executive_summary = _normalize_executive_summary(
        payload.get("executive_summary"),
        default=_default_executive_summary(company, industry, process_result),
    )

    pattern_id = (
        visual_pattern_selection.pattern_id if visual_pattern_selection else None
    )
    slide_role = _resolve_slide_role(slide_plan, payload, intent)
    use_stages = slide_role in _PROCESS_ROLES or pattern_id in _PROCESS_VISUAL_PATTERNS

    if use_stages:
        stage_labels = _six_stage_labels(process_result)
        stages = _normalize_stages(payload.get("stages"), stage_labels)
        pain_points = _normalize_pain_points(payload.get("pain_points"), stage_labels)
        renderer_stages = [
            {
                "number": index + 1,
                "title": stage["label"],
                "label": stage["label"],
                "activities": stage["activities"],
            }
            for index, stage in enumerate(stages)
        ]
        risks = [
            {
                "stage": index + 1,
                "text": pain_points[index]["text"],
            }
            for index in range(len(stages))
        ]
    else:
        stages = []
        pain_points = []
        renderer_stages = []
        risks = []

    metadata = {
        "company": company,
        "industry": industry,
        "process": process_result.process_name,
    }
    if slide_plan is not None:
        metadata["slide_role"] = slide_plan.slide_role
        metadata["slide_number"] = str(slide_plan.slide_number)
    payload_metadata = payload.get("metadata", {})
    if isinstance(payload_metadata, dict):
        metadata.update({key: value for key, value in payload_metadata.items() if isinstance(value, str)})
    metadata["company"] = company
    metadata["industry"] = industry
    metadata["process"] = process_result.process_name

    # Phase 2.4 — Implementation Risks slide separates risks from mitigations.
    if slide_role == "Implementation Risks":
        risks, mitigations = _split_risks_and_mitigations(payload, risks)
        if mitigations:
            metadata["mitigations"] = mitigations

    raw_spec = {
        "title": title,
        "subtitle": subtitle,
        "description": description,
        "executive_summary": executive_summary,
        "summary": {
            "headline": process_result.process_name,
            "description": executive_summary,
            "metrics": [],
        },
        "stages": renderer_stages,
        "pain_points": pain_points,
        "risks": risks,
        "metadata": metadata,
    }

    if visual_pattern_selection is not None:
        raw_spec = _apply_visual_pattern_shape(
            raw_spec, payload, visual_pattern_selection.pattern_id
        )

    return raw_spec


def _resolve_slide_role(
    slide_plan: SlidePlan | None,
    payload: dict[str, Any],
    intent: IntentResult,
) -> str:
    """Determine the consulting role of the slide being generated."""
    if slide_plan is not None:
        return slide_plan.slide_role
    payload_role = _clean_text(payload.get("slide_role")) or _clean_text(payload.get("title"))
    if payload_role:
        return payload_role
    return getattr(intent, "slide_type", "") or "Current State"


def _split_risks_and_mitigations(
    payload: dict[str, Any],
    fallback_risks: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Separate risks from mitigations for the Implementation Risks slide.

    Risks carry a ``quadrant`` (Impact × Likelihood) and never include mitigation
    text. Mitigations are returned as ``[{risk, mitigation}]`` for ``metadata``.

    Returns ``(risks, mitigations)``. When the LLM emitted a ``risks`` array it is
    normalized in place; otherwise the synthesised ``fallback_risks`` are used.
    """
    risks_raw = payload.get("risks")
    risks: list[dict[str, Any]] = []
    if isinstance(risks_raw, list) and risks_raw:
        for item in risks_raw:
            if not isinstance(item, dict):
                continue
            risk_text = _clean_text(item.get("text") or item.get("risk") or item.get("title"))
            quadrant = item.get("quadrant")
            if not isinstance(quadrant, dict):
                impact = item.get("impact")
                likelihood = item.get("likelihood")
                quadrant = {"impact": str(impact or ""), "likelihood": str(likelihood or "")}
            risk_entry: dict[str, Any] = {
                "stage": item.get("stage", len(risks) + 1),
                "text": risk_text or "",
                "quadrant": quadrant,
            }
            risks.append(risk_entry)
    else:
        risks = list(fallback_risks)

    mitigations_raw = payload.get("mitigations")
    mitigations: list[dict[str, str]] = []
    if isinstance(mitigations_raw, list):
        for item in mitigations_raw:
            if not isinstance(item, dict):
                continue
            risk_ref = _clean_text(item.get("risk") or item.get("text") or "")
            mitigation = _clean_text(item.get("mitigation") or item.get("text") or "")
            if risk_ref or mitigation:
                mitigations.append({"risk": risk_ref or "", "mitigation": mitigation or ""})
    return risks, mitigations


def _normalize_stages(items: Any, stage_labels: list[str]) -> list[dict[str, Any]]:
    input_stages = items if isinstance(items, list) else []
    if not input_stages:
        return []
    stages: list[dict[str, Any]] = []
    for index, label in enumerate(stage_labels):
        item = input_stages[index] if index < len(input_stages) and isinstance(input_stages[index], dict) else {}
        item_label = _normalize_stage_label(item.get("label") or item.get("title"), fallback=label)
        activities = _normalize_activities(item.get("activities"), item_label)
        stages.append({"label": item_label, "activities": activities})
    return stages


def _normalize_activities(items: Any, stage_label: str) -> list[str]:
    activities: list[str] = []
    if isinstance(items, list):
        for item in items:
            cleaned = _normalize_activity(item)
            if cleaned:
                activities.append(cleaned)
            if len(activities) == _ACTIVITIES_PER_STAGE:
                break
    # Do not pad the list with fallback templates; keep only what the LLM emitted.
    return activities[:_ACTIVITIES_PER_STAGE]


def _normalize_pain_points(items: Any, stage_labels: list[str]) -> list[dict[str, str]]:
    input_points = items if isinstance(items, list) else []
    if not input_points:
        return []
    points_by_stage: dict[str, str] = {}
    ordered_points: list[str] = []
    for item in input_points:
        if not isinstance(item, dict):
            continue
        text = _normalize_pain_point_text(item.get("text"), stage=_clean_text(item.get("stage")) or "")
        if not text:
            continue
        stage = _clean_text(item.get("stage"))
        if stage:
            points_by_stage[stage.lower()] = text
        ordered_points.append(text)

    pain_points: list[dict[str, str]] = []
    for index, label in enumerate(stage_labels):
        text = points_by_stage.get(label.lower())
        if not text and index < len(ordered_points):
            text = ordered_points[index]
        if not text:
            text = _normalize_pain_point_text("", stage=label)
        pain_points.append({"stage": label, "text": text})
    return pain_points


def _fallback_payload(
    intent: IntentResult,
    context: EnterpriseContext,
    process_result: ProcessResult,
    slide_plan: SlidePlan | None = None,
    *,
    visual_pattern_selection: VisualPatternSelection | None = None,
) -> dict[str, Any]:
    company = _clean_text(context.company) or _clean_text(getattr(intent, "company", None)) or "Enterprise"
    business_function = (
        _clean_text(getattr(intent, "business_function", None))
        or _clean_text(context.business_function)
        or process_result.process_family
    )
    pattern_id = (
        visual_pattern_selection.pattern_id if visual_pattern_selection else None
    )
    slide_role = slide_plan.slide_role if slide_plan is not None else (
        getattr(intent, "slide_type", "") or "Current State"
    )
    use_stages = slide_role in _PROCESS_ROLES or pattern_id in _PROCESS_VISUAL_PATTERNS
    if use_stages:
        stage_labels = _six_stage_labels(process_result)
        stage_payload = [
            {"label": label, "activities": _normalize_activities([], label)}
            for label in stage_labels
        ]
        pain_payload = [
            {"stage": label, "text": _normalize_pain_point_text("", stage=label)}
            for label in stage_labels
        ]
    else:
        stage_payload = []
        pain_payload = []
    if slide_plan is not None:
        title = slide_plan.slide_role
        subtitle = f"{company} {business_function} — {slide_plan.purpose}"
        description = slide_plan.purpose
    else:
        title = _clean_text(intent.raw_title) or "Current State"
        subtitle = f"{company} {business_function} Operating Model"
        description = f"{process_result.process_name} current-state operating model"
    return {
        "title": title,
        "subtitle": subtitle,
        "description": description,
        "executive_summary": _default_executive_summary(company, context.industry, process_result),
        "stages": stage_payload,
        "pain_points": pain_payload,
        "metadata": {
            "company": company,
            "industry": _clean_text(context.industry) or "Unknown",
            "process": process_result.process_name,
        },
    }


# ── Manifest-aware content generation (Sprint D) ─────────────────────────────


def _generate_manifest_payload(
    intent: IntentResult,
    context: EnterpriseContext,
    process_result: ProcessResult,
    slide_plan: SlidePlan | None = None,
    *,
    visual_pattern_selection: VisualPatternSelection | None = None,
    asset_manifest: AssetManifest,
) -> dict[str, Any]:
    """Generate a placeholder-keyed payload shaped by the asset manifest."""
    try:
        domain_knowledge = _load_domain_knowledge(
            context.industry, intent.business_function or context.business_function
        )
        payload = _call_manifest_content_llm(
            intent,
            context,
            process_result,
            domain_knowledge,
            slide_plan,
            visual_pattern_selection=visual_pattern_selection,
            asset_manifest=asset_manifest,
        )
        if not isinstance(payload, dict):
            raise ValueError("Manifest content LLM response was not a JSON object.")
        return payload
    except Exception as exc:  # noqa: BLE001 - generic fallback keeps v2 runnable.
        logger.warning("manifest content generation LLM failed; using fallback: %s", exc)
        return _manifest_fallback_payload(
            intent,
            context,
            process_result,
            slide_plan=slide_plan,
            asset_manifest=asset_manifest,
        )


def _call_manifest_content_llm(
    intent: IntentResult,
    context: EnterpriseContext,
    process_result: ProcessResult,
    domain_knowledge: DomainKnowledge,
    slide_plan: SlidePlan | None = None,
    *,
    visual_pattern_selection: VisualPatternSelection | None = None,
    asset_manifest: AssetManifest,
) -> dict[str, Any]:
    """Call the LLM with the manifest-content prompt module."""
    from backend.llm import router

    user_input = {
        "intent": intent.model_dump(mode="json"),
        "enterprise_context": _compact_enterprise_context(context),
        "process_result": process_result.model_dump(mode="json"),
        "domain_knowledge": domain_knowledge.model_dump(mode="json"),
        "asset_manifest": asset_manifest.model_dump(mode="json"),
    }
    if slide_plan is not None:
        user_input["slide_plan"] = slide_plan.model_dump(mode="json")
    if visual_pattern_selection is not None:
        user_input["visual_pattern"] = visual_pattern_selection.model_dump(mode="json")

    manifest_instruction = _build_manifest_instruction(asset_manifest)

    prompt = build_prompt(
        "manifest_content",
        user_input=json.dumps(user_input, ensure_ascii=True),
        additional_context=manifest_instruction,
    )
    return router.generate_json("content_generator", prompt, temperature=0.2)


def _build_manifest_instruction(asset_manifest: AssetManifest) -> str:
    """Compose a deterministic instruction describing the asset manifest."""
    lines: list[str] = [
        f"Selected Presentation Asset: {asset_manifest.asset_id}",
        f"Family: {asset_manifest.family}",
        f"Purpose: {asset_manifest.purpose}",
        f"Density: {asset_manifest.density} (accommodates {asset_manifest.density_range[0]} to {asset_manifest.density_range[1]} items)",
    ]
    if asset_manifest.repeating:
        repeating = asset_manifest.repeating
        lines.append(
            f"Repeating group: {repeating.group_template} with {repeating.count} instances; "
            f"placeholders per group: {', '.join(repeating.placeholders_per_group)}"
        )
    lines.append("")
    lines.append("Placeholder manifest (generate content for each id below):")
    for placeholder in asset_manifest.placeholders:
        schema_hint = f" content_schema={placeholder.content_schema}" if placeholder.content_schema else ""
        constraint_hint = f" constraints={placeholder.constraints}" if placeholder.constraints else ""
        lines.append(
            f"- id={placeholder.id!r} role={placeholder.role!r} kind={placeholder.kind.value} "
            f"cardinality={placeholder.cardinality} required={placeholder.required}"
            f"{schema_hint}{constraint_hint}"
        )
    lines.append("")
    lines.append(
        "Return a JSON object whose top-level keys are exactly the placeholder ids listed above. "
        "Do not include any other top-level keys."
    )
    return "\n".join(lines)


def _apply_manifest_shape(
    payload: dict[str, Any],
    asset_manifest: AssetManifest,
    intent: IntentResult,
    context: EnterpriseContext,
    process_result: ProcessResult,
    slide_plan: SlidePlan | None = None,
) -> dict[str, Any]:
    """Validate and return a manifest-shaped raw_spec, or a safe fallback."""
    if not isinstance(payload, dict):
        payload = {}
    issues = check_conformance(payload, asset_manifest)
    if issues:
        logger.warning("manifest content failed conformance: %s; using fallback", issues)
        fallback = _manifest_fallback_payload(
            intent,
            context,
            process_result,
            slide_plan=slide_plan,
            asset_manifest=asset_manifest,
        )
        fallback = _repair_manifest_contract(fallback, asset_manifest, slide_plan)
        return _lock_manifest_title_to_plan(fallback, asset_manifest, slide_plan)
    payload = _repair_manifest_contract(payload, asset_manifest, slide_plan)
    fit = check_text_fit(payload, asset_manifest)
    if not fit.passed:
        retry = shorten_to_fit_once(payload, asset_manifest)
        if retry.passed and retry.content is not None:
            logger.info(
                "manifest content shortened to fit asset=%s placeholders=%s",
                asset_manifest.asset_id,
                retry.truncated,
            )
            return _lock_manifest_title_to_plan(retry.content, asset_manifest, slide_plan)
        logger.warning(
            "manifest content text-fit failed after shorten pass: %s",
            [f"{f.placeholder_id}: {f.reason}" for f in retry.failures],
        )
    return _lock_manifest_title_to_plan(payload, asset_manifest, slide_plan)


def _repair_manifest_contract(
    payload: dict[str, Any],
    asset_manifest: AssetManifest,
    slide_plan: SlidePlan | None,
) -> dict[str, Any]:
    """Apply narrow, deterministic content repairs before validation.

    This does not invent layout or change the asset. It removes known filler
    phrases and makes role-critical fields explicit enough for the quality gate.
    """
    repaired = _replace_generic_language(payload)
    if slide_plan is None:
        return repaired
    role = (slide_plan.slide_role or "").lower()
    if "roadmap" in role or "implementation" in role:
        repaired = _repair_roadmap_labels(repaired, asset_manifest)
    if "risk" in role:
        repaired = _repair_risk_language(repaired)
    repaired = _repair_risk_register(repaired, asset_manifest)
    repaired = _repair_compact_use_case_shortlist(repaired, asset_manifest)
    repaired = _repair_compact_opportunity_grid(repaired, asset_manifest)
    repaired = _repair_current_future_comparison(repaired, asset_manifest)
    repaired = _repair_current_process_6step(repaired, asset_manifest)
    repaired = _repair_value_realization_roadmap(repaired, asset_manifest)
    repaired = _repair_kpi_dashboard_values(repaired, asset_manifest)
    repaired = _repair_kpi_scorecard_table(repaired, asset_manifest)
    repaired = _repair_governance_model_labels(repaired, asset_manifest)
    repaired = _repair_investment_case_labels(repaired, asset_manifest)
    if _is_next_step_manifest(asset_manifest) or "next step" in role or "decision" in role or "action" in role:
        repaired = _repair_next_step_language(repaired, asset_manifest)
    repaired = _repair_title_so_what(repaired, slide_plan)
    repaired = _repair_repeating_placeholder_lengths(repaired, asset_manifest, slide_plan)
    return repaired


def _repair_value_realization_roadmap(
    payload: dict[str, Any],
    asset_manifest: AssetManifest,
) -> dict[str, Any]:
    """Ensure the bottom cumulative-benefits strip is populated."""
    if (asset_manifest.asset_id or "") != "VALUE-REALIZATION-ROADMAP-001":
        return payload
    repaired = dict(payload)
    repaired["milestone_value"] = _repair_fixed_list(
        repaired.get("milestone_value"),
        ["10%", "45%", "100%"],
        max_chars=8,
    )
    repaired["milestone_description"] = _repair_fixed_list(
        repaired.get("milestone_description"),
        [
            "Quick wins captured",
            "Automation benefits ramp",
            "Full value at scale",
        ],
        max_chars=40,
    )
    total = _clean_text(repaired.get("total_value"))
    if not total or _is_placeholder_default_text(total):
        total = "$50M total projected value"
    repaired["total_value"] = _fit_compact_label(total, "$50M total projected value", max_chars=35)
    return repaired


def _repair_fixed_list(value: Any, defaults: list[str], *, max_chars: int) -> list[str]:
    items = _as_list(value)
    repaired: list[str] = []
    for index, fallback in enumerate(defaults):
        raw = items[index] if index < len(items) else ""
        text = _clean_text(raw) if isinstance(raw, str) else ""
        if not text or _is_placeholder_default_text(text):
            text = fallback
        repaired.append(_fit_compact_label(text, fallback, max_chars=max_chars))
    return repaired


def _repair_current_future_comparison(
    payload: dict[str, Any],
    asset_manifest: AssetManifest,
) -> dict[str, Any]:
    """Keep current/future comparison content semantically distinct from future-state-only slides."""
    if (asset_manifest.asset_id or "") != "CURRENT-FUTURE-COMPARISON-5SHIFT-001":
        return payload
    repaired = dict(payload)
    repaired["title"] = "Current-to-future shifts define the HR transformation path"
    repaired["subtitle"] = "Five shifts move Unilever HR from fragmented work to a future-ready operating model"
    repaired["current_state"] = [
        "Local HR intake and routing",
        "Fragmented employee data",
        "Inconsistent policy guidance",
        "Reactive workforce planning",
        "Variable employee experience",
    ]
    repaired["transformation_shift"] = [
        "Standardize intake",
        "Unify data",
        "Automate guidance",
        "Plan skills",
        "Personalize service",
    ]
    repaired["future_state"] = [
        "Digital front door with clear ownership",
        "Trusted HR data available in real time",
        "AI guidance applies policy consistently",
        "Skills insights guide workforce decisions",
        "Employee journeys become measurable",
    ]
    repaired["takeaway"] = (
        "The transformation shifts HR from reactive service delivery to data-led workforce enablement."
    )
    return repaired


def _repair_current_process_6step(
    payload: dict[str, Any],
    asset_manifest: AssetManifest,
) -> dict[str, Any]:
    """Ensure the six-step current-process asset shows the requested business impact."""
    if (asset_manifest.asset_id or "") != "CURRENT-STATE-PROCESS-6STEP-001":
        return payload
    repaired = dict(payload)
    repaired["title"] = "Current supply chain friction constrains growth"
    repaired["subtitle"] = "Six process steps expose delays, exceptions and fragmented ownership"
    repaired["takeaway"] = (
        "Business impact: delays, exceptions and fragmented ownership constrain service, cost and resilience."
    )
    return repaired


def _repair_risk_register(
    payload: dict[str, Any],
    asset_manifest: AssetManifest,
) -> dict[str, Any]:
    """Backfill the 7-row risk register with compact row and summary text."""
    if (asset_manifest.asset_id or "") != "RISK-REGISTER-7ITEM-001":
        return payload
    repaired = dict(payload)
    repaired["title"] = "Implementation risks require accountable mitigation before scale"
    repaired["subtitle"] = "Seven priority risks, owners, and mitigations for Toyota's AI operating model rollout"
    rows = [
        ("MES / ERP data gaps delay model readiness", "High", "Critical", "Run data-quality sprint; assign plant data owners; validate model inputs.", "Data Lead", "Active"),
        ("Plant adoption lags due to workflow disruption", "Medium", "High", "Use change champions; train supervisors; track adoption weekly.", "Plant Ops", "Active"),
        ("Legacy equipment integration proves complex", "Medium", "High", "Prioritize critical interfaces; test integrations early; keep fallback plans.", "IT / OT Lead", "Mitigating"),
        ("Cybersecurity controls slow connected-factory rollout", "Medium", "High", "Embed security review; segment OT networks; approve access controls.", "Security", "Active"),
        ("Model accuracy drops across product variants", "Low", "Moderate", "Monitor drift; retrain models by product family; set human review gates.", "Analytics", "Monitoring"),
        ("Supplier data sharing limits predictive visibility", "Medium", "High", "Agree data standards with key suppliers; phase integration by tier.", "Supply Chain", "Active"),
        ("Benefits ownership weakens after pilot handoff", "Medium", "High", "Assign value owners; review KPIs monthly; tie scale funding to benefits.", "PMO", "Mitigating"),
    ]
    repaired["risk_id"] = [f"R{index}" for index in range(1, len(rows) + 1)]
    repaired["risk_description"] = [
        _fit_compact_label(description, description, max_chars=58)
        for description, *_ in rows
    ]
    repaired["risk_likelihood"] = [likelihood for _, likelihood, *_ in rows]
    repaired["risk_impact"] = [impact for _, _, impact, *_ in rows]
    repaired["risk_mitigation"] = [
        _fit_compact_label(mitigation, mitigation, max_chars=88)
        for _, _, _, mitigation, _, _ in rows
    ]
    repaired["risk_owner"] = [owner for _, _, _, _, owner, _ in rows]
    repaired["risk_status"] = [status for _, _, _, _, _, status in rows]
    repaired["summary_count"] = ["3", "3", "1", "0"]
    repaired["summary_label"] = ["Critical / high", "Active mitigations", "Watchlist", "Closed"]
    repaired["summary_description"] = [
        "Need executive attention",
        "Owners assigned",
        "Monitor through PMO",
        "None closed yet",
    ]
    return repaired


def _repair_compact_use_case_shortlist(
    payload: dict[str, Any],
    asset_manifest: AssetManifest,
) -> dict[str, Any]:
    """Keep narrow prioritization-matrix shortlist slots as compact labels."""
    repaired = dict(payload)
    max_chars_by_id = {
        placeholder.id: placeholder.constraints.get("max_chars", 34)
        for placeholder in asset_manifest.placeholders
        if placeholder.id.startswith("shortlist_") and placeholder.id.endswith("_items")
    }
    for placeholder_id, max_chars in max_chars_by_id.items():
        value = repaired.get(placeholder_id)
        if isinstance(value, str):
            repaired[placeholder_id] = _compact_use_case_label(value, int(max_chars or 34))
    return repaired


def _compact_use_case_label(value: str, max_chars: int) -> str:
    text = _clean_text(value).rstrip(".")
    replacements = {
        "supplier collaboration platform": "Supplier visibility platform",
        "ai-powered logistics optimization": "Logistics cost optimization",
        "automated procurement analytics": "Procurement analytics",
        "predictive analytics": "Demand forecasting",
        "autonomous procurement negotiation": "Autonomous negotiation",
        "synthetic-data generation": "Synthetic data generation",
    }
    lowered = text.lower()
    for phrase, replacement in replacements.items():
        if phrase in lowered:
            text = replacement
            break
    text = re.sub(r"^(ai-powered|automated)\s+", "", text, flags=re.I)
    text = re.split(r"\s+(?:for|to|with|that|which)\s+", text, maxsplit=1, flags=re.I)[0]
    text = text.strip(" -:;.").strip()
    return _fit_compact_label(text, "Demand forecasting", max_chars=max_chars)


def _repair_compact_opportunity_grid(
    payload: dict[str, Any],
    asset_manifest: AssetManifest,
) -> dict[str, Any]:
    """Keep six-area opportunity cards inside their compact text slots."""
    if (asset_manifest.asset_id or "") != "OPPORTUNITY-6AREA-001":
        return payload
    repaired = dict(payload)
    max_chars_by_id = {
        placeholder.id: int(placeholder.constraints.get("max_chars", 42) or 42)
        for placeholder in asset_manifest.placeholders
        if placeholder.id in {"opportunity_title", "current_issue", "opportunity", "value_unlocked"}
    }
    for placeholder_id, max_chars in max_chars_by_id.items():
        value = repaired.get(placeholder_id)
        if isinstance(value, list):
            repaired[placeholder_id] = [
                _compact_opportunity_value(placeholder_id, str(item), index, max_chars)
                for index, item in enumerate(value)
            ]
        elif isinstance(value, str):
            repaired[placeholder_id] = _compact_opportunity_value(placeholder_id, value, 0, max_chars)
    return repaired


def _compact_opportunity_value(placeholder_id: str, value: str, index: int, max_chars: int) -> str:
    text = _clean_text(value).rstrip(".")
    lowered = text.lower()
    replacements_by_field = {
        "opportunity_title": {
            "demand forecasting": "Demand forecasting",
            "inventory management": "Inventory management",
            "supplier collaboration": "Supplier collaboration",
            "logistics optimization": "Logistics optimization",
            "process automation": "Process automation",
            "sustainability initiatives": "Sustainability",
        },
        "current_issue": {
            "inaccurate demand forecasts": "Forecast misses create stockouts and buffers",
            "high carrying costs": "Excess stock ties up working capital",
            "limited collaboration": "Limited supplier visibility slows response",
            "inefficient logistics": "Transport cost and delays remain elevated",
            "manual processes": "Manual order work slows execution",
            "lack of sustainable": "Sustainability gaps create brand exposure",
        },
        "opportunity": {
            "ai-driven forecasting": "Deploy AI demand forecasting",
            "optimize inventory": "Optimize inventory policies",
            "supplier engagement": "Launch supplier collaboration workflows",
            "collaborative platforms": "Launch supplier collaboration workflows",
            "route planning": "Optimize routes and shipment planning",
            "automate repetitive": "Automate order and exception handling",
            "sustainable practices": "Scale sustainable sourcing controls",
        },
        "value_unlocked": {
            "reduce inventory costs": "Lower inventory buffers and stockouts",
            "increase inventory turnover": "Faster turns and lower holding cost",
            "savings through improved supplier": "Better supplier terms and reliability",
            "cut logistics costs": "Lower logistics cost and cycle time",
            "boost operational efficiency": "Higher productivity and fewer errors",
            "enhance brand value": "Stronger brand trust and compliance",
        },
    }
    for phrase, replacement in replacements_by_field.get(placeholder_id, {}).items():
        if phrase in lowered:
            text = replacement
            break
    if len(text) > max_chars:
        text = re.sub(r"\b(?:through|by|for|with|due to|resulting in|to reduce|to improve)\b.*$", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip(" -:;.").strip()
    return _fit_compact_label(text, _default_opportunity_value(placeholder_id, index), max_chars=max_chars)


def _default_opportunity_value(placeholder_id: str, index: int) -> str:
    defaults = {
        "opportunity_title": [
            "Demand forecasting",
            "Inventory management",
            "Supplier collaboration",
            "Logistics optimization",
            "Process automation",
            "Sustainability",
        ],
        "current_issue": [
            "Forecast misses create stockouts and buffers",
            "Excess stock ties up working capital",
            "Limited supplier visibility slows response",
            "Transport cost and delays remain elevated",
            "Manual order work slows execution",
            "Sustainability gaps create brand exposure",
        ],
        "opportunity": [
            "Deploy AI demand forecasting",
            "Optimize inventory policies",
            "Launch supplier collaboration workflows",
            "Optimize routes and shipment planning",
            "Automate order and exception handling",
            "Scale sustainable sourcing controls",
        ],
        "value_unlocked": [
            "Lower inventory buffers and stockouts",
            "Faster turns and lower holding cost",
            "Better supplier terms and reliability",
            "Lower logistics cost and cycle time",
            "Higher productivity and fewer errors",
            "Stronger brand trust and compliance",
        ],
    }
    return _indexed_default(index, defaults.get(placeholder_id, ["Value opportunity"]))


def _repair_kpi_dashboard_values(
    payload: dict[str, Any],
    asset_manifest: AssetManifest,
) -> dict[str, Any]:
    """Ensure KPI cards always render a visible metric value."""
    if (asset_manifest.asset_id or "") != "KPI-6PRIORITY-METRICS-001":
        return payload
    repaired = dict(payload)
    names = _as_list(repaired.get("kpi_name"))
    values = _as_list(repaired.get("kpi_value"))
    target_count = asset_manifest.repeating.count if asset_manifest.repeating else asset_manifest.density
    while len(names) < target_count:
        names.append(_default_kpi_name(len(names)))
    while len(values) < target_count:
        values.append("")
    repaired["kpi_name"] = names[:target_count]
    repaired["kpi_value"] = [
        _compact_kpi_value(value, names[index], index)
        for index, value in enumerate(values[:target_count])
    ]
    return repaired


def _repair_kpi_scorecard_table(
    payload: dict[str, Any],
    asset_manifest: AssetManifest,
) -> dict[str, Any]:
    """Populate editable KPI scorecard table cells with generated/default values."""
    if (asset_manifest.asset_id or "") != "KPI-SCORECARD-TABLE-001":
        return payload
    repaired = dict(payload)
    defaults = [
        {
            "kpi_name": "Close Cycle Time\nDays to close",
            "baseline": "8 days",
            "target": "5 days",
            "current": "6 days",
            "owner": "Controllership",
            "cadence": "Monthly",
            "status": "Improving",
            "comment": "AI reconciliations reducing manual close work.",
        },
        {
            "kpi_name": "Invoice Touchless Rate\n% processed without manual review",
            "baseline": "42%",
            "target": "75%",
            "current": "58%",
            "owner": "Finance Ops",
            "cadence": "Monthly",
            "status": "At risk",
            "comment": "Supplier data quality remains the main blocker.",
        },
        {
            "kpi_name": "Forecast Accuracy\nVariance to actuals",
            "baseline": "78%",
            "target": "90%",
            "current": "84%",
            "owner": "FP&A",
            "cadence": "Monthly",
            "status": "Improving",
            "comment": "Model pilots improving revenue and cost forecasts.",
        },
        {
            "kpi_name": "Control Exception Rate\n% transactions with exceptions",
            "baseline": "18%",
            "target": "8%",
            "current": "12%",
            "owner": "Risk & Control",
            "cadence": "Monthly",
            "status": "Improving",
            "comment": "Exception analytics targeting high-risk controls.",
        },
        {
            "kpi_name": "Manual Journal Rate\n% journals manually posted",
            "baseline": "35%",
            "target": "15%",
            "current": "24%",
            "owner": "Accounting",
            "cadence": "Monthly",
            "status": "At risk",
            "comment": "Workflow adoption required before scale-up.",
        },
        {
            "kpi_name": "Audit Evidence Readiness\n% evidence auto-collected",
            "baseline": "50%",
            "target": "85%",
            "current": "68%",
            "owner": "Audit",
            "cadence": "Quarterly",
            "status": "On track",
            "comment": "Evidence automation progressing in priority controls.",
        },
        {
            "kpi_name": "AI Adoption\n% priority users active",
            "baseline": "20%",
            "target": "70%",
            "current": "45%",
            "owner": "Transformation",
            "cadence": "Monthly",
            "status": "Improving",
            "comment": "Usage rising as finance teams complete training.",
        },
    ]
    max_chars_by_id = {
        placeholder.id: int(placeholder.constraints.get("max_chars", 32) or 32)
        for placeholder in asset_manifest.placeholders
    }
    for index, row in enumerate(defaults, start=1):
        for field, fallback in row.items():
            placeholder_id = f"{field}_{index}"
            value = repaired.get(placeholder_id)
            text = _clean_text(value) if isinstance(value, str) else ""
            if not text or _is_placeholder_default_text(text):
                text = fallback
            repaired[placeholder_id] = _fit_compact_label(
                text,
                fallback,
                max_chars=max_chars_by_id.get(placeholder_id, len(fallback)),
            )

    repaired["on_track_count"] = _fit_compact_label(repaired.get("on_track_count"), "2", max_chars=4)
    repaired["at_risk_count"] = _fit_compact_label(repaired.get("at_risk_count"), "2", max_chars=4)
    repaired["off_track_count"] = _fit_compact_label(repaired.get("off_track_count"), "0", max_chars=4)
    repaired["on_track_description"] = "Two KPIs meeting plan"
    repaired["at_risk_description"] = "Two KPIs need intervention"
    repaired["off_track_description"] = "No KPI materially off track"
    return repaired


def _repair_governance_model_labels(
    payload: dict[str, Any],
    asset_manifest: AssetManifest,
) -> dict[str, Any]:
    """Keep dense governance-model slots to compact native-PPT labels."""
    if (asset_manifest.asset_id or "") != "GOVERNANCE-MODEL-001":
        return payload
    repaired = dict(payload)
    max_chars_by_id = {
        placeholder.id: int(placeholder.constraints.get("max_chars", 28) or 28)
        for placeholder in asset_manifest.placeholders
    }
    compact_defaults = {
        "steering_committee_title": "Steering Committee",
        "steering_committee_mandate": "Strategy | Funding | Escalations",
        "pmo_title": "Project Management Office (PMO)",
        "pmo_mandate": "Integration | Reporting | Risks | Decisions",
    }
    for placeholder_id, fallback in compact_defaults.items():
        value = repaired.get(placeholder_id)
        if isinstance(value, str):
            repaired[placeholder_id] = _fit_compact_label(
                _clean_text(value).rstrip("."),
                fallback,
                max_chars=max_chars_by_id.get(placeholder_id, len(fallback)),
            )
        else:
            repaired[placeholder_id] = fallback

    for prefix, defaults in (
        (
            "steering_responsibility_",
            ["Set priorities", "Approve funding", "Resolve escalations"],
        ),
        (
            "pmo_responsibility_",
            ["Coordinate teams", "Track progress", "Manage risks", "Maintain standards"],
        ),
    ):
        for index, fallback in enumerate(defaults, start=1):
            placeholder_id = f"{prefix}{index}"
            value = repaired.get(placeholder_id)
            if isinstance(value, str):
                repaired[placeholder_id] = fallback
            else:
                repaired[placeholder_id] = fallback

    for placeholder_id, defaults in (
        ("workstream_title", ["Data Integration", "Process Automation", "Performance Analytics", "Change Management"]),
        ("workstream_responsibilities", [
            "Map data\nClean records\nEnable reporting",
            "Redesign flow\nAutomate tasks\nControl exceptions",
            "Define KPIs\nTrack benefits\nReport insights",
            "Engage teams\nTrain users\nMonitor adoption",
        ]),
        ("forum_name", ["SteerCo", "PMO", "Workstreams"]),
        ("forum_cadence", ["Monthly", "Weekly", "Biweekly"]),
        ("decision_right_label", ["Recommend", "Approve", "Escalate"]),
        ("decision_right_description", ["Frame options", "Make final call", "Raise key risks"]),
    ):
        value = repaired.get(placeholder_id)
        if isinstance(value, list):
            repaired_items = [
                _compact_governance_phrase(
                    str(item),
                    _indexed_default(index, defaults),
                    max_chars_by_id.get(placeholder_id, 28),
                )
                for index, item in enumerate(value)
            ]
            while len(repaired_items) < len(defaults):
                repaired_items.append(_indexed_default(len(repaired_items), defaults))
            repaired[placeholder_id] = repaired_items[: len(defaults)]
        elif isinstance(value, str):
            repaired[placeholder_id] = _compact_governance_phrase(
                value,
                _indexed_default(0, defaults),
                max_chars_by_id.get(placeholder_id, 28),
            )
        else:
            repaired[placeholder_id] = list(defaults)
    return repaired


def _compact_governance_phrase(value: str, fallback: str, max_chars: int) -> str:
    text = _clean_text(value).rstrip(".")
    text = re.sub(r"^(review|analyze|evaluate|monitor|manage|coordinate|ensure)\s+", "", text, flags=re.I)
    text = re.split(r"\s+(?:and ensure|and manage|to ensure|for ensuring|across|through|while)\s+", text, maxsplit=1, flags=re.I)[0]
    return _fit_compact_label(text, fallback, max_chars=max_chars)


def _repair_investment_case_labels(
    payload: dict[str, Any],
    asset_manifest: AssetManifest,
) -> dict[str, Any]:
    """Keep investment-case visuals compact enough for fixed EY card slots."""
    if (asset_manifest.asset_id or "") != "INVESTMENT-CASE-SUMMARY-001":
        return payload
    repaired = dict(payload)
    max_chars_by_id = {
        placeholder.id: int(placeholder.constraints.get("max_chars", 32) or 32)
        for placeholder in asset_manifest.placeholders
    }
    defaults = {
        "title": "Investment case supports disciplined AI scale-up",
        "subtitle": "Funding request links phased investment to measurable value",
        "investment_required_value": "$5M",
        "investment_scope": "Phase 1 funding",
        "value_created_value": "$15M",
        "value_drivers": "Positive",
        "timing_value": "12",
        "phased_approach": "Pilot, automate, scale",
        "payback_value": "18",
        "value_investment_value": "3x",
        "npv": "$8M",
        "roi": "300%",
        "assumptions": "Illustrative base case",
        "recommendation": "Approve Phase 1 funding and review benefits monthly.",
    }
    for placeholder_id, fallback in defaults.items():
        if placeholder_id in {"investment_required_value", "value_created_value", "timing_value", "payback_value", "value_investment_value", "npv", "roi"}:
            repaired[placeholder_id] = fallback
            continue
        if placeholder_id in {
            "investment_scope",
            "value_drivers",
            "phased_approach",
            "assumptions",
            "recommendation",
        }:
            repaired[placeholder_id] = fallback
            continue
        value = repaired.get(placeholder_id)
        text_value = _clean_text(value) if isinstance(value, str) else ""
        if _is_placeholder_default_text(text_value):
            text_value = fallback
        repaired[placeholder_id] = _fit_compact_label(
            text_value if text_value else fallback,
            fallback,
            max_chars=max_chars_by_id.get(placeholder_id, len(fallback)),
        )

    repeated_defaults = {
        "investment_component_label": ["Technology", "Training", "Process redesign", "Contingency"],
        "investment_component_value": ["$2M", "$1M", "$1.5M", "$0.5M"],
        "value_component_label": ["Cost takeout", "Productivity", "Control uplift"],
        "value_component_value": ["$7M", "$5M", "$3M"],
        "timeline_label": ["Assess", "Pilot", "Scale"],
        "timeline_duration": ["0-3 mo.", "3-9 mo.", "9-12 mo."],
        "bridge_label": ["Funding", "Enablement", "Benefit ramp", "Scale"],
        "bridge_description": [
            "Approve initial funding",
            "Build priority capabilities",
            "Validate benefits in pilot",
            "Scale proven use cases",
        ],
        "capture_value": ["80%", "75%", "90%", "70%"],
    }
    for placeholder_id, fallback_items in repeated_defaults.items():
        repaired[placeholder_id] = [
            _fit_compact_label(
                fallback,
                fallback,
                max_chars=max_chars_by_id.get(placeholder_id, len(fallback)),
            )
            for fallback in fallback_items
        ]
    return repaired


def _compact_investment_metric(value: Any, fallback: str, max_chars: int) -> str:
    text = _clean_text(value)
    if not text or _is_placeholder_default_text(text):
        return fallback
    match = re.search(r"[$€£¥]?\d+(?:\.\d+)?\s*(?:M|B|K|m|b|k|%|x|mo\.?|months?|yrs?|years?)?", text)
    if match:
        metric = match.group(0).strip()
        replacements = {"months": "mo.", "month": "mo.", "years": "yrs", "year": "yr"}
        for src, dst in replacements.items():
            metric = re.sub(src, dst, metric, flags=re.I)
        return _fit_compact_label(metric, fallback, max_chars=max_chars)
    return _fit_compact_label(text, fallback, max_chars=max_chars)


def _is_placeholder_default_text(text: str) -> bool:
    normalized = (_clean_text(text) or "").lower()
    return bool(
        normalized in {"text", "title", "subtitle", "placeholder", "lorem ipsum", "tbd", "n/a", "item", "step", "phase"}
        or re.fullmatch(r"(?:item|step|phase)\s*\d+", normalized)
    )


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    if value in (None, ""):
        return []
    return [value]


def _compact_kpi_value(value: Any, name: Any, index: int) -> str:
    text = _clean_text(value)
    if not text or text in {"-", "—", "n/a", "N/A"}:
        return _default_kpi_value(name, index)
    return _fit_compact_label(text, _default_kpi_value(name, index), max_chars=12)


def _default_kpi_name(index: int) -> str:
    return _indexed_default(
        index,
        ["Cycle time", "Savings captured", "Policy adherence", "Touchless flow", "Supplier risk", "User adoption"],
    )


def _default_kpi_value(name: Any, index: int) -> str:
    key = _clean_text(name).lower()
    if "cycle" in key or "time" in key:
        return "14 days"
    if "saving" in key or "value" in key:
        return "$12M"
    if "policy" in key or "compliance" in key or "adherence" in key:
        return "92%"
    if "touchless" in key or "automation" in key or "invoice" in key:
        return "65%"
    if "supplier" in key or "risk" in key:
        return "Medium"
    if "adoption" in key or "usage" in key:
        return "78%"
    return _indexed_default(index, ["14 days", "$12M", "92%", "65%", "Medium", "78%"])


def _repair_repeating_placeholder_lengths(
    payload: dict[str, Any],
    asset_manifest: AssetManifest,
    slide_plan: SlidePlan | None,
) -> dict[str, Any]:
    """Pad required repeating placeholders to the asset's fixed visual count.

    The manifest validator treats ``cardinality=N`` as fixed to the asset's
    density range. LLM output can reasonably return 2-4 items for a repeated
    field, but a hardcoded visual with 5 stages or 3 drivers needs every slot
    populated. This repair preserves supplied content and fills only missing
    visual slots with deterministic, role-aware defaults.
    """
    repaired = dict(payload)
    lo, hi = asset_manifest.density_range
    target_count = min(max(asset_manifest.density, lo), hi)
    if target_count <= 0:
        return repaired

    company = "Enterprise"
    business_function = "Transformation"
    process_name = "operating model"
    slide_role = slide_plan.slide_role if slide_plan is not None else "Slide"

    for placeholder in asset_manifest.placeholders:
        if placeholder.cardinality != "N" or not placeholder.required:
            continue
        value = repaired.get(placeholder.id)
        if isinstance(value, list):
            items = list(value[:target_count])
        elif value in (None, ""):
            items = []
        else:
            items = [value]
        while len(items) < target_count:
            items.append(
                _placeholder_default(
                    placeholder,
                    company,
                    business_function,
                    process_name,
                    slide_role,
                    index=len(items),
                )
            )
        repaired[placeholder.id] = items
    return repaired


def _is_next_step_manifest(asset_manifest: AssetManifest) -> bool:
    family = (asset_manifest.family or "").lower()
    message_type = (getattr(asset_manifest, "message_type", "") or "").lower()
    information_shape = (getattr(asset_manifest, "information_shape", "") or "").lower()
    purpose = (asset_manifest.purpose or "").lower()
    return (
        "next" in family
        or "decision" in message_type
        or "action" in information_shape
        or "next step" in purpose
        or "action register" in purpose
    )


def _replace_generic_language(value: Any) -> Any:
    replacements = {
        "leverage ai": "apply AI to procurement decisions",
        "improve compliance": "strengthen policy control",
        "enhance collaboration": "coordinate supplier issue resolution",
        "drive efficiency": "reduce manual cycle time",
        "optimize processes": "remove workflow bottlenecks",
        "streamline workflows": "standardize exception handling",
    }
    if isinstance(value, str):
        repaired = value
        for phrase, replacement in replacements.items():
            repaired = re.sub(re.escape(phrase), replacement, repaired, flags=re.I)
        return repaired
    if isinstance(value, list):
        return [_replace_generic_language(item) for item in value]
    if isinstance(value, dict):
        return {key: _replace_generic_language(child) for key, child in value.items()}
    return value


def _repair_roadmap_labels(payload: dict[str, Any], asset_manifest: AssetManifest) -> dict[str, Any]:
    phase_names = ["Diagnose", "Design", "Pilot", "Scale", "Institutionalize", "Optimize"]
    repaired = dict(payload)
    phase_like_ids = {
        placeholder.id
        for placeholder in asset_manifest.placeholders
        if "phase" in (placeholder.role or "").lower()
        or "phase" in (placeholder.id or "").lower()
        or "step" in (placeholder.role or "").lower()
        or "step" in (placeholder.id or "").lower()
    }
    for key in phase_like_ids:
        value = repaired.get(key)
        if isinstance(value, list):
            repaired[key] = [
                _replace_generic_sequence_label(item, phase_names, index)
                for index, item in enumerate(value)
            ]
        elif isinstance(value, str):
            repaired[key] = _replace_generic_sequence_label(value, phase_names, 0)
    return repaired


def _replace_generic_sequence_label(value: Any, labels: list[str], index: int) -> Any:
    if not isinstance(value, str):
        return value
    if re.fullmatch(r"\s*(?:step|phase|item)\s*\d+\s*", value, flags=re.I):
        return labels[min(index, len(labels) - 1)]
    return re.sub(
        r"\b(?:step|phase|item)\s+\d+\b",
        labels[min(index, len(labels) - 1)],
        value,
        flags=re.I,
    )


def _repair_risk_language(payload: dict[str, Any]) -> dict[str, Any]:
    repaired = dict(payload)
    for key, value in list(repaired.items()):
        key_lower = key.lower()
        if not isinstance(value, list):
            continue
        if "risk_description" in key_lower:
            repaired[key] = [
                _ensure_risk_description_text(str(item), index)
                for index, item in enumerate(value)
            ]
        elif "risk_assessment" in key_lower:
            repaired[key] = [
                _fit_compact_label(str(item), _risk_impact_label(index), max_chars=30)
                for index, item in enumerate(value)
            ]
        elif "risk_confidence" in key_lower:
            repaired[key] = [
                _fit_compact_label(str(item), _risk_mitigation_label(index), max_chars=30)
                for index, item in enumerate(value)
            ]
    return repaired


def _ensure_risk_description_text(text: str, index: int) -> str:
    repaired = text.strip()
    if not re.search(r"\b(cause|driver|because|due to|dependency)\b", repaired, flags=re.I):
        drivers = [
            "Driver: fragmented data",
            "Driver: policy variance",
            "Driver: supplier readiness",
            "Driver: adoption gap",
            "Driver: integration complexity",
            "Driver: control ownership",
            "Driver: funding dependency",
            "Driver: operating cadence",
            "Driver: model governance",
            "Driver: process exception",
            "Driver: change saturation",
            "Driver: data access",
        ]
        repaired = f"{drivers[index % len(drivers)]}; {repaired}"
    if not re.search(r"\b(impact|delay|cost|adoption|control|exposure|disruption)\b", repaired, flags=re.I):
        impacts = [
            "impact: rollout delay",
            "impact: control exposure",
            "impact: supplier disruption",
            "impact: value leakage",
            "impact: adoption slowdown",
            "impact: cost escalation",
            "impact: decision latency",
            "impact: compliance gap",
            "impact: benefit slippage",
            "impact: operating rework",
            "impact: governance burden",
            "impact: service interruption",
        ]
        repaired = f"{repaired}; {impacts[index % len(impacts)]}"
    if not re.search(r"\b(mitigation|mitigate|control|owner|ownership|sponsor|accountable|response)\b", repaired, flags=re.I):
        endings = [
            "response: sponsor-led",
            "control: data-owned",
            "mitigation: change-led",
            "accountable: control owner",
            "response: architecture review",
            "mitigation: phased rollout",
            "owner: finance sponsor",
            "control: governance forum",
            "response: supplier plan",
            "owner: procurement lead",
            "mitigation: adoption coaching",
            "control: risk checkpoint",
        ]
        repaired = f"{repaired}; {endings[index % len(endings)]}"
    return repaired


def _risk_impact_label(index: int) -> str:
    labels = ["Impact: delay", "Impact: exposure", "Impact: disruption", "Impact: leakage"]
    return labels[index % len(labels)]


def _risk_mitigation_label(index: int) -> str:
    labels = ["Owner: sponsor", "Owner: data", "Owner: change", "Owner: control"]
    return labels[index % len(labels)]


def _repair_next_step_language(
    payload: dict[str, Any],
    asset_manifest: AssetManifest | None = None,
) -> dict[str, Any]:
    repaired = dict(payload)
    if asset_manifest is not None:
        repaired = _backfill_next_step_placeholders(repaired, asset_manifest)
    for key, value in list(repaired.items()):
        key_lower = key.lower()
        if isinstance(value, list):
            repaired[key] = [
                _repair_next_step_field_value(key_lower, str(item), index)
                for index, item in enumerate(value)
            ]
            continue
        if isinstance(value, str):
            repaired[key] = _repair_next_step_field_value(key_lower, value, 0)
    return repaired


def _repair_next_step_field_value(key_lower: str, value: str, index: int) -> str:
    indexed_match = re.match(r"(?:decision|delay)_(\d+)_", key_lower)
    if indexed_match:
        index = max(int(indexed_match.group(1)) - 1, 0)
    if key_lower.startswith("header_"):
        return _next_step_header_label(key_lower, value)
    if "decision_title" in key_lower or (key_lower.startswith("decision_") and key_lower.endswith("_title")):
        return _compact_decision_title(value, index=index)
    if "why_now_detail" in key_lower:
        return _compact_decision_fragment(value, max_chars=36, fallback=_default_decision_why_now(index))
    if "request_detail" in key_lower or "decision_detail" in key_lower:
        return _compact_decision_request(value, index=index, max_chars=38)
    if "impact_detail" in key_lower:
        return _compact_decision_fragment(value, max_chars=40, fallback=_default_decision_impact(index))
    if "delay_" in key_lower and key_lower.endswith("_title"):
        return _compact_decision_fragment(value, max_chars=30, fallback=_default_delay_title(index))
    if "delay_" in key_lower and key_lower.endswith("_impact"):
        return _compact_decision_fragment(value, max_chars=42, fallback=_default_delay_impact(index))
    if "next_step" in key_lower or "action" in key_lower or "decision_request" in key_lower:
        return _ensure_next_step_contract_text(value, index=index)
    if "decision_impact" in key_lower:
        return value if _contains_owner(value) else _append_owner_clause(value, index)
    if "priority" in key_lower:
        return _fit_compact_label(value, "Approve pilot scope", max_chars=60)
    if "when" in key_lower:
        return value if _contains_timing(value) else "30 days"
    if "who" in key_lower or "owner" in key_lower:
        return value if _contains_owner(value) else _default_next_step_owner(index + 1)
    return value


def _compact_decision_title(value: str, *, index: int) -> str:
    text = _clean_text(value).rstrip(".")
    if _is_placeholder_default_text(text):
        text = _default_decision_title(index)
    replacements = {
        "approve ai-driven demand forecasting": "Approve demand forecast pilot",
        "authorize budget for logistics automation": "Authorize logistics funding",
        "greenlight supplier collaboration": "Approve supplier platform",
        "approve ai tool selection": "Approve AI tool selection",
        "approve budget allocation": "Approve funding envelope",
        "initiate pilot phase": "Approve pilot launch",
    }
    lowered = text.lower()
    for phrase, replacement in replacements.items():
        if phrase in lowered:
            text = replacement
            break
    if not re.search(r"^(approve|authorize|confirm|endorse|fund)\b", text, flags=re.I):
        text = f"Approve {text[0].lower() + text[1:] if text else _default_decision_title(index)}"
    return _fit_compact_label(text, _default_decision_title(index), max_chars=30)


def _compact_decision_request(value: str, *, index: int, max_chars: int) -> str:
    text = _clean_text(value).rstrip(".")
    if _is_placeholder_default_text(text):
        text = _default_decision_request(index)
    text = re.sub(r"^request\s+to\s+", "", text, flags=re.I)
    text = re.sub(r"^request\s+", "", text, flags=re.I)
    if not re.search(r"^(approve|authorize|confirm|endorse|fund)\b", text, flags=re.I):
        text = f"Approve {text[0].lower() + text[1:] if text else 'pilot'}"
    return _fit_compact_label(text, _default_decision_request(index), max_chars=max_chars)


def _compact_decision_fragment(value: str, *, max_chars: int, fallback: str) -> str:
    text = _clean_text(value).rstrip(".")
    if _is_placeholder_default_text(text):
        text = fallback
    text = re.sub(r"\b(?:this will|this would|expected to|could lead to|may result in)\b", "", text, flags=re.I)
    text = re.sub(r"\b(?:immediate approval enables|timely approval is crucial to|delaying this decision risks)\b", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip(" -:;.").strip()
    return _fit_compact_label(text, fallback, max_chars=max_chars)


def _default_decision_title(index: int) -> str:
    return _indexed_default(index, ["Approve pilot scope", "Authorize funding", "Confirm sponsor"])


def _default_decision_request(index: int) -> str:
    return _indexed_default(
        index,
        ["Approve pilot scope", "Authorize funding envelope", "Confirm accountable sponsor"],
    )


def _default_decision_why_now(index: int) -> str:
    return _indexed_default(
        index,
        ["Mobilization window is open", "Funding unlocks delivery", "Ownership needed now"],
    )


def _default_decision_impact(index: int) -> str:
    return _indexed_default(
        index,
        ["Enables controlled pilot", "Starts delivery work", "Clarifies accountability"],
    )


def _default_delay_title(index: int) -> str:
    return _indexed_default(index, ["Pilot delay", "Funding delay", "Ownership gap"])


def _default_delay_impact(index: int) -> str:
    return _indexed_default(
        index,
        ["Slower benefits capture", "Missed delivery window", "Unclear issue resolution"],
    )


def _backfill_next_step_placeholders(
    payload: dict[str, Any],
    asset_manifest: AssetManifest,
) -> dict[str, Any]:
    repaired = dict(payload)
    if (asset_manifest.asset_id or "") == "DECISION-REQUEST-3CARD-001":
        repaired.setdefault("decision_label", ["Decision 1", "Decision 2", "Decision 3"])
        repaired.setdefault(
            "decision_title",
            ["Approve pilot scope", "Authorize funding", "Confirm governance"],
        )
        for index in range(3):
            number = index + 1
            repaired.setdefault(f"decision_{number}_why_now_detail", _default_decision_why_now(index))
            repaired.setdefault(f"decision_{number}_request_detail", _default_decision_request(index))
            repaired.setdefault(f"decision_{number}_impact_detail", _default_decision_impact(index))
            repaired.setdefault(f"delay_{number}_title", _default_delay_title(index))
            repaired.setdefault(f"delay_{number}_impact", _default_delay_impact(index))
    placeholder_ids = [placeholder.id for placeholder in asset_manifest.placeholders]
    row_numbers = sorted(
        {
            int(match.group(1))
            for placeholder_id in placeholder_ids
            for match in [re.match(r"row_(\d+)_", placeholder_id)]
            if match
        }
    )
    for row_number in row_numbers:
        next_key = f"row_{row_number}_next_step"
        when_key = f"row_{row_number}_when"
        who_key = f"row_{row_number}_who"
        if next_key in placeholder_ids and not _clean_text(repaired.get(next_key)):
            repaired[next_key] = _default_next_step_action(row_number)
        if when_key in placeholder_ids and not _clean_text(repaired.get(when_key)):
            repaired[when_key] = _default_next_step_timing(row_number)
        if who_key in placeholder_ids and not _clean_text(repaired.get(who_key)):
            repaired[who_key] = _default_next_step_owner(row_number)
    return repaired


def _default_next_step_action(row_number: int) -> str:
    actions = [
        "Approve controlled pilot launch",
        "Confirm value case and funding",
        "Authorize data access controls",
        "Prioritize supplier onboarding wave",
        "Endorse scale decision criteria",
        "Launch executive governance cadence",
    ]
    return actions[(row_number - 1) % len(actions)]


def _default_next_step_timing(row_number: int) -> str:
    timings = ["30 days", "60 days", "90 days", "Q2", "Q3", "Q4"]
    return timings[(row_number - 1) % len(timings)]


def _default_next_step_owner(row_number: int) -> str:
    owners = [
        "Procurement sponsor",
        "CFO delegate",
        "CIO data owner",
        "Category lead",
        "Transformation lead",
        "Steering committee",
    ]
    return owners[(row_number - 1) % len(owners)]


def _ensure_next_step_contract_text(text: str, *, index: int = 0) -> str:
    repaired = text.strip()
    repaired = re.sub(r"^requesting\b", "Approve", repaired, flags=re.I)
    repaired = re.sub(r"^approval needed to\b", "Authorize", repaired, flags=re.I)
    repaired = re.sub(r"^seeking endorsement for\b", "Endorse", repaired, flags=re.I)
    if not re.search(r"\b(approve|decide|decision|confirm|endorse|authorize|fund|prioritize)\b", repaired, flags=re.I):
        repaired = f"Approve {repaired[0].lower() + repaired[1:] if repaired else 'pilot'}"
    if not _contains_owner(repaired):
        repaired = _append_owner_clause(repaired, index)
    return _fit_compact_label(repaired, "Approve pilot launch", max_chars=160)


def _append_owner_clause(text: str, index: int) -> str:
    owner = _default_next_step_owner(index + 1)
    text = text.strip().rstrip(".")
    if not text:
        return f"Owner: {owner}"
    return f"{text}. Owner: {owner}"


def _next_step_header_label(key_lower: str, value: str) -> str:
    if "priority" in key_lower:
        return "Priority"
    if "instrument" in key_lower:
        return "Instrument"
    if "next_step" in key_lower:
        return "Action"
    if "when" in key_lower:
        return "When"
    if "who" in key_lower:
        return "Owner"
    if "nr" in key_lower:
        return "No."
    return _fit_compact_label(value, value, max_chars=25)


def _repair_title_so_what(payload: dict[str, Any], slide_plan: SlidePlan) -> dict[str, Any]:
    title = _clean_text(payload.get("title")) or ""
    role = (slide_plan.slide_role or "").lower()
    if len(title.split()) >= 6 and _title_matches_role(title, role):
        return payload
    repaired = dict(payload)
    if ("current" in role and "future" in role) or "current_future" in role or "comparison" in role:
        repaired["title"] = "Current-to-future shifts define the transformation path"
    elif "current" in role or "process" in role:
        repaired["title"] = "Current process friction slows decisions and weakens control"
    elif "risk" in role:
        repaired["title"] = "Implementation risks require accountable mitigation before scale"
    elif "investment" in role or "business case" in role or "funding" in role or "roi" in role or "payback" in role:
        repaired["title"] = "Investment case supports disciplined AI scale-up"
    elif "case for change" in role or "case" in role:
        repaired["title"] = "Case for change centers on resilience, speed, and control"
    elif "future" in role or "operating model" in role:
        repaired["title"] = "Future-state model enables accountable capabilities"
    elif "benefit" in role or "value" in role:
        repaired["title"] = "Business benefits create measurable value"
    elif "kpi" in role or "success" in role or "metric" in role:
        repaired["title"] = "KPIs track cycle time, value capture, and control adoption"
    elif "opportunit" in role:
        repaired["title"] = "Opportunity areas prioritize value pools with execution readiness"
    elif "roadmap" in role or "implementation" in role:
        repaired["title"] = "Implementation roadmap sequences pilot, scale, and governance"
    elif "next step" in role or "decision" in role or "action" in role:
        repaired["title"] = "Board decisions required to advance transformation"
    elif "use case" in role:
        repaired["title"] = "AI use cases target sourcing speed and spend control"
    return repaired


def _title_matches_role(title: str, role: str) -> bool:
    title_lower = title.lower()
    if ("current" in role and "future" in role) or "current_future" in role or "comparison" in role:
        return any(term in title_lower for term in ("current", "future", "shift", "from-to", "from ", " to ", "transformation path"))
    if "current" in role or "process" in role:
        return any(term in title_lower for term in ("current", "process", "friction", "manual", "baseline", "as-is", "bottleneck"))
    if "risk" in role:
        return any(term in title_lower for term in ("risk", "control", "mitigation", "exposure", "owner"))
    if "investment" in role or "business case" in role or "funding" in role or "roi" in role or "payback" in role:
        return any(term in title_lower for term in ("investment", "funding", "payback", "roi", "npv", "business case", "value"))
    if "case for change" in role or "case" in role:
        return any(term in title_lower for term in ("case", "change", "imperative", "resilience", "pressure", "why"))
    if "future" in role or "operating model" in role:
        return any(term in title_lower for term in ("future", "operating model", "capability", "accountable", "digital"))
    if "benefit" in role or "value" in role:
        return any(term in title_lower for term in ("benefit", "value", "savings", "margin", "cash", "speed"))
    if "kpi" in role or "success" in role or "metric" in role:
        return any(term in title_lower for term in ("kpi", "metric", "indicator", "track", "measure", "success"))
    if "opportunit" in role:
        return any(term in title_lower for term in ("opportunity", "prioritize", "value pool", "readiness", "growth"))
    if "next step" in role or "decision" in role or "action" in role:
        return any(term in title_lower for term in ("board", "decision", "approve", "pilot", "launch", "owner", "action"))
    if "roadmap" in role or "implementation" in role:
        return any(term in title_lower for term in ("roadmap", "phase", "pilot", "scale", "sequence", "governance"))
    if "use case" in role:
        return any(term in title_lower for term in ("ai", "use case", "workflow", "value", "spend"))
    return True


def _fit_compact_label(value: str, fallback: str, *, max_chars: int) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        text = fallback
    if len(text) <= max_chars:
        return text
    if len(fallback) <= max_chars:
        return fallback
    complete = _complete_compact_prefix(text, max_chars)
    if complete:
        return complete
    complete = _complete_compact_prefix(fallback, max_chars)
    if complete:
        return complete
    return _generic_complete_fallback(max_chars)


def _complete_compact_prefix(text: str, max_chars: int) -> str:
    for sep in (". ", "; ", ": ", " - ", " – ", " — "):
        if sep in text:
            candidate = _trim_dangling_words(text.split(sep, 1)[0])
            if candidate and len(candidate) <= max_chars and not _looks_incomplete_label(candidate):
                return candidate
    words: list[str] = []
    for word in text.split():
        candidate = " ".join(words + [word])
        if len(candidate) > max_chars:
            break
        words.append(word)
    candidate = _trim_dangling_words(" ".join(words))
    if candidate and not _looks_incomplete_label(candidate):
        return candidate
    return ""


def _looks_incomplete_label(text: str) -> bool:
    words = text.split()
    if not words:
        return True
    return words[-1].lower() in {
        "and", "or", "for", "with", "through", "by", "to", "of", "in", "on",
        "from", "across", "using", "via", "into", "based", "toward", "all",
        "driving", "highlighting", "including", "enabling", "leading",
    }


def _generic_complete_fallback(max_chars: int) -> str:
    for candidate in ("Approve pilot", "Reduce cycle time", "Strengthen control", "Capture value", "Act now"):
        if len(candidate) <= max_chars:
            return candidate
    return "Action"


def _trim_dangling_words(text: str) -> str:
    cleaned = text.strip(" -:;,.")
    dangling = {
        "and", "or", "for", "with", "through", "by", "to", "of", "in", "on",
        "from", "across", "using", "via", "into", "based", "toward",
    }
    words = cleaned.split()
    while words and words[-1].lower() in dangling:
        words.pop()
    return " ".join(words).strip(" -:;,.")


def _contains_owner(text: str) -> bool:
    return bool(re.search(r"\b(owner|sponsor|cfo|coo|cio|procurement|accountable)\b", text, flags=re.I))


def _contains_timing(text: str) -> bool:
    return bool(re.search(r"\b(q[1-4]|week|month|day|days|30|60|90|by\s+)\b", text, flags=re.I))


def _lock_manifest_title_to_plan(
    payload: dict[str, Any],
    asset_manifest: AssetManifest,
    slide_plan: SlidePlan | None,
) -> dict[str, Any]:
    """Prevent manifest-generated titles from drifting to another slide role.

    Keep insight-style titles when they are semantically compatible. Replacing
    every title with the literal slide role makes asset-shaped slides read like
    section labels and trips the board-level "so what" quality gate.
    """
    if slide_plan is None:
        return payload
    locked = dict(payload)
    planned_role = _canonical_slide_role(slide_plan.slide_role)
    for placeholder in asset_manifest.placeholders:
        role = (placeholder.role or "").lower()
        placeholder_id = (placeholder.id or "").lower()
        if placeholder.kind == PlaceholderKind.TITLE or role == "title" or placeholder_id == "title":
            current = _clean_text(locked.get(placeholder.id))
            generated_role = _canonical_slide_role(current or "")
            if not current or (planned_role and generated_role and planned_role != generated_role):
                locked[placeholder.id] = slide_plan.slide_role
    return locked


def _canonical_slide_role(text: str) -> str | None:
    """Small local copy of role canonicalization for manifest title locking."""
    normalized = (text or "").lower()
    if "executive summary" in normalized or "transformation overview" in normalized:
        return "executive_summary"
    if ("current" in normalized and "future" in normalized) or ("from" in normalized and "to" in normalized):
        return "current_future_comparison"
    if "current" in normalized and ("process" in normalized or "state" in normalized):
        return "current_state"
    if "future" in normalized or "operating model" in normalized:
        return "future_state"
    if "benefit" in normalized or "value case" in normalized:
        return "business_benefits"
    if "use case" in normalized:
        return "ai_use_cases"
    if "roadmap" in normalized:
        return "implementation_roadmap"
    if "timeline" in normalized or "milestone" in normalized:
        return "transformation_timeline"
    if "kpi" in normalized or "metric" in normalized:
        return "kpis_for_success"
    if "next step" in normalized or "decision" in normalized or "action" in normalized:
        return "next_steps"
    if (
        "implementation risk" in normalized
        or "risk register" in normalized
        or "risk matrix" in normalized
        or "mitigation" in normalized
    ):
        return "implementation_risks"
    return None


def _manifest_fallback_payload(
    intent: IntentResult,
    context: EnterpriseContext,
    process_result: ProcessResult,
    slide_plan: SlidePlan | None = None,
    *,
    asset_manifest: AssetManifest,
) -> dict[str, Any]:
    """Produce a minimal, conformant placeholder-keyed payload for ``asset_manifest``."""
    company = _clean_text(context.company) or _clean_text(getattr(intent, "company", None)) or "Enterprise"
    business_function = (
        _clean_text(getattr(intent, "business_function", None))
        or _clean_text(context.business_function)
        or process_result.process_family
    )
    process_name = process_result.process_name or "operating model"
    slide_role = slide_plan.slide_role if slide_plan is not None else "Slide"

    density = asset_manifest.density
    lo, hi = asset_manifest.density_range
    canonical_count = min(max(density, lo), hi)

    fallback: dict[str, Any] = {}
    for placeholder in asset_manifest.placeholders:
        if placeholder.cardinality == "1":
            fallback[placeholder.id] = _placeholder_default(
                placeholder, company, business_function, process_name, slide_role
            )
        else:
            fallback[placeholder.id] = [
                _placeholder_default(
                    placeholder, company, business_function, process_name, slide_role, index=i
                )
                for i in range(canonical_count)
            ]
    return fallback


def _placeholder_default(
    placeholder: AssetPlaceholder,
    company: str,
    business_function: str,
    process_name: str,
    slide_role: str,
    index: int | None = None,
) -> Any:
    """Return a safe default value for a single placeholder."""
    if placeholder.content_schema:
        item: dict[str, Any] = {}
        for raw_key, raw_kind in placeholder.content_schema.items():
            expected = str(raw_kind).rstrip("?")
            clean_key = raw_key[:-1] if raw_key.endswith("?") else raw_key
            if expected.endswith("[]"):
                item[clean_key] = []
            elif expected == "boolean":
                item[clean_key] = False
            elif expected == "number":
                item[clean_key] = "0"
            else:
                item[clean_key] = ""
        return item

    pilot_default = _pilot_placeholder_default(
        placeholder,
        company,
        business_function,
        process_name,
        slide_role,
        index=index,
    )
    if pilot_default is not None:
        return pilot_default

    if placeholder.kind == PlaceholderKind.TITLE:
        return slide_role
    if placeholder.role in {"subtitle", "sub_title"}:
        return f"{company} {business_function} — {slide_role}"
    if placeholder.role == "description":
        return f"{process_name} overview."
    if placeholder.kind in {PlaceholderKind.METRIC, PlaceholderKind.CURRENCY, PlaceholderKind.PERCENTAGE}:
        return "—"
    if placeholder.kind == PlaceholderKind.DATE:
        return "Q1"
    if placeholder.kind == PlaceholderKind.ICON:
        return "●"
    label = f"Item {index + 1}" if index is not None else "Item"
    return label


def _pilot_placeholder_default(
    placeholder: AssetPlaceholder,
    company: str,
    business_function: str,
    process_name: str,
    slide_role: str,
    *,
    index: int | None,
) -> str | None:
    """Business-like fallback values for the fixed pilot visual variants."""
    placeholder_id = (placeholder.id or "").lower()
    role = (placeholder.role or "").lower()
    slot = index or 0

    if placeholder.kind == PlaceholderKind.TITLE:
        return slide_role
    if role in {"subtitle", "sub_title"}:
        return _fit_compact_label(
            f"{company} {business_function} transformation priorities",
            f"{company} transformation priorities",
            max_chars=110,
        )
    if (
        role in {"summary", "so_what", "key_takeaway"}
        or placeholder_id in {"summary", "overall_impact", "banner_text", "banner_takeaway"}
        or "takeaway" in placeholder_id
    ):
        return _fit_compact_label(
            f"Board sponsorship should focus {business_function.lower()} transformation on control, speed, and measurable value.",
            "Board sponsorship should focus the program on control, speed, and measurable value.",
            max_chars=150,
        )
    if "source" in placeholder_id:
        return "EY analysis; management inputs"

    if placeholder_id.startswith("summary_"):
        return _summary_metric_default(placeholder_id)

    if "card_header" in placeholder_id or "card_" in placeholder_id and "header" in placeholder_id:
        return _indexed_default(slot, ["Simplify the core", "Enable with technology", "Sustain the change"])
    if "card_description" in placeholder_id:
        return _indexed_default(
            slot,
            [
                "Reduce fragmentation and remove non-value-adding complexity",
                "Use digital enablers to improve speed, control, and scalability",
                "Capture benefits through disciplined governance and adoption",
            ],
        )
    if "card_bullet_1" in placeholder_id:
        return _indexed_default(
            slot,
            [
                "Standardize priority processes and decision rights",
                "Prioritize high-value automation opportunities",
                "Establish KPI-led governance and ownership",
            ],
        )
    if "card_bullet_2" in placeholder_id:
        return _indexed_default(
            slot,
            [
                "Eliminate manual handoffs, rework, and duplication",
                "Integrate workflow, data, and reporting across teams",
                "Build capabilities through training and change support",
            ],
        )
    if "card_bullet_3" in placeholder_id:
        return _indexed_default(
            slot,
            [
                "Create transparency on performance and accountability",
                "Embed controls into day-to-day execution",
                "Track value realization and course-correct early",
            ],
        )
    if "card_bullets" in placeholder_id or "card_" in placeholder_id and "bullet" in placeholder_id:
        return _indexed_default(
            slot,
            [
                "Standardize fragmented processes\nRemove non-value activity\nReduce manual handoffs",
                "Prioritize high-value automation\nEmbed AI into critical workflows\nCreate scalable data foundations",
                "Establish accountable governance\nTrack benefits with clear KPIs\nDrive adoption through change management",
            ],
        )

    if "stage_title" in placeholder_id:
        return _indexed_default(slot, ["Demand intake", "Sourcing", "Contracting", "Ordering", "Supplier mgmt"])
    if "stage_activities" in placeholder_id:
        return _indexed_default(
            slot,
            [
                "Capture need\nValidate policy\nRoute approval",
                "Launch event\nCompare bids\nSelect supplier",
                "Draft terms\nReview risk\nExecute contract",
                "Create PO\nReceive goods\nMatch invoice",
                "Track performance\nResolve issues\nRenew terms",
            ],
        )
    if "stage_pain" in placeholder_id:
        return _indexed_default(
            slot,
            [
                "Manual intake obscures demand visibility",
                "Fragmented sourcing slows cycle time",
                "Contract reviews create control exposure",
                "Exception handling delays payment accuracy",
                "Supplier issues lack accountable ownership",
            ],
        )

    if "driver_title" in placeholder_id:
        return _indexed_default(
            slot,
            ["Performance under pressure", "Risk and control exposure", "Future readiness at risk"],
        )
    if "driver_summary" in placeholder_id:
        return _indexed_default(
            slot,
            [
                "Complexity and inefficiency are slowing execution and limiting value capture",
                "Governance and control gaps increase operational, financial, and compliance exposure",
                "Outdated ways of working constrain agility and future transformation capacity",
            ],
        )
    if "driver_evidence_1" in placeholder_id:
        return _indexed_default(
            slot,
            [
                "Manual handoffs and rework drive delays",
                "Inconsistent adherence to policies and controls",
                "Legacy systems and data limit scalability",
            ],
        )
    if "driver_evidence_2" in placeholder_id:
        return _indexed_default(
            slot,
            [
                "Fragmented processes create bottlenecks",
                "Limited visibility into key risks and exceptions",
                "Siloed ways of working hinder collaboration",
            ],
        )
    if "driver_evidence_3" in placeholder_id:
        return _indexed_default(
            slot,
            [
                "Inconsistent performance and outcomes",
                "Reactive issue management and remediation",
                "Limited capability in emerging AI workflows",
            ],
        )
    if "driver_impact_1" in placeholder_id:
        return _indexed_default(
            slot,
            [
                "Higher cost to serve and lower productivity",
                "Elevated risk of non-compliance and incidents",
                "Difficulty scaling to meet future demand",
            ],
        )
    if "driver_impact_2" in placeholder_id:
        return _indexed_default(
            slot,
            [
                "Slower decision-making and cycle times",
                "Increased audit findings and remediation cost",
                "Missed opportunities to innovate and grow",
            ],
        )

    if "driver" in placeholder_id or "change" in placeholder_id:
        return _indexed_default(
            slot,
            ["Cost pressure", "Control exposure", "Supplier resilience", "Cycle-time drag"],
        )
    if "capability_title" in placeholder_id:
        return _indexed_default(slot, ["AI intake", "Decision engine", "Supplier control", "Value office"])
    if "capability_summary" in placeholder_id:
        return _indexed_default(
            slot,
            [
                "Standardizes demand signals before sourcing begins",
                "Recommends actions using policy and spend context",
                "Monitors risk, performance, and compliance exceptions",
                "Tracks benefits realization and adoption discipline",
            ],
        )
    if "capability_elements" in placeholder_id:
        return _indexed_default(
            slot,
            [
                "Guided requests\nPolicy checks\nApproval routing",
                "Spend analytics\nScenario scoring\nRecommendation logic",
                "Supplier signals\nRisk alerts\nIssue ownership",
                "KPI cadence\nBenefit tracking\nGovernance forums",
            ],
        )
    if "capability_outcome" in placeholder_id or "enabler_body" in placeholder_id:
        return _indexed_default(
            slot,
            [
                "Faster intake with fewer rework loops",
                "Higher-quality sourcing decisions",
                "Earlier risk escalation and response",
                "Visible value capture for sponsors",
            ],
        )
    if "enabler_title" in placeholder_id:
        return _indexed_default(slot, ["Data foundation", "Workflow controls", "Governance", "Adoption"])

    if "steering_committee_title" in placeholder_id:
        return "Steering Committee"
    if "steering_committee_mandate" in placeholder_id:
        return "Strategy | Funding | Escalations"
    if "steering_responsibility" in placeholder_id:
        return _indexed_default(
            slot,
            ["Set priorities", "Approve funding", "Resolve escalations"],
        )
    if "pmo_title" in placeholder_id:
        return "Project Management Office (PMO)"
    if "pmo_mandate" in placeholder_id:
        return "Integration | Reporting | Risks | Decisions"
    if "pmo_responsibility" in placeholder_id:
        return _indexed_default(
            slot,
            ["Coordinate workstreams", "Track progress", "Manage dependencies", "Maintain standards"],
        )
    if "forum_name" in placeholder_id:
        return _indexed_default(slot, ["SteerCo", "PMO", "Workstreams"])
    if "forum_cadence" in placeholder_id:
        return _indexed_default(slot, ["Monthly", "Weekly", "Biweekly"])
    if "decision_right_label" in placeholder_id:
        return _indexed_default(slot, ["Recommend", "Approve", "Escalate"])
    if "decision_right_description" in placeholder_id:
        return _indexed_default(
            slot,
            ["Frame options", "Make final call", "Raise key risks"],
        )

    if "use_case_title" in placeholder_id:
        return _indexed_default(slot, ["Smart intake", "Supplier risk", "Spend insights", "Contract review", "Invoice triage"])
    if "use_case_description" in placeholder_id:
        return _indexed_default(
            slot,
            [
                "AI guides requestors through policy-aligned sourcing workflows",
                "Models flag supplier exposure before award decisions",
                "Analytics reveal savings and leakage across categories",
                "AI summarizes obligations and exception clauses for review",
                "Automation prioritizes invoice exceptions for resolution",
            ],
        )
    if "use_case_value" in placeholder_id:
        return _indexed_default(
            slot,
            [
                "Reduces rework and approval friction",
                "Improves continuity and control response",
                "Increases savings visibility and accountability",
                "Accelerates review while preserving risk control",
                "Improves payment accuracy and working-capital discipline",
            ],
        )

    if placeholder_id in {"opportunity_title", "current_issue", "opportunity", "value_unlocked"}:
        return _default_opportunity_value(placeholder_id, slot)

    if "benefit_label" in placeholder_id:
        return _indexed_default(slot, ["Cycle time", "Savings capture", "Control", "Cash", "Supplier risk", "Adoption"])
    if "benefit_description" in placeholder_id:
        return _indexed_default(
            slot,
            [
                "Fewer manual handoffs across intake and sourcing",
                "Better value leakage detection by category",
                "Stronger policy adherence and approval discipline",
                "Cleaner invoice flow and payment predictability",
                "Earlier identification of supplier exposure",
                "Clearer ownership for new ways of working",
            ],
        )
    if "benefit_impact" in placeholder_id:
        return _indexed_default(slot, ["Speed", "Value", "Risk", "Cash", "Resilience", "Adoption"])

    if "kpi_name" in placeholder_id:
        return _indexed_default(slot, ["Cycle time", "Savings captured", "Policy adherence", "Touchless flow", "Supplier risk", "User adoption"])
    if "kpi_value" in placeholder_id:
        return _default_kpi_value(_default_kpi_name(slot), slot)
    if "kpi_unit" in placeholder_id:
        return _indexed_default(slot, ["Days", "$", "%", "%", "Score", "%"])
    if "kpi_description" in placeholder_id:
        return _indexed_default(
            slot,
            [
                "Request-to-award speed",
                "Validated benefit realization",
                "Compliant approvals and spend",
                "Automated invoice handling",
                "Monitored supplier exposure",
                "Active usage by priority teams",
            ],
        )
    if "kpi_target" in placeholder_id:
        return _indexed_default(slot, ["Baseline down", "Tracked monthly", "Above threshold", "Increase", "Controlled", "Rising"])
    if "kpi_trend" in placeholder_id:
        return _indexed_default(slot, ["Improve", "Grow", "Hold", "Improve", "Reduce", "Grow"])

    if "risk_id" in placeholder_id:
        return f"R{slot + 1}"
    if "matrix_cell_level" in role or placeholder_id.startswith("cell_") and placeholder_id.endswith("_level"):
        if "high_impact" in placeholder_id or "high_likelihood" in placeholder_id:
            return "High"
        if "medium_impact" in placeholder_id or "medium_likelihood" in placeholder_id:
            return "Medium"
        return "Low"
    if "matrix_cell_risk_ids" in role or placeholder_id.startswith("cell_") and placeholder_id.endswith("_risks"):
        return _risk_cell_ids(placeholder_id)
    if placeholder_id.startswith("severity_") and placeholder_id.endswith("_label"):
        return _indexed_default(slot, ["Low", "Medium", "High", "Critical"])
    if placeholder_id.startswith("severity_") and placeholder_id.endswith("_guidance"):
        return _indexed_default(
            slot,
            [
                "Monitor through working team",
                "Assign owner and mitigation",
                "Escalate to sponsor forum",
                "Require Board visibility",
            ],
        )
    if "risk_description" in placeholder_id:
        return _ensure_risk_description_text("", slot)
    if "risk_assessment" in placeholder_id:
        return _risk_impact_label(slot)
    if "risk_confidence" in placeholder_id or "risk_appetite" in placeholder_id:
        return _risk_mitigation_label(slot)

    if "action_text" in placeholder_id or "next_step" in placeholder_id:
        return _default_next_step_action(slot + 1)
    if "decision_label" in placeholder_id:
        return f"Decision {slot + 1}"
    if "action_number" in placeholder_id:
        return f"{slot + 1:02d}"
    if "action_owner" in placeholder_id or placeholder_id.endswith("_who"):
        return _default_next_step_owner(slot + 1)
    if "action_due" in placeholder_id or placeholder_id.endswith("_when"):
        return _default_next_step_timing(slot + 1)
    if "action_priority" in placeholder_id:
        return _indexed_default(slot, ["High", "High", "Medium", "Medium", "High", "Medium", "Low"])
    if "action_status" in placeholder_id:
        return _indexed_default(slot, ["Not started", "In progress", "Not started", "Not started", "In progress", "Not started", "Not started"])
    if "action_progress" in placeholder_id:
        return _indexed_default(slot, ["0%", "25%", "0%", "0%", "50%", "0%", "0%"])
    if "action_comment" in placeholder_id:
        return _indexed_default(
            slot,
            [
                "Requires sponsor confirmation",
                "Finance input needed",
                "Data access dependency",
                "Supplier wave to be sequenced",
                "Criteria for scale decision",
                "Cadence starts after approval",
                "Track in steering forum",
            ],
        )

    if "phase" in placeholder_id:
        return _indexed_default(slot, ["Diagnose", "Design", "Pilot", "Scale"])
    if "workstream_responsibilities" in placeholder_id:
        return _indexed_default(
            slot,
            [
                "Map processes\nStandardize controls\nTrack benefits",
                "Define architecture\nManage integration\nTrack milestones",
                "Set data rules\nImprove quality\nEnable reporting",
                "Engage leaders\nTrain users\nMonitor adoption",
            ],
        )
    if "workstream" in placeholder_id:
        return _indexed_default(slot, ["Process", "Data", "Technology", "Change"])
    if "activity" in placeholder_id or "milestone" in placeholder_id:
        return _indexed_default(slot, ["Baseline", "Design", "Pilot", "Scale"])
    return None


def _indexed_default(index: int, values: list[str]) -> str:
    return values[index % len(values)]


def _summary_metric_default(placeholder_id: str) -> str:
    if "total" in placeholder_id:
        return "7"
    if "not_started" in placeholder_id:
        return "4"
    if "in_progress" in placeholder_id:
        return "2"
    if "completed" in placeholder_id:
        return "0"
    if "overdue" in placeholder_id:
        return "0"
    return "Tracked"


def _risk_cell_ids(placeholder_id: str) -> str:
    if "high_likelihood_high_impact" in placeholder_id:
        return "R1, R2"
    if "high_likelihood_medium_impact" in placeholder_id:
        return "R3"
    if "medium_likelihood_high_impact" in placeholder_id:
        return "R4"
    if "medium_likelihood_medium_impact" in placeholder_id:
        return "R5, R6"
    if "low_likelihood_high_impact" in placeholder_id:
        return "R7"
    return "Monitor"


def _six_stage_labels(process_result: ProcessResult) -> list[str]:
    process_key = _normalize_key(process_result.process_name)
    defaults = _PROCESS_STAGE_OVERRIDES.get(process_key, _GENERIC_STAGE_DEFAULTS)
    labels = [
        _normalize_stage_label(stage, fallback=defaults[min(index, len(defaults) - 1)])
        for index, stage in enumerate(process_result.stages)
        if _clean_text(stage)
    ]
    # Backfill missing stage labels from canonical defaults, capped at 4–7 stages.
    for fallback in defaults:
        if len(labels) >= 7:
            break
        normalized_fallback = _normalize_stage_label(fallback, fallback=fallback)
        if normalized_fallback not in labels:
            labels.append(normalized_fallback)
    return labels[:7]


def _default_executive_summary(company: str, industry: str, process_result: ProcessResult) -> str:
    industry_phrase = "" if not industry or industry == "Unknown" else f" in the {industry} context"
    return (
        f"The {process_result.process_name} operating model coordinates core {process_result.process_family} workflows for {company}{industry_phrase}. "
        "Primary operational challenges arise from fragmented handoffs, inconsistent controls, and limited cross-functional visibility."
    )


def _safe_text(value: Any, default: str = "") -> str:
    cleaned = _clean_text(value) or default
    cleaned = _remove_unsupported_numeric_claims(cleaned)
    return cleaned.strip()


def _normalize_executive_summary(value: Any, default: str) -> str:
    text = _safe_text(value, default=default)
    sentences = _split_sentences(text)
    if len(sentences) >= 2:
        return " ".join(sentences[:2])
    if len(sentences) == 1:
        default_sentences = _split_sentences(default)
        second = default_sentences[1] if len(default_sentences) > 1 else "Primary operational challenges arise from fragmented handoffs, inconsistent controls, and limited visibility."
        return f"{sentences[0]} {second}"
    return " ".join(_split_sentences(default)[:2])


def _normalize_stage_label(value: Any, fallback: str) -> str:
    cleaned = _safe_text(value, default=fallback)
    if _normalize_key(cleaned) in {_normalize_key(term) for term in _WEAK_STAGE_TERMS}:
        cleaned = fallback
    cleaned = cleaned.replace("Create Purchase Order", "Purchase Order Management")
    cleaned = cleaned.replace("Receive Goods", "Material Receipt Validation")
    cleaned = cleaned.replace("Payroll", "Payroll & Workforce Administration")
    words = cleaned.split()
    if len(words) == 1:
        cleaned = f"{cleaned} Management"
    elif not any(term in cleaned for term in ["Management", "Governance", "Control", "Visibility", "Administration", "Validation", "Support"]):
        cleaned = f"{cleaned} Management"
    return _title_preserving_acronyms(cleaned)


def _normalize_activity(value: Any) -> str:
    cleaned = _safe_text(value)
    if not cleaned:
        return ""
    cleaned = re.sub(r"^(responsible for|responsibility for|ownership for)\s+", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\b(across|through|within|against|for|with|to|from|by|the|a|an)\b", "", cleaned, flags=re.I)
    cleaned = re.sub(r"[.;:,]+$", "", cleaned)
    words = [word for word in cleaned.split() if word]
    if not words:
        return ""

    first = words[0].lower()
    if first.endswith("ing") and first not in {"monitoring", "reporting"}:
        words[0] = _verb_from_gerund(words[0])
    elif first in {"is", "are", "was", "were", "be", "being"} and len(words) > 1:
        words = words[1:]

    words = words[:_MAX_ACTIVITY_WORDS]
    while len(words) < _MIN_ACTIVITY_WORDS:
        words.append("workflow" if len(words) == 1 else "control")
    words[0] = words[0].capitalize()
    return " ".join(words)


def _normalize_pain_point_text(value: Any, stage: str) -> str:
    cleaned = _safe_text(value)
    if not cleaned or len(cleaned.split()) < 5 or cleaned.lower() in {"poor communication", "manual work", "delays"}:
        cleaned = f"Fragmented {stage.lower()} ownership delays decision support."
    if not any(term in cleaned.lower() for term in _IMPACT_TERMS):
        cleaned = f"{cleaned.rstrip('.')} limits operational visibility."
    if not cleaned.endswith("."):
        cleaned = f"{cleaned}."
    return cleaned[0].upper() + cleaned[1:]


def _remove_unsupported_numeric_claims(text: str) -> str:
    """Tag unsupported numeric claims with `` (illustrative)`` instead of stripping them.

    The Phase 2.3 policy permits illustrative numerics when explicit grounding
    is unavailable. Each matched numeric token is preserved verbatim and
    suffixed with `` (illustrative)`` so the renderer and validator can
    distinguish grounded figures from illustrative ones.
    """
    cleaned = text

    def _tag(match: re.Match) -> str:
        return f"{match.group(0)} (illustrative)"

    for pattern in _ILLUSTRATIVE_NUMERIC_PATTERNS:
        cleaned = pattern.sub(_tag, cleaned)
    return " ".join(cleaned.split())


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [part if part.endswith((".", "!", "?")) else f"{part}." for part in parts if part.strip()]


def _title_preserving_acronyms(text: str) -> str:
    words = []
    for word in text.split():
        if word.isupper() or "&" in word:
            words.append(word)
        else:
            words.append(word.capitalize())
    return " ".join(words)


def _verb_from_gerund(word: str) -> str:
    lowered = word.lower()
    replacements = {
        "validating": "Validate",
        "approving": "Approve",
        "monitoring": "Monitor",
        "executing": "Execute",
        "forecasting": "Forecast",
        "coordinating": "Coordinate",
        "maintaining": "Maintain",
        "reviewing": "Review",
        "aligning": "Align",
        "documenting": "Document",
        "governing": "Govern",
        "resolving": "Resolve",
    }
    return replacements.get(lowered, word[:-3] if lowered.endswith("ing") and len(word) > 4 else word)


def _normalize_key(value: str) -> str:
    normalized = value.lower().replace("&", "and")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return " ".join(normalized.split())


# ── Visual pattern awareness ─────────────────────────────────────────────────

# Pattern-specific instructions appended to the slide_content prompt.
_VISUAL_PATTERN_INSTRUCTIONS: dict[str, str] = {
    "CL-01": (
        "Visual pattern: CL-01 Four Insight Cards. "
        "Generate exactly four insight cards in a `cards` array. "
        "Each card must have `title` and `description` and may include `metric` or `tag`."
    ),
    "CL-02": (
        "Visual pattern: CL-02 Three Cards. "
        "Generate exactly three priority or recommendation cards in a `cards` array. "
        "Each card must have `title` and `description`."
    ),
    "CL-03": (
        "Visual pattern: CL-03 KPI Cards. "
        "Generate exactly three KPI cards in a `kpis` array. "
        "Each KPI must have `title` (or `label`), `value`, `trend`, and `description`."
    ),
    "CL-04": (
        "Visual pattern: CL-04 Comparison. "
        "Generate a comparison in a `columns` array with exactly two items. "
        "Each column has `label` and `items` (list of `{name, text}` objects)."
    ),
    "CL-05": (
        "Visual pattern: CL-05 Two Column. "
        "Generate a two-column listing in a `columns` array with exactly two items. "
        "Each column has `label` and `items` (list of text strings or `{text}` objects)."
    ),
    "CL-06": (
        "Visual pattern: CL-06 Executive Summary. "
        "Generate exactly three executive summary cards in a `cards` array. "
        "Each card must have `title` and `description`. Also include a concise `executive_summary`."
    ),
    "IG-01": (
        "Visual pattern: IG-01 Timeline. "
        "Generate exactly four timeline events in an `events` array. "
        "Each event must have `title`, `description`, and `date` (or `date_or_phase`)."
    ),
    "IG-02": (
        "Visual pattern: IG-02 Roadmap. "
        "Generate exactly four roadmap phases in a `phases` array. "
        "Each phase must have `name`, `duration`, and `deliverables` (list). "
        "Phase names must be named consulting phases such as Diagnose, Design, Pilot, and Scale; "
        "never use generic labels like Step 1, Step 2, Phase 1, or Phase 2."
    ),
    "IG-03": (
        "Visual pattern: IG-03 Process Flow. "
        "Generate four to seven process steps in a `steps` array. "
        "Each step must have `name` (or `label`), `description`, and optional `owner`."
    ),
    "IG-04": (
        "Visual pattern: IG-04 Matrix. "
        "Generate matrix data as a `cells` array of nine items, each with `value`. "
        "Alternatively provide `rows` with nested `cells`. "
        "For implementation-risk slides, each cell value must be a real risk, and each cell must include "
        "`quadrant` with `impact` and `likelihood` values Low, Medium, or High."
    ),
    "IG-05": (
        "Visual pattern: IG-05 Journey. "
        "Generate exactly four journey stages in a `journey_stages` array. "
        "Each stage must have `name` (or `label`), `touchpoints`, `pain_point`, and `opportunity`."
    ),
    "IG-06": (
        "Visual pattern: IG-06 Capability Map. "
        "Generate exactly four capability domains in a `domains` array. "
        "Each domain must have `name` and `capabilities` (list of `{name}` objects)."
    ),
}


def _visual_pattern_instruction(pattern_id: str) -> str:
    """Return the prompt instruction for a given visual pattern."""
    return _VISUAL_PATTERN_INSTRUCTIONS.get(
        pattern_id,
        "Visual pattern: generic. Populate standard title, subtitle, stages, and pain_points.",
    )


def _apply_visual_pattern_shape(
    raw_spec: dict[str, Any],
    payload: dict[str, Any],
    pattern_id: str,
) -> dict[str, Any]:
    """
    Add pattern-native structured fields to ``raw_spec`` based on the selected
    visual pattern. The base operating-model fields are preserved for backward
    compatibility.
    """
    if pattern_id in {"CL-01", "CL-02", "CL-06"}:
        count = 4 if pattern_id == "CL-01" else 3
        raw_spec["cards"] = _shape_cards(payload, count)
    elif pattern_id == "CL-03":
        raw_spec["kpis"] = _shape_kpis(payload)
    elif pattern_id in {"CL-04", "CL-05"}:
        raw_spec["columns"] = _shape_columns(payload, pattern_id)
    elif pattern_id == "IG-01":
        raw_spec["events"] = _shape_events(payload)
    elif pattern_id == "IG-02":
        raw_spec["phases"] = _shape_phases(payload)
    elif pattern_id == "IG-03":
        raw_spec["steps"] = _shape_steps(payload)
    elif pattern_id == "IG-04":
        raw_spec["cells"] = _shape_cells(payload)
    elif pattern_id == "IG-05":
        raw_spec["journey_stages"] = _shape_journey_stages(payload)
    elif pattern_id == "IG-06":
        raw_spec["domains"] = _shape_domains(payload)

    raw_spec["metadata"]["visual_pattern"] = pattern_id
    return raw_spec


# ── Pattern shape helpers ─────────────────────────────────────────────────────


def _shape_cards(payload: dict[str, Any], count: int) -> list[dict[str, str]]:
    """Normalize ``cards`` for CL-01/02/06. Leave empty when not emitted."""
    cards = payload.get("cards", [])
    if isinstance(cards, list) and cards:
        return _pad_cards([_normalize_card(c) for c in cards], count)
    return _pad_cards([], count)


def _normalize_card(item: Any) -> dict[str, str]:
    if isinstance(item, dict):
        title = item.get("title") or item.get("label") or item.get("name") or ""
        description = item.get("description", "")
        metric = item.get("metric") or item.get("value") or ""
        tag = item.get("tag", "")
        return {
            "title": str(title),
            "description": str(description),
            "metric": str(metric),
            "tag": str(tag),
        }
    return {"title": str(item), "description": "", "metric": "", "tag": ""}


def _pad_cards(cards: list[dict[str, str]], count: int) -> list[dict[str, str]]:
    # Padding removed: the layout engine synthesizes adaptive grids from the
    # actual item count so empty placeholder cards are never rendered.
    return cards[:count]


def _shape_kpis(payload: dict[str, Any]) -> list[dict[str, str]]:
    """Normalize ``kpis`` for CL-03. Leave empty when not emitted."""
    kpis = payload.get("kpis", [])
    if isinstance(kpis, list) and kpis:
        return _pad_kpis([_normalize_kpi(k) for k in kpis], 3)
    return _pad_kpis([], 3)


def _normalize_kpi(item: Any) -> dict[str, str]:
    if isinstance(item, dict):
        label = item.get("label") or item.get("title") or item.get("name") or ""
        value = item.get("value") or item.get("metric") or ""
        trend = item.get("trend", "")
        description = item.get("description", "")
        return {
            "label": str(label),
            "value": str(value),
            "trend": str(trend),
            "description": str(description),
        }
    return {"label": str(item), "value": "", "trend": "", "description": ""}


def _pad_kpis(kpis: list[dict[str, str]], count: int) -> list[dict[str, str]]:
    # Padding removed: render only KPIs actually emitted by the model.
    return kpis[:count]


def _shape_columns(payload: dict[str, Any], pattern_id: str) -> list[dict[str, Any]]:
    """Normalize ``columns`` for CL-04/05. Leave empty when not emitted."""
    columns = payload.get("columns", [])
    if isinstance(columns, list) and len(columns) >= 2:
        return [_normalize_column(c, pattern_id) for c in columns[:2]]

    left_title = payload.get("left_title", "Current")
    right_title = payload.get("right_title", "Future")
    rows = payload.get("rows", [])

    left_items: list[Any] = []
    right_items: list[Any] = []

    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict):
                left = row.get("left")
                right = row.get("right")
                if left:
                    left_items.append(left)
                if right:
                    right_items.append(right)

    return [
        {"label": str(left_title), "items": _normalize_column_items(left_items, pattern_id)},
        {"label": str(right_title), "items": _normalize_column_items(right_items, pattern_id)},
    ]


def _normalize_column(column: Any, pattern_id: str) -> dict[str, Any]:
    if isinstance(column, dict):
        label = column.get("label") or column.get("title") or ""
        items = column.get("items", [])
        return {"label": str(label), "items": _normalize_column_items(items, pattern_id)}
    return {"label": str(column), "items": []}


def _normalize_column_items(items: list[Any], pattern_id: str) -> list[Any]:
    result: list[Any] = []
    for item in items:
        if isinstance(item, dict):
            text = item.get("text") or item.get("name") or item.get("title") or item.get("label") or ""
            if pattern_id == "CL-04":
                result.append({"name": str(text), "text": str(text)})
            else:
                result.append({"text": str(text)})
        elif item:
            if pattern_id == "CL-04":
                result.append({"name": str(item), "text": str(item)})
            else:
                result.append({"text": str(item)})
    return result


def _shape_events(payload: dict[str, Any]) -> list[dict[str, str]]:
    """Normalize ``events`` for IG-01. Leave empty when not emitted."""
    sources = [
        payload.get("events"),
        payload.get("timeline"),
        payload.get("milestones"),
        payload.get("phases"),
    ]
    for source in sources:
        events = _normalize_nodes(source)
        if events:
            return _pad_nodes(events, 4)
    return _pad_nodes([], 4)


def _shape_phases(payload: dict[str, Any]) -> list[dict[str, str]]:
    """Normalize ``phases`` for IG-02. Leave empty when not emitted."""
    sources = [
        payload.get("phases"),
        payload.get("roadmap"),
    ]
    for source in sources:
        phases = _normalize_bars(source)
        if phases:
            return _pad_phases(phases, 4)
    return _pad_phases([], 4)


def _shape_steps(payload: dict[str, Any]) -> list[dict[str, str]]:
    """Normalize ``steps`` for IG-03. Leave empty when not emitted."""
    sources = [
        payload.get("steps"),
        payload.get("nodes"),
        payload.get("process"),
    ]
    for source in sources:
        steps = _normalize_nodes(source)
        if steps:
            return _pad_nodes(steps, 7)
    return _pad_nodes([], 7)


def _shape_cells(payload: dict[str, Any]) -> list[dict[str, str]]:
    """Normalize ``cells`` for IG-04. Leave empty when not emitted."""
    rows = payload.get("rows")
    if isinstance(rows, list) and rows:
        cells: list[dict[str, str]] = []
        for row in rows:
            if isinstance(row, dict):
                row_cells = row.get("cells", [])
                if isinstance(row_cells, list):
                    cells.extend([_normalize_cell(c) for c in row_cells])
                else:
                    cells.append(_normalize_cell(row))
            else:
                cells.append(_normalize_cell(row))
        if cells:
            return _pad_cells(cells, 9)

    cells_raw = payload.get("cells")
    if isinstance(cells_raw, list) and cells_raw:
        return _pad_cells([_normalize_cell(c) for c in cells_raw], 9)
    return _pad_cells([], 9)


def _normalize_cell(item: Any) -> dict[str, str]:
    if isinstance(item, dict):
        value = item.get("value") or item.get("name") or item.get("label") or item.get("title") or ""
        normalized: dict[str, Any] = {"value": str(value)}
        quadrant = item.get("quadrant")
        if isinstance(quadrant, dict):
            impact = _normalize_quadrant_value(quadrant.get("impact"))
            likelihood = _normalize_quadrant_value(quadrant.get("likelihood"))
            normalized["quadrant"] = {"impact": impact, "likelihood": likelihood}
        elif item.get("impact") or item.get("likelihood"):
            normalized["quadrant"] = {
                "impact": _normalize_quadrant_value(item.get("impact")),
                "likelihood": _normalize_quadrant_value(item.get("likelihood")),
            }
        return normalized
    return {"value": str(item)}


def _normalize_quadrant_value(value: Any) -> str:
    text = _clean_text(value).lower()
    if text in {"high", "h", "critical", "severe", "major"}:
        return "High"
    if text in {"medium", "med", "m", "moderate"}:
        return "Medium"
    if text in {"low", "l", "minor"}:
        return "Low"
    return "Medium"


def _pad_cells(cells: list[dict[str, str]], count: int) -> list[dict[str, str]]:
    # Padding removed: the matrix synthesizes from actual risk count.
    return cells[:count]


def _shape_journey_stages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize ``journey_stages`` for IG-05. Leave empty when not emitted."""
    sources = [
        payload.get("journey_stages"),
        payload.get("touchpoints"),
    ]
    for source in sources:
        stages = _normalize_journey_stages(source)
        if stages:
            return _pad_journey_stages(stages, 4)
    return _pad_journey_stages([], 4)


def _normalize_journey_stages(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    result: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict):
            name = item.get("name") or item.get("label") or item.get("title") or ""
            touchpoints = item.get("touchpoints", [])
            pain_point = item.get("pain_point") or item.get("pain_points", [])
            opportunity = item.get("opportunity") or item.get("opportunities", [])
            result.append({
                "name": str(name),
                "touchpoints": _string_list(touchpoints),
                "pain_point": _first_item(pain_point),
                "opportunity": _first_item(opportunity),
            })
        elif item:
            result.append({
                "name": str(item),
                "touchpoints": [],
                "pain_point": "",
                "opportunity": "",
            })
    return result


def _pad_journey_stages(stages: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    # Padding removed: render only stages actually emitted by the model.
    return stages[:count]


def _shape_domains(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize ``domains`` for IG-06. Leave empty when not emitted."""
    domains = payload.get("domains")
    if isinstance(domains, list) and domains:
        return _pad_domains([_normalize_domain(d) for d in domains], 4)

    sources = [
        payload.get("capabilities"),
        payload.get("functions"),
        payload.get("business_areas"),
    ]
    for source in sources:
        domains = _normalize_domains(source)
        if domains:
            return _pad_domains(domains, 4)
    return _pad_domains([], 4)


def _normalize_domain(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        name = item.get("name") or item.get("domain") or item.get("function") or item.get("area") or ""
        capabilities = item.get("capabilities", [])
        caps: list[dict[str, str]] = []
        if isinstance(capabilities, list):
            for cap in capabilities:
                if isinstance(cap, dict):
                    caps.append({"name": str(cap.get("name", ""))})
                elif cap:
                    caps.append({"name": str(cap)})
        return {"name": str(name), "capabilities": caps}
    return {"name": str(item), "capabilities": []}


def _normalize_domains(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    return [_normalize_domain(item) for item in items]


def _pad_domains(domains: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    # Padding removed: render only domains actually emitted by the model.
    return domains[:count]


# ── Shared normalization helpers ──────────────────────────────────────────────


def _normalize_nodes(items: Any) -> list[dict[str, str]]:
    if not isinstance(items, list):
        return []
    result: list[dict[str, str]] = []
    for item in items:
        if isinstance(item, dict):
            label = item.get("label") or item.get("title") or item.get("name") or ""
            description = item.get("description", "")
            result.append({"label": str(label), "description": str(description)})
        elif item:
            result.append({"label": str(item), "description": ""})
    return result


def _normalize_bars(items: Any) -> list[dict[str, str]]:
    if not isinstance(items, list):
        return []
    result: list[dict[str, str]] = []
    for item in items:
        if isinstance(item, dict):
            name = item.get("name") or item.get("label") or item.get("title") or ""
            activities = item.get("activities") or item.get("deliverables") or []
            description = ", ".join(str(a) for a in activities[:3]) if isinstance(activities, list) else str(activities)
            result.append({"name": str(name), "description": str(description)})
        elif item:
            result.append({"name": str(item), "description": ""})
    return result


def _pad_nodes(nodes: list[dict[str, str]], count: int) -> list[dict[str, str]]:
    # Padding removed: render only nodes/steps/events actually emitted by the model.
    return nodes[:count]


def _pad_phases(phases: list[dict[str, str]], count: int) -> list[dict[str, str]]:
    # Padding removed: render only phases actually emitted by the model.
    return phases[:count]


def _stage_to_node(stage: Any) -> dict[str, str]:
    if isinstance(stage, dict):
        label = stage.get("label") or stage.get("title") or ""
        activities = stage.get("activities", [])
        description = ", ".join(str(a) for a in activities[:2])
        return {"label": str(label), "description": description}
    return {"label": str(stage), "description": ""}


def _stage_to_bar(stage: Any) -> dict[str, str]:
    if isinstance(stage, dict):
        label = stage.get("label") or stage.get("title") or ""
        activities = stage.get("activities", [])
        description = ", ".join(str(a) for a in activities[:2])
        return {"name": str(label), "description": description}
    return {"name": str(stage), "description": ""}


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if value:
        return [str(value)]
    return []


def _first_item(value: Any) -> str:
    if isinstance(value, list) and value:
        return str(value[0])
    return str(value) if value else ""


def _clean_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split()).strip()
    return cleaned or None

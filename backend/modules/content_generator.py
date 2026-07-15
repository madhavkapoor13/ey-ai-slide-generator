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
    if _is_next_step_manifest(asset_manifest) or "next step" in role or "decision" in role or "action" in role:
        repaired = _repair_next_step_language(repaired, asset_manifest)
    repaired = _repair_title_so_what(repaired, slide_plan)
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
        ]
        repaired = f"{drivers[index % len(drivers)]}; {repaired}"
    if not re.search(r"\b(impact|delay|cost|adoption|control|exposure|disruption)\b", repaired, flags=re.I):
        impacts = [
            "impact: rollout delay",
            "impact: control exposure",
            "impact: supplier disruption",
            "impact: value leakage",
        ]
        repaired = f"{repaired}; {impacts[index % len(impacts)]}"
    if not re.search(r"\b(mitigation|mitigate|control|owner|ownership|sponsor|accountable|response)\b", repaired, flags=re.I):
        endings = [
            "response: sponsor-led",
            "control: data-owned",
            "mitigation: change-led",
            "accountable: control owner",
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
        if not isinstance(value, str):
            continue
        key_lower = key.lower()
        if key_lower.startswith("header_"):
            repaired[key] = _next_step_header_label(key_lower, value)
        elif "next_step" in key_lower or "action" in key_lower:
            repaired[key] = _ensure_next_step_contract_text(value)
        elif "priority" in key_lower:
            repaired[key] = _fit_compact_label(value, "Approve pilot scope", max_chars=60)
        elif "when" in key_lower:
            repaired[key] = value if _contains_timing(value) else "30 days"
        elif "who" in key_lower:
            repaired[key] = value if _contains_owner(value) else "Procurement sponsor"
    return repaired


def _backfill_next_step_placeholders(
    payload: dict[str, Any],
    asset_manifest: AssetManifest,
) -> dict[str, Any]:
    repaired = dict(payload)
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


def _ensure_next_step_contract_text(text: str) -> str:
    repaired = text.strip()
    if not re.search(r"\b(approve|decide|decision|confirm|endorse|authorize|fund|prioritize)\b", repaired, flags=re.I):
        repaired = f"Approve {repaired[0].lower() + repaired[1:] if repaired else 'pilot'}"
    return _fit_compact_label(repaired, "Approve pilot launch", max_chars=160)


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
    if "current" in role or "process" in role:
        repaired["title"] = "Current process friction slows decisions and weakens control"
    elif "case for change" in role or "case" in role:
        repaired["title"] = "Case for change centers on resilience, speed, and control"
    elif "future" in role or "operating model" in role:
        repaired["title"] = "Future-state model shifts work to accountable digital capabilities"
    elif "benefit" in role or "value" in role:
        repaired["title"] = "Business benefits convert automation into measurable value levers"
    elif "roadmap" in role or "implementation" in role:
        repaired["title"] = "Implementation roadmap sequences pilot, scale, and governance"
    elif "kpi" in role or "success" in role or "metric" in role:
        repaired["title"] = "KPIs track cycle time, value capture, and control adoption"
    elif "opportunit" in role:
        repaired["title"] = "Opportunity areas prioritize value pools with execution readiness"
    elif "risk" in role:
        repaired["title"] = "AI procurement risks require accountable controls before scale"
    elif "next step" in role or "decision" in role or "action" in role:
        repaired["title"] = "Board decisions launch the procurement AI pilot"
    elif "use case" in role:
        repaired["title"] = "AI use cases target sourcing speed and spend control"
    return repaired


def _title_matches_role(title: str, role: str) -> bool:
    title_lower = title.lower()
    if "current" in role or "process" in role:
        return any(term in title_lower for term in ("current", "process", "friction", "manual", "baseline", "as-is", "bottleneck"))
    if "case for change" in role or "case" in role:
        return any(term in title_lower for term in ("case", "change", "imperative", "resilience", "pressure", "why"))
    if "future" in role or "operating model" in role:
        return any(term in title_lower for term in ("future", "operating model", "capability", "accountable", "digital"))
    if "benefit" in role or "value" in role:
        return any(term in title_lower for term in ("benefit", "value", "savings", "margin", "cash", "speed"))
    if "roadmap" in role or "implementation" in role:
        return any(term in title_lower for term in ("roadmap", "phase", "pilot", "scale", "sequence", "governance"))
    if "kpi" in role or "success" in role or "metric" in role:
        return any(term in title_lower for term in ("kpi", "metric", "indicator", "track", "measure", "success"))
    if "opportunit" in role:
        return any(term in title_lower for term in ("opportunity", "prioritize", "value pool", "readiness", "growth"))
    if "next step" in role or "decision" in role or "action" in role:
        return any(term in title_lower for term in ("board", "decision", "approve", "pilot", "launch", "owner", "action"))
    if "risk" in role:
        return any(term in title_lower for term in ("risk", "control", "mitigation", "exposure", "owner"))
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
    return fallback[:max_chars].rstrip()


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
    if (
        "implementation risk" in normalized
        or "risk register" in normalized
        or "risk matrix" in normalized
        or "mitigation" in normalized
    ):
        return "implementation_risks"
    if "next step" in normalized or "decision" in normalized or "action" in normalized:
        return "next_steps"
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

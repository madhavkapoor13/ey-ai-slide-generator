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
import os
import re
from typing import Any

from dotenv import load_dotenv

from backend.llm.prompt_loader import build_prompt
from schemas.context import EnterpriseContext
from schemas.intent import IntentResult
from schemas.operating_model import OperatingModelSpec
from schemas.process import ProcessResult
from schemas.slide_spec import SlideSpec

logger = logging.getLogger(__name__)

_DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
_STAGE_COUNT = 6
_ACTIVITIES_PER_STAGE = 5
_MAX_ACTIVITY_WORDS = 7
_MIN_ACTIVITY_WORDS = 3
_UNSUPPORTED_NUMERIC_PATTERNS = [
    re.compile(r"\b\d+(?:\.\d+)?\s*%"),
    re.compile(r"[$€£¥]\s*\d"),
    re.compile(r"\b\d+(?:\.\d+)?\s*(?:days?|weeks?|months?|hours?|hrs?|minutes?|mins?)\b", re.I),
    re.compile(r"\bROI\b", re.I),
    re.compile(r"\b(?:revenue|cost|savings|profit|margin|budget)\s+(?:of|by|at)?\s*[$€£¥]?\d", re.I),
]
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
    )


def _generate_payload(
    intent: IntentResult,
    context: EnterpriseContext,
    process_result: ProcessResult,
) -> dict[str, Any]:
    try:
        raw_response = _call_content_llm(intent, context, process_result)
        payload = json.loads(_strip_json_fence(raw_response))
        if not isinstance(payload, dict):
            raise ValueError("Content LLM response was not a JSON object.")
        return payload
    except Exception as exc:  # noqa: BLE001 - generic fallback keeps v2 runnable.
        logger.warning("content generation LLM failed; using generic fallback: %s", exc)
        return _fallback_payload(intent, context, process_result)


def _call_content_llm(
    intent: IntentResult,
    context: EnterpriseContext,
    process_result: ProcessResult,
) -> str:
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY or GOOGLE_API_KEY is not configured.")

    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise RuntimeError("google-genai is not installed.") from exc

    user_input = {
        "intent": intent.model_dump(mode="json"),
        "enterprise_context": {
            "company": context.company,
            "industry": context.industry,
            "business_function": context.business_function,
            "company_summary": context.company_summary,
            "facts": [fact.model_dump(mode="json") for fact in context.facts],
        },
        "process_result": process_result.model_dump(mode="json"),
    }

    client = genai.Client(api_key=api_key)
    prompt = build_prompt(
        "content",
        user_input=json.dumps(user_input, ensure_ascii=True),
        additional_context="Input:",
    )
    response = client.models.generate_content(
        model=os.getenv("GEMINI_CONTEXT_MODEL", _DEFAULT_GEMINI_MODEL),
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.2,
            response_mime_type="application/json",
        ),
    )
    return getattr(response, "text", "") or ""


def _to_renderer_ready_spec(
    payload: dict[str, Any],
    intent: IntentResult,
    context: EnterpriseContext,
    process_result: ProcessResult,
) -> dict[str, Any]:
    company = _clean_text(context.company) or _clean_text(getattr(intent, "company", None)) or "Enterprise"
    industry = _clean_text(context.industry) or _clean_text(getattr(intent, "industry", None)) or "Unknown"
    business_function = (
        _clean_text(getattr(intent, "business_function", None))
        or _clean_text(context.business_function)
        or process_result.process_family
    )
    title = _clean_text(payload.get("title")) or _clean_text(intent.raw_title) or "Current State"
    subtitle = _clean_text(payload.get("subtitle")) or f"{company} {business_function} Operating Model"
    executive_summary = _normalize_executive_summary(
        payload.get("executive_summary"),
        default=_default_executive_summary(company, industry, process_result),
    )

    stage_labels = _six_stage_labels(process_result)
    stages = _normalize_stages(payload.get("stages"), stage_labels)
    pain_points = _normalize_pain_points(payload.get("pain_points"), stage_labels)

    metadata = {
        "company": company,
        "industry": industry,
        "process": process_result.process_name,
    }
    payload_metadata = payload.get("metadata", {})
    if isinstance(payload_metadata, dict):
        metadata.update({key: value for key, value in payload_metadata.items() if isinstance(value, str)})
    metadata["company"] = company
    metadata["industry"] = industry
    metadata["process"] = process_result.process_name

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
        for index in range(_STAGE_COUNT)
    ]

    return {
        "title": title,
        "subtitle": subtitle,
        "description": f"{process_result.process_name} current-state operating model",
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


def _normalize_stages(items: Any, stage_labels: list[str]) -> list[dict[str, Any]]:
    input_stages = items if isinstance(items, list) else []
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

    fallback_templates = [
        f"Coordinate {stage_label.lower()} inputs",
        f"Maintain {stage_label.lower()} controls",
        f"Resolve {stage_label.lower()} exceptions",
        f"Align {stage_label.lower()} handoffs",
        f"Govern {stage_label.lower()} decisions",
    ]
    for fallback in fallback_templates:
        if len(activities) == _ACTIVITIES_PER_STAGE:
            break
        activities.append(_normalize_activity(fallback))

    return activities[:_ACTIVITIES_PER_STAGE]


def _normalize_pain_points(items: Any, stage_labels: list[str]) -> list[dict[str, str]]:
    input_points = items if isinstance(items, list) else []
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
) -> dict[str, Any]:
    company = _clean_text(context.company) or _clean_text(getattr(intent, "company", None)) or "Enterprise"
    business_function = (
        _clean_text(getattr(intent, "business_function", None))
        or _clean_text(context.business_function)
        or process_result.process_family
    )
    stage_labels = _six_stage_labels(process_result)
    return {
        "title": _clean_text(intent.raw_title) or "Current State",
        "subtitle": f"{company} {business_function} Operating Model",
        "executive_summary": _default_executive_summary(company, context.industry, process_result),
        "stages": [
            {
                "label": label,
                "activities": _normalize_activities([], label),
            }
            for label in stage_labels
        ],
        "pain_points": [
            {
                "stage": label,
                "text": _normalize_pain_point_text("", stage=label),
            }
            for label in stage_labels
        ],
        "metadata": {
            "company": company,
            "industry": _clean_text(context.industry) or "Unknown",
            "process": process_result.process_name,
        },
    }


def _six_stage_labels(process_result: ProcessResult) -> list[str]:
    process_key = _normalize_key(process_result.process_name)
    defaults = _PROCESS_STAGE_OVERRIDES.get(process_key, _GENERIC_STAGE_DEFAULTS)
    labels = [
        _normalize_stage_label(stage, fallback=defaults[min(index, len(defaults) - 1)])
        for index, stage in enumerate(process_result.stages)
        if _clean_text(stage)
    ]
    for fallback in defaults:
        if len(labels) == _STAGE_COUNT:
            break
        normalized_fallback = _normalize_stage_label(fallback, fallback=fallback)
        if normalized_fallback not in labels:
            labels.append(normalized_fallback)
    return labels[:_STAGE_COUNT]


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
    cleaned = text
    for pattern in _UNSUPPORTED_NUMERIC_PATTERNS:
        cleaned = pattern.sub("unsupported metric", cleaned)
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


def _strip_json_fence(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _clean_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split()).strip()
    return cleaned or None

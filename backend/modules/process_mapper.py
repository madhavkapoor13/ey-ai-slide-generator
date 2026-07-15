"""
backend/modules/process_mapper.py
==================================
Enterprise Process Mapper — Sprint 3.

The mapper selects a standard enterprise process from the user's business
function, industry, and grounded company context. It does not generate slide
content, activities, KPIs, pain points, or executive summaries.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from backend.llm.prompt_loader import build_prompt
from schemas.context import EnterpriseContext
from schemas.intent import IntentResult
from schemas.process import ProcessResult

logger = logging.getLogger(__name__)


_PROCESS_MAP: dict[str, ProcessResult] = {
    "finance": ProcessResult(
        process_name="Record-to-Report",
        process_family="Finance",
        confidence=0.94,
        reasoning="Finance operating models are commonly represented using the Record-to-Report enterprise process.",
        stages=[
            "Journal Entry",
            "General Ledger",
            "Financial Close",
            "Consolidation",
            "Management Reporting",
        ],
    ),
    "procurement": ProcessResult(
        process_name="Procure-to-Pay",
        process_family="Procurement",
        confidence=0.94,
        reasoning="Procurement functions are commonly represented using the Procure-to-Pay enterprise process.",
        stages=[
            "Requisition",
            "Sourcing",
            "Purchase Order",
            "Goods Receipt",
            "Invoice Processing",
            "Payment",
        ],
    ),
    "human_resources": ProcessResult(
        process_name="Hire-to-Retire",
        process_family="Human Resources",
        confidence=0.94,
        reasoning="Human Resources functions are commonly represented using the Hire-to-Retire enterprise process.",
        stages=[
            "Workforce Planning",
            "Recruiting",
            "Onboarding",
            "Talent Management",
            "Payroll and Benefits",
            "Separation",
        ],
    ),
    "sales": ProcessResult(
        process_name="Order-to-Cash",
        process_family="Sales",
        confidence=0.94,
        reasoning="Sales and revenue operations are commonly represented using the Order-to-Cash enterprise process.",
        stages=[
            "Customer Order",
            "Order Management",
            "Fulfillment",
            "Billing",
            "Collections",
            "Cash Application",
        ],
    ),
    "customer_service": ProcessResult(
        process_name="Case-to-Resolution",
        process_family="Customer Service",
        confidence=0.93,
        reasoning="Customer Service functions are commonly represented using the Case-to-Resolution enterprise process.",
        stages=[
            "Case Intake",
            "Triage",
            "Assignment",
            "Resolution",
            "Closure",
            "Feedback",
        ],
    ),
    "supply_chain": ProcessResult(
        process_name="Plan-Source-Make-Deliver",
        process_family="Supply Chain",
        confidence=0.93,
        reasoning="Supply Chain functions are commonly represented using the Plan-Source-Make-Deliver process model.",
        stages=[
            "Plan",
            "Source",
            "Make",
            "Deliver",
            "Return",
        ],
    ),
    "manufacturing": ProcessResult(
        process_name="Manufacturing Operations",
        process_family="Manufacturing",
        confidence=0.94,
        reasoning="Manufacturing functions are commonly represented using the Manufacturing Operations enterprise process.",
        stages=[
            "Production Planning",
            "Material Preparation",
            "Production Execution",
            "Quality Control",
            "Maintenance",
            "Finished Goods Handover",
        ],
    ),
    "marketing": ProcessResult(
        process_name="Campaign-to-Lead",
        process_family="Marketing",
        confidence=0.93,
        reasoning="Marketing functions are commonly represented using the Campaign-to-Lead enterprise process.",
        stages=[
            "Campaign Planning",
            "Audience Targeting",
            "Content Development",
            "Campaign Execution",
            "Lead Capture",
            "Lead Qualification",
        ],
    ),
}

_ALIASES: dict[str, str] = {
    "accounting": "finance",
    "controllership": "finance",
    "financial planning": "finance",
    "fp&a": "finance",
    "human resources": "human_resources",
    "hr": "human_resources",
    "people": "human_resources",
    "talent": "human_resources",
    "purchasing": "procurement",
    "sourcing": "procurement",
    "supply management": "procurement",
    "revenue": "sales",
    "commercial": "sales",
    "customer support": "customer_service",
    "customer success": "customer_service",
    "service": "customer_service",
    "logistics": "supply_chain",
    "operations": "supply_chain",
    "manufacturing": "manufacturing",
    "production": "manufacturing",
    "marketing": "marketing",
    "demand generation": "marketing",
}


def identify_process(
    intent: IntentResult,
    context: EnterpriseContext,
) -> ProcessResult:
    """
    Identify the enterprise process for the intent and context.

    Common business functions are mapped deterministically. Gemini is used
    only as a fallback for functions that do not confidently match the table.
    """
    business_function_candidates = _business_function_candidates(intent, context)
    business_function = business_function_candidates[0] if business_function_candidates else "Unknown"
    logger.info(
        "identifying process: company=%s industry=%s business_function=%s",
        context.company,
        context.industry,
        business_function or "Unknown",
    )

    for candidate in business_function_candidates:
        match_key = _match_business_function(candidate)
        if match_key:
            return _PROCESS_MAP[match_key].model_copy(deep=True)

    return _identify_process_with_llm(intent, context, business_function)


def _business_function_candidates(intent: IntentResult, context: EnterpriseContext) -> list[str]:
    values = [
        getattr(intent, "business_function", None),
        intent.metadata.get("business_function") if intent.metadata else None,
        getattr(context, "business_function", None),
        getattr(context, "domain", None),
        intent.raw_title,
        intent.raw_content,
    ]
    candidates: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = _clean_text(value)
        if cleaned and cleaned.lower() != "unknown" and cleaned.lower() not in seen:
            candidates.append(cleaned)
            seen.add(cleaned.lower())
    return candidates


def _match_business_function(value: str) -> str | None:
    normalized = _normalize(value)
    if normalized in _PROCESS_MAP:
        return normalized
    if normalized in _ALIASES:
        return _ALIASES[normalized]

    for alias, key in _ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", normalized):
            return key
    for key in _PROCESS_MAP:
        if re.search(rf"\b{re.escape(key.replace('_', ' '))}\b", normalized):
            return key
    return None


def _identify_process_with_llm(
    intent: IntentResult,
    context: EnterpriseContext,
    business_function: str,
) -> ProcessResult:
    try:
        payload = _call_process_mapper_llm(intent, context, business_function)
        return _to_process_result(payload)
    except Exception as exc:  # noqa: BLE001 - fallback should not break the pipeline.
        logger.warning("process mapper LLM fallback failed: %s", exc)
        return ProcessResult(
            process_name="Unknown Enterprise Process",
            process_family=business_function if business_function != "Unknown" else "Unknown",
            confidence=0.0,
            reasoning="No deterministic process mapping was available and the LLM fallback did not return a usable process.",
            stages=[],
        )


def _call_process_mapper_llm(
    intent: IntentResult,
    context: EnterpriseContext,
    business_function: str,
) -> dict[str, Any]:
    """Call the multi-provider router for the process-mapping LLM fallback."""
    from backend.llm import router

    user_input = {
        "intent": {
            "company": getattr(intent, "company", None),
            "industry": getattr(intent, "industry", None),
            "business_function": business_function,
            "slide_type": intent.slide_type,
            "raw_title": intent.raw_title,
            "raw_content": intent.raw_content,
        },
        "enterprise_context": {
            "company": context.company,
            "industry": context.industry,
            "business_function": context.business_function,
            "company_summary": context.company_summary,
            "facts": [
                {"fact_type": fact.type, "text": fact.statement[:300]}
                for fact in context.facts[:5]
            ],
        },
        "allowed_processes": [
            result.process_name for result in _PROCESS_MAP.values()
        ],
    }

    prompt = build_prompt(
        "process",
        user_input=json.dumps(user_input, ensure_ascii=True),
        additional_context="Input:",
    )
    return router.generate_json("process_mapper", prompt, temperature=0.0)


def _to_process_result(payload: dict[str, Any]) -> ProcessResult:
    stages = payload.get("stages", [])
    if not isinstance(stages, list):
        stages = []
    clean_stages = [_clean_text(stage) for stage in stages if _clean_text(stage)]

    return ProcessResult(
        process_name=_clean_text(payload.get("process_name")) or "Unknown Enterprise Process",
        process_family=_clean_text(payload.get("process_family")) or "Unknown",
        confidence=float(payload.get("confidence", 0.0)),
        reasoning=_clean_text(payload.get("reasoning")) or "Selected as the closest APQC-style enterprise process.",
        stages=clean_stages,
    )


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


def _normalize(value: str) -> str:
    normalized = _clean_text(value) or ""
    normalized = normalized.lower().replace("&", "and")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return " ".join(normalized.split())

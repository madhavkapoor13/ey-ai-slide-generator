"""
backend/modules/information_analyzer.py
=======================================
Sprint C — Information Analyzer module.

Deterministically assesses whether enough information exists to plan a
consulting deck. This module does NOT call an LLM and does NOT ask questions.
It only inspects the original user prompt, IntentResult, and DeckSpec to
detect missing or vague required fields.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from schemas.information import InformationResult
from schemas.intent import IntentResult
from schemas.presentation import DeckSpec

logger = logging.getLogger(__name__)

_REQUIRED_FIELDS = ["company", "industry", "business_function", "audience", "objective"]

_BUSINESS_FUNCTION_KEYWORDS: dict[str, list[str]] = {
    "finance": ["finance", "accounting", "controllership", "fp&a", "financial planning"],
    "procurement": ["procurement", "purchasing", "sourcing", "supply management"],
    "human_resources": ["hr", "human resources", "human-resources", "people", "talent"],
    "sales": ["sales", "revenue", "commercial"],
    "supply_chain": ["supply chain", "supply-chain", "logistics", "operations"],
    "manufacturing": ["manufacturing", "production"],
    "marketing": ["marketing", "demand generation"],
    "customer_service": ["customer service", "customer support", "customer success"],
}

_AUDIENCE_KEYWORDS: list[str] = [
    "board",
    "executive",
    "leadership",
    "management",
    "stakeholder",
    "sponsor",
    "team",
]


def analyze_information(
    user_prompt: str,
    intent: IntentResult,
    deck_spec: DeckSpec,
) -> InformationResult:
    """
    Determine whether enough information exists to plan a consulting deck.

    This function is fully deterministic and does not call an LLM.

    Parameters
    ----------
    user_prompt:
        The original request from the consultant.
    intent:
        Structured intent extracted from the request.
    deck_spec:
        Deck plan produced by the Presentation Planner.

    Returns
    -------
    InformationResult
        Assessment of completeness, missing fields, analysis, and confidence.
    """
    logger.info(
        "analyzing information: prompt=%r company=%s function=%s",
        user_prompt,
        intent.company or "Unknown",
        intent.business_function or "Unknown",
    )

    detected = {
        "company": _detect_company(user_prompt, intent),
        "industry": _detect_industry(intent),
        "business_function": _detect_business_function(user_prompt, intent),
        "audience": _detect_audience(deck_spec),
        "objective": _detect_objective(deck_spec),
    }

    missing_fields = [field for field, present in detected.items() if not present]
    has_enough = len(missing_fields) == 0
    confidence = _confidence_level(len(missing_fields))
    analysis = _build_analysis(detected, missing_fields)

    logger.info(
        "information analysis complete: has_enough=%s missing=%s confidence=%s",
        has_enough,
        missing_fields,
        confidence,
    )

    return InformationResult(
        has_enough_information=has_enough,
        missing_fields=missing_fields,
        analysis=analysis,
        confidence=confidence,
    )


def _detect_company(user_prompt: str, intent: IntentResult) -> bool:
    if _has_value(intent.company):
        return True
    return _extract_company(user_prompt) is not None


def _detect_industry(intent: IntentResult) -> bool:
    return _has_value(intent.industry)


def _detect_business_function(user_prompt: str, intent: IntentResult) -> bool:
    if _has_value(intent.business_function):
        return True
    return _extract_business_function(user_prompt) is not None


def _detect_audience(deck_spec: DeckSpec) -> bool:
    return _has_value(deck_spec.audience)


def _detect_objective(deck_spec: DeckSpec) -> bool:
    return _has_value(deck_spec.objective)


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if not isinstance(value, str):
        return False
    cleaned = value.strip().lower()
    return cleaned not in ("", "unknown", "tbd", "n/a")


def _extract_company(text: str) -> str | None:
    patterns = [
        r"\b(?:for|about|on|at)\s+([A-Z][A-Za-z0-9&\.\- ]{1,60})(?:\s+(?:current state|finance|retail|process|workflow|slide|transformation|strategy|proposal|roadmap|update)\b|[.,:\n]|$)",
        r"\bcompany\s*[:=-]\s*([A-Z][A-Za-z0-9&\.\- ]{1,60})(?:[.,:\n]|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            candidate = _clean_company(match.group(1))
            if candidate and not _is_business_function_keyword(candidate):
                return candidate
    return None


def _is_business_function_keyword(text: str) -> bool:
    lowered = text.lower()
    for keywords in _BUSINESS_FUNCTION_KEYWORDS.values():
        for keyword in keywords:
            if lowered == keyword.lower():
                return True
    return False


def _extract_business_function(text: str) -> str | None:
    lowered = text.lower()
    for function, keywords in _BUSINESS_FUNCTION_KEYWORDS.items():
        for keyword in keywords:
            if re.search(rf"\b{re.escape(keyword)}\b", lowered):
                return function
    return None


def _clean_company(value: str) -> str | None:
    cleaned = " ".join(value.split()).strip().rstrip(".,:;")
    stop_phrases = [
        " current state",
        " finance",
        " retail",
        " process",
        " workflow",
        " slide",
        " transformation",
        " strategy",
        " proposal",
        " roadmap",
        " update",
    ]
    lowered = cleaned.lower()
    for phrase in stop_phrases:
        index = lowered.find(phrase)
        if index > 0:
            cleaned = cleaned[:index].strip()
            break
    return cleaned if cleaned else None


def _confidence_level(missing_count: int) -> str:
    if missing_count == 0:
        return "high"
    if missing_count <= 2:
        return "medium"
    return "low"


def _build_analysis(detected: dict[str, bool], missing_fields: list[str]) -> str:
    present_fields = [field for field, present in detected.items() if present]

    if not missing_fields:
        return (
            f"All required fields are present: {', '.join(present_fields)}. "
            "The request contains enough information to plan a consulting deck."
        )

    analysis = f"Detected: {', '.join(present_fields)}. " if present_fields else "No required fields were detected. "
    analysis += f"Missing: {', '.join(missing_fields)}."
    return analysis.strip()

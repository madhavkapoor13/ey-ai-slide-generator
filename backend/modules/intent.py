"""
backend/modules/intent.py
=========================
Sprint H.2 — Intelligent Intent Module.

Classifies the user's raw request into a normalised ``IntentResult`` that
downstream modules can act on without re-parsing the raw strings.

Extraction strategy
-------------------
1. Deterministic entity extraction (primary):
   - ``backend/modules/intent_entity_extractor.py`` loads reusable mappings
     from ``backend/knowledge/intent_entities.json``.
   - Extracts company, industry, business_function, audience, objective, and
     slide_type via regex, keyword maps, and alias tables.
2. LLM enrichment (fallback):
   - Only invoked when deterministic confidence is below the threshold.
   - Uses the existing ``backend/ai/prompts/intent.md`` prompt via
     ``prompt_loader``.
   - Merges LLM results on top of deterministic values, preserving the
     deterministic value when it is already high-confidence.

Public API
----------
::

    result: IntentResult = extract_intent(title, content)
"""

from __future__ import annotations

import json
import logging
from typing import Any

from backend.llm.prompt_loader import build_prompt, get_prompt
from backend.modules.intent_entity_extractor import (
    extract_entities,
    get_value,
    overall_confidence,
)
from schemas.intent import IntentResult

logger = logging.getLogger(__name__)

INTENT_PROMPT = get_prompt("intent")

# Confidence threshold below which the LLM fallback is invoked.
# Deterministic extraction for common consulting prompts is expected to score
# above this threshold; genuinely ambiguous prompts fall through to the LLM.
_DETERMINISTIC_CONFIDENCE_THRESHOLD = 0.75

# ---------------------------------------------------------------------------
# Keyword signal sets — used for slide_type classification.
# ---------------------------------------------------------------------------

_OPERATING_MODEL_SIGNALS: frozenset[str] = frozenset(
    [
        "operating model",
        "current state",
        "business stages",
        "detailed business activities",
        "executive summary",
        "value leakage",
        "kpis",
        "pain points, business risks",
        "risks, and inefficiencies",
    ]
)

_PROCESS_FLOW_SIGNALS: frozenset[str] = frozenset(
    [
        "process flow",
        "workflow",
        "step by step",
        "pipeline",
        "sequence",
        "flow",
    ]
)

_COMPARISON_SIGNALS: frozenset[str] = frozenset(
    [
        "comparison",
        "compare",
        "versus",
        "vs",
        "side by side",
    ]
)

_CURRENT_FUTURE_SIGNALS: frozenset[str] = frozenset(
    [
        "current future",
        "as-is to-be",
        "as is to be",
        "before after",
        "transformation",
        "future state",
    ]
)


def extract_intent(title: str, content: str) -> IntentResult:
    """
    Extract structured intent from the user's raw request.

    The implementation is hybrid:

    1. Run deterministic entity extraction first.
    2. If the overall confidence is high enough, return immediately.
    3. Otherwise, invoke the LLM fallback and merge its results on top of the
       deterministic values.

    Parameters
    ----------
    title:
        Raw slide title provided by the user.
    content:
        Raw slide content / description provided by the user.

    Returns
    -------
    IntentResult
        Populated with detected ``company``, ``industry``,
        ``business_function``, ``audience``, ``objective``, ``slide_type``,
        and an overall ``confidence``.
    """
    combined = f"{title} {content}".lower()

    # Step 1: deterministic extraction.
    entities = extract_entities(title, content)
    slide_type = _classify(combined)
    deterministic_confidence = overall_confidence(entities)
    extraction_source = "deterministic"

    # Step 2: LLM fallback if deterministic extraction is weak.
    if deterministic_confidence < _DETERMINISTIC_CONFIDENCE_THRESHOLD:
        logger.info(
            "intent: deterministic confidence %.2f below threshold %.2f; invoking LLM fallback",
            deterministic_confidence,
            _DETERMINISTIC_CONFIDENCE_THRESHOLD,
        )
        llm_values = _extract_intent_llm(title, content)
        # When deterministic confidence is low we let the LLM override
        # deterministic values for fields it returns.
        entities = _merge_llm_entities(entities, llm_values, override=True)
        if llm_values.get("slide_type"):
            slide_type = llm_values["slide_type"]
        deterministic_confidence = max(
            deterministic_confidence, llm_values.get("confidence", 0.0)
        )
        extraction_source = "hybrid"

    result = IntentResult(
        slide_type=slide_type,
        raw_title=title,
        raw_content=content,
        company=get_value(entities, "company"),
        industry=get_value(entities, "industry"),
        business_function=get_value(entities, "business_function"),
        audience=get_value(entities, "audience"),
        objective=get_value(entities, "objective"),
        confidence=round(deterministic_confidence, 2),
        metadata={
            "extraction_source": extraction_source,
            "tone": entities.get("tone", {}).get("value")
            if isinstance(entities.get("tone"), dict)
            else None,
        },
    )

    logger.info(
        "intent extracted: slide_type=%s company=%s industry=%s business_function=%s audience=%s",
        result.slide_type,
        result.company or "Unknown",
        result.industry or "Unknown",
        result.business_function or "Unknown",
        result.audience or "Unknown",
    )
    return result


def _classify(combined_text: str) -> str:
    """
    Map a lowercased combined text to a slide type using keyword signals.

    Returns ``"unknown"`` if no signals match — downstream callers should
    handle this gracefully by defaulting to ``"process_flow"``.
    """
    if any(signal in combined_text for signal in _OPERATING_MODEL_SIGNALS):
        return "operating_model"
    if any(signal in combined_text for signal in _COMPARISON_SIGNALS):
        return "comparison"
    if any(signal in combined_text for signal in _CURRENT_FUTURE_SIGNALS):
        return "current_future"
    if any(signal in combined_text for signal in _PROCESS_FLOW_SIGNALS):
        return "process_flow"
    return "process_flow"


def _extract_intent_llm(title: str, content: str) -> dict[str, Any]:
    """
    LLM fallback for intent extraction.

    Uses the existing ``intent.md`` prompt via ``prompt_loader``. The prompt
    primarily targets ``slide_type``, ``confidence``, ``industry_signal``, and
    ``tone``; this function maps those keys onto the richer IntentResult shape
    and leaves company/business-function/audience/objective for deterministic
    extraction or downstream clarification.

    Returns an empty dict if no API key is available or the call fails, so the
    pipeline can continue on deterministic results alone.
    """
    from backend.llm import router

    user_input = json.dumps(
        {"title": title, "content": content},
        ensure_ascii=True,
    )
    prompt = build_prompt(
        "intent",
        user_input=user_input,
        additional_context="Input:",
    )

    try:
        payload = router.generate_json("intent", prompt, temperature=0.2)
    except Exception as exc:  # noqa: BLE001
        logger.warning("intent: LLM fallback failed: %s", exc)
        return {}

    return _normalize_llm_intent_response(payload)


def _normalize_llm_intent_response(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize a parsed LLM response dict into intent fields."""
    if not isinstance(payload, dict):
        logger.warning("intent: LLM response was not a JSON object")
        return {}

    result: dict[str, Any] = {}

    if payload.get("slide_type"):
        result["slide_type"] = str(payload["slide_type"]).strip()

    if payload.get("confidence") is not None:
        try:
            result["confidence"] = float(payload["confidence"])
        except (TypeError, ValueError):
            result["confidence"] = 0.0

    # Map legacy prompt keys onto canonical fields.
    if payload.get("industry_signal"):
        result["industry"] = str(payload["industry_signal"]).strip()

    if payload.get("tone"):
        result["tone"] = {"value": str(payload["tone"]).strip(), "confidence": 0.7}

    # Accept any richer fields the model may return.
    for field in ("company", "industry", "business_function", "audience", "objective"):
        if field not in result and payload.get(field):
            result[field] = str(payload[field]).strip()

    return result


def _merge_llm_entities(
    deterministic: dict[str, dict[str, Any]],
    llm: dict[str, Any],
    override: bool = False,
) -> dict[str, dict[str, Any]]:
    """
    Merge LLM fallback values on top of deterministic extraction.

    By default, deterministic values are preserved and LLM values fill only
    missing or empty fields. When ``override`` is True (e.g., deterministic
    confidence was below the threshold), LLM values take precedence for any
    field they return.
    """
    merged = dict(deterministic)

    for field in ("company", "industry", "business_function", "audience", "objective"):
        current = merged.get(field, {})
        llm_value = llm.get(field)
        if not llm_value:
            continue
        if override or not current.get("value"):
            merged[field] = {
                "value": str(llm_value).strip(),
                "confidence": llm.get("confidence", 0.7),
            }

    if "tone" in llm:
        merged["tone"] = llm["tone"]

    return merged

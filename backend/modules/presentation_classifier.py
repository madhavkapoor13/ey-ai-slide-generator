"""
backend/modules/presentation_classifier.py
==========================================
Sprint E.1 — Hybrid Presentation Classifier.

Classifies a user request into one of the curated consulting presentation types
in backend/knowledge/presentation_taxonomy.json.

Classification strategy
-----------------------
1. Deterministic keyword + intent-based scoring (primary path).
2. LLM-based fallback only when deterministic confidence is below threshold.

The keyword/signal logic lives in this module. The taxonomy file contains
presentation knowledge only (description, narrative, slide sequences, variants,
audience, applicability). It does NOT contain classification rules.

Output
------
PresentationClassification with presentation_type, confidence, and
reasoning_summary.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from backend.llm.prompt_loader import build_prompt
from schemas.intent import IntentResult
from schemas.presentation import PresentationClassification

logger = logging.getLogger(__name__)

_TAXONOMY_PATH = Path(__file__).resolve().parents[1] / "knowledge" / "presentation_taxonomy.json"
_CONFIDENCE_THRESHOLD = 0.25

# Classification signals are intentionally maintained in code, separate from the
# taxonomy knowledge base. Each type lists keywords and intent signals that
# suggest the prompt belongs to that presentation type.
_TYPE_SIGNALS: dict[str, dict[str, Any]] = {
    "Transformation Proposal": {
        "keywords": [
            "transformation",
            "proposal",
            "transform",
            "change program",
            "future state",
            "operating model",
            "modernization",
            "modernize",
            "roadmap",
            "target state",
        ],
        "intent_slide_types": ["operating_model", "current_future"],
    },
    "AI Strategy": {
        "keywords": [
            "ai strategy",
            "artificial intelligence",
            "machine learning",
            "ai roadmap",
            "ai vision",
            "ai use cases",
            "generative ai",
            "genai",
            "ai governance",
            "ai adoption",
        ],
        "intent_slide_types": ["process_flow", "operating_model"],
    },
    "Operating Model Assessment": {
        "keywords": [
            "operating model assessment",
            "target operating model",
            "operating model design",
            "org model",
            "organization model",
            "current operating model",
            "tom",
            "operating model",
        ],
        "intent_slide_types": ["operating_model", "current_future"],
    },
    "Current State Assessment": {
        "keywords": [
            "current state",
            "current state assessment",
            "as-is",
            "as is",
            "baseline",
            "current process",
            "process assessment",
            "pain points",
        ],
        "intent_slide_types": ["current_future", "process_flow", "operating_model"],
    },
    "Future State Vision": {
        "keywords": [
            "future state",
            "future state vision",
            "to-be",
            "to be",
            "vision",
            "target state",
            "future operating model",
            "strategic vision",
        ],
        "intent_slide_types": ["current_future", "operating_model"],
    },
    "Board Update": {
        "keywords": [
            "board update",
            "board readout",
            "board of directors",
            "steering committee",
            "program update",
            "status update",
            "executive update",
            "board meeting",
            "board deck",
            "board",
        ],
        "intent_slide_types": ["current_future", "process_flow"],
    },
    "Capability Overview": {
        "keywords": [
            "capability overview",
            "capability map",
            "capability framework",
            "capabilities",
            "capability assessment",
            "capability model",
            "competency",
            "competencies",
        ],
        "intent_slide_types": ["operating_model", "current_future"],
    },
    "Maturity Assessment": {
        "keywords": [
            "maturity assessment",
            "maturity model",
            "maturity level",
            "capability maturity",
            "digital maturity",
            "process maturity",
            "maturity gap",
        ],
        "intent_slide_types": ["current_future", "operating_model"],
    },
    "Due Diligence": {
        "keywords": [
            "due diligence",
            "diligence",
            "m&a",
            "merger",
            "acquisition",
            "target company",
            "investment memo",
            "commercial diligence",
            "technology diligence",
            "vendor diligence",
        ],
        "intent_slide_types": ["comparison", "operating_model"],
    },
    "Roadmap": {
        "keywords": [
            "roadmap",
            "implementation roadmap",
            "initiative roadmap",
            "program roadmap",
            "sequencing",
            "milestones",
            "phased approach",
            "rollout plan",
        ],
        "intent_slide_types": ["process_flow", "current_future"],
    },
}


class _TaxonomyCache:
    """Simple cache for the parsed taxonomy file."""

    def __init__(self) -> None:
        self._data: dict[str, Any] | None = None

    def load(self) -> dict[str, Any]:
        if self._data is None:
            self._data = json.loads(_TAXONOMY_PATH.read_text(encoding="utf-8"))
        return self._data


_taxonomy_cache = _TaxonomyCache()


def classify_presentation(user_prompt: str, intent: IntentResult) -> PresentationClassification:
    """
    Classify the user request into a presentation taxonomy type.

    Uses deterministic keyword + intent scoring as the primary path. If the
    resulting confidence is below the threshold, invokes an LLM fallback.
    """
    logger.info("classifying presentation for prompt: %r", user_prompt)

    deterministic = _deterministic_classify(user_prompt, intent)
    logger.info(
        "deterministic classification: type=%s confidence=%.2f",
        deterministic.presentation_type,
        deterministic.confidence,
    )

    if deterministic.confidence >= _CONFIDENCE_THRESHOLD:
        return deterministic

    logger.info(
        "deterministic confidence %.2f below threshold %.2f; invoking LLM fallback",
        deterministic.confidence,
        _CONFIDENCE_THRESHOLD,
    )
    try:
        return _llm_classify(user_prompt, intent)
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM classification failed; using deterministic result: %s", exc)
        return deterministic


def _deterministic_classify(user_prompt: str, intent: IntentResult) -> PresentationClassification:
    """
    Score each presentation type using keyword overlap and intent signals.

    The user prompt, title, and content are combined so that explicit titles
    reinforce the classification. Multi-word keyword phrases (e.g., "board
    update") are weighted more heavily than single-word matches because they are
    stronger classification signals.

    Confidence is normalized against a target high-confidence score so that
    clear keyword matches return high confidence and sparse matches return low
    confidence, triggering the LLM fallback when needed.
    """
    combined_text = _normalize_text(
        " ".join(
            part
            for part in (
                user_prompt,
                intent.raw_title,
                intent.raw_content,
            )
            if part
        )
    )
    taxonomy = _taxonomy_cache.load()
    available_types = set(taxonomy.get("presentation_types", {}).keys())

    scores: dict[str, float] = {}
    matched_keywords: dict[str, list[str]] = {}

    for presentation_type, signals in _TYPE_SIGNALS.items():
        if presentation_type not in available_types:
            continue

        keyword_hits: list[str] = []
        score = 0.0
        for keyword in signals["keywords"]:
            if keyword in combined_text:
                keyword_hits.append(keyword)
                # Phrase matches (multi-word) are stronger signals.
                score += 2.0 if " " in keyword else 1.0

        matched_keywords[presentation_type] = keyword_hits

        # Intent slide-type signal.
        if intent.slide_type in signals.get("intent_slide_types", []):
            score += 2.0

        # Business-function applicability signal from taxonomy knowledge.
        type_info = taxonomy["presentation_types"].get(presentation_type, {})
        applicable_functions = type_info.get("business_function_applicability", [])
        if intent.business_function and intent.business_function in applicable_functions:
            score += 1.0

        scores[presentation_type] = score

    if not scores:
        return PresentationClassification(
            presentation_type="Transformation Proposal",
            confidence=0.0,
            reasoning_summary="No classification signals available; defaulting to Transformation Proposal.",
        )

    best_type = max(scores, key=scores.get)  # type: ignore[arg-type]
    best_score = scores[best_type]

    # Normalize against a target score of 8.0, which represents a strong match
    # of multiple keywords (including phrase matches) plus intent/function signals.
    confidence = min(1.0, best_score / 8.0)

    reasoning = _build_reasoning_summary(
        best_type,
        best_score,
        matched_keywords.get(best_type, []),
        intent,
    )

    return PresentationClassification(
        presentation_type=best_type,
        confidence=round(confidence, 2),
        reasoning_summary=reasoning,
    )


def _build_reasoning_summary(
    presentation_type: str,
    score: float,
    keyword_hits: list[str],
    intent: IntentResult,
) -> str:
    """Produce a concise, human-readable reasoning summary."""
    reasons: list[str] = []
    if keyword_hits:
        joined = ", ".join(keyword_hits[:5])
        reasons.append(f"matched keywords: {joined}")
    if intent.slide_type and intent.slide_type in _TYPE_SIGNALS.get(presentation_type, {}).get(
        "intent_slide_types", []
    ):
        reasons.append(f"intent slide_type '{intent.slide_type}' aligns with this type")
    if intent.business_function:
        reasons.append(f"business function '{intent.business_function}' is applicable")

    if not reasons:
        reasons.append("selected as best available match based on weak signals")

    return f"{presentation_type} selected (score={score:.1f}) because " + "; ".join(reasons) + "."


def _llm_classify(user_prompt: str, intent: IntentResult) -> PresentationClassification:
    """
    LLM fallback classifier for ambiguous or low-confidence requests.

    Uses the curated taxonomy as the allowed set of presentation types.
    Routed through the multi-provider LLM router so OpenAI is preferred when
    configured, with Gemini as a fallback.
    """
    from backend.llm import router

    taxonomy = _taxonomy_cache.load()
    allowed_types = list(taxonomy.get("presentation_types", {}).keys())

    user_input = json.dumps(
        {
            "user_prompt": user_prompt,
            "intent": intent.model_dump(mode="json"),
            "allowed_presentation_types": allowed_types,
        },
        ensure_ascii=True,
    )

    prompt = build_prompt(
        "presentation_classifier",
        user_input=user_input,
        additional_context="Input:",
    )
    payload = router.generate_json("presentation_classifier", prompt, temperature=0.1)
    if not isinstance(payload, dict):
        raise ValueError("LLM classifier response was not a JSON object.")

    return PresentationClassification(
        presentation_type=_clean_text(payload.get("presentation_type")) or allowed_types[0],
        confidence=float(payload.get("confidence", 0.5)),
        reasoning_summary=_clean_text(payload.get("reasoning_summary"))
        or "Classified via LLM fallback.",
    )


def _normalize_text(text: str | None) -> str:
    """Lowercase, collapse whitespace, and remove non-alphanumeric punctuation."""
    if not text:
        return ""
    lowered = text.lower()
    # Keep internal spaces and alphanumerics; replace other punctuation with space.
    normalized = re.sub(r"[^a-z0-9\s]", " ", lowered)
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

"""
backend/modules/presentation_planner.py
=======================================
Sprint E.1 — Intelligent Narrative Planner.

This module is responsible ONLY for planning the consulting narrative.
It does NOT generate slide content, KPIs, business activities, pain points,
or rendering instructions.

Inputs:
    - The original user prompt (str).
    - A structured IntentResult.

Output:
    - A DeckSpec describing the deck plan: presentation type, objective,
      audience, narrative, estimated slide count, and an ordered sequence
      of SlidePlan objects.

Behavior:
    1. Classify the request using the Presentation Classifier.
    2. Load the matching taxonomy entry from presentation_taxonomy.json.
    3. Use the taxonomy as the narrative scaffold.
    4. Adapt/customize the scaffold to the user's specific prompt via LLM.
    5. Return the validated DeckSpec.

If the LLM is unavailable, the planner falls back to a taxonomy-grounded
plan personalized with intent fields.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from backend.llm.prompt_loader import build_prompt
from backend.modules.presentation_classifier import classify_presentation
from schemas.intent import IntentResult
from schemas.presentation import DeckSpec, PresentationClassification, SlidePlan

logger = logging.getLogger(__name__)

_DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
_TAXONOMY_PATH = Path(__file__).resolve().parents[1] / "knowledge" / "presentation_taxonomy.json"


class _TaxonomyCache:
    """Simple cache for the parsed presentation taxonomy."""

    def __init__(self) -> None:
        self._data: dict[str, Any] | None = None

    def load(self) -> dict[str, Any]:
        if self._data is None:
            self._data = json.loads(_TAXONOMY_PATH.read_text(encoding="utf-8"))
        return self._data


_taxonomy_cache = _TaxonomyCache()


def plan_presentation(user_prompt: str, intent: IntentResult) -> DeckSpec:
    """
    Plan a consulting deck from the original user prompt and extracted intent.

    The original user prompt is the primary input. IntentResult provides
    structured context such as company, industry, and business function.

    Parameters
    ----------
    user_prompt:
        The original request from the consultant.
    intent:
        Structured intent extracted from the request.

    Returns
    -------
    DeckSpec
        A pure planning artifact describing what deck should be created.
        If the LLM fails, a deterministic taxonomy-grounded fallback plan
        is returned.
    """
    logger.info(
        "planning presentation: user_prompt=%r company=%s function=%s",
        user_prompt,
        intent.company or "Unknown",
        intent.business_function or "Unknown",
    )

    classification = classify_presentation(user_prompt, intent)
    logger.info(
        "presentation classified as %s (confidence=%.2f)",
        classification.presentation_type,
        classification.confidence,
    )

    taxonomy = _taxonomy_cache.load()
    taxonomy_entry = _get_taxonomy_entry(taxonomy, classification)

    try:
        raw_response = _call_presentation_planner_llm(
            user_prompt, intent, classification, taxonomy_entry
        )
        payload = json.loads(_strip_json_fence(raw_response))
        if not isinstance(payload, dict):
            raise ValueError("Presentation planner LLM response was not a JSON object.")
        return _to_deck_spec(payload)
    except Exception as exc:  # noqa: BLE001 - fallback keeps planner runnable.
        logger.warning("presentation planner LLM failed; using taxonomy fallback: %s", exc)
        return _taxonomy_fallback_deck(user_prompt, intent, classification, taxonomy_entry)


def _get_taxonomy_entry(
    taxonomy: dict[str, Any], classification: PresentationClassification
) -> dict[str, Any]:
    """Return the taxonomy entry for the classified presentation type."""
    types = taxonomy.get("presentation_types", {})
    entry = types.get(classification.presentation_type)
    if not isinstance(entry, dict):
        logger.warning(
            "unknown presentation type %r; falling back to Transformation Proposal",
            classification.presentation_type,
        )
        entry = types.get("Transformation Proposal", {})
    return entry if isinstance(entry, dict) else {}


def _call_presentation_planner_llm(
    user_prompt: str,
    intent: IntentResult,
    classification: PresentationClassification,
    taxonomy_entry: dict[str, Any],
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

    scaffold = _build_taxonomy_scaffold(taxonomy_entry)
    user_input = {
        "user_prompt": user_prompt,
        "intent": intent.model_dump(mode="json"),
        "classification": classification.model_dump(mode="json"),
        "taxonomy_scaffold": scaffold,
    }

    client = genai.Client(api_key=api_key)
    prompt = build_prompt(
        "presentation_planner",
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


def _build_taxonomy_scaffold(taxonomy_entry: dict[str, Any]) -> dict[str, Any]:
    """Extract the parts of the taxonomy that guide the planner LLM."""
    return {
        "description": taxonomy_entry.get("description", ""),
        "objective": taxonomy_entry.get("objective", ""),
        "expected_audience": taxonomy_entry.get("expected_audience", ""),
        "consulting_narrative": taxonomy_entry.get("consulting_narrative", ""),
        "default_slide_sequence": taxonomy_entry.get("default_slide_sequence", []),
        "visualization_preferences": taxonomy_entry.get("visualization_preferences", {}),
        "optional_slides": taxonomy_entry.get("optional_slides", []),
    }


def _to_deck_spec(payload: dict[str, Any]) -> DeckSpec:
    """Convert the parsed LLM JSON payload into a validated DeckSpec."""
    slides_data = payload.get("slides", [])
    if not isinstance(slides_data, list):
        slides_data = []

    slides: list[SlidePlan] = []
    for index, item in enumerate(slides_data, start=1):
        if not isinstance(item, dict):
            continue
        slide_number = int(item.get("slide_number", index))
        slides.append(
            SlidePlan(
                slide_number=slide_number,
                slide_role=_clean_text(item.get("slide_role")) or f"Slide {slide_number}",
                purpose=_clean_text(item.get("purpose")) or "Communicate the key message.",
                required_inputs=_clean_string_list(item.get("required_inputs", [])),
                dependencies=_clean_string_list(item.get("dependencies", [])),
                visualization_type=_clean_text(item.get("visualization_type")) or "Executive Summary",
            )
        )

    estimated = int(payload.get("estimated_slide_count", len(slides)))
    if estimated != len(slides):
        logger.warning(
            "presentation planner returned mismatched slide count: estimated=%d actual=%d",
            estimated,
            len(slides),
        )
        estimated = len(slides)

    return DeckSpec(
        presentation_type=_clean_text(payload.get("presentation_type")) or "Consulting Deck",
        objective=_clean_text(payload.get("objective")) or "Align stakeholders on the path forward.",
        audience=_clean_text(payload.get("audience")) or "Senior client leadership",
        narrative=_clean_text(payload.get("narrative")) or "Situation → Complication → Resolution",
        estimated_slide_count=max(estimated, 1),
        slides=slides,
    )


def _taxonomy_fallback_deck(
    user_prompt: str,
    intent: IntentResult,
    classification: PresentationClassification,
    taxonomy_entry: dict[str, Any],
) -> DeckSpec:
    """
    Deterministic fallback deck rooted in the taxonomy scaffold.

    Personalizes objective/audience with intent fields and follows the
    taxonomy's default slide sequence.
    """
    company = _intent_value_or_default(intent.company, "the organization")
    business_function = _intent_value_or_default(intent.business_function, "")

    base_objective = _clean_text(taxonomy_entry.get("objective")) or "Align stakeholders."
    base_audience = _clean_text(taxonomy_entry.get("expected_audience")) or "Senior client leadership"
    narrative = _clean_text(taxonomy_entry.get("consulting_narrative")) or "Situation → Complication → Resolution"

    objective = _personalize_text(base_objective, company, business_function)
    audience = _personalize_text(base_audience, company, business_function)

    sequence = taxonomy_entry.get("default_slide_sequence", [])
    if not isinstance(sequence, list) or not sequence:
        # Ultimate fallback if taxonomy entry is empty.
        return _minimal_fallback_deck(classification, company, business_function)

    visualization_preferences = taxonomy_entry.get("visualization_preferences", {}) or {}
    if not isinstance(visualization_preferences, dict):
        visualization_preferences = {}

    slides: list[SlidePlan] = []
    previous_roles: list[str] = []
    for index, item in enumerate(sequence, start=1):
        if not isinstance(item, dict):
            continue
        role = _clean_text(item.get("slide_role")) or f"Slide {index}"
        purpose_template = _clean_text(item.get("purpose")) or f"Communicate the {role} message."
        purpose = _personalize_text(purpose_template, company, business_function)
        visualization = _clean_text(item.get("visualization_type")) or visualization_preferences.get(
            role, "Executive Summary"
        )
        required_inputs = _clean_string_list(item.get("required_inputs", []))

        slides.append(
            SlidePlan(
                slide_number=index,
                slide_role=role,
                purpose=purpose,
                required_inputs=required_inputs,
                dependencies=list(previous_roles),
                visualization_type=visualization,
            )
        )
        previous_roles.append(role)

    return DeckSpec(
        presentation_type=classification.presentation_type,
        objective=objective,
        audience=audience,
        narrative=narrative,
        estimated_slide_count=len(slides),
        slides=slides,
    )


def _minimal_fallback_deck(
    classification: PresentationClassification, company: str, business_function: str
) -> DeckSpec:
    """Minimal ultimate fallback when taxonomy data is missing."""
    effective_company = company or "the organization"
    effective_function = business_function or "business"
    return DeckSpec(
        presentation_type=classification.presentation_type,
        objective=f"Align {effective_company} leadership on a prioritized {effective_function} initiative.",
        audience="Senior client leadership",
        narrative="Executive Summary → Current State → Future State → Roadmap → Next Steps",
        estimated_slide_count=1,
        slides=[
            SlidePlan(
                slide_number=1,
                slide_role="Executive Summary",
                purpose=f"Frame the recommendation for {effective_company}'s {effective_function} initiative.",
                required_inputs=[],
                dependencies=[],
                visualization_type="Executive Summary",
            )
        ],
    )


def _intent_value_or_default(value: str | None, default: str) -> str:
    """Return the intent value if it is meaningful, otherwise the default."""
    cleaned = _clean_text(value)
    if cleaned and cleaned.lower() not in ("unknown", "n/a", ""):
        return cleaned
    return default


def _personalize_text(text: str, company: str, business_function: str) -> str:
    """
    Inject company and business function placeholders into a template string.

    Empty or unknown values are replaced with sensible defaults and any double
    spaces introduced by empty substitutions are collapsed.
    """
    effective_company = company or "the organization"
    effective_function = business_function or ""
    personalized = text.replace("{company}", effective_company).replace(
        "{business_function}", effective_function
    )
    return " ".join(personalized.split())


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


def _clean_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]

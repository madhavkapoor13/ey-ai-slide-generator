"""
backend/modules/presentation_planner.py
=======================================
Sprint B.1 — Presentation Planner module.

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
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from dotenv import load_dotenv

from backend.llm.prompt_loader import build_prompt
from schemas.intent import IntentResult
from schemas.presentation import DeckSpec, SlidePlan

logger = logging.getLogger(__name__)

_DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"


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
        If the LLM fails, a deterministic fallback plan is returned.
    """
    logger.info(
        "planning presentation: user_prompt=%r company=%s function=%s",
        user_prompt,
        intent.company or "Unknown",
        intent.business_function or "Unknown",
    )

    try:
        raw_response = _call_presentation_planner_llm(user_prompt, intent)
        payload = json.loads(_strip_json_fence(raw_response))
        if not isinstance(payload, dict):
            raise ValueError("Presentation planner LLM response was not a JSON object.")
        return _to_deck_spec(payload)
    except Exception as exc:  # noqa: BLE001 - fallback keeps planner runnable.
        logger.warning("presentation planner LLM failed; using fallback: %s", exc)
        return _fallback_deck(user_prompt, intent)


def _call_presentation_planner_llm(user_prompt: str, intent: IntentResult) -> str:
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
        "user_prompt": user_prompt,
        "intent": intent.model_dump(mode="json"),
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


def _fallback_deck(user_prompt: str, intent: IntentResult) -> DeckSpec:
    """
    Deterministic fallback deck when the LLM is unavailable.

    Produces a minimal, defensible consulting narrative without content.
    """
    company = _clean_text(intent.company) or "the client"
    business_function = _clean_text(intent.business_function) or "the business function"

    slide_roles = [
        ("Executive Summary", "Frame the recommendation and the decision required."),
        ("Current State", f"Describe the current state of {business_function} at {company}."),
        ("Opportunities", "Identify the improvement opportunities for consideration."),
        ("Future State", "Articulate the target operating model."),
        ("Roadmap", "Outline the high-level implementation path."),
        ("Next Steps", "Define immediate actions and decision points."),
    ]

    slides: list[SlidePlan] = []
    dependencies: list[str] = []
    for index, (role, purpose) in enumerate(slide_roles, start=1):
        slide_dependencies = list(dependencies)
        visualization = "Executive Summary" if role == "Executive Summary" else "Process Flow"
        slides.append(
            SlidePlan(
                slide_number=index,
                slide_role=role,
                purpose=purpose,
                required_inputs=[],
                dependencies=slide_dependencies,
                visualization_type=visualization,
            )
        )
        dependencies.append(role)

    return DeckSpec(
        presentation_type="Transformation Proposal",
        objective=f"Align {company} leadership on a prioritized {business_function} transformation path.",
        audience="Senior client leadership",
        narrative="Current State → Opportunities → Future State → Roadmap → Next Steps",
        estimated_slide_count=len(slides),
        slides=slides,
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


def _clean_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]

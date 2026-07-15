"""
backend/modules/clarification.py
================================
Sprint C — Clarification Engine module.

Generates the minimum number of clarification questions needed to resolve
missing information before planning a consulting deck.

Content questions are generated whenever required. Visualization questions
are generated only when the visualization choice is genuinely ambiguous or
cannot be inferred from the prompt or deck plan.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from backend.llm.prompt_loader import build_prompt
from schemas.clarification import ClarificationQuestion, ClarificationResult
from schemas.information import InformationResult
from schemas.presentation import DeckSpec

logger = logging.getLogger(__name__)

_CONTENT_QUESTIONS: dict[str, dict[str, Any]] = {
    "company": {
        "question": "Which company or client is this deck for?",
        "reason": "The request does not name a company or client.",
    },
    "industry": {
        "question": "Which industry or sector does this relate to?",
        "reason": "The request does not specify an industry or sector.",
    },
    "business_function": {
        "question": "Which business function is in scope (e.g., Finance, Procurement, HR, Supply Chain)?",
        "reason": "The request does not specify a business function.",
    },
    "audience": {
        "question": "Who is the intended audience for this deck?",
        "reason": "The request does not specify who will view the deck.",
    },
    "objective": {
        "question": "What decision or alignment should this deck produce?",
        "reason": "The request does not state the deck's objective.",
    },
}

_VISUALIZATION_SIGNALS: frozenset[str] = frozenset(
    [
        "process flow",
        "timeline",
        "roadmap",
        "comparison",
        "matrix",
        "capability map",
        "infographic",
        "swimlane",
        "chart",
        "diagram",
    ]
)


def generate_clarifications(
    user_prompt: str,
    deck_spec: DeckSpec,
    information_result: InformationResult,
) -> ClarificationResult:
    """
    Generate the minimum clarification questions for a deck request.

    Parameters
    ----------
    user_prompt:
        The original request from the consultant.
    deck_spec:
        Deck plan produced by the Presentation Planner.
    information_result:
        Output of the Information Analyzer.

    Returns
    -------
    ClarificationResult
        Separated content and visualization questions.
    """
    logger.info(
        "generating clarifications: missing=%s",
        information_result.missing_fields,
    )

    content_questions = _build_content_questions(information_result.missing_fields)

    try:
        visualization_questions = _generate_visualization_questions(
            user_prompt, deck_spec, information_result
        )
    except Exception as exc:  # noqa: BLE001 - fallback keeps engine runnable.
        logger.warning("visualization question generation failed; using fallback: %s", exc)
        visualization_questions = _fallback_visualization_questions(
            user_prompt, deck_spec, information_result
        )

    all_questions = content_questions + visualization_questions
    return ClarificationResult(
        needs_clarification=len(all_questions) > 0,
        content_questions=content_questions,
        visualization_questions=visualization_questions,
    )


def _build_content_questions(missing_fields: list[str]) -> list[ClarificationQuestion]:
    questions: list[ClarificationQuestion] = []
    for field in missing_fields:
        if field not in _CONTENT_QUESTIONS:
            continue
        template = _CONTENT_QUESTIONS[field]
        questions.append(
            ClarificationQuestion(
                id=field,
                category="content",
                question=template["question"],
                required=True,
                reason=template["reason"],
            )
        )
    return questions


def _generate_visualization_questions(
    user_prompt: str,
    deck_spec: DeckSpec,
    information_result: InformationResult,
) -> list[ClarificationQuestion]:
    if information_result.missing_fields and len(information_result.missing_fields) >= 3:
        # If many content fields are missing, defer visualization choice until content is resolved.
        return []

    ambiguity = _visualization_ambiguity(user_prompt, deck_spec)
    if not ambiguity["is_ambiguous"]:
        return []

    return _fallback_visualization_questions(user_prompt, deck_spec, information_result)


def _visualization_ambiguity(user_prompt: str, deck_spec: DeckSpec) -> dict[str, Any]:
    """
    Determine whether the visualization choice is ambiguous.

    Returns a dict with:
        - is_ambiguous: bool
        - detected_signals: list of visualization signals found
    """
    combined = f"{user_prompt} {deck_spec.presentation_type or ''}".lower()
    detected = [signal for signal in _VISUALIZATION_SIGNALS if signal in combined]

    if not detected:
        # No explicit visualization signal; ambiguous only if deck type suggests visual content.
        visual_presentation_types = {"roadmap", "comparison", "process flow", "timeline"}
        pt_lower = (deck_spec.presentation_type or "").lower()
        if any(vt in pt_lower for vt in visual_presentation_types):
            return {"is_ambiguous": True, "detected_signals": []}
        return {"is_ambiguous": False, "detected_signals": []}

    if len(detected) == 1:
        # Exactly one signal found; visualization is inferable.
        return {"is_ambiguous": False, "detected_signals": detected}

    # Multiple signals found; ambiguous.
    return {"is_ambiguous": True, "detected_signals": detected}


def _fallback_visualization_questions(
    user_prompt: str,
    deck_spec: DeckSpec,
    information_result: InformationResult,
) -> list[ClarificationQuestion]:
    ambiguity = _visualization_ambiguity(user_prompt, deck_spec)
    if not ambiguity["is_ambiguous"]:
        return []

    detected = ambiguity["detected_signals"]
    if len(detected) > 1:
        return [
            ClarificationQuestion(
                id="visualization_preference",
                category="visualization",
                question=f"Which visualization type would best communicate this deck: {', '.join(detected)}?",
                required=False,
                reason="Multiple visualization signals were detected in the request.",
            )
        ]

    # No signal detected but deck type suggests a visual.
    return [
        ClarificationQuestion(
            id="visualization_preference",
            category="visualization",
            question="What visualization type would best communicate this deck (e.g., roadmap, process flow, comparison, timeline)?",
            required=False,
            reason="The request does not specify how the deck should be visualized.",
        )
    ]


def _call_clarification_llm(
    user_prompt: str,
    deck_spec: DeckSpec,
    information_result: InformationResult,
) -> dict[str, Any]:
    from backend.llm import router

    user_input = {
        "missing_fields": information_result.missing_fields,
        "user_prompt": user_prompt,
        "deck_spec": deck_spec.model_dump(mode="json"),
    }

    prompt = build_prompt(
        "clarification",
        user_input=json.dumps(user_input, ensure_ascii=True),
        additional_context="Input:",
    )
    return router.generate_json("clarification", prompt, temperature=0.2)

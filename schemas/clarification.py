"""
schemas/clarification.py
========================
Sprint C schema — output of the Clarification Engine module.

ClarificationResult separates content clarification questions from
visualization clarification questions. The engine asks the minimum number
of questions necessary to resolve missing information.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ClarificationQuestion(BaseModel):
    """
    A single clarification question for the user.

    Attributes
    ----------
    id:
        Stable identifier for the question.
    category:
        "content" for substance questions, "visualization" for visual-format questions.
    question:
        The question text shown to the user.
    required:
        Whether the answer is required before planning can continue.
    reason:
        Why this question is being asked.
    """

    id: str = Field(..., description="Stable question identifier.")
    category: str = Field(
        ...,
        description="Question category: content | visualization",
    )
    question: str = Field(..., description="Question text for the user.")
    required: bool = Field(
        ...,
        description="Whether an answer is required to proceed.",
    )
    reason: str = Field(..., description="Why this question is needed.")


class ClarificationResult(BaseModel):
    """
    Complete set of clarification questions generated for a request.

    Attributes
    ----------
    needs_clarification:
        True when at least one question is present.
    content_questions:
        Substance questions (company, audience, objective, business function, etc.).
    visualization_questions:
        Visual-format questions, generated only when the visualization choice
        is genuinely ambiguous or cannot be inferred from the prompt.
    """

    needs_clarification: bool = Field(
        ...,
        description="Whether any clarification questions were generated.",
    )
    content_questions: list[ClarificationQuestion] = Field(
        default_factory=list,
        description="Content clarification questions.",
    )
    visualization_questions: list[ClarificationQuestion] = Field(
        default_factory=list,
        description="Visualization clarification questions (only when ambiguous).",
    )

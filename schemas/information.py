"""
schemas/information.py
======================
Sprint C schema — output of the Information Analyzer module.

InformationResult captures a deterministic assessment of whether enough
information exists to generate a consulting deck. It does not ask questions;
it only detects missing information and records confidence in the assessment.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


ConfidenceLevel = Literal["high", "medium", "low"]


class InformationResult(BaseModel):
    """
    Deterministic assessment of information completeness for deck planning.

    Attributes
    ----------
    has_enough_information:
        True when all required fields are present and credible.
    missing_fields:
        List of required fields that are missing or too vague.
        Possible values: company, industry, audience, objective, business_function.
    analysis:
        Short explanation of what was inferred and what is missing.
    confidence:
        high — all required fields present.
        medium — most fields present but some inferred.
        low — several fields missing.
    """

    has_enough_information: bool = Field(
        ...,
        description="Whether sufficient information exists to plan a deck.",
    )
    missing_fields: list[str] = Field(
        default_factory=list,
        description="Required fields that are missing or too vague.",
    )
    analysis: str = Field(
        ...,
        description="Explanation of what was inferred and what is missing.",
    )
    confidence: ConfidenceLevel = Field(
        ...,
        description="Confidence in the completeness assessment: high | medium | low",
    )

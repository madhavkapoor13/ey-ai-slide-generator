"""
schemas/validation.py
=====================
Phase 2 schema — output of the Validation Module.

ValidationResult wraps the validated SlideSpec together with per-claim
quality metadata so that callers can decide whether to surface warnings,
reject the spec, or proceed to rendering.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

# Forward reference — resolved at runtime; avoids a circular import.
from schemas.slide_spec import SlideSpec


class ClaimMetadata(BaseModel):
    """
    Quality metadata for a single factual claim found in the generated content.

    Attributes
    ----------
    claim:
        The verbatim claim string extracted from the generated slide content.
    verified:
        Whether the claim has been corroborated against enterprise context
        or an external knowledge source.
    confidence:
        Float in [0.0, 1.0] representing verification confidence.
    """

    claim: str = Field(..., description="Verbatim claim string from the generated content.")
    verified: bool = Field(
        default=False,
        description="Whether the claim has been corroborated.",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Verification confidence score (0.0–1.0).",
    )


class ValidationResult(BaseModel):
    """
    Output of the Validation Module.

    Attributes
    ----------
    is_valid:
        Top-level gate: True means the SlideSpec is safe to render.
    issues:
        List of human-readable issue strings. Empty when ``is_valid=True``.
    claims:
        Per-claim quality metadata extracted during validation.
    validated_spec:
        The (potentially corrected) SlideSpec ready for rendering.
        None only when validation has fatally rejected the content.
    """

    is_valid: bool = Field(..., description="True if the SlideSpec is safe to pass to the renderer.")
    issues: list[str] = Field(
        default_factory=list,
        description="Human-readable list of issues detected during validation.",
    )
    claims: list[ClaimMetadata] = Field(
        default_factory=list,
        description="Per-claim quality metadata from the validation step.",
    )
    validated_spec: Optional[SlideSpec] = Field(
        default=None,
        description="The validated (and optionally corrected) SlideSpec. None on fatal rejection.",
    )

"""
backend/models.py
=================
FastAPI request and response models.

Phase 1 models
--------------
Phase 1 uses ``SlideRequest`` defined inline in ``routes.py``.
That model is NOT duplicated here to avoid breaking the existing route.

Phase 2 models
--------------
All Phase 2 models are defined below. They are intentionally kept
separate from Phase 1 to allow independent versioning.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from schemas.clarification import ClarificationResult
from schemas.intent import IntentResult
from schemas.presentation import DeckSpec
from schemas.presentation_asset import UserPreferences


# ── Phase 2 Request ───────────────────────────────────────────────────────────

class GenerateV2Request(BaseModel):
    """
    Request body for ``POST /generate/v2``.

    Mirrors the shape of the Phase 1 ``SlideRequest`` for backwards
    compatibility in client code, but is versioned separately so
    Phase 2 can add fields (e.g. ``industry``, ``tone``) without
    affecting Phase 1.

    Attributes
    ----------
    title:
        Slide title provided by the user.
    content:
        Slide content / description provided by the user.
    preferences:
        Optional explicit style/audience preferences that bias Presentation
        Asset retrieval. When omitted, the pipeline infers a conservative
        default from the prompt (audience from IntentResult.audience;
        style from prompt cues like "board-level", "minimal"). Explicit
        preferences always win; inferred preferences are a fallback only.
    """

    title: str = Field(..., description="Slide title provided by the user.")
    content: str = Field(..., description="Slide content or description provided by the user.")
    preferences: Optional[UserPreferences] = Field(
        default=None,
        description="Optional explicit user preferences; overrides inferred defaults.",
    )


class PlanV2Request(GenerateV2Request):
    """Request body for ``POST /plan/v2``."""


class SlideVariantOption(BaseModel):
    """One visual variant the user can choose for a planned slide."""

    variant_id: str = Field(..., description="User-facing visual variant identifier.")
    asset_id: str = Field(..., description="Presentation Asset id backing the variant.")
    label: str = Field(..., description="Human-readable variant label.")


class SlidePlanVariantOptions(BaseModel):
    """Available and recommended visual variants for one planned slide."""

    slide_number: int = Field(..., ge=1, description="Slide number from the deck plan.")
    slide_role: str = Field(..., description="Slide role from the deck plan.")
    slide_type: Optional[str] = Field(default=None, description="Resolved pilot slide type.")
    recommended_variant: Optional[str] = Field(default=None, description="Recommended variant id.")
    available_variants: list[SlideVariantOption] = Field(default_factory=list)


class PlanV2Response(BaseModel):
    """JSON plan preview returned before PowerPoint generation."""

    title: str = Field(..., description="Original request title.")
    content: str = Field(..., description="Original request content.")
    intent: IntentResult = Field(..., description="Structured intent extracted from the prompt.")
    deck_spec: DeckSpec = Field(..., description="Editable deck plan.")
    needs_clarification: bool = Field(default=False)
    clarification_result: Optional[ClarificationResult] = Field(default=None)
    warnings: list[str] = Field(default_factory=list)
    slide_variants: list[SlidePlanVariantOptions] = Field(default_factory=list)


class GenerateFromPlanV2Request(GenerateV2Request):
    """Request body for ``POST /generate/v2/from-plan``."""

    deck_spec: DeckSpec = Field(..., description="User-approved edited deck plan.")


# ── Phase 2 Response ──────────────────────────────────────────────────────────

class GenerateV2Response(BaseModel):
    """
    Metadata response envelope for ``POST /generate/v2``.

    The actual slide file is returned as a ``FileResponse``.
    This model is used for error responses and future JSON-mode support.

    Attributes
    ----------
    pipeline_version:
        Identifies which pipeline produced the result.
    slide_type:
        The slide type that was detected and rendered.
    is_valid:
        Whether the validation module passed the generated spec.
    issues:
        Any non-fatal validation issues detected during generation.
    """

    pipeline_version: str = Field(
        default="v2",
        description="Pipeline version identifier.",
    )
    slide_type: str = Field(..., description="Detected and rendered slide type.")
    is_valid: bool = Field(..., description="Whether the validation module passed the spec.")
    issues: list[str] = Field(
        default_factory=list,
        description="Non-fatal validation issues detected during generation.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Extensible metadata bag for future enrichment.",
    )

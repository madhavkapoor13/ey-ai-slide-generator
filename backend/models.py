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

from typing import Any

from pydantic import BaseModel, Field


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
    """

    title: str = Field(..., description="Slide title provided by the user.")
    content: str = Field(..., description="Slide content or description provided by the user.")


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

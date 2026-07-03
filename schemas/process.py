"""
schemas/process.py
==================
Sprint 3 schema — output of the Enterprise Process Mapper module.

ProcessResult identifies the most appropriate enterprise process for the
requested business function. It does not contain slide content, KPIs,
pain points, activities, or executive summaries.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ProcessStage(BaseModel):
    """A named stage within a standard enterprise process."""

    name: str = Field(..., description="Stage name within the enterprise process.")


class ProcessResult(BaseModel):
    """
    Structured enterprise process definition selected by the process mapper.
    """

    process_name: str = Field(..., description="Canonical enterprise process name.")
    process_family: str = Field(..., description="Business function or process family.")
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence that the selected process matches the request.",
    )
    reasoning: str = Field(..., description="Concise factual reason for the selection.")
    stages: list[str] = Field(
        default_factory=list,
        description="High-level stages in the selected process.",
    )

"""
schemas/evaluation.py
=====================
Version 2 evaluation contracts for slide-level and deck-level quality signals.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class SlideEvaluationReport(BaseModel):
    """Structured debugging and quality report for one generated slide."""

    slide_number: int = Field(..., ge=1)
    role: str = ""
    slide_type: Optional[str] = None
    pattern: Optional[str] = None
    variant_id: Optional[str] = None
    template_source_slide: Optional[int] = None
    asset: Optional[str] = None
    asset_version: Optional[int] = None
    population: str = "not_attempted"
    missing_placeholders: int = 0
    content_completeness: float = Field(default=0.0, ge=0.0, le=1.0)
    text_fit: str = "not_checked"
    text_fit_failures: list[str] = Field(default_factory=list)
    consulting_language_warnings: list[str] = Field(default_factory=list)
    role_contract_failures: list[str] = Field(default_factory=list)
    placeholder_leakage: list[str] = Field(default_factory=list)
    fallback_used: bool = False
    fallback_asset: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)
    raw_spec: dict[str, Any] = Field(default_factory=dict)


class DeckEvaluationReport(BaseModel):
    """Aggregate quality metrics for a generated deck."""

    asset_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    variant_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    asset_diversity: float = Field(default=0.0, ge=0.0, le=1.0)
    repeated_asset_count: int = 0
    max_family_repetition: int = 0
    fallback_usage_by_family: dict[str, int] = Field(default_factory=dict)
    repeated_assets: list[str] = Field(default_factory=list)
    repeated_slide_titles: list[str] = Field(default_factory=list)
    repeated_slide_messages: list[str] = Field(default_factory=list)
    duplicate_roles: list[str] = Field(default_factory=list)
    missing_roles: list[str] = Field(default_factory=list)
    asset_family_mismatches: list[str] = Field(default_factory=list)
    consulting_language_warnings: list[str] = Field(default_factory=list)
    placeholder_leakage: list[str] = Field(default_factory=list)
    overflow_slides: list[int] = Field(default_factory=list)
    demo_ready: bool = False
    visual_diversity: float = Field(default=0.0, ge=0.0, le=1.0)
    average_content_completeness: float = Field(default=0.0, ge=0.0, le=1.0)
    text_fit_failure_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    planner_confidence: Optional[float] = None
    planner_confidence_min: Optional[float] = None
    low_confidence_roles: list[str] = Field(default_factory=list)
    asset_selector_confidence: Optional[float] = None
    narrative_consistency_warnings: list[str] = Field(default_factory=list)
    slide_reports: list[SlideEvaluationReport] = Field(default_factory=list)

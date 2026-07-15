"""
schemas/layout.py
=================
Sprint V3 — Visual Layout Engine schemas.

These models describe a reusable, normalized slide layout. They contain no
PowerPoint-specific code, coordinates, or shapes; all positions are expressed
as floats in the 0.0–1.0 range and will be converted by a renderer later.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class HeaderSpecification(BaseModel):
    """Normalized header region at the top of the slide."""

    height: float = Field(
        ..., ge=0.0, le=1.0, description="Header height as a fraction of the canvas."
    )
    title_area: Optional[dict[str, Any]] = Field(
        default=None,
        description="Optional normalized bounding box for the slide title.",
    )
    subtitle_area: Optional[dict[str, Any]] = Field(
        default=None,
        description="Optional normalized bounding box for the subtitle.",
    )
    description_area: Optional[dict[str, Any]] = Field(
        default=None,
        description=(
            "Optional normalized bounding box for the slide description. "
            "When absent, renderers compute a position just below the subtitle "
            "area so subtitle and description never overlap."
        ),
    )


class BodySpecification(BaseModel):
    """Normalized main content region of the slide."""

    x: float = Field(..., ge=0.0, le=1.0, description="Left position as a fraction of the canvas.")
    y: float = Field(..., ge=0.0, le=1.0, description="Top position as a fraction of the canvas.")
    width: float = Field(..., ge=0.0, le=1.0, description="Width as a fraction of the canvas.")
    height: float = Field(..., ge=0.0, le=1.0, description="Height as a fraction of the canvas.")


class FooterSpecification(BaseModel):
    """Normalized footer region at the bottom of the slide."""

    height: float = Field(
        ..., ge=0.0, le=1.0, description="Footer height as a fraction of the canvas."
    )
    note_area: Optional[dict[str, Any]] = Field(
        default=None,
        description="Optional normalized bounding box for footer notes or sources.",
    )


class ComponentSpecification(BaseModel):
    """A single layout component (card, node, cell, bar, etc.)."""

    component_id: str = Field(..., description="Unique identifier for this component.")
    type: str = Field(
        ...,
        description=(
            "Component type. Known types: card, kpi_card, executive_card, "
            "text, list_item, label, content_box, node, axis, bar, cell, "
            "column, icon, connector."
        ),
    )
    x: float = Field(..., ge=0.0, le=1.0, description="Left position as a fraction of the canvas.")
    y: float = Field(..., ge=0.0, le=1.0, description="Top position as a fraction of the canvas.")
    width: float = Field(..., ge=0.0, le=1.0, description="Width as a fraction of the canvas.")
    height: float = Field(..., ge=0.0, le=1.0, description="Height as a fraction of the canvas.")
    placeholder: str = Field(
        ...,
        description="Semantic placeholder key that content generation will fill.",
    )
    constraints: list[str] = Field(
        default_factory=list,
        description="Layout constraints for the renderer, e.g. max lines, icon position.",
    )


class LayoutSpecification(BaseModel):
    """
    Complete normalized layout for a visual pattern.

    Attributes
    ----------
    layout_id:
        Short layout identifier, e.g. ``"CL01"``.
    visual_pattern:
        The visual pattern this layout expresses, e.g. ``"CL-01"``.
    category:
        Top-level pattern category: ``"creative_listing"`` or ``"infographic"``.
    canvas_type:
        Target canvas aspect ratio, e.g. ``"widescreen_16_9"``.
    header:
        Header region specification.
    body:
        Body region specification.
    footer:
        Footer region specification.
    components:
        Ordered list of layout components.
    spacing:
        Spacing strategy, e.g. ``"equal"``, ``"compact"``, ``"stretched"``.
    alignment:
        Alignment strategy, e.g. ``"left"``, ``"center"``, ``"distributed"``.
    color_scheme:
        Optional color-scheme hint for the renderer/template selector.
    supports_images:
        Whether the layout reserves space for images.
    supports_percentages:
        Whether the layout can render numeric percentages.
    metadata:
        Extra renderer hints (variant, min_items, max_items, etc.).
    """

    layout_id: str = Field(..., description="Layout identifier.")
    visual_pattern: str = Field(
        ..., description="Visual pattern ID this layout implements."
    )
    category: str = Field(..., description="Pattern category.")
    canvas_type: str = Field(
        default="widescreen_16_9",
        description="Target canvas type.",
    )
    header: HeaderSpecification
    body: BodySpecification
    footer: FooterSpecification
    components: list[ComponentSpecification]
    spacing: str = Field(..., description="Spacing strategy.")
    alignment: str = Field(..., description="Alignment strategy.")
    color_scheme: str = Field(
        default="default",
        description="Color-scheme hint.",
    )
    supports_images: bool
    supports_percentages: bool
    metadata: dict[str, Any] = Field(default_factory=dict)
    grid: Optional[dict[str, Any]] = Field(
        default=None,
        description=(
            "Optional grid metadata used to synthesize component positions "
            "when the content item count differs from the canonical layout. "
            "Keys: rows, cols, flow, max_cols, strategy, max_cell_height."
        ),
    )

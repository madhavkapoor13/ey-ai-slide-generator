"""
schemas/presentation_asset.py
=============================
Presentation Asset Library — boundary-object schemas.

These models describe the reusable PowerPoint elements that replace the
legacy drawing renderer. An ``AssetManifest`` is the machine-readable
contract authored per asset: it tells the Asset Inspector how to bind
content, the Asset Selector how to score relevance, the Content Generator
what to produce, and the Asset Populator which shapes to fill.

Two families of models live here:

1. The *manifest* layer — describes a single reusable asset
   (``AssetManifest`` and its ``AssetPlaceholder`` list).
2. The *selection* layer — the output of the Asset Selector
   (``AssetSelection``) and the query it scores
   (``AssetSelectionQuery``).

These are pure planning / contract objects. No PowerPoint objects, no
coordinates, no rendering instructions. Renderers / populators consume
them; they do not depend on python-pptx.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class PlaceholderKind(str, Enum):
    """
    Typed kind of a fillable placeholder.

    The kind tells the Content Generator exactly what to emit for a slot
    (e.g. a METRIC expects a numeric value, a CURRENCY expects an amount
    with a unit, a TIMELINE_NODE expects a label + optional date), and
    tells the Populator how to coerce the value into the shape's text.

    Extensible: new kinds can be added as enum members without breaking
    existing manifests (unknown kinds fall back to BODY content shape).
    """

    TITLE = "title"
    BODY = "body"
    METRIC = "metric"
    DATE = "date"
    ICON = "icon"
    PERCENTAGE = "percentage"
    CURRENCY = "currency"
    CHEVRON = "chevron"
    TIMELINE_NODE = "timeline_node"


class PlaceholderBinding(BaseModel):
    """
    How to physically find a placeholder inside the asset's ``.pptx`` slide.

    A placeholder is bound either to a native PowerPoint placeholder (by
    index) or to a free-form custom shape (by name). Both modes are
    supported per-placeholder because Slidefox elements mix native
    placeholders and hand-drawn shapes. Exactly one binding mode should
    be populated per placeholder.
    """

    native_placeholder_idx: Optional[int] = Field(
        default=None,
        description="Index into slide.placeholders for native placeholder binding.",
    )
    shape_name: Optional[str] = Field(
        default=None,
        description="Shape name (shape.name) for free-form custom-shape binding.",
    )
    table_shape_name: Optional[str] = Field(
        default=None,
        description="Shape name of a native PowerPoint table for cell binding.",
    )
    row_index: Optional[int] = Field(
        default=None,
        ge=0,
        description="Zero-based row index for native PowerPoint table cell binding.",
    )
    col_index: Optional[int] = Field(
        default=None,
        ge=0,
        description="Zero-based column index for native PowerPoint table cell binding.",
    )


class AssetPlaceholder(BaseModel):
    """
    A single fillable slot inside an asset.

    Attributes
    ----------
    id:
        Stable placeholder id used as the content key in the generated
        ``SlideSpec.raw_spec`` (e.g. ``"title"``, ``"phase_1"``,
        ``"kpi_2_value"``).
    role:
        Semantic role of the slot for retrieval / prompt hints
        (e.g. ``"title"``, ``"phase"``, ``"kpi_value"``, ``"axis_label"``).
    kind:
        Typed content kind; drives Content Generator output shape and
        Populator text coercion.
    cardinality:
        ``"1"`` for a single value, ``"N"`` for a repeating slot whose
        count is driven by the manifest's ``repeating`` block.
    required:
        If ``True`` the Populator must receive a value; missing required
        placeholders trip the manifest-conformance validator.
    content_schema:
        Optional shape of the value for structured placeholders, e.g.
        ``{"label": "string", "owner": "string?", "deliverables": "string[]?"}``.
        Consumed by manifest-aware Content Generation.
    constraints:
        Rendering constraints, e.g. ``{"max_chars": 80, "max_lines": 2}``.
    binding:
        How to find this slot inside the ``.pptx``.
    """

    id: str = Field(..., description="Stable placeholder id (used as the raw_spec content key).")
    role: str = Field(..., description="Semantic role of the slot.")
    kind: PlaceholderKind = Field(
        default=PlaceholderKind.BODY,
        description="Typed content kind; drives generation and population.",
    )
    cardinality: str = Field(
        default="1",
        description="Cardinality: '1' for a single value, 'N' for a repeating slot.",
    )
    required: bool = Field(default=True, description="Whether a value is mandatory.")
    content_schema: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional value shape for structured placeholders.",
    )
    constraints: dict[str, Any] = Field(
        default_factory=dict,
        description="Rendering constraints (max_chars, max_lines, ...).",
    )
    binding: PlaceholderBinding = Field(..., description="How to find this slot in the .pptx.")


class RepeatingGroup(BaseModel):
    """
    Describes a parametric group of placeholders that repeats ``count`` times.

    Example: a roadmap asset with 3 phases might name its textboxes
    ``Phase1Label``, ``Phase1Owner``, ``Phase2Label``, ...
    The repeating block records the template (``"Phase{N}Label"``),
    the per-group placeholder ids, and the canonical ``count`` (here 3).
    The Populator instantiates/cleans groups up to the actual content count
    at population time.
    """

    group_template: str = Field(
        ...,
        description="Naming template for the group, e.g. 'Phase{N}Group'.",
    )
    placeholders_per_group: list[str] = Field(
        ...,
        description="Placeholder ids (or templates) that belong to each group.",
    )
    index_token: str = Field(
        default="{N}",
        description="Token replaced by the group index (1-based).",
    )
    count: int = Field(
        ...,
        ge=1,
        description="Canonical number of repeating groups baked into the asset.",
    )


class AssetCertification(BaseModel):
    """
    Production-readiness metadata for a Presentation Asset.

    Certification is intentionally additive: existing manifests remain valid,
    while production selectors can prefer or require certified assets.
    """

    certified: bool = Field(default=False, description="Whether the asset passed certification.")
    certified_at: Optional[str] = Field(default=None, description="ISO timestamp for certification.")
    preview_hash: Optional[str] = Field(default=None, description="Smoke-test or rendered-preview hash.")
    warnings: list[str] = Field(default_factory=list, description="Non-fatal certification warnings.")
    errors: list[str] = Field(default_factory=list, description="Fatal certification errors.")


class AssetManifest(BaseModel):
    """
    The full manifest for one reusable Presentation Asset.

    Stored on disk as ``asset.json`` next to ``asset.pptx`` under
    ``presentation_assets/<family>/<asset_id>/``. Auto-discovered by the
    registry on backend restart; no registration call required.
    """

    asset_id: str = Field(
        ...,
        description="Stable, human-readable asset id, e.g. 'ROADMAP-3PHASE-001'.",
    )
    asset_version: int = Field(
        default=1,
        ge=1,
        description="Version of the authored Presentation Asset contract.",
    )
    schema_version: str = Field(
        default="1.0.0",
        description="Manifest schema version for forward compatibility.",
    )
    message_type: Optional[str] = Field(
        default=None,
        description="Primary consulting message this asset communicates.",
    )
    information_shape: Optional[str] = Field(
        default=None,
        description="Semantic information shape, e.g. sequence, comparison, matrix.",
    )
    text_fit_policy: str = Field(
        default="regenerate_then_reject",
        description="Asset-level overflow policy; placeholders may override in constraints.",
    )
    certification: AssetCertification = Field(
        default_factory=AssetCertification,
        description="Certification metadata for production use.",
    )
    family: str = Field(
        ...,
        description=(
            "Consulting visual family. One of the folder names under "
            "presentation_assets/ (e.g. 'roadmap', 'executive_summary'). "
            "The only bridge to the reasoning layer's VisualPatternSelection."
        ),
    )
    family_aliases: list[str] = Field(
        default_factory=list,
        description="Alternative family names matched as a fallback during selection.",
    )
    purpose: str = Field(..., description="One-line description of what this asset communicates.")
    audience_tags: list[str] = Field(
        default_factory=list,
        description="Audiences this asset suits, e.g. ['board', 'executive'].",
    )
    style_tags: list[str] = Field(
        default_factory=list,
        description="Style descriptors, e.g. ['minimal', 'modern', 'board-ready'].",
    )
    recommended_for: list[str] = Field(
        default_factory=list,
        description="Use-cases this asset is a strong fit for; a positive retrieval signal.",
    )
    avoid_for: list[str] = Field(
        default_factory=list,
        description="Use-cases this asset is a weak fit for; a negative retrieval signal.",
    )
    density: int = Field(
        ...,
        ge=1,
        description="Canonical slot count baked into the asset (e.g. 3 phases).",
    )
    density_range: list[int] = Field(
        ...,
        min_length=2,
        max_length=2,
        description="Min and max slot counts the asset accommodates, e.g. [3, 6].",
    )
    fits_content_kinds: list[str] = Field(
        default_factory=list,
        description="Content kinds (from SlidePlan) this asset can carry, e.g. ['phases', 'milestones'].",
    )
    supports_images: bool = Field(default=False, description="Whether the asset reserves space for images.")
    source_slide_index: int = Field(
        default=0,
        ge=0,
        description="Zero-based slide index in asset.pptx to copy/populate.",
    )
    placeholders: list[AssetPlaceholder] = Field(
        ...,
        description="Fillable slots in the asset (bound to native placeholders or named shapes).",
    )
    repeating: Optional[RepeatingGroup] = Field(
        default=None,
        description="Optional parametric repeating group spec.",
    )


class AssetSelection(BaseModel):
    """
    Result of the deterministic Asset Selector.

    A typed boundary object produced by the Selector and consumed by the
    Deck Executor (carried onto ``SlideSpec``) and by the Content Generator
    (used to shape the LLM prompt) and the Populator (used to open the
    right .pptx).
    """

    asset_id: str = Field(..., description="Id of the selected asset.")
    family: str = Field(..., description="Family of the selected asset.")
    manifest: AssetManifest = Field(..., description="The selected asset's full manifest.")
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Normalised selection score in [0.0, 1.0].",
    )
    score_breakdown: dict[str, float] = Field(
        default_factory=dict,
        description="Per-signal score contributions, for debugging / future rerank.",
    )
    reasoning: str = Field(..., description="Human-readable explanation of the selection.")
    candidate_ids: list[str] = Field(
        default_factory=list,
        description="Top-N candidate asset ids (for future UI / rerank).",
    )


class AssetSelectionQuery(BaseModel):
    """
    The inputs the Asset Selector scores against the registry.

    Assembled by the Deck Executor from signals already in scope at the
    per-slide planning moment: VisualPatternSelection (family), SlidePlan
    (role/purpose/keywords), Intent (audience), and explicit-or-inferred
    UserPreferences (style).
    """

    family: str = Field(..., description="Target consulting visual family.")
    audience: list[str] = Field(default_factory=list, description="Audience tags to match.")
    style: list[str] = Field(default_factory=list, description="Style tags to match.")
    keywords: list[str] = Field(
        default_factory=list,
        description="Purpose / use-case keywords for keyword-overlap scoring (and recommended_for/avoid_for).",
    )
    content_count: Optional[int] = Field(
        default=None,
        description="Estimated slot count for capacity-fit scoring.",
    )
    content_kind_hints: list[str] = Field(
        default_factory=list,
        description="Content kinds from SlidePlan (e.g. 'phases', 'kpis') for fits_content_kinds scoring.",
    )
    message_type: Optional[str] = Field(
        default=None,
        description="VisualBrief message_type used as an additive selection signal.",
    )
    information_shape: Optional[str] = Field(
        default=None,
        description="VisualBrief information_shape used as an additive selection signal.",
    )
    require_certified: bool = Field(
        default=False,
        description="When True, selector filters to certified assets when certified candidates exist.",
    )


class UserPreferences(BaseModel):
    """
    Optional, user-supplied style / audience preferences that bias asset
    retrieval. Two provenances:

    - **Explicit override** — supplied by the caller on the request
      (``GenerateV2Request.preferences``). When present, it always wins.
    - **Inferred default** — when the caller omits preferences, the
      IntentExtractor / PresentationPlanner derives a conservative default
      from the prompt (audience from ``IntentResult.audience``; style
      inferred from prompt cues like "board-level", "minimal").

    Used as retrieval filters only — they never change the asset's drawn
    look. Empty lists mean "no preference"; the Selector does not penalise
    for missing tags in that case.
    """

    audience: list[str] = Field(
        default_factory=list,
        description="Audience tags to prefer, e.g. ['board', 'executive'].",
    )
    style: list[str] = Field(
        default_factory=list,
        description="Style descriptors to prefer, e.g. ['minimal', 'board-ready'].",
    )
    density: Optional[str] = Field(
        default=None,
        description="Optional density hint: 'comfortable' | 'compact' | 'dense'.",
    )
    allow_images: Optional[bool] = Field(
        default=None,
        description="Optional constraint: True requires supports_images, False forbids it.",
    )
    user_visual_preferences: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Optional slide-type to variant override map, e.g. "
            "{'roadmap': 'ROADMAP_3PHASE_WORKSTREAM', 'risks': 'RISK_MATRIX'}. "
            "When present, the visual variant resolver applies it before defaults."
        ),
    )

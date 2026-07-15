"""
backend/layout_engine/layout_engine.py
======================================
Sprint V3 — Visual Layout Engine.

Transforms a ``VisualPatternSelection`` into a reusable, normalized
``LayoutSpecification``. This module does not render PowerPoint or create
shapes; it only describes where slide content belongs.
"""

from __future__ import annotations

import logging
import math
import re

from backend.layout_engine import layout_registry
from schemas.layout import (
    BodySpecification,
    ComponentSpecification,
    FooterSpecification,
    HeaderSpecification,
    LayoutSpecification,
)
from schemas.visual import VisualPatternSelection

logger = logging.getLogger(__name__)

_FALLBACK_LAYOUT_ID = "GENERIC"


def _fallback_layout() -> LayoutSpecification:
    """Return a minimal generic layout used when no specific layout matches."""
    generic = layout_registry.find_by_pattern("*")
    if generic is not None:
        return generic

    logger.warning("layout_engine: generic layout not found; using hardcoded fallback")
    return LayoutSpecification(
        layout_id=_FALLBACK_LAYOUT_ID,
        visual_pattern="*",
        category="any",
        canvas_type="widescreen_16_9",
        header=HeaderSpecification(height=0.15),
        body=BodySpecification(x=0.05, y=0.18, width=0.9, height=0.62),
        footer=FooterSpecification(height=0.10),
        components=[
            ComponentSpecification(
                component_id="content_box",
                type="content_box",
                x=0.07,
                y=0.20,
                width=0.86,
                height=0.58,
                placeholder="content",
                constraints=["flexible"],
            )
        ],
        spacing="equal",
        alignment="left",
        supports_images=False,
        supports_percentages=False,
    )


def generate_layout(
    visual_pattern_selection: VisualPatternSelection,
    item_count: int | None = None,
) -> LayoutSpecification:
    """
    Generate a ``LayoutSpecification`` for the selected visual pattern.

    Parameters
    ----------
    visual_pattern_selection:
        Output of the Visual Planner containing ``pattern_id`` and ``category``.
    item_count:
        Actual number of content items to lay out. When supplied and different
        from the canonical component count, the engine synthesizes a new
        component arrangement using the layout's ``grid`` metadata so there are
        no empty rectangles and no dropped items.

    Returns
    -------
    LayoutSpecification
        Normalized layout describing header, body, footer, and components.
        If no specific layout matches the pattern, a generic fallback layout
        is returned.
    """
    pattern_id = visual_pattern_selection.pattern_id
    layout = layout_registry.find_by_pattern(pattern_id)

    if layout is None:
        logger.info(
            "layout_engine: no layout found for pattern %s; using fallback",
            pattern_id,
        )
        return _fallback_layout()

    if item_count is not None and layout.grid is not None:
        logger.info(
            "layout_engine: synthesizing layout %s for %d items",
            layout.layout_id,
            item_count,
        )
        return _synthesize_layout(layout, item_count)

    logger.info(
        "layout_engine: selected layout %s for pattern %s",
        layout.layout_id,
        pattern_id,
    )
    return layout


def _synthesize_layout(
    canonical: LayoutSpecification,
    item_count: int,
) -> LayoutSpecification:
    """
    Regenerate component positions for ``item_count`` items using the
    canonical layout's body geometry and ``grid`` metadata.

    Header, footer, spacing, alignment, and component type are preserved.
    """
    if item_count <= 0:
        item_count = 1

    grid = canonical.grid or {}

    if grid.get("strategy") == "two_column":
        components = _synthesize_two_column_components(canonical, item_count)
    else:
        components = _synthesize_grid_components(canonical, item_count, grid)

    metadata = dict(canonical.metadata)
    metadata["synthesized"] = True
    metadata["synthesized_item_count"] = item_count

    return LayoutSpecification(
        layout_id=f"{canonical.layout_id}_synth_{item_count}",
        visual_pattern=canonical.visual_pattern,
        category=canonical.category,
        canvas_type=canonical.canvas_type,
        header=canonical.header,
        body=canonical.body,
        footer=canonical.footer,
        components=components,
        spacing=canonical.spacing,
        alignment=canonical.alignment,
        color_scheme=canonical.color_scheme,
        supports_images=canonical.supports_images,
        supports_percentages=canonical.supports_percentages,
        metadata=metadata,
        grid=grid,
    )


def _synthesize_grid_components(
    canonical: LayoutSpecification,
    item_count: int,
    grid: dict[str, Any],
) -> list[ComponentSpecification]:
    """Synthesize a regular grid of identical components."""
    body = canonical.body
    rows, cols = _compute_grid(item_count, grid)

    base = _find_data_component(canonical.components)
    if base is None:
        return list(canonical.components)

    prefix = _placeholder_prefix(base.placeholder)
    components: list[ComponentSpecification] = []

    for index in range(item_count):
        row, col = _index_to_row_col(index, rows, cols, grid.get("flow", "row"))
        x, y, width, height = _compute_component_bounds(
            row, col, rows, cols, body, grid
        )
        components.append(
            ComponentSpecification(
                component_id=f"{prefix}_{index + 1}",
                type=base.type,
                placeholder=f"{prefix}_{index + 1}",
                x=x,
                y=y,
                width=width,
                height=height,
                constraints=list(base.constraints),
            )
        )

    # Add horizontal connectors between adjacent single-row timeline/flow items.
    if (
        rows == 1
        and item_count > 1
        and base.type in {"node", "bar"}
    ):
        gap = float(grid.get("gap", 0.02))
        connector_height = float(grid.get("connector_height", 0.015))
        for index in range(item_count - 1):
            left_comp = components[index]
            right_comp = components[index + 1]
            # Draw the connector from the center of the left component to the
            # center of the right component so it is long enough to be visible.
            conn_x = left_comp.x + left_comp.width / 2
            conn_y = left_comp.y + left_comp.height / 2 - connector_height / 2
            conn_width = (right_comp.x + right_comp.width / 2) - conn_x
            components.append(
                ComponentSpecification(
                    component_id=f"connector_{index + 1}_{index + 2}",
                    type="connector",
                    placeholder=f"connector_{index + 1}_{index + 2}",
                    x=conn_x,
                    y=conn_y,
                    width=conn_width,
                    height=connector_height,
                    constraints=["arrow"],
                )
            )

    # Preserve structural label components (e.g. matrix axis labels) from the
    # canonical layout so synthesized layouts still render axes and legends.
    data_placeholders = {c.placeholder for c in components}
    for component in canonical.components:
        if component.type == "label" and component.placeholder not in data_placeholders:
            components.append(component)

    return components


def _find_data_component(
    components: list[ComponentSpecification],
) -> ComponentSpecification | None:
    """Return the first component that represents data (not axis/connector/label)."""
    for component in components:
        if re.search(r"_\d+$", component.placeholder):
            return component
    # Fallback: ignore purely structural components.
    for component in components:
        if component.type not in {"axis", "connector", "label"}:
            return component
    return components[0] if components else None


def _synthesize_two_column_components(
    canonical: LayoutSpecification,
    row_count: int,
) -> list[ComponentSpecification]:
    """Synthesize a two-column layout with ``row_count`` rows per column."""
    body = canonical.body
    gap = 0.02
    margin = 0.02
    label_height = 0.06

    left_label = _find_component(canonical.components, "left_label")
    right_label = _find_component(canonical.components, "right_label")
    left_item = _find_component(canonical.components, "left_item_1")
    right_item = _find_component(canonical.components, "right_item_1")

    col_width = (body.width - 2 * margin - gap) / 2
    left_x = body.x + margin
    right_x = left_x + col_width + gap

    usable_height = body.height - label_height - gap
    row_height = usable_height / row_count if row_count > 0 else usable_height

    components: list[ComponentSpecification] = []

    if left_label is not None:
        components.append(
            _reposition_component(left_label, left_x, body.y, col_width, label_height)
        )
    if right_label is not None:
        components.append(
            _reposition_component(right_label, right_x, body.y, col_width, label_height)
        )

    for index in range(row_count):
        y = body.y + label_height + gap + index * row_height
        if left_item is not None:
            components.append(
                _reposition_component(
                    left_item, left_x, y, col_width, row_height - gap,
                    component_id=f"left_item_{index + 1}",
                    placeholder=f"left_item_{index + 1}",
                )
            )
        if right_item is not None:
            components.append(
                _reposition_component(
                    right_item, right_x, y, col_width, row_height - gap,
                    component_id=f"right_item_{index + 1}",
                    placeholder=f"right_item_{index + 1}",
                )
            )

    return components


def _find_component(
    components: list[ComponentSpecification], component_id: str
) -> ComponentSpecification | None:
    for component in components:
        if component.component_id == component_id:
            return component
    return None


def _reposition_component(
    component: ComponentSpecification,
    x: float,
    y: float,
    width: float,
    height: float,
    *,
    component_id: str | None = None,
    placeholder: str | None = None,
) -> ComponentSpecification:
    return ComponentSpecification(
        component_id=component_id or component.component_id,
        type=component.type,
        placeholder=placeholder or component.placeholder,
        x=x,
        y=y,
        width=width,
        height=height,
        constraints=list(component.constraints),
    )


def _compute_grid(item_count: int, grid: dict[str, Any]) -> tuple[int, int]:
    """Determine rows and columns from grid metadata and item count."""
    strategy = grid.get("strategy", "auto")

    # Explicit fixed grid.
    rows_raw = grid.get("rows")
    cols_raw = grid.get("cols")
    if isinstance(rows_raw, int) and isinstance(cols_raw, int):
        return rows_raw, cols_raw
    if isinstance(cols_raw, int):
        return (item_count + cols_raw - 1) // cols_raw, cols_raw
    if isinstance(rows_raw, int):
        return rows_raw, (item_count + rows_raw - 1) // rows_raw

    max_cols = grid.get("max_cols")
    if isinstance(max_cols, int):
        cols = min(max_cols, item_count)
        return (item_count + cols - 1) // cols, cols

    if strategy == "square":
        cols = math.ceil(math.sqrt(item_count))
        rows = (item_count + cols - 1) // cols
        return rows, cols

    if strategy == "cards":
        if item_count <= 3:
            return 1, item_count
        if item_count == 4:
            return 2, 2
        cols = (item_count + 1) // 2
        return 2, cols

    # Default / "row": single row with one column per item.
    return 1, item_count


def _index_to_row_col(
    index: int, rows: int, cols: int, flow: str
) -> tuple[int, int]:
    """Convert a flat item index to (row, col) given a flow direction."""
    if flow == "col":
        return index % rows, index // rows
    return index // cols, index % cols


def _compute_component_bounds(
    row: int,
    col: int,
    rows: int,
    cols: int,
    body: BodySpecification,
    grid: dict[str, Any],
) -> tuple[float, float, float, float]:
    """Compute normalized (x, y, width, height) for a grid cell."""
    gap = float(grid.get("gap", 0.02))
    margin = float(grid.get("margin", 0.02))

    usable_width = body.width - 2 * margin
    usable_height = body.height - 2 * margin

    cell_width = (usable_width - gap * (cols - 1)) / cols
    cell_height = (usable_height - gap * (rows - 1)) / rows
    max_cell_height = grid.get("max_cell_height")
    if max_cell_height is not None:
        cell_height = min(cell_height, float(max_cell_height))

    x = body.x + margin + col * (cell_width + gap)
    y = body.y + margin + row * (cell_height + gap)

    return x, y, cell_width, cell_height


def _placeholder_prefix(placeholder: str) -> str:
    """Extract the placeholder prefix (e.g. ``card_1`` → ``card``)."""
    match = re.match(r"^([a-zA-Z_]+)_\d+", placeholder)
    if match:
        return match.group(1)
    return "item"

"""
ppt_renderer/components/connector_renderer.py
=============================================
Connector component renderer.

Draws directional arrows/lines between layout components. The connector's
normalized bounding box describes the line's start and end region; the renderer
draws a straight connector shape inside that box.
"""

from __future__ import annotations

from typing import Any

from pptx.enum.shapes import MSO_CONNECTOR
from pptx.util import Inches

from ppt_renderer.components.coordinates import convert_bounds
from backend.design_system.theme_loader import get_current_theme


def render(
    component_specification,
    presentation,
    slide,
    content: dict[str, Any],
    *,
    layout_context: dict[str, Any] | None = None,
) -> None:
    """Render a connector as a directional arrow within its bounding box."""
    theme = get_current_theme()
    left, top, width, height = convert_bounds(component_specification, presentation)

    style = "arrow"
    constraints = component_specification.constraints or []
    if "dashed" in constraints:
        style = "dashed"
    elif "line" in constraints:
        style = "line"

    # Default to a horizontal connector centered vertically in the box.
    start_x = left
    start_y = top + height // 2
    end_x = left + width
    end_y = start_y

    connector = slide.shapes.add_connector(
        MSO_CONNECTOR.STRAIGHT,
        start_x,
        start_y,
        end_x,
        end_y,
    )
    connector.line.color.rgb = theme.color("connector")
    connector.line.width = Inches(0.015)

    # python-pptx connectors do not expose an arrowhead API on the line itself,
    # so we write the OOXML tailEnd element directly.
    if style == "arrow":
        _set_arrowhead(connector)


def _set_arrowhead(connector) -> None:
    """Add a triangle arrowhead to the end of a connector via OOXML."""
    from lxml import etree

    P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
    A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"

    spPr = connector._element.find(f"{{{P_NS}}}spPr")
    if spPr is None:
        return
    ln = spPr.find(f"{{{A_NS}}}ln")
    if ln is None:
        return
    tail = ln.find(f"{{{A_NS}}}tailEnd")
    if tail is None:
        tail = etree.SubElement(ln, f"{{{A_NS}}}tailEnd")
    tail.set("type", "triangle")
    tail.set("w", "med")
    tail.set("len", "med")

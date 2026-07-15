"""
ppt_renderer/components/component_dispatcher.py
===============================================
Component dispatch router.

Inspects ``component.type`` and delegates to the appropriate component
renderer. Unknown component types are skipped gracefully.
"""

from __future__ import annotations

import logging
from typing import Any

from ppt_renderer.components import (
    card_renderer,
    connector_renderer,
    executive_card_renderer,
    matrix_renderer,
    text_renderer,
    timeline_renderer,
)

logger = logging.getLogger(__name__)

# Map component types to renderer modules. Each module must expose a
# ``render(component_specification, presentation, slide, content)`` function.
_DISPATCH_TABLE: dict[str, Any] = {
    "card": card_renderer,
    "kpi_card": card_renderer,
    "executive_card": executive_card_renderer,
    "text": text_renderer,
    "list_item": text_renderer,
    "label": text_renderer,
    "content_box": text_renderer,
    "node": timeline_renderer,
    "axis": timeline_renderer,
    "bar": timeline_renderer,
    "cell": matrix_renderer,
    "column": matrix_renderer,
    "connector": connector_renderer,
}


def render(
    component_specification,
    presentation,
    slide,
    content: dict[str, Any],
    *,
    layout_context: dict[str, Any] | None = None,
) -> None:
    """
    Render a single component by dispatching to its specialized renderer.

    Unknown component types are logged and skipped without raising.
    The optional ``layout_context`` carries visual-pattern-level design intent
    (e.g., ``pattern_id``) that renderers can use for design-language lookups.
    """
    component_type = component_specification.type
    renderer_module = _DISPATCH_TABLE.get(component_type)

    if renderer_module is None:
        logger.warning(
            "component_dispatcher: skipping unknown component type '%s' (%s)",
            component_type,
            component_specification.component_id,
        )
        return

    renderer_module.render(
        component_specification,
        presentation,
        slide,
        content,
        layout_context=layout_context,
    )

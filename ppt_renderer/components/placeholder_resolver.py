"""
ppt_renderer/components/placeholder_resolver.py
===============================================
Generic placeholder-to-content binding for layout components.

The renderer must never inspect business logic. It only consumes the
placeholders supplied through the LayoutSpecification and resolves them
against the SlideSpec ``raw_spec`` content dictionary.
"""

from __future__ import annotations

import re
from typing import Any


_PLACEHOLDER_RE = re.compile(r"^(?P<prefix>[a-zA-Z_]+)_(?P<index>\d+)(?:\.(?P<field>.+))?$")


def resolve_placeholder(placeholder: str, content: dict[str, Any]) -> Any:
    """
    Resolve a placeholder string against slide content.

    Examples
    --------
    - ``title`` → ``content["title"]``
    - ``subtitle`` → ``content["subtitle"]``
    - ``card_1`` → ``content["cards"][0]``
    - ``card_1.title`` → ``content["cards"][0]["title"]``
    - ``kpi_2.value`` → ``content["kpis"][1]["value"]``
    - ``step_1.label`` → ``content["steps"][0]["label"]``
    - ``content`` → ``content`` (entire dict)
    """
    placeholder = placeholder.strip()

    # Direct scalar fields.
    if placeholder in ("title", "subtitle", "description", "section_title"):
        return content.get(placeholder, "")

    if placeholder == "content":
        return content

    if placeholder in ("left_label", "right_label"):
        columns = content.get("columns", [])
        idx = 0 if placeholder == "left_label" else 1
        if len(columns) > idx and isinstance(columns[idx], dict):
            return columns[idx].get("label", "")
        return ""

    axis_defaults = {
        "x_axis_low": "Low",
        "x_axis_medium": "Medium",
        "x_axis_high": "High",
        "y_axis_low": "Low",
        "y_axis_medium": "Medium",
        "y_axis_high": "High",
    }
    if placeholder in axis_defaults:
        return axis_defaults[placeholder]

    match = _PLACEHOLDER_RE.match(placeholder)
    if not match:
        return ""

    prefix = match.group("prefix")
    index = int(match.group("index")) - 1
    field = match.group("field")

    collection_key = _collection_key(prefix)
    collection = content.get(collection_key)
    if not isinstance(collection, list) or not (0 <= index < len(collection)):
        return ""

    item = collection[index]
    if field is None:
        return item
    if isinstance(item, dict):
        return item.get(field, "")
    return ""


def _collection_key(prefix: str) -> str:
    """Map a placeholder prefix to the content collection key."""
    mapping = {
        "card": "cards",
        "kpi": "kpis",
        "step": "steps",
        "event": "events",
        "phase": "phases",
        "stage": "stages",
        "cell": "cells",
        "domain": "domains",
        "item": "items",
    }
    return mapping.get(prefix, prefix + "s")

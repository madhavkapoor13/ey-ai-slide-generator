"""
backend/design_system/color_palette.py
======================================
Color palette utilities for the Design System.
"""

from __future__ import annotations

from pptx.dml.color import RGBColor


def hex_to_rgb(hex_color: str) -> RGBColor:
    """Convert a hex color string to a python-pptx ``RGBColor``."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        raise ValueError(f"Invalid hex color: {hex_color}")
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return RGBColor(r, g, b)

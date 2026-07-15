"""
backend/design_system/theme.py
==============================
Design System theme facade.

Wraps a ``schemas.theme.Theme`` and exposes renderer-friendly accessors that
return python-pptx objects (``RGBColor``, ``Pt``, ``Inches``).
"""

from __future__ import annotations

from pptx.dml.color import RGBColor
from pptx.util import Inches, Pt

from backend.design_system.color_palette import hex_to_rgb
from schemas.theme import Theme as ThemeSchema


class DesignTheme:
    """Runtime theme wrapper used by component renderers."""

    def __init__(self, schema: ThemeSchema):
        self._schema = schema

    @property
    def name(self) -> str:
        return self._schema.name

    @property
    def version(self) -> str:
        return self._schema.version

    def color(self, name: str, default: str = "#000000") -> RGBColor:
        """Return a color token as an ``RGBColor``."""
        return hex_to_rgb(self._schema.color_palette.get(name, default))

    def font(self, name: str, default: str = "Arial") -> str:
        """Return a font family token."""
        return self._schema.typography.get_font(name, default)

    def size(self, name: str, default: float = 10.0) -> Pt:
        """Return a font size token as ``Pt``."""
        return Pt(self._schema.typography.get_size(name, default))

    def space(self, name: str, default: float = 0.0) -> Inches:
        """Return a spacing token as ``Inches``."""
        return Inches(self._schema.spacing.get(name, default))

    def raw(self) -> ThemeSchema:
        """Return the underlying schema model."""
        return self._schema

"""
schemas/theme.py
================
Sprint V5 — Design System theme schemas.

These models describe a reusable design system: color palette, typography,
and spacing tokens. Tokens are stored in plain JSON so designers can tune the
visual system without touching renderer code.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ColorPalette(BaseModel):
    """Named color tokens. Values are hex strings, e.g. ``#FFE600``."""

    colors: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of token name to hex color.",
    )

    def get(self, name: str, default: str = "#000000") -> str:
        return self.colors.get(name, default)


class Typography(BaseModel):
    """Font family and size tokens. Sizes are in points."""

    fonts: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of token name to font family.",
    )
    sizes: dict[str, float] = Field(
        default_factory=dict,
        description="Mapping of token name to size in points.",
    )

    def get_font(self, name: str, default: str = "Arial") -> str:
        return self.fonts.get(name, default)

    def get_size(self, name: str, default: float = 10.0) -> float:
        return self.sizes.get(name, default)


class Spacing(BaseModel):
    """Spacing and margin tokens. Values are in inches."""

    values: dict[str, float] = Field(
        default_factory=dict,
        description="Mapping of token name to length in inches.",
    )

    def get(self, name: str, default: float = 0.0) -> float:
        return self.values.get(name, default)


class Theme(BaseModel):
    """
    Complete design system theme.

    Attributes
    ----------
    name:
        Theme identifier, e.g. ``"ey_blue"``.
    version:
        Theme version string.
    color_palette:
        Named color tokens.
    typography:
        Font and size tokens.
    spacing:
        Spacing and margin tokens.
    metadata:
        Extra theme metadata (author, brand, etc.).
    """

    name: str = Field(..., description="Theme identifier.")
    version: str = Field(default="1.0", description="Theme version.")
    color_palette: ColorPalette
    typography: Typography
    spacing: Spacing
    metadata: dict[str, Any] = Field(default_factory=dict)

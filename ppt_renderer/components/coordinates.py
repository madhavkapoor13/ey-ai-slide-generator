"""
ppt_renderer/components/coordinates.py
======================================
Coordinate conversion helpers for normalized layout specifications.

All values from the Layout Engine are in the 0.0–1.0 range. This module
deterministically converts them into PowerPoint-native coordinates based on
the actual presentation slide dimensions.
"""

from __future__ import annotations

from pptx import Presentation
from pptx.util import Inches


def convert_x(normalized_x: float, presentation: Presentation) -> Inches:
    """Convert a normalized x coordinate to PowerPoint inches."""
    return Inches(presentation.slide_width.inches * normalized_x)


def convert_y(normalized_y: float, presentation: Presentation) -> Inches:
    """Convert a normalized y coordinate to PowerPoint inches."""
    return Inches(presentation.slide_height.inches * normalized_y)


def convert_width(normalized_width: float, presentation: Presentation) -> Inches:
    """Convert a normalized width to PowerPoint inches."""
    return Inches(presentation.slide_width.inches * normalized_width)


def convert_height(normalized_height: float, presentation: Presentation) -> Inches:
    """Convert a normalized height to PowerPoint inches."""
    return Inches(presentation.slide_height.inches * normalized_height)


def convert_bounds(component, presentation: Presentation) -> tuple[Inches, Inches, Inches, Inches]:
    """
    Convert a component's normalized bounding box to PowerPoint coordinates.

    Returns (left, top, width, height) as ``Inches`` objects.
    """
    return (
        convert_x(component.x, presentation),
        convert_y(component.y, presentation),
        convert_width(component.width, presentation),
        convert_height(component.height, presentation),
    )


def safe_body_bounds(
    header_height: float,
    footer_height: float,
    presentation: Presentation,
) -> tuple[Inches, Inches, Inches, Inches]:
    """
    Return the usable body rectangle after subtracting header and footer.

    Returns (left, top, width, height) as ``Inches`` objects.
    """
    left = Inches(0)
    top = convert_y(header_height, presentation)
    width = presentation.slide_width
    height = Inches(
        presentation.slide_height.inches
        - presentation.slide_height.inches * (header_height + footer_height)
    )
    return left, top, width, height

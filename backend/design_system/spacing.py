"""
backend/design_system/spacing.py
================================
Spacing utilities for the Design System.
"""

from __future__ import annotations

from pptx.util import Inches


def inches(length: float) -> Inches:
    """Convert an inch value to a python-pptx ``Inches`` length."""
    return Inches(length)

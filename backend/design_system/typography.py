"""
backend/design_system/typography.py
===================================
Typography utilities for the Design System.
"""

from __future__ import annotations

from pptx.util import Pt


def pt_size(points: float) -> Pt:
    """Convert a point value to a python-pptx ``Pt`` length."""
    return Pt(points)

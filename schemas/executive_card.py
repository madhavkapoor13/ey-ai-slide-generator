"""
schemas/executive_card.py
=========================
Design Sprint D1 — Executive Insight Card content schema.

This schema defines the content contract for the reusable Executive Insight
Card component. It is deliberately simple: the renderer only consumes the
fields it is given and never infers business meaning.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ExecutiveCardContent(BaseModel):
    """
    Content for a single Executive Insight Card.

    All fields except ``title`` are optional. The renderer decides how to
    display each supplied field based on the active theme and layout.
    """

    title: str = Field(..., description="Card title.")
    description: str = Field(default="", description="Short card description.")
    metric: Optional[str] = Field(default=None, description="Optional metric value.")
    tag: Optional[str] = Field(default=None, description="Optional footer tag.")
    highlight: Optional[str] = Field(default=None, description="Optional highlight badge.")
    priority: Optional[str] = Field(default=None, description="Optional priority hint for theming.")

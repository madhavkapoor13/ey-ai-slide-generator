"""
schemas/knowledge.py
===================
Sprint F schema — output of the Enterprise Knowledge Manager.

DomainKnowledge carries curated consulting concepts for a business function.
It is intentionally limited in Sprint F to common KPIs, pain points,
transformation themes, and risks. Benchmark numbers, maturity models, and
strategic objectives are excluded from this version.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DomainKnowledge(BaseModel):
    """
    Structured consulting knowledge for a single business domain.

    Attributes
    ----------
    domain:
        Canonical domain name, e.g. "Finance" or "Procurement".
    aliases:
        Alternative names and process aliases for the domain.
    common_kpis:
        Representative KPIs used in the domain.
    common_pain_points:
        Typical operational challenges observed in the domain.
    transformation_themes:
        Common improvement and transformation levers.
    common_risks:
        Risks that transformation programs in the domain should consider.
    """

    domain: str = Field(..., description="Canonical domain name.")
    aliases: list[str] = Field(
        default_factory=list,
        description="Alternative names and process aliases for the domain.",
    )
    common_kpis: list[str] = Field(
        default_factory=list,
        description="Representative KPIs used in the domain.",
    )
    common_pain_points: list[str] = Field(
        default_factory=list,
        description="Typical operational challenges observed in the domain.",
    )
    transformation_themes: list[str] = Field(
        default_factory=list,
        description="Common improvement and transformation levers.",
    )
    common_risks: list[str] = Field(
        default_factory=list,
        description="Risks that transformation programs in the domain should consider.",
    )

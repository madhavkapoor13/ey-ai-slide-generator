"""
schemas/context.py
==================
Phase 2 schema — output of the Enterprise Context Builder module.

EnterpriseContext enriches a raw user request with industry-level
knowledge, research facts, and domain signals before content generation.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class ResearchSource(BaseModel):
    """
    Pointer to an external or internal knowledge source.

    Attributes
    ----------
    label:
        Human-readable name of the source (e.g. "EY Global Report 2024").
    reference:
        URI, DOI, internal ID, or any string that uniquely identifies
        the source for traceability.
    """

    label: str = Field(..., description="Human-readable source name.")
    reference: str = Field(..., description="URI, DOI, or internal ID for the source.")


class ResearchFact(BaseModel):
    """
    A single grounded fact surfaced during context building.

    Attributes
    ----------
    claim:
        The fact or insight expressed as a plain sentence.
    source:
        Optional pointer to where this fact was sourced from.
    """

    claim: str = Field(..., description="Fact or insight expressed as a plain sentence.")
    source: Optional[ResearchSource] = Field(
        default=None,
        description="Optional source attribution for the claim.",
    )


class EnterpriseContext(BaseModel):
    """
    Enriched enterprise context assembled from user intent and external knowledge.

    Attributes
    ----------
    industry:
        Detected or inferred industry vertical (e.g. "Financial Services").
    domain:
        Functional domain within the industry (e.g. "Procure-to-Pay").
    facts:
        List of grounded research facts relevant to this request.
    enrichment_metadata:
        Arbitrary key-value bag for tracking enrichment provenance
        (e.g. which sources were queried, latency, model version).
    """

    industry: str = Field(
        default="Unknown",
        description="Detected industry vertical (e.g. 'Financial Services').",
    )
    domain: str = Field(
        default="Unknown",
        description="Functional domain within the industry (e.g. 'Procure-to-Pay').",
    )
    facts: list[ResearchFact] = Field(
        default_factory=list,
        description="Grounded research facts relevant to this request.",
    )
    enrichment_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Provenance and tracing data from the enrichment step.",
    )

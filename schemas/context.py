"""
schemas/context.py
==================
Phase 2 schema — output of the Enterprise Context Builder module.

EnterpriseContext carries grounded public business context before any
process mapping or slide content generation happens.
"""

from __future__ import annotations

from typing import Any

from pydantic import AliasChoices, BaseModel, Field, model_validator


class ResearchSource(BaseModel):
    """
    Pointer to a public knowledge source.

    Attributes
    ----------
    source:
        Human-readable name of the source (e.g. "Nike Annual Report").
    url:
        Public URL for traceability.
    type:
        Source category such as official_website, annual_report, sec_filing,
        earnings_report, investor_relations, or business_source.
    """

    source: str = Field(
        ...,
        validation_alias=AliasChoices("source", "label", "title"),
        description="Human-readable source name.",
    )
    url: str = Field(
        ...,
        validation_alias=AliasChoices("url", "reference"),
        description="Public source URL.",
    )
    type: str = Field(default="business_source", description="Source category.")

    @property
    def label(self) -> str:
        """Backward-compatible alias for older placeholder code."""
        return self.source

    @property
    def reference(self) -> str:
        """Backward-compatible alias for older placeholder code."""
        return self.url


class ResearchFact(BaseModel):
    """
    A single grounded factual statement surfaced during context building.

    Attributes
    ----------
    statement:
        The fact expressed as a plain sentence.
    source:
        Human-readable source name.
    url:
        Public URL where the statement can be checked.
    type:
        Fact category. The context builder should only produce factual
        company context, not KPIs, pain points, or recommendations.
    """

    statement: str = Field(
        ...,
        validation_alias=AliasChoices("statement", "claim"),
        description="Fact expressed as a plain sentence.",
    )
    source: str = Field(..., description="Human-readable source name.")
    url: str = Field(default="", description="Public source URL.")
    type: str = Field(default="company_fact", description="Fact category.")

    @model_validator(mode="before")
    @classmethod
    def _coerce_legacy_source(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        source = data.get("source")
        if isinstance(source, dict):
            data = data.copy()
            data["source"] = source.get("source") or source.get("label") or "Unknown source"
            data["url"] = data.get("url") or source.get("url") or source.get("reference") or ""
        return data

    @property
    def claim(self) -> str:
        """Backward-compatible alias for older placeholder code."""
        return self.statement


class EnterpriseContext(BaseModel):
    """
    Grounded public company context assembled from user intent and Google Search.

    Attributes
    ----------
    company:
        Company being researched.
    industry:
        Industry vertical stated by the user or identified from sources.
    business_function:
        Business function stated by the user or identified from sources.
    company_summary:
        Concise factual company summary from public sources.
    facts:
        List of grounded factual statements.
    sources:
        De-duplicated source list used for the summary and facts.
    warnings:
        Non-fatal warnings, including company-not-found or unavailable API.
    enrichment_metadata:
        Arbitrary key-value bag for tracking enrichment provenance
        (e.g. which sources were queried, latency, model version).
    """

    company: str = Field(default="Unknown", description="Company being researched.")
    industry: str = Field(
        default="Unknown",
        description="Industry vertical stated by the user or identified from sources.",
    )
    business_function: str = Field(
        default="Unknown",
        description="Business function stated by the user or identified from sources.",
    )
    company_summary: str = Field(
        default="",
        description="Concise factual company summary from public sources.",
    )
    facts: list[ResearchFact] = Field(
        default_factory=list,
        description="Grounded factual statements relevant to the company.",
    )
    sources: list[ResearchSource] = Field(
        default_factory=list,
        description="De-duplicated public sources used for context building.",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal context-building warnings.",
    )
    enrichment_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Provenance and tracing data from the enrichment step.",
    )

    @model_validator(mode="before")
    @classmethod
    def _coerce_legacy_domain(cls, data: Any) -> Any:
        if isinstance(data, dict) and "business_function" not in data and "domain" in data:
            data = data.copy()
            data["business_function"] = data.get("domain")
        return data

    @property
    def domain(self) -> str:
        """Backward-compatible alias for Sprint 1 placeholder modules."""
        return self.business_function

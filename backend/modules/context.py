"""
backend/modules/context.py
==========================
Enterprise Context Builder — Sprint 2.

This module collects grounded public company context only. It does not
generate slide content, KPIs, pain points, process maps, recommendations,
or executive summaries.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from dotenv import load_dotenv

from backend.llm.prompt_loader import build_prompt
from schemas.context import EnterpriseContext, ResearchFact, ResearchSource
from schemas.intent import IntentResult

logger = logging.getLogger(__name__)
_DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
_SOURCE_TYPES = {
    "official_website",
    "annual_report",
    "investor_relations",
    "earnings_report",
    "sec_filing",
    "business_source",
}


def build_context(intent: IntentResult) -> EnterpriseContext:
    """
    Build grounded public company context from a classified intent.

    Failures are returned as warnings on ``EnterpriseContext`` so the
    orchestrator can continue gracefully during company lookup issues.
    """
    company = _company_from_intent(intent)
    requested_industry = _first_non_empty(
        getattr(intent, "industry", None),
        intent.metadata.get("industry") if intent.metadata else None,
    )
    business_function = _first_non_empty(
        getattr(intent, "business_function", None),
        intent.metadata.get("business_function") if intent.metadata else None,
    )

    if not company:
        return EnterpriseContext(
            company="Unknown",
            industry=requested_industry or "Unknown",
            business_function=business_function or "Unknown",
            warnings=["Company could not be identified from IntentResult."],
            enrichment_metadata={"provider": "gemini", "grounding": "google_search"},
        )

    logger.info("building context: company=%s slide_type=%s", company, intent.slide_type)

    parsed: dict[str, Any] | None = None
    provider_used = "openai"
    grounding = "none"

    # Prefer the multi-provider router (OpenAI first) for the context request.
    # If the router fails, fall back to Gemini's Google Search grounding.
    try:
        parsed = _call_context_llm(intent, company, requested_industry, business_function)
    except Exception as router_exc:  # noqa: BLE001
        logger.warning(
            "context builder router path failed for company=%s: %s; falling back to Gemini grounded search",
            company,
            router_exc,
        )
        try:
            raw_response = _call_gemini_grounded_search(
                intent, company, requested_industry, business_function
            )
            parsed = _parse_json_response(raw_response)
            provider_used = "gemini"
            grounding = "google_search"
        except Exception as gemini_exc:  # noqa: BLE001 - context builder degrades to warnings by design.
            logger.exception("context builder failed for company=%s", company)
            return EnterpriseContext(
                company=company,
                industry=requested_industry or "Unknown",
                business_function=business_function or "Unknown",
                warnings=[f"Enterprise context could not be built: {gemini_exc}"],
                enrichment_metadata={"provider": provider_used, "grounding": grounding},
            )

    context = _to_enterprise_context(parsed, company, requested_industry, business_function)
    context.enrichment_metadata = {"provider": provider_used, "grounding": grounding}

    if not context.company_summary or len(context.facts) == 0:
        context.warnings.append(f"Grounded public context for {company} was incomplete.")

    return context


def _call_gemini_grounded_search(
    intent: IntentResult,
    company: str,
    requested_industry: str | None,
    business_function: str | None,
) -> dict[str, Any]:
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY or GOOGLE_API_KEY is not configured.")

    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise RuntimeError("google-genai is not installed.") from exc

    user_input = {
        "intent": {
            "company": company,
            "industry": requested_industry,
            "business_function": business_function,
            "slide_type": intent.slide_type,
            "raw_title": intent.raw_title,
            "raw_content": intent.raw_content,
        },
        "search_preferences": [
            "official website",
            "annual reports",
            "investor relations",
            "earnings reports",
            "SEC filings",
            "reputable public business sources",
        ],
    }

    client = genai.Client(api_key=api_key)
    model = os.getenv("GEMINI_CONTEXT_MODEL", _DEFAULT_GEMINI_MODEL)
    prompt = build_prompt(
        "context",
        user_input=json.dumps(user_input, ensure_ascii=True),
        additional_context="IntentResult:",
    )
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0,
            tools=[types.Tool(google_search=types.GoogleSearch())],
        ),
    )

    return {
        "text": getattr(response, "text", "") or "",
        "citations": _extract_grounding_citations(response),
        "model": model,
    }


def _call_context_llm(
    intent: IntentResult,
    company: str,
    requested_industry: str | None,
    business_function: str | None,
) -> dict[str, Any]:
    """Call the multi-provider router for enterprise context building."""
    from backend.llm import router

    user_input = {
        "intent": {
            "company": company,
            "industry": requested_industry,
            "business_function": business_function,
            "slide_type": intent.slide_type,
            "raw_title": intent.raw_title,
            "raw_content": intent.raw_content,
        },
        "search_preferences": [
            "official website",
            "annual reports",
            "investor relations",
            "earnings reports",
            "SEC filings",
            "reputable public business sources",
        ],
    }

    prompt = build_prompt(
        "context",
        user_input=json.dumps(user_input, ensure_ascii=True),
        additional_context="IntentResult:",
    )
    return router.generate_json("context_builder", prompt, temperature=0.0)


def _parse_json_response(raw_response: dict[str, Any]) -> dict[str, Any]:
    text = raw_response.get("text", "")
    json_text = _strip_json_fence(text)
    parsed = json.loads(json_text)
    if not isinstance(parsed, dict):
        raise ValueError("Gemini context response was not a JSON object.")

    if raw_response.get("citations"):
        parsed.setdefault("_grounding_citations", raw_response["citations"])
    if raw_response.get("model"):
        parsed.setdefault("_model", raw_response["model"])
    return parsed


def _to_enterprise_context(
    payload: dict[str, Any],
    fallback_company: str,
    fallback_industry: str | None,
    fallback_business_function: str | None,
) -> EnterpriseContext:
    company = _clean_text(payload.get("company")) or fallback_company
    industry = _clean_text(payload.get("industry")) or fallback_industry or "Unknown"
    business_function = (
        _clean_text(payload.get("business_function"))
        or _clean_text(payload.get("domain"))
        or fallback_business_function
        or "Unknown"
    )
    company_summary = _clean_text(payload.get("company_summary")) or ""

    sources = _normalize_sources(payload.get("sources", []))
    citation_sources = _normalize_sources(payload.get("_grounding_citations", []))
    source_by_url = {source.url: source for source in sources}
    for source in citation_sources:
        source_by_url.setdefault(source.url, source)
    sources = list(source_by_url.values())

    facts = _normalize_facts(payload.get("facts", []), source_by_url)
    warnings = [warning for warning in payload.get("warnings", []) if isinstance(warning, str)]

    if company.lower() in {"unknown", "not found", "unavailable"}:
        warnings.append(f"Company could not be found: {fallback_company}.")

    return EnterpriseContext(
        company=company,
        industry=industry,
        business_function=business_function,
        company_summary=company_summary,
        facts=facts,
        sources=sources,
        warnings=warnings,
        enrichment_metadata={
            "provider": "gemini",
            "grounding": "google_search",
            "model": payload.get("_model", _DEFAULT_GEMINI_MODEL),
        },
    )


def _normalize_facts(items: Any, source_by_url: dict[str, ResearchSource]) -> list[ResearchFact]:
    facts: list[ResearchFact] = []
    seen: set[str] = set()
    if not isinstance(items, list):
        return facts

    for item in items:
        if not isinstance(item, dict):
            continue
        statement = _clean_text(item.get("statement") or item.get("claim"))
        url = _clean_text(item.get("url") or item.get("reference"))
        source_name = _clean_text(item.get("source") or item.get("label"))

        if not statement or not url:
            continue

        source = source_by_url.get(url)
        if source and not source_name:
            source_name = source.source
        source_name = source_name or _source_name_from_url(url)
        fact_type = _normalize_type(item.get("type"), default="company_fact")

        key = statement.lower()
        if key in seen:
            continue
        seen.add(key)
        facts.append(
            ResearchFact(
                statement=statement,
                source=source_name,
                url=url,
                type=fact_type,
            )
        )

    return facts


def _normalize_sources(items: Any) -> list[ResearchSource]:
    sources: list[ResearchSource] = []
    seen: set[str] = set()
    if not isinstance(items, list):
        return sources

    for item in items:
        if not isinstance(item, dict):
            continue
        url = _clean_text(item.get("url") or item.get("reference"))
        if not url or url in seen:
            continue
        seen.add(url)
        source = _clean_text(item.get("source") or item.get("label") or item.get("title"))
        sources.append(
            ResearchSource(
                source=source or _source_name_from_url(url),
                url=url,
                type=_normalize_type(item.get("type"), default="business_source"),
            )
        )

    return sources


def _extract_grounding_citations(interaction: Any) -> list[dict[str, str]]:
    citations: list[dict[str, str]] = []
    for candidate in getattr(interaction, "candidates", []) or []:
        metadata = getattr(candidate, "grounding_metadata", None)
        for chunk in getattr(metadata, "grounding_chunks", []) or []:
            web = getattr(chunk, "web", None)
            url = getattr(web, "uri", None)
            if not url:
                continue
            citations.append(
                {
                    "source": getattr(web, "title", None) or _source_name_from_url(url),
                    "url": url,
                    "type": "business_source",
                }
            )

    for step in getattr(interaction, "steps", []) or []:
        if getattr(step, "type", None) != "model_output":
            continue
        for block in getattr(step, "content", []) or []:
            for annotation in getattr(block, "annotations", []) or []:
                if getattr(annotation, "type", None) != "url_citation":
                    continue
                url = getattr(annotation, "url", None)
                if not url:
                    continue
                citations.append(
                    {
                        "source": getattr(annotation, "title", None) or _source_name_from_url(url),
                        "url": url,
                        "type": "business_source",
                    }
                )
    return citations


def _company_from_intent(intent: IntentResult) -> str | None:
    direct = _first_non_empty(
        getattr(intent, "company", None),
        intent.metadata.get("company") if intent.metadata else None,
    )
    if direct:
        return direct

    combined = f"{intent.raw_title}\n{intent.raw_content}"
    patterns = [
        r"\b(?:for|about|on|at)\s+([A-Z][A-Za-z0-9&.\- ]{1,60})(?:\s+(?:current state|finance|retail|process|workflow|slide)\b|[.,:\n]|$)",
        r"\bcompany\s*[:=-]\s*([A-Z][A-Za-z0-9&.\- ]{1,60})(?:[.,:\n]|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, combined)
        if match:
            return _clean_company(match.group(1))
    return None


def _strip_json_fence(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _first_non_empty(*values: Any) -> str | None:
    for value in values:
        cleaned = _clean_text(value)
        if cleaned:
            return cleaned
    return None


def _clean_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split()).strip()
    return cleaned or None


def _clean_company(value: str) -> str | None:
    cleaned = _clean_text(value)
    if not cleaned:
        return None
    stop_phrases = [" current state", " finance", " retail", " process", " workflow", " slide"]
    lowered = cleaned.lower()
    for phrase in stop_phrases:
        index = lowered.find(phrase)
        if index > 0:
            cleaned = cleaned[:index].strip()
            break
    return cleaned or None


def _normalize_type(value: Any, default: str) -> str:
    cleaned = _clean_text(value)
    if cleaned in _SOURCE_TYPES or cleaned == "company_fact":
        return cleaned
    return default


def _source_name_from_url(url: str) -> str:
    match = re.match(r"https?://(?:www\.)?([^/]+)", url)
    return match.group(1) if match else "Public source"

"""
backend/modules/intent_entity_extractor.py
==========================================
Sprint H.2 — Deterministic entity extractor for the Intent module.

Loads reusable entity mappings from ``backend/knowledge/intent_entities.json``
and extracts structured intent fields from the raw user prompt.

Extraction strategy:
- Company names via regex (handles possessives such as "Microsoft's").
- Industry, business function, and audience via keyword/alias matching.
- Objective via heuristic cleanup of the request sentence.

The module is fully deterministic and does not call any LLM.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_ENTITIES_PATH = Path(__file__).resolve().parents[1] / "knowledge" / "intent_entities.json"


class _EntityCache:
    """Simple cache for the parsed intent entity knowledge base."""

    def __init__(self) -> None:
        self._data: dict[str, Any] | None = None

    def load(self) -> dict[str, Any]:
        if self._data is None:
            self._data = json.loads(_ENTITIES_PATH.read_text(encoding="utf-8"))
        return self._data


_entity_cache = _EntityCache()


def load_entities() -> dict[str, Any]:
    """Return the parsed ``intent_entities.json`` knowledge base."""
    return _entity_cache.load()


def normalize_text(text: str | None) -> str:
    """Lowercase and collapse whitespace for normalized matching."""
    if not text:
        return ""
    return " ".join(str(text).lower().split())


def _boundary_pattern(term: str) -> str:
    """Return a regex that matches ``term`` as a whole word/phrase."""
    return rf"(?<!\w){re.escape(term)}(?!\w)"


def _best_category_match(text: str, category_map: dict[str, list[str]]) -> tuple[str, str] | None:
    """
    Find the canonical category whose alias has the longest match in ``text``.

    Returns ``(canonical, matched_alias)`` or ``None``.
    """
    text_lower = text.lower()
    best: tuple[int, str, str] | None = None

    for canonical, aliases in category_map.items():
        for alias in aliases:
            alias_lower = alias.lower()
            pattern = _boundary_pattern(alias_lower)
            for match in re.finditer(pattern, text_lower):
                if best is None or len(alias) > best[0]:
                    best = (len(alias), canonical, alias)

    if best is None:
        return None
    return best[1], best[2]


def _clean_company(value: str, entities: dict[str, Any]) -> str | None:
    """
    Strip trailing punctuation, possessives, and entity-like trailing words
    from a company candidate.

    Trailing business-function, industry, audience, and stop-phrase words are
    removed so that ``Microsoft's AI Procurement Transformation`` is cleaned
    to ``Microsoft``.
    """
    cleaned = " ".join(value.split()).strip().rstrip(".,:;")

    # Build a sorted list of trim phrases: stop phrases + entity aliases.
    # Longest phrases are checked first so multi-word aliases are removed whole.
    trim_phrases: set[str] = set()
    trim_phrases.update(entities.get("company_stop_phrases", []))
    for category in ("business_functions", "industries", "audiences"):
        for aliases in entities.get(category, {}).values():
            trim_phrases.update(str(alias).strip() for alias in aliases if alias)

    sorted_phrases = sorted(trim_phrases, key=len, reverse=True)

    changed = True
    while changed:
        changed = False

        # Remove trailing possessive before phrase checks.
        if cleaned.lower().endswith("'s"):
            cleaned = cleaned[:-2].strip()
            changed = True

        lowered = cleaned.lower()
        for phrase in sorted_phrases:
            phrase_lower = phrase.lower()
            if lowered == phrase_lower:
                cleaned = ""
                changed = True
                break
            if lowered.endswith(" " + phrase_lower):
                cleaned = cleaned[: -(len(phrase) + 1)].strip().rstrip(",")
                changed = True
                break

        if not cleaned:
            break

    cleaned = cleaned.rstrip(".,:;")
    return cleaned if cleaned else None


def _is_business_function_keyword(text: str, entities: dict[str, Any]) -> bool:
    """Return True if the candidate exactly matches a business-function alias."""
    lowered = text.lower()
    for aliases in entities.get("business_functions", {}).values():
        for alias in aliases:
            if alias.lower() == lowered:
                return True
    return False


def extract_company(text: str, entities: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Extract a company name from ``text`` using regex heuristics.

    Handles possessive forms ("Microsoft's") and strips trailing stop phrases.
    """
    if entities is None:
        entities = load_entities()

    stop_phrases = entities.get("company_stop_phrases", [])

    patterns = [
        # "for Microsoft", "about Amazon", "at Toyota" (including possessives)
        # The group is non-greedy so it stops at the first stop phrase, period,
        # or end of string. Compiled case-insensitively so capitalised stop
        # phrases like "Transformation" still terminate the match.
        (
            r"\b(?:for|about|on|at|by)\s+([A-Z][A-Za-z0-9&\.\-' ]{1,60}?)(?:'s)?(?:\s+(?:"
            + "|".join(re.escape(p) for p in stop_phrases)
            + r")\b|[.,:\n]|$)",
            re.IGNORECASE,
        ),
        # "company: Microsoft"
        (
            r"\b(?:company|client|organization)\s*[:=-]\s*([A-Z][A-Za-z0-9&\.\-' ]{1,60}?)(?:'s)?(?:[.,:\n]|$)",
            re.IGNORECASE,
        ),
    ]

    for pattern, flags in patterns:
        match = re.search(pattern, text, flags)
        if match:
            candidate = _clean_company(match.group(1), entities)
            if candidate and candidate[0].isupper() and not _is_business_function_keyword(candidate, entities):
                return {"value": candidate, "confidence": 0.95}

    return {"value": None, "confidence": 0.0}


def extract_industry(
    text: str,
    company_value: str | None,
    entities: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Extract an industry from ``text`` or from the known-company lookup.

    Prefers explicit industry terms in the text; falls back to the
    known-companies table when a company was detected.
    """
    if entities is None:
        entities = load_entities()

    match = _best_category_match(text, entities.get("industries", {}))
    if match:
        return {"value": match[0], "confidence": 0.9}

    if company_value:
        known = entities.get("known_companies", {})
        # Prefer case-insensitive exact match; otherwise try normalized match.
        for name, industry in known.items():
            if name.lower() == company_value.lower():
                return {"value": industry, "confidence": 0.85}

    return {"value": None, "confidence": 0.0}


def extract_business_function(
    text: str, entities: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Extract a canonical business function via keyword/alias matching."""
    if entities is None:
        entities = load_entities()

    match = _best_category_match(text, entities.get("business_functions", {}))
    if match:
        return {"value": match[0], "confidence": 0.9}

    return {"value": None, "confidence": 0.0}


def extract_audience(
    text: str, entities: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Extract a canonical audience via keyword/alias matching."""
    if entities is None:
        entities = load_entities()

    match = _best_category_match(text, entities.get("audiences", {}))
    if match:
        return {"value": match[0], "confidence": 0.85}

    return {"value": None, "confidence": 0.0}


def extract_objective(text: str, company_value: str | None = None) -> dict[str, Any]:
    """
    Extract the objective/topic of the request via heuristic sentence cleanup.

    Captures the phrase that follows the instructional prefix and the first
    "for/about/on" preposition, then strips the detected company name and any
    trailing audience phrase so the remaining text describes what the deck is
    about.
    """
    sentence = text.strip()

    deliverables = (
        "executive summary|operating model|slide|deck|presentation|summary|"
        "process|workflow|proposal|initiative|program|plan|update|strategy|"
        "roadmap|transformation"
    )
    audiences = (
        "board of directors|board|executives|executive committee|leadership|"
        "management|stakeholders|sponsors|team"
    )

    # Match instructional prefix + deliverable + first preposition, capturing
    # everything up to an optional trailing audience phrase.
    pattern = rf"(?i)^(?:create|build|make|generate|design|prepare|develop)\s+(?:an?\s+)?(?:[\w\s]+?\s+)?(?:{deliverables})\s+(?:for|about|on)\s+(.+?)(?:\s+for\s+(?:the\s+)?(?:{audiences})\b.*)?$"
    match = re.search(pattern, sentence)
    sentence = match.group(1).strip() if match else sentence

    # Remove leading company name/possessive.
    if company_value:
        sentence = re.sub(
            rf"^{re.escape(company_value)}'?s?\s+",
            "",
            sentence,
            flags=re.IGNORECASE,
        )

    # Remove any remaining trailing audience phrase.
    sentence = re.sub(
        rf"\s+for\s+(?:the\s+)?(?:{audiences})\b.*$",
        "",
        sentence,
        flags=re.IGNORECASE,
    )

    # Remove leading articles.
    sentence = re.sub(r"^(?:a|an|the)\s+", "", sentence, flags=re.IGNORECASE)

    # Keep only the first clause/sentence.
    sentence = re.split(r"[.!?]\s+", sentence)[0]

    sentence = sentence.strip().rstrip(".,:;")

    if len(sentence) < 3:
        return {"value": None, "confidence": 0.0}

    return {"value": sentence, "confidence": 0.75}


def extract_entities(
    title: str, content: str, entities: dict[str, Any] | None = None
) -> dict[str, dict[str, Any]]:
    """
    Run deterministic extraction for all intent fields.

    Returns a dict of ``field -> {"value": ..., "confidence": ...}``.

    Both ``title`` and ``content`` are combined for extraction. In many
    frontend flows (including the Office.js add-in) the user's full prompt is
    passed as ``title`` while ``content`` is empty. Combining the fields lets
    the deterministic extractor find company, function, and other entities
    regardless of which field carried them.
    """
    if entities is None:
        entities = load_entities()

    text = f"{title or ''} {content or ''}".strip()

    company_result = extract_company(text, entities)
    industry_result = extract_industry(text, company_result.get("value"), entities)
    business_function_result = extract_business_function(text, entities)
    audience_result = extract_audience(text, entities)
    # Objective should be derived from the user's prompt text. Prefer explicit
    # content; fall back to title when the frontend only populated one field.
    objective_text = content or title or ""
    objective_result = extract_objective(objective_text, company_result.get("value"))

    # If the objective is just an audience phrase (e.g., "the board"), discard it.
    if objective_result.get("value"):
        objective_lower = str(objective_result["value"]).lower()
        audience_aliases = set()
        for aliases in entities.get("audiences", {}).values():
            audience_aliases.update(str(a).lower() for a in aliases)
        if objective_lower in audience_aliases or len(objective_lower) < 4:
            objective_result = {"value": None, "confidence": 0.0}

    return {
        "company": company_result,
        "industry": industry_result,
        "business_function": business_function_result,
        "audience": audience_result,
        "objective": objective_result,
    }


def overall_confidence(entities_result: dict[str, dict[str, Any]]) -> float:
    """
    Compute an overall extraction confidence as the average confidence across
    the five standard intent fields. Missing fields contribute 0.0.
    """
    fields = ["company", "industry", "business_function", "audience", "objective"]
    total = sum(entities_result.get(field, {}).get("confidence", 0.0) for field in fields)
    return round(total / len(fields), 2)


def get_value(entities_result: dict[str, dict[str, Any]], field: str) -> Optional[str]:
    """Return the extracted string value for ``field``, or ``None``."""
    value = entities_result.get(field, {}).get("value")
    return str(value).strip() if value else None

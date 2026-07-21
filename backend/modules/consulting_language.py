"""
backend/modules/consulting_language.py
======================================
Deterministic consulting-language quality checks.

This module is deliberately offline and rule-based. It catches the quality
failures that make generated decks feel obviously AI-authored before they reach
PowerPoint rendering: filler phrases, role/content mismatch, weak roadmap
labels, unsupported numeric claims, and repeated language.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any


GENERIC_PHRASES = (
    "leverage ai",
    "improve compliance",
    "enhance collaboration",
    "drive efficiency",
    "optimize processes",
    "streamline workflows",
    "key considerations",
    "this slide shows",
    "overview of",
    "enable transformation",
)

_NUMERIC_CLAIM_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:%|percent|bps?|x|days?|weeks?|months?|hours?|hrs?)\b",
    re.I,
)

_INCOMPLETE_ENDING_WORDS = {
    "and",
    "or",
    "of",
    "for",
    "to",
    "with",
    "through",
    "by",
    "in",
    "on",
    "as",
    "from",
    "into",
    "across",
    "between",
    "at",
    "all",
    "driving",
    "highlighting",
    "including",
    "enabling",
    "leading",
    "supporting",
    "creating",
    "delivering",
    "reducing",
    "improving",
    "enhancing",
}


@dataclass
class ConsultingLanguageResult:
    """Result of one slide's consulting-language quality check."""

    warnings: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.issues


def validate_consulting_language(raw: dict[str, Any], slide_role: str = "") -> ConsultingLanguageResult:
    """Validate one slide against board-level consulting content contracts."""
    result = ConsultingLanguageResult()
    texts = list(_walk_text(raw))
    joined = " ".join(texts)
    normalized = joined.lower()
    role = slide_role.lower()
    action_register_shape = _is_action_register_shape(raw)
    decision_request_shape = _is_decision_request_shape(raw)

    for phrase in GENERIC_PHRASES:
        if phrase in normalized:
            result.warnings.append(f"generic consulting language: {phrase!r}")

    for claim in _NUMERIC_CLAIM_RE.findall(joined):
        window = _context_window(joined, claim)
        if _claim_is_in_timing_field(raw, claim):
            continue
        if _claim_is_kpi_metric_value(raw, claim, role):
            continue
        if _claim_is_investment_metric_value(raw, claim, role):
            continue
        if _is_operational_timing_claim(
            claim,
            role,
            window,
            normalized,
            action_register_shape=action_register_shape,
        ):
            continue
        if "illustrative" not in window.lower() and "source" not in window.lower():
            result.warnings.append(f"unsupported numeric claim: {claim!r}")

    repeated = repeated_phrases(texts)
    for phrase, count in repeated.items():
        if count >= 3:
            result.warnings.append(f"repeated phrase: {phrase!r} ({count}x)")

    for text in texts:
        if _looks_incomplete_phrase(text):
            result.issues.append(f"incomplete phrase: {text!r}")

    so_what = _extract_so_what(raw)
    if (
        not _is_board_level_so_what(so_what)
        and not _action_register_has_board_ready_contract(raw)
        and not _decision_request_has_board_ready_contract(raw)
    ):
        result.issues.append("missing board-level so-what.")

    if "benefit" in role or "value" in role:
        _require_any(normalized, ("cost", "speed", "risk", "control", "cash", "margin", "value", "cycle"), "benefits require explicit value levers.", result)
    if "use case" in role:
        _require_any(normalized, ("workflow", "process", "sourcing", "invoice", "supplier", "requisition"), "use cases require workflow context.", result)
        _require_any(normalized, ("ai", "model", "automation", "analytics", "prediction", "agent"), "use cases require AI capability.", result)
        _require_any(normalized, ("outcome", "reduce", "increase", "improve", "accelerate", "control", "value", "savings", "cycle", "accuracy", "visibility", "spend", "risk"), "use cases require business outcome.", result)
    if "roadmap" in role or "implementation" in role:
        for leaked in ("step 1", "step 2", "phase 1", "phase 2", "item 1"):
            if leaked in normalized:
                result.issues.append("roadmap phases must be named, not generic numbered labels.")
                break
    if "risk" in role:
        _require_any(normalized, ("cause", "driver", "because", "due to", "root", "dependency"), "risks require cause.", result)
        _require_any(normalized, ("impact", "delay", "cost", "adoption", "control", "exposure", "disruption", "value leakage"), "risks require impact.", result)
        _require_any(normalized, ("mitigation", "mitigate", "control", "owner", "ownership", "sponsor", "accountable", "response"), "risks require mitigation and ownership.", result)
    if "next step" in role or "decision" in role or "action" in role or action_register_shape or decision_request_shape:
        if decision_request_shape:
            if not _decision_request_has_board_ready_contract(raw):
                result.issues.append("decision request requires decision, urgency, impact, and delay consequence.")
        elif not _has_action_register_decision(raw):
            _require_any(normalized, ("approve", "decide", "decision", "confirm", "endorse", "authorize", "fund", "prioritize", "launch"), "next steps require a board decision.", result)
        if not decision_request_shape:
            _require_any(normalized, ("owner", "sponsor", "cfo", "coo", "cio", "procurement"), "next steps require an owner.", result)
            if not _has_action_register_timing(raw):
                _require_any(normalized, ("q1", "q2", "q3", "q4", "week", "month", "day", "days", "30", "60", "90", "by "), "next steps require timing.", result)

    return result


def repeated_phrases(texts: list[str], *, phrase_size: int = 3) -> dict[str, int]:
    """Return repeated word n-grams across slide text."""
    counts: Counter[str] = Counter()
    for text in texts:
        words = [
            word
            for word in re.findall(r"[a-zA-Z][a-zA-Z0-9&'-]*", text.lower())
            if len(word) > 2
        ]
        for index in range(0, max(0, len(words) - phrase_size + 1)):
            phrase = " ".join(words[index : index + phrase_size])
            counts[phrase] += 1
    return {phrase: count for phrase, count in counts.items() if count > 1}


def _require_any(text: str, terms: tuple[str, ...], message: str, result: ConsultingLanguageResult) -> None:
    if not any(term in text for term in terms):
        result.issues.append(message)


def _is_operational_timing_claim(
    claim: str,
    role: str,
    window: str,
    full_text: str = "",
    *,
    action_register_shape: bool = False,
) -> bool:
    """Timing commitments in roadmap/next-step content are plans, not unsupported value claims."""
    claim_lower = claim.lower()
    if not re.search(r"\b(days?|weeks?|months?|hours?|hrs?)\b", claim_lower):
        return False
    if action_register_shape:
        return True
    if any(term in role for term in ("next step", "decision", "action", "roadmap", "implementation")):
        return True
    window_lower = window.lower()
    if any(term in window_lower for term in ("timing", "by ", "within", "pilot", "launch", "wave", "when")):
        return True
    return (
        any(term in full_text for term in ("approve", "authorize", "decision", "owner", "sponsor"))
        and any(term in full_text for term in ("pilot", "launch", "action", "next step"))
    )


def _extract_so_what(raw: dict[str, Any]) -> str:
    first_candidate = ""
    for key in ("so_what", "executive_summary", "subtitle", "description", "headline", "title"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            cleaned = value.strip()
            if not first_candidate:
                first_candidate = cleaned
            if _is_board_level_so_what(cleaned):
                return cleaned
    summary = raw.get("summary")
    if isinstance(summary, dict):
        for key in ("headline", "description"):
            value = summary.get(key)
            if isinstance(value, str) and value.strip():
                cleaned = value.strip()
                if _is_board_level_so_what(cleaned):
                    return cleaned
    candidates = [
        text for text in _walk_text(raw)
        if len(text.split()) >= 6 and _has_implication_language(text)
    ]
    if candidates:
        return max(candidates, key=len)
    return first_candidate


def _is_action_register_shape(raw: dict[str, Any]) -> bool:
    keys = set(_walk_keys(raw))
    has_action = any("next_step" in key or "action" in key or "decision" in key for key in keys)
    has_timing = any("when" in key or "timing" in key for key in keys)
    has_owner = any("who" in key or "owner" in key for key in keys)
    has_row_binding = any(
        key.startswith("row_") and ("next_step" in key or "when" in key or "who" in key)
        for key in keys
    )
    return has_row_binding or (has_action and has_timing and has_owner)


def _is_decision_request_shape(raw: dict[str, Any]) -> bool:
    keys = set(_walk_keys(raw))
    has_decision_cards = any(key == "decision_title" or key.startswith("decision_") for key in keys)
    has_why_now = any("why_now" in key for key in keys)
    has_delay = any(key.startswith("delay_") or "delay" in key for key in keys)
    return has_decision_cards and has_why_now and has_delay


def _decision_request_has_board_ready_contract(raw: dict[str, Any]) -> bool:
    if not _is_decision_request_shape(raw):
        return False
    text = " ".join(_walk_text(raw)).lower()
    has_decision = any(term in text for term in ("approve", "authorize", "confirm", "endorse", "fund", "decision"))
    has_urgency = any(term in text for term in ("now", "must", "needed", "unlock", "window", "before", "prevent"))
    has_impact = any(term in text for term in ("impact", "enable", "protect", "control", "value", "speed", "benefit"))
    has_delay = any(term in text for term in ("delay", "slip", "slow", "missed", "unowned", "defer"))
    return has_decision and has_urgency and has_impact and has_delay


def _has_action_register_decision(raw: dict[str, Any]) -> bool:
    decision_terms = ("approve", "decide", "decision", "confirm", "endorse", "authorize", "fund", "prioritize", "launch")
    for key_lower, text in _walk_key_text(raw):
        if not (
            key_lower.startswith("row_")
            or key_lower in {"title", "decision", "action", "next_step", "next_steps"}
            or "next_step" in key_lower
            or "decision" in key_lower
            or "action" in key_lower
        ):
            continue
        if any(term in text for term in decision_terms):
            return True
    return False


def _has_action_register_timing(raw: dict[str, Any]) -> bool:
    for key_lower, text in _walk_key_text(raw):
        if "when" not in key_lower and "timing" not in key_lower:
            continue
        if re.search(r"\b(q[1-4]|week|month|day|days|30|60|90|by\s+)\b", text):
            return True
    return False


def _action_register_has_board_ready_contract(raw: dict[str, Any]) -> bool:
    if not _is_action_register_shape(raw):
        return False
    return _has_action_register_decision(raw) and _has_action_register_timing(raw) and _has_action_register_owner(raw)


def _has_action_register_owner(raw: dict[str, Any]) -> bool:
    for key_lower, text in _walk_key_text(raw):
        if "who" not in key_lower and "owner" not in key_lower:
            continue
        if any(term in text for term in ("owner", "sponsor", "cfo", "coo", "cio", "procurement", "lead")):
            return True
    return False


def _claim_is_in_timing_field(raw: dict[str, Any], claim: str) -> bool:
    claim_lower = claim.lower()
    for key_lower, text in _walk_key_text(raw):
        if not any(term in key_lower for term in ("when", "timing", "duration", "date")):
            continue
        if claim_lower in text:
            return True
    return False


def _claim_is_kpi_metric_value(raw: dict[str, Any], claim: str, role: str) -> bool:
    if not any(term in role for term in ("kpi", "metric", "success")):
        return False
    claim_lower = claim.lower()
    for key_lower, text in _walk_key_text(raw):
        if (
            key_lower not in {"value", "metric", "target", "kpi_value", "kpi_target"}
            and "kpi_value" not in key_lower
            and "kpi_target" not in key_lower
        ):
            continue
        if claim_lower in text:
            return True
    return False


def _claim_is_investment_metric_value(raw: dict[str, Any], claim: str, role: str) -> bool:
    if not any(term in role for term in ("investment", "business case", "funding", "roi", "payback")):
        return False
    claim_lower = claim.lower()
    metric_keys = (
        "investment_required_value",
        "value_created_value",
        "timing_value",
        "payback_value",
        "value_investment_value",
        "npv",
        "roi",
        "capture_value",
        "component_value",
    )
    for key_lower, text in _walk_key_text(raw):
        if not any(metric_key in key_lower for metric_key in metric_keys):
            continue
        if claim_lower in text:
            return True
    return False


def _is_board_level_so_what(text: str) -> bool:
    if not text:
        return False
    if _looks_incomplete_phrase(text):
        return False
    words = text.split()
    if len(words) >= 6:
        return True
    return len(words) >= 4 and _has_implication_language(text)


def _has_implication_language(text: str) -> bool:
    normalized = text.lower()
    terms = (
        "accelerate",
        "reduce",
        "increase",
        "improve",
        "protect",
        "unlock",
        "enable",
        "requires",
        "should",
        "must",
        "approve",
        "decide",
        "risk",
        "value",
        "cost",
        "control",
        "margin",
        "cash",
        "adoption",
        "supplier",
        "procurement",
    )
    return any(term in normalized for term in terms)


def _walk_text(value: Any):
    if isinstance(value, str):
        cleaned = " ".join(value.split())
        if cleaned:
            yield cleaned
    elif isinstance(value, dict):
        for child in value.values():
            yield from _walk_text(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_text(child)


def _looks_incomplete_phrase(text: str) -> bool:
    cleaned = " ".join(str(text or "").split()).strip(" -:;,.")
    if not cleaned:
        return False
    words = re.findall(r"[A-Za-z][A-Za-z'-]*", cleaned)
    if not words:
        return False
    last = words[-1].lower()
    if last in _INCOMPLETE_ENDING_WORDS:
        return True
    return bool(
        re.search(
            r"\b(this slide outlines|this slide highlights|this slide shows)\b",
            cleaned,
            flags=re.I,
        )
    )


def _walk_keys(value: Any):
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key).lower()
            yield from _walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_keys(child)


def _walk_key_text(value: Any):
    if isinstance(value, dict):
        for key, child in value.items():
            key_lower = str(key).lower()
            text = " ".join(_walk_text(child)).lower()
            if text:
                yield key_lower, text
            yield from _walk_key_text(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_key_text(child)


def _context_window(text: str, match: str, window: int = 40) -> str:
    index = text.find(match)
    if index < 0:
        return match
    return text[max(0, index - window) : index + len(match) + window]

"""
backend/modules/presentation_planner.py
=======================================
Sprint E.1 — Intelligent Narrative Planner.

This module is responsible ONLY for planning the consulting narrative.
It does NOT generate slide content, KPIs, business activities, pain points,
or rendering instructions.

Inputs:
    - The original user prompt (str).
    - A structured IntentResult.

Output:
    - A DeckSpec describing the deck plan: presentation type, objective,
      audience, narrative, estimated slide count, and an ordered sequence
      of SlidePlan objects.

Behavior:
    1. Classify the request using the Presentation Classifier.
    2. Load the matching taxonomy entry from presentation_taxonomy.json.
    3. Use the taxonomy as the narrative scaffold.
    4. Adapt/customize the scaffold to the user's specific prompt via LLM.
    5. Return the validated DeckSpec.

If the LLM is unavailable, the planner falls back to a taxonomy-grounded
plan personalized with intent fields.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from backend.llm.prompt_loader import build_prompt
from backend.modules.presentation_classifier import classify_presentation
from backend.modules.story_templates import StoryTemplateRole, find_story_template, get_story_template
from schemas.intent import IntentResult
from schemas.presentation import DeckSpec, PresentationClassification, SlidePlan

logger = logging.getLogger(__name__)

_TAXONOMY_PATH = Path(__file__).resolve().parents[1] / "knowledge" / "presentation_taxonomy.json"


class _TaxonomyCache:
    """Simple cache for the parsed presentation taxonomy."""

    def __init__(self) -> None:
        self._data: dict[str, Any] | None = None

    def load(self) -> dict[str, Any]:
        if self._data is None:
            self._data = json.loads(_TAXONOMY_PATH.read_text(encoding="utf-8"))
        return self._data


_taxonomy_cache = _TaxonomyCache()


def plan_presentation(user_prompt: str, intent: IntentResult) -> DeckSpec:
    """
    Plan a consulting deck from the original user prompt and extracted intent.

    The original user prompt is the primary input. IntentResult provides
    structured context such as company, industry, and business function.

    Parameters
    ----------
    user_prompt:
        The original request from the consultant.
    intent:
        Structured intent extracted from the request.

    Returns
    -------
    DeckSpec
        A pure planning artifact describing what deck should be created.
        If the LLM fails, a deterministic taxonomy-grounded fallback plan
        is returned.
    """
    logger.info(
        "planning presentation: user_prompt=%r company=%s function=%s",
        user_prompt,
        intent.company or "Unknown",
        intent.business_function or "Unknown",
    )

    classification = classify_presentation(user_prompt, intent)
    logger.info(
        "presentation classified as %s (confidence=%.2f)",
        classification.presentation_type,
        classification.confidence,
    )

    taxonomy = _taxonomy_cache.load()
    taxonomy_entry = _get_taxonomy_entry(taxonomy, classification)

    try:
        payload = _call_presentation_planner_llm(
            user_prompt, intent, classification, taxonomy_entry
        )
        deck_spec = _to_deck_spec(payload)
    except Exception as exc:  # noqa: BLE001 - fallback keeps planner runnable.
        logger.warning("presentation planner LLM failed; using taxonomy fallback: %s", exc)
        deck_spec = _taxonomy_fallback_deck(user_prompt, intent, classification, taxonomy_entry)

    single_slide_role = _single_slide_role_requested(user_prompt)
    if single_slide_role is not None:
        deck_spec = _force_single_slide_deck(user_prompt, deck_spec, single_slide_role)
        deck_spec = _score_planner_confidence(user_prompt, deck_spec)
        return deck_spec

    deck_spec = _apply_story_template(user_prompt, deck_spec)
    deck_spec = _reconcile_enumerated_slides(user_prompt, deck_spec)
    deck_spec = _score_planner_confidence(user_prompt, deck_spec)
    return deck_spec


# ── Enumerated-slide reconciliation ───────────────────────────────────────────

# Maximum number of slides an enumerated prompt may produce. Guards against
# run-away parsing of long prompts with many comma-separated clauses.
_MAX_DECK_SLIDES = 18

# Generic role keywords drawn from a topic name to detect existing matches.
_ROLE_KEYWORD_BUCKETS = {
    "executive summary": ("executive summary", "summary", "overview"),
    "section divider": (
        "section divider", "dark section divider", "section break",
        "chapter divider", "divider slide",
    ),
    "current state vs future state": (
        "current state vs future state", "current state versus future state",
        "current vs future", "current versus future", "from current to future",
        "from-to", "from to", "transformation shifts",
    ),
    "current state": (
        "current state", "current procurement challenges", "challenges",
        "baseline", "as-is", "current operating model", "current", "baseline",
    ),
    "future state": (
        "future state", "future-state operating model", "future operating model",
        "target state", "vision", "future",
    ),
    "investment case": (
        "investment case", "business case", "funding request", "funding",
        "budget", "roi", "return on investment", "payback", "value case",
        "financial case", "economics",
    ),
    "value realization roadmap": (
        "value realization roadmap", "value realisation roadmap",
        "value realization", "value realisation", "benefit capture roadmap",
        "benefits roadmap", "benefit roadmap", "time-phased value",
        "time phased value", "value capture", "benefit pools",
    ),
    "business benefits": ("business benefits", "benefits", "benefit"),
    "ai use cases": ("ai use cases", "use cases", "use case", "ai use case"),
    "implementation roadmap": ("implementation roadmap", "roadmap", "rollout plan"),
    "transformation timeline": ("transformation timeline", "timeline", "milestones", "schedule"),
    "risk register": (
        "risk register", "implementation risk register", "risk log",
        "mitigation register", "risk table",
    ),
    "implementation risks": ("implementation risks", "risks", "risk"),
    "kpi scorecard table": (
        "kpi scorecard table", "kpi scorecard", "scorecard table",
        "metric scorecard", "performance scorecard", "management scorecard",
    ),
    "kpis for success": ("kpis for success", "kpis", "kpi", "success metrics", "success"),
    "next steps": (
        "next steps", "next step", "actions", "immediate actions", "recommendations",
        "board decisions", "board decision", "decisions", "decision", "approvals", "approval",
    ),
    "opportunities": ("opportunities", "opportunity", "improvement areas"),
    "maturity assessment": ("maturity assessment", "maturity"),
}


def _extract_enumerated_topics(user_prompt: str) -> list[str]:
    """
    Pull a list of explicitly enumerated slide-like topics from the user prompt.

    Looks for the "Include X, Y, and Z" / "Include a, b, c, d" pattern that
    the Microsoft board prompt uses. Returns an empty list when no enumeration
    is detected.
    """
    if not user_prompt:
        return []
    text = " ".join(user_prompt.split())
    lowered = text.lower()
    # Find the clause starting with "include" (case-insensitive) up to the
    # next sentence boundary.
    start = lowered.find("include")
    if start == -1:
        return []
    tail = text[start:]
    # Cut at the first sentence-ending period followed by space / end.
    cut = -1
    for i, ch in enumerate(tail):
        if ch == "." and (i + 1 >= len(tail) or tail[i + 1].isspace()):
            cut = i
            break
    if cut != -1:
        tail = tail[:cut]
    # Drop the leading "Include" verb and the audience qualifier, keep the list.
    body = tail[len("include"):].strip()
    # Trim leading "an" / "a" / "the"
    body = body.lstrip()
    if body.lower().startswith("an "):
        body = body[3:]
    elif body.lower().startswith("a "):
        body = body[2:]
    elif body.lower().startswith("the "):
        body = body[4:]
    body = body.strip()
    # Drop an optional trailing audience clause: "... and next steps. The audience is ..."
    # Already handled by the cut above; ensure final word trimmed of period.
    body = body.rstrip(".")

    # Split on commas and the word "and".
    parts: list[str] = []
    for chunk in body.split(","):
        for sub in chunk.split(" and "):
            sub = sub.strip()
            if sub:
                parts.append(sub)
    # Keep tokens that look like slide topics (>1 word OR known keyword).
    return [p for p in parts if len(p.split()) >= 1 and len(p) <= 80]


def _canonical_role_for_text(text: str) -> str | None:
    """Map free-form slide text to a canonical role key, or None."""
    lowered = text.lower()
    if "section" in lowered and ("divider" in lowered or "break" in lowered):
        return "section divider"
    if "divider slide" in lowered or "chapter divider" in lowered:
        return "section divider"
    if (
        ("current" in lowered and "future" in lowered)
        or ("from" in lowered and "to" in lowered)
        or "transformation shifts" in lowered
    ):
        return "current state vs future state"
    if (
        "risk register" in lowered
        or "risk log" in lowered
        or "mitigation register" in lowered
        or ("risk" in lowered and "owner" in lowered and "status" in lowered)
    ):
        return "risk register"
    if (
        "scorecard" in lowered
        and ("kpi" in lowered or "metric" in lowered or "performance" in lowered)
    ):
        return "kpi scorecard table"
    if (
        "value realization" in lowered
        or "value realisation" in lowered
        or "benefit capture roadmap" in lowered
        or "benefit pools" in lowered
        or "time-phased value" in lowered
        or "time phased value" in lowered
    ):
        return "value realization roadmap"
    for role_key, keywords in _ROLE_KEYWORD_BUCKETS.items():
        if role_key in lowered:
            return role_key
        if any(k in lowered for k in keywords):
            return role_key
    return None


def _single_slide_role_requested(user_prompt: str) -> str | None:
    """Return the requested canonical role when the prompt hard-limits output to one slide."""
    text = " ".join(str(user_prompt or "").lower().split())
    if not text:
        return None
    single_slide_signal = (
        "create only" in text
        or "generate only" in text
        or "only one slide" in text
        or "one slide only" in text
        or "1-slide" in text
        or "single slide" in text
        or "do not create any other slides" in text
        or "do not include any other slides" in text
        or "do not create other slides" in text
    )
    if not single_slide_signal:
        return None
    return _canonical_role_for_text(user_prompt)


def _force_single_slide_deck(user_prompt: str, deck_spec: DeckSpec, canonical_role: str) -> DeckSpec:
    """Honor explicit single-slide prompts before story templates can expand them."""
    display_role = _ROLE_DISPLAY_NAMES.get(canonical_role, _titlecase_topic(canonical_role))
    existing = next(
        (slide for slide in deck_spec.slides if _canonical_role_for_text(slide.slide_role) == canonical_role),
        None,
    )
    purpose = _purpose_for_canonical_role(display_role, canonical_role)
    prompt_constraints = _single_slide_prompt_constraints(user_prompt)
    if prompt_constraints:
        purpose = f"{purpose} {prompt_constraints}"
    slide = SlidePlan(
        slide_number=1,
        slide_role=display_role,
        purpose=purpose,
        required_inputs=existing.required_inputs if existing else [],
        dependencies=[],
        visualization_type=_ROLE_VISUALIZATION_HINT.get(canonical_role, display_role),
        confidence=max(existing.confidence if existing else 0.0, 0.97),
        confidence_reason="Explicit single-slide constraint in user prompt.",
    )
    return DeckSpec(
        presentation_type=deck_spec.presentation_type,
        objective=deck_spec.objective,
        audience=deck_spec.audience,
        narrative=f"Single-slide response: {display_role}.",
        estimated_slide_count=1,
        slides=[slide],
    )


def _single_slide_prompt_constraints(user_prompt: str) -> str:
    """Preserve explicit count/content constraints when forcing one slide."""
    text = " ".join(str(user_prompt or "").lower().split())
    constraints: list[str] = []
    if any(term in text for term in ("six-step", "6-step", "six step", "6 step")):
        constraints.append("Use exactly six process steps.")
    elif any(term in text for term in ("five-step", "5-step", "five step", "5 step")):
        constraints.append("Use exactly five process steps.")
    if "activities" in text:
        constraints.append("Include activities.")
    if "pain point" in text or "pain points" in text:
        constraints.append("Include pain points.")
    if "business impact" in text:
        constraints.append("Include overall business impact.")
    if "dark" in text:
        constraints.append("Use a dark section divider.")
    return " ".join(constraints)


def _topic_matches_role(topic: str, slide_role: str) -> bool:
    """True if the enumerated topic maps to the same canonical role as the slide."""
    topic_canonical = _canonical_role_for_text(topic)
    role_canonical = _canonical_role_for_text(slide_role)
    return topic_canonical is not None and topic_canonical == role_canonical


def _fuzzy_role_for_topic(topic: str) -> str:
    """Return the canonical role name for an enumerated topic, or the topic
    itself Title-Cased when no canonical mapping applies."""
    for role_key, keywords in _ROLE_KEYWORD_BUCKETS.items():
        if any(k in topic.lower() for k in keywords):
            return _ROLE_DISPLAY_NAMES.get(role_key, role_key.title())
    return _titlecase_topic(topic)


# Canonical human-readable role names. Defaults to ``.title()``; provide
# entries where the default produces ugly casing (e.g. "Ai" / "Kpis").
_ROLE_DISPLAY_NAMES = {
    "executive summary": "Executive Summary",
    "section divider": "Section Divider",
    "current state vs future state": "Current State vs Future State",
    "current state": "Current Procurement Process",
    "future state": "Future-State Operating Model",
    "investment case": "Investment Case",
    "value realization roadmap": "Value Realization Roadmap",
    "business benefits": "Business Benefits",
    "ai use cases": "AI Use Cases",
    "implementation roadmap": "Implementation Roadmap",
    "transformation timeline": "Transformation Timeline",
    "risk register": "Risk Register",
    "implementation risks": "Implementation Risks",
    "kpi scorecard table": "KPI Scorecard Table",
    "kpis for success": "KPIs for Success",
    "next steps": "Next Steps",
    "opportunities": "Opportunities",
    "maturity assessment": "Maturity Assessment",
}

# Sensible visualization_type hints for appended enumerated slides. The Deck
# Executor later calls visual_planner.plan_visual_pattern() with the role, so
# this value is a planning hint rather than the final pattern decision.
_ROLE_VISUALIZATION_HINT = {
    "executive summary": "Executive Summary",
    "section divider": "Section Divider",
    "current state vs future state": "Current State vs Future State Comparison",
    "current state": "Process Flow",
    "future state": "Operating Model",
    "investment case": "Investment Case",
    "value realization roadmap": "Value Realization Roadmap",
    "business benefits": "Benefits Stack",
    "ai use cases": "Use Case Portfolio",
    "implementation roadmap": "Roadmap",
    "transformation timeline": "Timeline",
    "risk register": "Risk Register",
    "implementation risks": "Risk Matrix",
    "kpi scorecard table": "KPI Scorecard Table",
    "kpis for success": "KPI Dashboard",
    "next steps": "Board Decisions",
    "opportunities": "Creative Listing",
    "maturity assessment": "Maturity Matrix",
}


# Acronyms that should stay upper-case in title-cased topics.
_ACRONYMS = {"ai", "kpi", "kpis", "roi", "it", "hr", "hr's", "tom", "erp"}


def _titlecase_topic(topic: str) -> str:
    """Title-case a raw topic, preserving known acronyms as upper-case."""
    out: list[str] = []
    for word in topic.split():
        lower = word.lower()
        if lower in _ACRONYMS:
            out.append(lower.upper().replace("KPIS", "KPIs"))
        else:
            out.append(word[:1].upper() + word[1:].lower() if word else word)
    return " ".join(out)


def _reconcile_enumerated_slides(user_prompt: str, deck_spec: DeckSpec) -> DeckSpec:
    """
    Ensure every explicitly enumerated slide topic in the user's prompt appears
    as its own slide.

    1. Appends any missing enumerated topics.
    2. Re-sorts the resulting deck to the user's enumerated order.
    3. Keeps distinct extra slides and places them next to their nearest
       enumerated neighbor.

    This is the deterministic safety net behind the LLM-side rule 7. It runs
    on both the LLM-emitted plan and the taxonomy fallback so planner failures
    cannot silently drop user-requested slides.
    """
    topics = _extract_enumerated_topics(user_prompt)
    if not topics:
        return deck_spec

    slides = list(deck_spec.slides)
    # Drop duplicate canonical roles (e.g. LLM emits both "Executive Summary" and
    # "Transformation Overview"). Keep the first occurrence.
    seen_canonical: set[str] = set()
    deduped: list[SlidePlan] = []
    for slide in slides:
        canonical = _canonical_role_for_text(slide.slide_role)
        if canonical and canonical in seen_canonical:
            logger.info("planner.reconcile.dedup: skipping duplicate role %r", slide.slide_role)
            continue
        if canonical:
            seen_canonical.add(canonical)
        deduped.append(slide)
    slides = deduped

    existing_roles = [s.slide_role for s in slides]
    missing_topics: list[str] = []
    for topic in topics:
        if not any(_topic_matches_role(topic, role) for role in existing_roles):
            missing_topics.append(topic)

    if missing_topics:
        if len(slides) + len(missing_topics) > _MAX_DECK_SLIDES:
            logger.warning(
                "planner.reconcile: capping appended slides — would exceed %d",
                _MAX_DECK_SLIDES,
            )
            keep = _MAX_DECK_SLIDES - len(slides)
            missing_topics = missing_topics[:keep]

        next_number = (slides[-1].slide_number + 1) if slides else 1
        previous_roles = existing_roles[:]
        for topic in missing_topics:
            role = _fuzzy_role_for_topic(topic)
            canonical = _canonical_role_for_text(role)
            # If the fuzzy role already exists, use the raw topic text so we keep both.
            if role in previous_roles:
                role = topic.title()
            viz = _ROLE_VISUALIZATION_HINT.get(canonical, "Executive Summary")
            slides.append(
                SlidePlan(
                    slide_number=next_number,
                    slide_role=role,
                    purpose=_purpose_for_canonical_role(role, canonical),
                    required_inputs=[],
                    dependencies=list(previous_roles),
                    visualization_type=viz,
                )
            )
            previous_roles.append(role)
            next_number += 1

    slides = _normalize_roles_to_specific_enumerated_topics(slides, topics)

    # Re-sort slides to the user's enumerated order. Distinct extras are placed
    # immediately after their nearest enumerated neighbor.
    slides = _sort_slides_to_enumerated_order(slides, topics)
    slides = _move_decision_slides_to_close(user_prompt, slides)
    slides = _renumber_slides(slides)

    logger.info(
        "planner.reconcile: %d enumerated topics, %d slides after ordering",
        len(topics),
        len(slides),
    )
    return DeckSpec(
        presentation_type=deck_spec.presentation_type,
        objective=deck_spec.objective,
        audience=deck_spec.audience,
        narrative=deck_spec.narrative,
        estimated_slide_count=len(slides),
        slides=slides,
    )


def _renumber_slides(slides: list[SlidePlan]) -> list[SlidePlan]:
    """Return slides with contiguous 1-indexed slide numbers after reconciliation."""
    return [
        SlidePlan(
            slide_number=index,
            slide_role=slide.slide_role,
            purpose=slide.purpose,
            required_inputs=slide.required_inputs,
            dependencies=slide.dependencies,
            visualization_type=slide.visualization_type,
            confidence=slide.confidence,
            confidence_reason=slide.confidence_reason,
        )
        for index, slide in enumerate(slides, start=1)
    ]


def _apply_story_template(user_prompt: str, deck_spec: DeckSpec) -> DeckSpec:
    """Adapt the plan through a reusable story template for its presentation type."""
    topics = _extract_enumerated_topics(user_prompt)
    if topics:
        return deck_spec

    template = find_story_template(deck_spec.presentation_type)
    if template is None:
        return deck_spec
    existing_by_canonical: dict[str, SlidePlan] = {}
    extras: list[SlidePlan] = []
    for slide in deck_spec.slides:
        canonical = _canonical_role_for_text(slide.slide_role)
        if canonical and canonical not in existing_by_canonical:
            existing_by_canonical[canonical] = slide
        elif canonical is None:
            extras.append(slide)

    slides: list[SlidePlan] = []
    previous_roles: list[str] = []
    for template_role in template.roles:
        existing = existing_by_canonical.get(template_role.canonical_role)
        slide = _slide_from_template_role(
            template_role,
            existing,
            len(slides) + 1,
            previous_roles,
            confidence=0.82 if existing else 0.72,
        )
        slides.append(slide)
        previous_roles.append(slide.slide_role)

    for extra in extras:
        slides.append(
            SlidePlan(
                slide_number=len(slides) + 1,
                slide_role=extra.slide_role,
                purpose=extra.purpose,
                required_inputs=extra.required_inputs,
                dependencies=list(previous_roles),
                visualization_type=extra.visualization_type,
                confidence=0.45,
                confidence_reason="Extra role not present in the selected story template.",
            )
        )
        previous_roles.append(extra.slide_role)

    return DeckSpec(
        presentation_type=deck_spec.presentation_type,
        objective=deck_spec.objective,
        audience=deck_spec.audience,
        narrative=_merge_narrative(deck_spec.narrative, template.narrative),
        estimated_slide_count=len(slides),
        slides=slides,
    )


def _slide_from_template_role(
    template_role: StoryTemplateRole,
    existing: SlidePlan | None,
    slide_number: int,
    previous_roles: list[str],
    *,
    confidence: float,
) -> SlidePlan:
    if existing is None:
        return SlidePlan(
            slide_number=slide_number,
            slide_role=template_role.display_role,
            purpose=template_role.purpose,
            required_inputs=[],
            dependencies=list(previous_roles),
            visualization_type=template_role.visualization_type,
            confidence=confidence,
            confidence_reason="Required by the selected story template.",
        )
    return SlidePlan(
        slide_number=slide_number,
        slide_role=existing.slide_role or template_role.display_role,
        purpose=existing.purpose or template_role.purpose,
        required_inputs=existing.required_inputs,
        dependencies=list(previous_roles),
        visualization_type=existing.visualization_type or template_role.visualization_type,
        confidence=confidence,
        confidence_reason="Matched the selected story template and planner output.",
    )


def _merge_narrative(existing: str, template_narrative: str) -> str:
    existing_clean = " ".join(str(existing or "").split())
    template_clean = " ".join(str(template_narrative or "").split())
    if not existing_clean:
        return template_clean
    if template_clean in existing_clean:
        return existing_clean
    return f"{existing_clean} | Template: {template_clean}"


def _score_planner_confidence(user_prompt: str, deck_spec: DeckSpec) -> DeckSpec:
    topics = _extract_enumerated_topics(user_prompt)
    topic_canonicals = {_canonical_role_for_text(topic) for topic in topics}
    template = get_story_template(deck_spec.presentation_type)
    template_canonicals = {role.canonical_role for role in template.roles}
    slides: list[SlidePlan] = []
    for slide in deck_spec.slides:
        canonical = _canonical_role_for_text(slide.slide_role)
        confidence = slide.confidence
        reason = slide.confidence_reason
        if canonical and canonical in topic_canonicals:
            confidence = max(confidence, 0.94)
            reason = "Explicitly requested by the user prompt."
        elif canonical and canonical in template_canonicals:
            confidence = max(confidence, 0.82)
            reason = "Required by the selected story template."
        elif canonical is None:
            confidence = min(confidence, 0.45)
            reason = "Role is outside known story-template roles."
        slides.append(
            SlidePlan(
                slide_number=slide.slide_number,
                slide_role=slide.slide_role,
                purpose=slide.purpose,
                required_inputs=slide.required_inputs,
                dependencies=slide.dependencies,
                visualization_type=slide.visualization_type,
                confidence=round(confidence, 2),
                confidence_reason=reason,
            )
        )
    return DeckSpec(
        presentation_type=deck_spec.presentation_type,
        objective=deck_spec.objective,
        audience=deck_spec.audience,
        narrative=deck_spec.narrative,
        estimated_slide_count=len(slides),
        slides=slides,
    )


def _normalize_roles_to_specific_enumerated_topics(
    slides: list[SlidePlan], topics: list[str]
) -> list[SlidePlan]:
    """Upgrade generic LLM roles when the user's enumerated topic is specific.

    Example: an LLM role of "Roadmap" satisfies "implementation roadmap", but
    the role should become "Implementation Roadmap" so downstream visual and
    asset selection receive the stronger consulting intent. Generic user
    topics such as "current state" are left alone to preserve taxonomy roles.
    """
    specific_by_canonical: dict[str, str] = {}
    for topic in topics:
        canonical = _canonical_role_for_text(topic)
        specific = _specific_role_for_topic(topic)
        if canonical and specific:
            specific_by_canonical[canonical] = specific

    normalized: list[SlidePlan] = []
    for slide in slides:
        canonical = _canonical_role_for_text(slide.slide_role)
        desired = specific_by_canonical.get(canonical or "")
        if desired and slide.slide_role != desired:
            normalized.append(
                SlidePlan(
                    slide_number=slide.slide_number,
                    slide_role=desired,
                    purpose=_purpose_for_canonical_role(desired, canonical),
                    required_inputs=slide.required_inputs,
                    dependencies=slide.dependencies,
                    visualization_type=_ROLE_VISUALIZATION_HINT.get(
                        canonical, slide.visualization_type
                    ),
                    confidence=slide.confidence,
                    confidence_reason=slide.confidence_reason,
                )
            )
        else:
            normalized.append(slide)
    return normalized


def _specific_role_for_topic(topic: str) -> str | None:
    """Return an upgraded display role only for specific enumerated topics."""
    lowered = topic.lower().strip()
    generic_topics = {
        "executive summary",
        "summary",
        "current state",
        "future state",
        "benefits",
        "business benefits",
        "use cases",
        "roadmap",
        "timeline",
        "risks",
        "kpis",
        "metrics",
        "next steps",
    }
    if lowered in generic_topics:
        return None
    canonical = _canonical_role_for_text(topic)
    if canonical:
        return _ROLE_DISPLAY_NAMES.get(canonical, canonical.title())
    return None


def _purpose_for_canonical_role(role: str, canonical: str | None) -> str:
    """Return a specific, selection-friendly purpose for canonical slide roles."""
    if canonical == "executive summary":
        return "Summarize the board-level recommendation, value at stake, and decisions required."
    if canonical == "section divider":
        return "Introduce the requested section using a section divider slide."
    if canonical == "current state":
        return "Map the current procurement process and identify the operating friction that AI must address."
    if canonical == "future state":
        return "Describe the future-state procurement operating model, including capabilities, governance, and AI enablement."
    if canonical == "investment case":
        return "Summarize required investment, value created, payback, and the board approval case."
    if canonical == "business benefits":
        return "Quantify and structure the business benefits expected from the transformation."
    if canonical == "ai use cases":
        return "Prioritize AI procurement use cases by value, feasibility, and operating impact."
    if canonical == "implementation roadmap":
        return "Sequence the implementation phases, milestones, and dependencies."
    if canonical == "transformation timeline":
        return "Show the transformation timeline and major milestones."
    if canonical == "risk register":
        return "List seven implementation risks with likelihood, impact, mitigation, owner, status, and summary counts."
    if canonical == "implementation risks":
        return "Assess implementation risks, likely impact, and mitigations."
    if canonical == "kpi scorecard table":
        return "Define priority KPIs with baseline, target, owner, reporting cadence, and management summary."
    if canonical == "kpis for success":
        return "Define the KPIs and targets used to measure success."
    if canonical == "next steps":
        return "Clarify immediate next steps and board decisions required."
    return f"Communicate the {role.lower()} message requested by the user."


def _sort_slides_to_enumerated_order(
    slides: list[SlidePlan], topics: list[str]
) -> list[SlidePlan]:
    """
    Return slides ordered by the user's enumerated topic list.

    Slides that match an enumerated topic go at that topic's index. Distinct
    extra slides are placed after the enumerated topic whose canonical role is
    closest to the extra slide's role; extras with no match are appended at the
    end while preserving their original relative order.
    """
    topic_canonicals = [_canonical_role_for_text(t) for t in topics]

    def sort_key(item: tuple[int, SlidePlan]) -> tuple[float, int]:
        original_index, slide = item
        canonical = _canonical_role_for_text(slide.slide_role)
        if canonical in topic_canonicals:
            pos = topic_canonicals.index(canonical)
        else:
            nearest = _nearest_enumerated_index(canonical, topic_canonicals)
            pos = nearest + 0.5
        return (pos, original_index)

    indexed = list(enumerate(slides))
    indexed.sort(key=sort_key)
    return [slide for _, slide in indexed]


def _move_decision_slides_to_close(user_prompt: str, slides: list[SlidePlan]) -> list[SlidePlan]:
    """Keep board decisions/actions at the close unless explicitly requested first."""
    if _is_decision_first_prompt(user_prompt):
        return slides
    decision_slides = [
        slide for slide in slides
        if _canonical_role_for_text(slide.slide_role) == "next steps"
        or "decision" in (slide.visualization_type or "").lower()
        or "action" in (slide.slide_role or "").lower()
    ]
    if not decision_slides:
        return slides
    others = [slide for slide in slides if slide not in decision_slides]
    if not others:
        return slides
    return others + decision_slides


def _is_decision_first_prompt(user_prompt: str) -> bool:
    text = " ".join(str(user_prompt or "").lower().split())
    decision_first_signals = (
        "decision-first",
        "decision first",
        "start with board decisions",
        "lead with board decisions",
        "open with board decisions",
        "begin with board decisions",
        "board memo",
        "decision memo",
        "approval memo",
    )
    return any(signal in text for signal in decision_first_signals)


def _nearest_enumerated_index(
    slide_canonical: str | None, topic_canonicals: list[str]
) -> int:
    """Find the index of the enumerated topic closest to an extra slide."""
    if slide_canonical is None or not topic_canonicals:
        return len(topic_canonicals)
    if slide_canonical in topic_canonicals:
        return topic_canonicals.index(slide_canonical)
    # Prefer a topic in the same broad bucket (same first word of canonical key).
    slide_prefix = slide_canonical.split()[0] if slide_canonical else ""
    for idx, tc in enumerate(topic_canonicals):
        if tc and tc.split()[0] == slide_prefix:
            return idx
    return len(topic_canonicals)


def _get_taxonomy_entry(
    taxonomy: dict[str, Any], classification: PresentationClassification
) -> dict[str, Any]:
    """Return the taxonomy entry for the classified presentation type."""
    types = taxonomy.get("presentation_types", {})
    entry = types.get(classification.presentation_type)
    if not isinstance(entry, dict):
        logger.warning(
            "unknown presentation type %r; falling back to Transformation Proposal",
            classification.presentation_type,
        )
        entry = types.get("Transformation Proposal", {})
    return entry if isinstance(entry, dict) else {}


def _call_presentation_planner_llm(
    user_prompt: str,
    intent: IntentResult,
    classification: PresentationClassification,
    taxonomy_entry: dict[str, Any],
) -> dict[str, Any]:
    from backend.llm import router

    scaffold = _build_taxonomy_scaffold(taxonomy_entry)
    user_input = {
        "user_prompt": user_prompt,
        "intent": intent.model_dump(mode="json"),
        "classification": classification.model_dump(mode="json"),
        "taxonomy_scaffold": scaffold,
    }

    prompt = build_prompt(
        "presentation_planner",
        user_input=json.dumps(user_input, ensure_ascii=True),
        additional_context="Input:",
    )
    return router.generate_json("presentation_planner", prompt, temperature=0.2)


def _build_taxonomy_scaffold(taxonomy_entry: dict[str, Any]) -> dict[str, Any]:
    """Extract the parts of the taxonomy that guide the planner LLM."""
    return {
        "description": taxonomy_entry.get("description", ""),
        "objective": taxonomy_entry.get("objective", ""),
        "expected_audience": taxonomy_entry.get("expected_audience", ""),
        "consulting_narrative": taxonomy_entry.get("consulting_narrative", ""),
        "default_slide_sequence": taxonomy_entry.get("default_slide_sequence", []),
        "visualization_preferences": taxonomy_entry.get("visualization_preferences", {}),
        "optional_slides": taxonomy_entry.get("optional_slides", []),
    }


def _to_deck_spec(payload: dict[str, Any]) -> DeckSpec:
    """Convert the parsed LLM JSON payload into a validated DeckSpec."""
    slides_data = payload.get("slides", [])
    if not isinstance(slides_data, list):
        slides_data = []

    slides: list[SlidePlan] = []
    seen_canonical_roles: set[str] = set()
    for index, item in enumerate(slides_data, start=1):
        if not isinstance(item, dict):
            continue
        slide_number = int(item.get("slide_number", index))
        role = _clean_text(item.get("slide_role")) or f"Slide {slide_number}"
        canonical = _canonical_role_for_text(role)
        # Drop exact-duplicate canonical roles from the LLM plan (e.g. a second
        # "Transformation Overview" that maps to Executive Summary).
        if canonical and canonical in seen_canonical_roles:
            logger.info("planner.dedup: skipping duplicate canonical role %r", role)
            continue
        if canonical:
            seen_canonical_roles.add(canonical)
        slides.append(
            SlidePlan(
                slide_number=slide_number,
                slide_role=role,
                purpose=_clean_text(item.get("purpose")) or "Communicate the key message.",
                required_inputs=_clean_string_list(item.get("required_inputs", [])),
                dependencies=_clean_string_list(item.get("dependencies", [])),
                visualization_type=_clean_text(item.get("visualization_type")) or "Executive Summary",
            )
        )

    estimated = int(payload.get("estimated_slide_count", len(slides)))
    if estimated != len(slides):
        logger.warning(
            "presentation planner returned mismatched slide count: estimated=%d actual=%d",
            estimated,
            len(slides),
        )
        estimated = len(slides)

    return DeckSpec(
        presentation_type=_clean_text(payload.get("presentation_type")) or "Consulting Deck",
        objective=_clean_text(payload.get("objective")) or "Align stakeholders on the path forward.",
        audience=_clean_text(payload.get("audience")) or "Senior client leadership",
        narrative=_clean_text(payload.get("narrative")) or "Situation → Complication → Resolution",
        estimated_slide_count=max(estimated, 1),
        slides=slides,
    )


def _taxonomy_fallback_deck(
    user_prompt: str,
    intent: IntentResult,
    classification: PresentationClassification,
    taxonomy_entry: dict[str, Any],
) -> DeckSpec:
    """
    Deterministic fallback deck rooted in the taxonomy scaffold.

    Personalizes objective/audience with intent fields and follows the
    taxonomy's default slide sequence.
    """
    company = _intent_value_or_default(intent.company, "the organization")
    business_function = _intent_value_or_default(intent.business_function, "")

    base_objective = _clean_text(taxonomy_entry.get("objective")) or "Align stakeholders."
    base_audience = _clean_text(taxonomy_entry.get("expected_audience")) or "Senior client leadership"
    narrative = _clean_text(taxonomy_entry.get("consulting_narrative")) or "Situation → Complication → Resolution"

    objective = _personalize_text(base_objective, company, business_function)
    audience = _personalize_text(base_audience, company, business_function)

    sequence = taxonomy_entry.get("default_slide_sequence", [])
    if not isinstance(sequence, list) or not sequence:
        # Ultimate fallback if taxonomy entry is empty.
        return _minimal_fallback_deck(classification, company, business_function)

    visualization_preferences = taxonomy_entry.get("visualization_preferences", {}) or {}
    if not isinstance(visualization_preferences, dict):
        visualization_preferences = {}

    slides: list[SlidePlan] = []
    previous_roles: list[str] = []
    for index, item in enumerate(sequence, start=1):
        if not isinstance(item, dict):
            continue
        role = _clean_text(item.get("slide_role")) or f"Slide {index}"
        purpose_template = _clean_text(item.get("purpose")) or f"Communicate the {role} message."
        purpose = _personalize_text(purpose_template, company, business_function)
        visualization = _clean_text(item.get("visualization_type")) or visualization_preferences.get(
            role, "Executive Summary"
        )
        required_inputs = _clean_string_list(item.get("required_inputs", []))

        slides.append(
            SlidePlan(
                slide_number=index,
                slide_role=role,
                purpose=purpose,
                required_inputs=required_inputs,
                dependencies=list(previous_roles),
                visualization_type=visualization,
            )
        )
        previous_roles.append(role)

    return DeckSpec(
        presentation_type=classification.presentation_type,
        objective=objective,
        audience=audience,
        narrative=narrative,
        estimated_slide_count=len(slides),
        slides=slides,
    )


def _minimal_fallback_deck(
    classification: PresentationClassification, company: str, business_function: str
) -> DeckSpec:
    """Minimal ultimate fallback when taxonomy data is missing."""
    effective_company = company or "the organization"
    effective_function = business_function or "business"
    return DeckSpec(
        presentation_type=classification.presentation_type,
        objective=f"Align {effective_company} leadership on a prioritized {effective_function} initiative.",
        audience="Senior client leadership",
        narrative="Executive Summary → Current State → Future State → Roadmap → Next Steps",
        estimated_slide_count=1,
        slides=[
            SlidePlan(
                slide_number=1,
                slide_role="Executive Summary",
                purpose=f"Frame the recommendation for {effective_company}'s {effective_function} initiative.",
                required_inputs=[],
                dependencies=[],
                visualization_type="Executive Summary",
            )
        ],
    )


def _intent_value_or_default(value: str | None, default: str) -> str:
    """Return the intent value if it is meaningful, otherwise the default."""
    cleaned = _clean_text(value)
    if cleaned and cleaned.lower() not in ("unknown", "n/a", ""):
        return cleaned
    return default


def _personalize_text(text: str, company: str, business_function: str) -> str:
    """
    Inject company and business function placeholders into a template string.

    Empty or unknown values are replaced with sensible defaults and any double
    spaces introduced by empty substitutions are collapsed.
    """
    effective_company = company or "the organization"
    effective_function = business_function or ""
    personalized = text.replace("{company}", effective_company).replace(
        "{business_function}", effective_function
    )
    return " ".join(personalized.split())


def _clean_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split()).strip()
    return cleaned or None


def _clean_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]

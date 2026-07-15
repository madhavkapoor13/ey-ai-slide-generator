"""
backend/modules/deck_executor.py
================================
Sprint G.1 — Deck Executor.

Executes a DeckSpec by generating one slide at a time. Each SlidePlan is
handed to the Content Generator with full slide-awareness, the resulting
SlideSpec is validated, and the outcome is recorded. Execution continues if
an individual slide fails, producing a partial deck rather than aborting the
entire request.

The Deck Executor does NOT build enterprise context, perform process mapping,
or plan the deck. Those steps are completed before execution.

Sprint C — reversed per-slide ordering
---------------------------------------
For each slide, the order is now:

  1. Visual Planner     → VisualPatternSelection     (family signal)
  2. Asset Selector     → AssetSelection             (concrete asset, BEFORE content)
  3. Content Generator  → SlideSpec (carrying asset_id)
  4. Validator

Selecting the asset BEFORE content generation lets Sprint D build the LLM
prompt directly from the chosen asset's manifest (so a 3-phase roadmap
asset asks the LLM for exactly 3 phases — no generation-then-trim).
"""

from __future__ import annotations

import logging
import os

from backend.modules.content_generator import generate_slide_content
from backend.modules.consulting_language import validate_consulting_language
from backend.modules.validator import validate_content
from backend.modules.visual_planner import plan_visual_pattern
from schemas.context import EnterpriseContext
from schemas.deck_execution import DeckExecutionResult, SlideExecutionResult
from schemas.evaluation import DeckEvaluationReport, SlideEvaluationReport
from schemas.intent import IntentResult
from schemas.presentation import DeckSpec, SlidePlan
from schemas.process import ProcessResult
from schemas.slide_spec import SlideSpec
from schemas.visual import VisualBrief

logger = logging.getLogger(__name__)

# Slide roles that anchor on the mapped enterprise process. All other roles
# receive an empty ProcessResult so the LLM is not biased toward generic
# procurement stages.
_PROCESS_ROLES = {
    "Current State",
    "Current Procurement Process",
    "Process Flow",
    "Operating Model",
    "Future State",
    "Future-State Operating Model",
}

_ASSET_COMPATIBILITY_THRESHOLD = 0.35

_ROLE_FAMILY_COMPATIBILITY: dict[str, set[str]] = {
    "business_benefits": {"business_benefits", "list", "comparison", "strategy"},
    "ai_use_cases": {"strategy", "list", "comparison"},
    "implementation_risks": {"risk", "comparison", "list", "strategy"},
    "next_steps": {"next_steps", "roadmap", "list", "executive_summary"},
    "kpis_for_success": {"kpi"},
    "implementation_roadmap": {"roadmap", "timeline"},
    "current_state": {"process"},
    "future_state": {"capability_map", "comparison"},
    "executive_summary": {"executive_summary"},
    "opportunities": {"opportunity_matrix", "comparison", "strategy"},
}


def _process_for_slide(
    slide_plan: SlidePlan, process_result: ProcessResult
) -> ProcessResult:
    """Return the real process_result for process roles, else an empty one."""
    if slide_plan.slide_role in _PROCESS_ROLES:
        return process_result
    return ProcessResult(
        process_name="",
        process_family="",
        confidence=0.0,
        reasoning="not applicable for this slide role",
        stages=[],
    )


def execute_deck(
    deck_spec: DeckSpec,
    intent: IntentResult,
    enterprise_context: EnterpriseContext,
    process_result: ProcessResult,
    *,
    user_preferences=None,
) -> DeckExecutionResult:
    """
    Execute a DeckSpec slide by slide.

    Parameters
    ----------
    deck_spec:
        The planned deck containing SlidePlans.
    intent:
        Structured intent from the user request.
    enterprise_context:
        Grounded enterprise context.
    process_result:
        Mapped enterprise process.
    user_preferences:
        Optional explicit :class:`UserPreferences` (Sprint C). Used by the
        sibling Asset Selector for audience/style filters; when None, the
        Selector derives a conservative default from IntentResult.audience
        and the slide plan. Defaults to None to keep existing callers and
        tests unaffected.

    Returns
    -------
    DeckExecutionResult
        Aggregate outcome, including successful slides, failed slides, and
        per-slide execution details.
    """
    deck_spec = _gate_deck_plan(deck_spec)

    logger.info(
        "executing deck: presentation_type=%s slides=%d",
        deck_spec.presentation_type,
        len(deck_spec.slides),
    )

    slides: list[SlideExecutionResult] = []
    successful_slides: list[SlideSpec] = []
    failed_slides: list[SlideExecutionResult] = []
    previous_family: str | None = None

    for slide_plan in deck_spec.slides:
        try:
            visual_selection = _plan_visual_for_slide(slide_plan, previous_family)
            if visual_selection is not None:
                previous_family = visual_selection.category or None
            slide_process = _process_for_slide(slide_plan, process_result)
            # Sprint C — reversed order: select the Presentation Asset BEFORE
            # content generation so the chosen manifest can shape the LLM prompt.
            # Skip the selector entirely when there is no visual family choice.
            asset_selection = (
                _select_asset_for_slide(slide_plan, visual_selection, intent, user_preferences)
                if visual_selection is not None
                else None
            )
            # A synthetic fallback asset means no real template is available;
            # route the slide through the legacy content path instead of forcing
            # a placeholder-keyed manifest that the legacy validator will reject.
            from backend.presentation_assets.asset_selector import _FALLBACK_ASSET_ID

            if asset_selection is not None and asset_selection.asset_id == _FALLBACK_ASSET_ID:
                asset_selection = None
            slide_spec = generate_slide_content(
                intent,
                enterprise_context,
                slide_process,
                slide_plan,
                visual_pattern_selection=visual_selection,
                asset_id=asset_selection.asset_id if asset_selection else None,
                asset_manifest=asset_selection.manifest if asset_selection else None,
            )
            validation_result = validate_content(slide_spec)
            validation_result = _apply_post_generation_quality_gate(
                slide_plan,
                slide_spec,
                validation_result,
            )
            evaluation_report = _slide_evaluation_report(
                slide_plan,
                slide_spec,
                validation_result,
                visual_selection,
                asset_selection,
            )

            if validation_result.is_valid and validation_result.validated_spec is not None:
                execution_result = SlideExecutionResult(
                    slide_plan=slide_plan,
                    slide_spec=validation_result.validated_spec,
                    validation_result=validation_result,
                    success=True,
                    evaluation_report=evaluation_report,
                )
                successful_slides.append(validation_result.validated_spec)
            else:
                issues = validation_result.issues
                error_message = "; ".join(issues) if issues else "Validation failed."
                execution_result = SlideExecutionResult(
                    slide_plan=slide_plan,
                    slide_spec=slide_spec,
                    validation_result=validation_result,
                    success=False,
                    error=error_message,
                    evaluation_report=evaluation_report,
                )
                failed_slides.append(execution_result)

        except Exception as exc:  # noqa: BLE001 - per-slide failure must not abort the deck.
            logger.exception(
                "slide generation failed: slide_number=%d slide_role=%s",
                slide_plan.slide_number,
                slide_plan.slide_role,
            )
            execution_result = SlideExecutionResult(
                slide_plan=slide_plan,
                slide_spec=None,
                validation_result=None,
                success=False,
                error=str(exc),
                evaluation_report=SlideEvaluationReport(
                    slide_number=slide_plan.slide_number,
                    role=slide_plan.slide_role,
                    population="generation_failed",
                    warnings=[str(exc)],
                ),
            )
            failed_slides.append(execution_result)

        slides.append(execution_result)

    total_slides = len(deck_spec.slides)
    all_succeeded = total_slides > 0 and len(failed_slides) == 0 and len(successful_slides) == total_slides
    partial_success = len(successful_slides) > 0 and len(failed_slides) > 0

    logger.info(
        "deck execution complete: total=%d successful=%d failed=%d",
        total_slides,
        len(successful_slides),
        len(failed_slides),
    )

    return DeckExecutionResult(
        deck_spec=deck_spec,
        slides=slides,
        successful_slides=successful_slides,
        failed_slides=failed_slides,
        all_succeeded=all_succeeded,
        partial_success=partial_success,
        evaluation_report=_deck_evaluation_report(slides),
    )


def _plan_visual_for_slide(
    slide_plan: SlidePlan,
    previous_family: str | None = None,
):
    """
    Decide this slide's visual pattern exactly once before content generation.

    The selection is computed deterministically against the slide plan's
    role/purpose/visualization_type (no content exists yet). It is passed into
    `generate_slide_content` so the LLM is shaped to the same pattern the
    renderer will later use, and stamped onto the returned SlideSpec. This makes
    the visual planner the single source of truth for the slide's visual —
    `slide_service` reads the carried `visual_pattern_id` instead of re-scoring.

    ``previous_family`` is the category of the previous slide's visual pattern.
    When set, the planner avoids selecting another pattern from the same family
    to prevent visual fatigue.

    Returns None if planning fails so that content generation still proceeds
    (without a visual selection) rather than aborting the slide.
    """
    from schemas.visual import VisualPatternSelection  # local import; rarely None path

    if slide_plan.slide_role == "Section Divider":
        return VisualPatternSelection(
            pattern_id="SECTION-DIVIDER",
            category="creative_listing",
            confidence=1.0,
            reasoning="Section divider layout.",
            recommended_variant=None,
        )

    minimal_spec = SlideSpec(
        slide_type="operating_model",
        raw_spec={"title": slide_plan.slide_role, "subtitle": slide_plan.purpose},
    )
    try:
        selection = plan_visual_pattern(
            slide_plan, minimal_spec, exclude_category=previous_family
        )
        if not isinstance(selection, VisualPatternSelection):
            return None
        logger.info(
            "deck_executor: visual planned — slide=%d pattern=%s family=%s confidence=%s",
            slide_plan.slide_number,
            selection.pattern_id,
            selection.category,
            selection.confidence,
        )
        return selection
    except Exception as exc:  # noqa: BLE001 - planning must not abort a slide.
        logger.warning(
            "deck_executor: visual planning failed for slide %d (%s): %s",
            slide_plan.slide_number,
            slide_plan.slide_role,
            exc,
        )
        return None


def _gate_deck_plan(deck_spec: DeckSpec) -> DeckSpec:
    """Remove duplicate canonical slide roles before expensive generation.

    This is intentionally conservative: keep the first instance of a role and
    preserve genuinely distinct slides. It prevents the failure seen in the
    Microsoft golden prompt where a second executive summary/KPI slide made it
    to rendering even though the user asked for each section once.
    """
    seen: set[str] = set()
    gated: list[SlidePlan] = []
    for slide in deck_spec.slides:
        canonical = _canonical_slide_role(slide.slide_role)
        if canonical and canonical in seen:
            logger.warning(
                "deck_executor: dropping duplicate canonical role slide=%d role=%s canonical=%s",
                slide.slide_number,
                slide.slide_role,
                canonical,
            )
            continue
        if canonical:
            seen.add(canonical)
        gated.append(slide)

    if len(gated) == len(deck_spec.slides):
        return deck_spec

    renumbered = [
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
        for index, slide in enumerate(gated, start=1)
    ]
    return DeckSpec(
        presentation_type=deck_spec.presentation_type,
        objective=deck_spec.objective,
        audience=deck_spec.audience,
        narrative=deck_spec.narrative,
        estimated_slide_count=len(renumbered),
        slides=renumbered,
    )


def _canonical_slide_role(role: str) -> str | None:
    text = (role or "").lower()
    if "executive summary" in text or "transformation overview" in text:
        return "executive_summary"
    if "current" in text and ("process" in text or "state" in text):
        return "current_state"
    if "future" in text or "operating model" in text:
        return "future_state"
    if "benefit" in text or "value case" in text:
        return "business_benefits"
    if "use case" in text:
        return "ai_use_cases"
    if "roadmap" in text:
        return "implementation_roadmap"
    if "timeline" in text or "milestone" in text:
        return "transformation_timeline"
    if "kpi" in text or "metric" in text:
        return "kpis_for_success"
    if "risk" in text or "mitigation" in text:
        return "implementation_risks"
    if "next step" in text or "decision" in text or "action" in text:
        return "next_steps"
    return None


def _canonical_generated_role(raw: dict) -> str | None:
    """Infer canonical role from generated visible text."""
    if not isinstance(raw, dict):
        return None
    fields: list[str] = []
    for key in ("title", "subtitle", "description", "executive_summary"):
        value = raw.get(key)
        if isinstance(value, str):
            fields.append(value)
    summary = raw.get("summary")
    if isinstance(summary, dict):
        for key in ("headline", "description"):
            value = summary.get(key)
            if isinstance(value, str):
                fields.append(value)
    return _canonical_slide_role(" ".join(fields))


def _apply_post_generation_quality_gate(slide_plan: SlidePlan, slide_spec: SlideSpec, validation_result):
    """Reject semantic drift that structural validation alone cannot see."""
    if validation_result is None:
        return validation_result
    raw = slide_spec.raw_spec if isinstance(slide_spec.raw_spec, dict) else {}
    issues = list(validation_result.issues or [])

    planned = _canonical_slide_role(slide_plan.slide_role)
    generated = _canonical_generated_role(raw)
    if planned and generated and planned != generated:
        issues.append(
            f"role-title mismatch: planned {planned!r} but generated content reads as {generated!r}."
        )

    language = validate_consulting_language(raw, slide_plan.slide_role)
    issues.extend(f"consulting-language warning: {issue}" for issue in language.issues)
    issues.extend(f"consulting-language warning: {warning}" for warning in language.warnings)

    fatal = [issue for issue in issues if not issue.startswith("consulting-language warning:")]
    if fatal:
        return validation_result.model_copy(
            update={"is_valid": False, "issues": issues, "validated_spec": None}
        )
    return validation_result.model_copy(update={"issues": issues})


def _select_asset_for_slide(
    slide_plan: SlidePlan,
    visual_selection,
    intent: IntentResult,
    user_preferences=None,
):
    """
    Decide this slide's Presentation Asset exactly once, AFTER visual
    family planning and BEFORE content generation (Sprint C — reversed order).

    The asset is selected so the Content Generator (Sprint D) can build its
    LLM prompt from the chosen asset's manifest. The asset_id is threaded
    into ``generate_slide_content`` and stamped onto the returned SlideSpec,
    where the Populator (Sprint E) reads it to open the right .pptx.

    Returns None when selection fails so content generation still proceeds
    without a chosen asset (the legacy renderer path is unaffected; the
    Populator falls back to the fallback-asset slide).

    Uses lazy imports of the presentation_assets package so the Deck Executor
    stays importable even if the asset library is empty during early testing.
    """
    from backend.presentation_assets import asset_selector
    from schemas.presentation_asset import AssetSelectionQuery

    if visual_selection is None:
        logger.info(
            "deck_executor: asset selection skipped — no visual selection for slide %d",
            slide_plan.slide_number,
        )
        return None

    try:
        family = asset_selector.family_for_pattern(visual_selection.pattern_id)
        visual_brief = _visual_brief_for_slide(slide_plan, visual_selection, intent)
        audience: list[str] = []
        style: list[str] = []
        keywords: list[str] = []
        if user_preferences is not None:
            audience = list(user_preferences.audience)
            style = list(user_preferences.style)
        # Inferred default: audience from IntentResult.audience when not explicit.
        if not audience and getattr(intent, "audience", None):
            audience = [str(intent.audience).lower()]
        if not audience and visual_brief.audience:
            audience = [visual_brief.audience]
        # Keywords for scoring and recommended_for/avoid_for overlap.
        if slide_plan.purpose:
            keywords.append(slide_plan.purpose)
        if slide_plan.visualization_type:
            keywords.append(slide_plan.visualization_type)

        query = AssetSelectionQuery(
            family=family,
            audience=audience,
            style=style,
            keywords=keywords,
            content_count=visual_brief.content_units,
            content_kind_hints=[slide_plan.visualization_type] if slide_plan.visualization_type else [],
            message_type=visual_brief.message_type,
            information_shape=visual_brief.information_shape,
            require_certified=_requires_certified_assets(),
        )
        selection = asset_selector.select(query)
        compatibility_score, compatibility_reasons = _asset_compatibility_score(
            slide_plan,
            visual_brief,
            selection,
        )
        selection.score_breakdown["compatibility"] = round(compatibility_score, 4)
        if compatibility_score < _ASSET_COMPATIBILITY_THRESHOLD:
            logger.warning(
                "deck_executor: asset rejected for low metadata compatibility — slide=%d role=%s requested_family=%s asset=%s score=%.2f reasons=%s",
                slide_plan.slide_number,
                slide_plan.slide_role,
                family,
                selection.asset_id,
                compatibility_score,
                compatibility_reasons,
            )
            return None
        logger.info(
            "deck_executor: asset selected — slide=%d family=%s asset=%s confidence=%s brief=%s/%s",
            slide_plan.slide_number,
            family,
            selection.asset_id,
            selection.confidence,
            visual_brief.message_type,
            visual_brief.information_shape,
        )
        return selection
    except Exception as exc:  # noqa: BLE001 - selection must not abort a slide.
        logger.warning(
            "deck_executor: asset selection failed for slide %d (%s): %s",
            slide_plan.slide_number,
            slide_plan.slide_role,
            exc,
        )
        return None


def _asset_compatibility_score(
    slide_plan: SlidePlan,
    visual_brief: VisualBrief,
    asset_selection,
) -> tuple[float, list[str]]:
    """Score role/brief/manifest compatibility using asset metadata."""
    manifest = getattr(asset_selection, "manifest", None)
    if manifest is None:
        return 0.0, ["missing_manifest"]

    reasons: list[str] = []
    score = 0.0
    message_type = _normalize_family_value(visual_brief.message_type)
    information_shape = _normalize_family_value(visual_brief.information_shape)
    slide_terms = _token_set(
        [
            slide_plan.slide_role,
            slide_plan.purpose,
            slide_plan.visualization_type,
            visual_brief.message_type,
            visual_brief.information_shape,
        ]
    )

    manifest_message = _normalize_family_value(getattr(manifest, "message_type", "") or "")
    if message_type and manifest_message and message_type == manifest_message:
        score += 0.30
        reasons.append("message_type")

    manifest_shape = _normalize_family_value(getattr(manifest, "information_shape", "") or "")
    if information_shape and manifest_shape and information_shape == manifest_shape:
        score += 0.25
        reasons.append("information_shape")

    content_kind_terms = _token_set(getattr(manifest, "fits_content_kinds", []) or [])
    if slide_terms & content_kind_terms:
        score += 0.20
        reasons.append("fits_content_kinds")

    recommended_terms = _token_set(getattr(manifest, "recommended_for", []) or [])
    if slide_terms & recommended_terms:
        score += 0.20
        reasons.append("recommended_for")

    family_terms = _token_set(
        [getattr(manifest, "family", ""), getattr(asset_selection, "family", "")]
        + list(getattr(manifest, "family_aliases", []) or [])
    )
    if slide_terms & family_terms:
        score += 0.10
        reasons.append("family_alias")

    canonical_role = _canonical_slide_role(slide_plan.slide_role)
    asset_family = _normalize_family_value(
        getattr(manifest, "family", "") or getattr(asset_selection, "family", "")
    )
    if canonical_role and asset_family in _ROLE_FAMILY_COMPATIBILITY.get(canonical_role, set()):
        score += 0.45
        reasons.append("role_family_compatibility")

    avoid_terms = _phrase_set(getattr(manifest, "avoid_for", []) or [])
    slide_phrases = _phrase_set(
        [
            slide_plan.slide_role,
            slide_plan.purpose,
            slide_plan.visualization_type,
            visual_brief.message_type,
            visual_brief.information_shape,
        ]
    )
    if slide_phrases & avoid_terms:
        score -= 0.35
        reasons.append("avoid_for")

    return max(0.0, min(score, 1.0)), reasons or ["no_metadata_overlap"]


def _requires_certified_assets() -> bool:
    """Demo and production generation must never select uncertified assets."""
    return os.getenv("EY_GENERATION_MODE", "development").strip().lower() in {
        "demo",
        "production",
    }


def _normalize_family_value(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _token_set(values) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        normalized = _normalize_family_value(str(value or ""))
        if not normalized:
            continue
        tokens.add(normalized)
        tokens.update(part for part in normalized.split("_") if part)
    return tokens


def _phrase_set(values) -> set[str]:
    return {
        _normalize_family_value(str(value or ""))
        for value in values
        if _normalize_family_value(str(value or ""))
    }


def _visual_brief_for_slide(
    slide_plan: SlidePlan,
    visual_selection,
    intent: IntentResult,
) -> VisualBrief:
    """Build the minimal V2 VisualBrief without changing the planner boundary."""
    text = " ".join(
        part
        for part in (
            slide_plan.slide_role,
            slide_plan.purpose,
            slide_plan.visualization_type,
            getattr(visual_selection, "pattern_id", ""),
        )
        if part
    ).lower()
    if "risk" in text or "mitigation" in text:
        message_type, information_shape = "risk_matrix", "matrix"
    elif "next step" in text or "decision" in text or "action" in text:
        message_type, information_shape = "board_decisions", "actions"
    elif "kpi" in text or "metric" in text:
        message_type, information_shape = "kpi_dashboard", "metrics"
    elif "current state" in text or "current process" in text or "as is" in text or "as-is" in text:
        message_type, information_shape = "process_flow", "sequence"
    elif "future state" in text or "target state" in text or "target operating model" in text:
        message_type, information_shape = "operating_model", "capability_map"
    elif "timeline" in text or "milestone" in text:
        message_type, information_shape = "timeline", "sequence"
    elif "roadmap" in text or "phase" in text or "implementation" in text:
        message_type, information_shape = "implementation_roadmap", "sequence"
    elif "use case" in text or "portfolio" in text:
        message_type, information_shape = "ai_use_case_portfolio", "portfolio"
    elif "strategy" in text or "pillar" in text or "priority" in text:
        message_type, information_shape = "strategy_pillars", "portfolio"
    elif "benefit" in text or "value case" in text:
        message_type, information_shape = "business_benefits", "stack"
    elif "compare" in text or "comparison" in text or "current" in text and "future" in text:
        message_type, information_shape = "comparison", "comparison"
    elif "process" in text or "flow" in text:
        message_type, information_shape = "process_flow", "sequence"
    elif "operating model" in text or "capability" in text:
        message_type, information_shape = "operating_model", "capability_map"
    elif "matrix" in text:
        message_type, information_shape = "matrix", "matrix"
    else:
        message_type, information_shape = "executive_summary", "summary"

    density = "balanced"
    content_units = 3
    if any(term in text for term in ("dense", "detailed", "6", "7")):
        density, content_units = "dense", 6
    elif any(term in text for term in ("simple", "minimal", "summary")):
        density, content_units = "sparse", 3
    elif "4" in text or "four" in text:
        content_units = 4
    elif "5" in text or "five" in text:
        content_units = 5
    elif message_type in {"board_decisions", "kpi_dashboard"}:
        content_units = 4

    return VisualBrief(
        message_type=message_type,
        information_shape=information_shape,
        content_units=content_units,
        audience=str(getattr(intent, "audience", "") or "").lower(),
        density=density,
    )


def _slide_evaluation_report(
    slide_plan: SlidePlan,
    slide_spec: SlideSpec,
    validation_result,
    visual_selection,
    asset_selection,
) -> SlideEvaluationReport:
    """Create a V2 slide-level report from existing execution signals."""
    warnings = list(validation_result.issues if validation_result else [])
    text_fit_failures = [
        issue for issue in warnings if issue.startswith("text-fit failed")
    ]
    language_warnings = [
        issue for issue in warnings if issue.startswith("consulting-language warning:")
    ]
    role_contract_failures = [
        issue for issue in warnings
        if issue.startswith("consulting-language:") or issue.startswith("role-title mismatch:")
    ]
    placeholder_leakage = [
        issue for issue in warnings if "placeholder leakage" in issue.lower()
    ]
    raw = slide_spec.raw_spec if isinstance(slide_spec.raw_spec, dict) else {}
    required = []
    missing = 0
    asset_version = None
    if asset_selection is not None:
        manifest = getattr(asset_selection, "manifest", None)
        asset_version = getattr(manifest, "asset_version", None)
        placeholders = getattr(manifest, "placeholders", [])
        if not isinstance(placeholders, list):
            placeholders = []
        required = [ph.id for ph in placeholders if getattr(ph, "required", False)]
        for placeholder_id in required:
            value = raw.get(placeholder_id)
            if value in (None, "", []):
                missing += 1
    completeness = 1.0
    if required:
        completeness = max(0.0, 1.0 - (missing / len(required)))
    if text_fit_failures:
        completeness = min(completeness, 0.75)

    return SlideEvaluationReport(
        slide_number=slide_plan.slide_number,
        role=slide_plan.slide_role,
        pattern=getattr(visual_selection, "pattern_id", None),
        asset=slide_spec.asset_id,
        asset_version=asset_version,
        population="validated" if validation_result and validation_result.is_valid else "validation_failed",
        missing_placeholders=missing,
        content_completeness=round(completeness, 4),
        text_fit="failed" if text_fit_failures else ("passed" if slide_spec.asset_id else "not_checked"),
        text_fit_failures=text_fit_failures,
        consulting_language_warnings=language_warnings,
        role_contract_failures=role_contract_failures,
        placeholder_leakage=placeholder_leakage,
        fallback_used=False,
        warnings=warnings,
        raw_spec=raw,
    )


def _deck_evaluation_report(slides: list[SlideExecutionResult]) -> DeckEvaluationReport:
    """Aggregate basic deck-level metrics from slide reports."""
    reports = [slide.evaluation_report for slide in slides if slide.evaluation_report]
    if not reports:
        return DeckEvaluationReport()
    asset_ids = [r.asset for r in reports if r.asset]
    repeated_assets = sorted({asset for asset in asset_ids if asset_ids.count(asset) > 1})
    titles = [
        slide.slide_spec.raw_spec.get("title", "")
        for slide in slides
        if slide.slide_spec is not None and isinstance(slide.slide_spec.raw_spec, dict)
    ]
    normalized_titles = [str(title).strip().lower() for title in titles if str(title).strip()]
    repeated_titles = sorted({title for title in normalized_titles if normalized_titles.count(title) > 1})
    roles = [
        _canonical_slide_role(slide.slide_plan.slide_role) or slide.slide_plan.slide_role.strip().lower()
        for slide in slides
        if slide.slide_plan is not None and slide.slide_plan.slide_role
    ]
    duplicate_roles = sorted({role for role in roles if roles.count(role) > 1})
    fallback_by_family: dict[str, int] = {}
    for report in reports:
        if report.fallback_used:
            family = (report.fallback_asset or "unknown").split("-")[1].lower() if report.fallback_asset else "unknown"
            fallback_by_family[family] = fallback_by_family.get(family, 0) + 1
    text_failures = sum(1 for report in reports if report.text_fit == "failed")
    overflow_slides = [report.slide_number for report in reports if report.text_fit == "failed"]
    completeness = sum(r.content_completeness for r in reports) / len(reports)
    patterns = [r.pattern for r in reports if r.pattern]
    diversity = len(set(patterns)) / len(patterns) if patterns else 0.0
    families = [_family_from_asset(asset) for asset in asset_ids]
    family_counts = [families.count(family) for family in set(families)] if families else []
    confidences = [
        slide.slide_plan.confidence
        for slide in slides
        if slide.slide_plan is not None
    ]
    low_confidence_roles = [
        slide.slide_plan.slide_role
        for slide in slides
        if slide.slide_plan is not None and slide.slide_plan.confidence < 0.6
    ]
    language_warnings = [
        warning
        for report in reports
        for warning in report.consulting_language_warnings
    ]
    placeholder_leakage = [
        warning
        for report in reports
        for warning in report.placeholder_leakage
    ]
    role_failures = [
        warning
        for report in reports
        for warning in report.role_contract_failures
    ]
    demo_ready = (
        bool(reports)
        and not duplicate_roles
        and not repeated_titles
        and not language_warnings
        and not placeholder_leakage
        and not role_failures
        and not overflow_slides
        and all(slide.success for slide in slides)
        and len(asset_ids) == len(reports)
    )
    return DeckEvaluationReport(
        asset_coverage=round(len(asset_ids) / len(reports), 4),
        asset_diversity=round(len(set(asset_ids)) / len(asset_ids), 4) if asset_ids else 0.0,
        repeated_asset_count=len(repeated_assets),
        max_family_repetition=max(family_counts) if family_counts else 0,
        fallback_usage_by_family=fallback_by_family,
        repeated_assets=repeated_assets,
        repeated_slide_titles=repeated_titles,
        duplicate_roles=duplicate_roles,
        consulting_language_warnings=language_warnings,
        placeholder_leakage=placeholder_leakage,
        overflow_slides=overflow_slides,
        demo_ready=demo_ready,
        visual_diversity=round(diversity, 4),
        average_content_completeness=round(completeness, 4),
        text_fit_failure_rate=round(text_failures / len(reports), 4),
        planner_confidence=round(sum(confidences) / len(confidences), 4) if confidences else None,
        planner_confidence_min=round(min(confidences), 4) if confidences else None,
        low_confidence_roles=low_confidence_roles,
        slide_reports=reports,
    )


def _family_from_asset(asset_id: str) -> str:
    parts = str(asset_id or "").split("-")
    return parts[0].lower() if parts else "unknown"

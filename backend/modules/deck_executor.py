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
"""

from __future__ import annotations

import logging

from backend.modules.content_generator import generate_slide_content
from backend.modules.validator import validate_content
from schemas.context import EnterpriseContext
from schemas.deck_execution import DeckExecutionResult, SlideExecutionResult
from schemas.intent import IntentResult
from schemas.presentation import DeckSpec
from schemas.process import ProcessResult
from schemas.slide_spec import SlideSpec

logger = logging.getLogger(__name__)


def execute_deck(
    deck_spec: DeckSpec,
    intent: IntentResult,
    enterprise_context: EnterpriseContext,
    process_result: ProcessResult,
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

    Returns
    -------
    DeckExecutionResult
        Aggregate outcome, including successful slides, failed slides, and
        per-slide execution details.
    """
    logger.info(
        "executing deck: presentation_type=%s slides=%d",
        deck_spec.presentation_type,
        len(deck_spec.slides),
    )

    slides: list[SlideExecutionResult] = []
    successful_slides: list[SlideSpec] = []
    failed_slides: list[SlideExecutionResult] = []

    for slide_plan in deck_spec.slides:
        try:
            slide_spec = generate_slide_content(
                intent, enterprise_context, process_result, slide_plan
            )
            validation_result = validate_content(slide_spec)

            if validation_result.is_valid and validation_result.validated_spec is not None:
                execution_result = SlideExecutionResult(
                    slide_plan=slide_plan,
                    slide_spec=validation_result.validated_spec,
                    validation_result=validation_result,
                    success=True,
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
    )

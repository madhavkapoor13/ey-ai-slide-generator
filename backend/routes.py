import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from fastapi.responses import FileResponse

from backend.models import GenerateFromPlanV2Request, GenerateV2Request, PlanV2Request
from backend.orchestrator import plan_pipeline
from backend.presentation_assets.visual_variant_registry import variant_for_asset_id
from backend.services.slide_service import generate_slide, generate_slide_v2, generate_slide_v2_from_plan
from schemas.presentation import DeckSpec, SlidePlan

router = APIRouter()
logger = logging.getLogger(__name__)

PPTX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.presentationml.presentation"
)


class SlideRequest(BaseModel):
    title: str
    content: str


# ── Phase 1 routes (unchanged) ────────────────────────────────────────────────

@router.post("/generate")
async def generate_slide_api(request: SlideRequest):
    logger.warning("POST /generate executed — Phase 1 legacy pipeline")
    logger.info("request received: title=%s content_length=%s", request.title, len(request.content))

    try:
        ppt_path = generate_slide(
            request.title,
            request.content
        )
    except Exception:
        logger.exception("slide generation failed")
        raise

    logger.info("response sent: path=%s", ppt_path)

    return FileResponse(
        ppt_path,
        media_type=PPTX_MEDIA_TYPE,
        filename="generated_slide.pptx"
    )


@router.post("/generate-slide")
async def generate_slide_legacy_api(request: SlideRequest):
    logger.warning("POST /generate-slide executed — delegating to Phase 1 legacy pipeline")
    return await generate_slide_api(request)


# ── Phase 2 route ─────────────────────────────────────────────────────────────

@router.post("/plan/v2")
async def plan_v2_api(request: PlanV2Request):
    """Return an editable deck plan preview without generating a PPTX."""
    logger.warning("POST /plan/v2 executed — editable plan preview")
    logger.info(
        "v2 plan request received: title=%s content_length=%s",
        request.title,
        len(request.content),
    )

    try:
        return plan_pipeline(request.title, request.content)
    except Exception:
        logger.exception("v2 plan generation failed")
        raise


@router.post("/generate/v2/from-plan")
async def generate_slide_v2_from_plan_api(request: GenerateFromPlanV2Request):
    """Generate a PPTX from a user-approved edited DeckSpec."""
    logger.warning("POST /generate/v2/from-plan executed — approved plan pipeline")
    logger.info(
        "v2 approved-plan request received: title=%s content_length=%s slides=%d",
        request.title,
        len(request.content),
        len(request.deck_spec.slides),
    )

    try:
        deck_spec = _normalize_and_validate_deck_spec(request.deck_spec)
        _validate_visual_preferences(request.preferences)
        ppt_path = generate_slide_v2_from_plan(
            request.title,
            request.content,
            deck_spec,
            preferences=request.preferences,
        )
    except ValueError as exc:
        logger.error("v2 approved-plan validation failure: %s", exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        logger.exception("v2 approved-plan generation failed")
        raise

    logger.info("v2 approved-plan response sent: path=%s", ppt_path)

    return FileResponse(
        ppt_path,
        media_type=PPTX_MEDIA_TYPE,
        filename="generated_slide_v2.pptx",
    )


@router.post("/generate/v2")
async def generate_slide_v2_api(request: GenerateV2Request):
    """
    Phase 2 slide generation endpoint.

    Routes the request through the full AI orchestration pipeline:
    Intent → Context → Process Mapping → Content Generation → Validation → Render.

    The response is the same ``.pptx`` file format as ``/generate``, ensuring
    the Office Add-in frontend requires no changes to consume this endpoint.
    """
    logger.warning("POST /generate/v2 executed — Sprint 1-4 orchestrator pipeline")
    logger.info(
        "v2 request received: title=%s content_length=%s",
        request.title,
        len(request.content),
    )

    try:
        ppt_path = generate_slide_v2(request.title, request.content)
    except ValueError as exc:
        # Raised when the orchestrator pipeline produces an invalid spec
        logger.error("v2 validation failure: %s", exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        logger.exception("v2 slide generation failed")
        raise

    logger.info("v2 response sent: path=%s", ppt_path)

    return FileResponse(
        ppt_path,
        media_type=PPTX_MEDIA_TYPE,
        filename="generated_slide_v2.pptx",
    )


def _normalize_and_validate_deck_spec(deck_spec: DeckSpec) -> DeckSpec:
    if not deck_spec.slides:
        raise ValueError("deck plan must contain at least one slide")

    normalized_slides: list[SlidePlan] = []
    for index, slide in enumerate(deck_spec.slides, start=1):
        if not slide.slide_role.strip():
            raise ValueError(f"slide {index} must have a non-empty slide_role")
        if not slide.purpose.strip():
            raise ValueError(f"slide {index} must have a non-empty purpose")
        if not slide.visualization_type.strip():
            raise ValueError(f"slide {index} must have a non-empty visualization_type")
        normalized_slides.append(slide.model_copy(update={"slide_number": index}))

    return deck_spec.model_copy(
        update={
            "estimated_slide_count": len(normalized_slides),
            "slides": normalized_slides,
        }
    )


def _validate_visual_preferences(preferences) -> None:
    if preferences is None:
        return
    for slide_type, variant_id in preferences.user_visual_preferences.items():
        if not variant_id:
            continue
        if variant_for_asset_id(variant_id) is None:
            # ``variant_for_asset_id`` only checks asset ids; route through the
            # resolver's public matching behavior by accepting variant ids too.
            from backend.presentation_assets.visual_variant_registry import _variant_by_id

            try:
                _variant_by_id(variant_id)
            except ValueError as exc:
                raise ValueError(
                    f"unknown visual variant override for {slide_type!r}: {variant_id!r}"
                ) from exc

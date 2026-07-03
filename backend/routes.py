import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from fastapi.responses import FileResponse

from backend.services.slide_service import generate_slide, generate_slide_v2
from backend.models import GenerateV2Request

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

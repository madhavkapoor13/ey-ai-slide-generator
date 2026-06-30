import logging

from fastapi import APIRouter
from pydantic import BaseModel
from fastapi.responses import FileResponse

from backend.services.slide_service import generate_slide

router = APIRouter()
logger = logging.getLogger(__name__)

PPTX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.presentationml.presentation"
)


class SlideRequest(BaseModel):
    title: str
    content: str


@router.post("/generate")
async def generate_slide_api(request: SlideRequest):
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
    return await generate_slide_api(request)

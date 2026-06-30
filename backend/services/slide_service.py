import logging

from backend.llm.planner import create_operating_model_spec, create_slide_spec
from ppt_renderer.operating_model_renderer import OperatingModelRenderer
from ppt_renderer.renderer import ProcessFlowRenderer

logger = logging.getLogger(__name__)


def generate_slide(title, content):

    if _is_operating_model_request(title, content):
        logger.info("operating model generation selected")
        slide_spec = create_operating_model_spec(
            title,
            content
        )
        logger.info("LLM completed: operating_model stages=%s", len(slide_spec.get("stages", [])))

        renderer = OperatingModelRenderer()
    else:
        logger.info("process flow generation selected")
        slide_spec = create_slide_spec(
            title,
            content
        )
        logger.info("LLM completed: process_flow nodes=%s", len(slide_spec.get("nodes", [])))

        renderer = ProcessFlowRenderer()

    output_path = "generated_slide.pptx"

    renderer.render(
        slide_spec,
        output_path
    )
    logger.info("PPT generated: path=%s", output_path)

    return output_path


def _is_operating_model_request(title, content):
    text = f"{title} {content}".lower()

    operating_model_signals = [
        "operating model",
        "current state",
        "business stages",
        "detailed business activities",
        "executive summary",
        "value leakage",
        "kpis",
        "pain points, business risks",
        "risks, and inefficiencies",
    ]

    return any(signal in text for signal in operating_model_signals)

import logging

from backend.llm.planner import create_operating_model_spec, create_slide_spec
from ppt_renderer.operating_model_renderer import OperatingModelRenderer
from ppt_renderer.renderer import ProcessFlowRenderer

logger = logging.getLogger(__name__)


# ── Phase 1 (unchanged) ───────────────────────────────────────────────────────

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


# ── Phase 2 ───────────────────────────────────────────────────────────────────

def generate_slide_v2(title: str, content: str) -> str:
    """
    Phase 2 slide generation — orchestrator-driven pipeline.

    Routes the request through the full AI orchestration pipeline and
    delegates rendering to the existing Phase 1 renderers via the
    ``SlideSpec.raw_spec`` contract. The Phase 1 rendering layer is NOT
    duplicated or modified.

    Parameters
    ----------
    title:
        Raw slide title from the user request.
    content:
        Raw slide content / description from the user request.

    Returns
    -------
    str
        Absolute path to the generated ``.pptx`` file.

    Raises
    ------
    ValueError
        If the orchestrator pipeline produces an invalid ``ValidationResult``
        (``is_valid=False``). The caller (FastAPI route) converts this to
        an HTTP 422 response.
    """
    from backend.orchestrator import run_pipeline  # local import avoids circular deps at module load

    logger.info("v2 generation started: title=%s", title)

    result = run_pipeline(title, content)

    if not result.is_valid:
        logger.error("v2 pipeline rejected spec: issues=%s", result.issues)
        raise ValueError(f"Generated spec failed validation: {result.issues}")

    spec = result.validated_spec
    output_path = "generated_slide_v2.pptx"

    renderer = _select_renderer(spec.slide_type)
    renderer.render(spec.raw_spec, output_path)

    logger.info("v2 PPT generated: path=%s slide_type=%s", output_path, spec.slide_type)
    return output_path


def _select_renderer(slide_type: str):
    """
    Select the appropriate Phase 1 renderer for the given slide type.

    This is the ONLY place in Phase 2 code that references renderer classes.
    All renderer logic remains inside ``ppt_renderer/`` untouched.

    Parameters
    ----------
    slide_type:
        Normalised slide type from ``SlideSpec.slide_type``.

    Returns
    -------
    Renderer instance with a ``.render(spec_dict, output_path)`` method.
    """
    if slide_type == "operating_model":
        return OperatingModelRenderer()
    # Default: ProcessFlowRenderer handles process_flow, comparison,
    # current_future, and unknown until dedicated renderers are built.
    return ProcessFlowRenderer()


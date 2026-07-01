"""
schemas/slide_spec.py
=====================
Phase 2 schema — the canonical Slide Specification consumed by the renderer.

SlideSpec is the contract between the orchestrator and the PowerPoint
rendering layer. The renderer must only ever consume a SlideSpec; it must
not receive raw LLM output or module-internal data structures.
"""

from __future__ import annotations

from typing import Any, Dict

from pydantic import BaseModel, Field


class SlideSpec(BaseModel):
    """
    Canonical slide specification passed from the orchestrator to the renderer.

    The ``raw_spec`` field carries the dict that existing Phase 1 renderers
    already understand (operating model JSON or process flow JSON), so Phase 2
    pipelines can reuse the existing rendering layer without modification.

    Attributes
    ----------
    slide_type:
        Normalised type that tells the renderer which renderer to invoke.
        Must match one of: ``"operating_model"``, ``"process_flow"``,
        ``"comparison"``, ``"current_future"``.
    raw_spec:
        The renderer-ready dict payload. Schema is renderer-specific and
        mirrors the JSON produced by Phase 1 LLM planners.
    version:
        Spec format version. Allows renderers to handle future schema changes.
    generated_by:
        Identifier of the component that produced this spec.
        E.g. ``"orchestrator"``, ``"planner_v1"``.
    """

    slide_type: str = Field(
        ...,
        description="Renderer identifier: operating_model | process_flow | comparison | current_future",
    )
    raw_spec: Dict[str, Any] = Field(
        ...,
        description="Renderer-ready dict payload. Format is renderer-specific.",
    )
    version: str = Field(
        default="2.0",
        description="Spec format version for forward compatibility.",
    )
    generated_by: str = Field(
        default="orchestrator",
        description="Component that produced this SlideSpec.",
    )

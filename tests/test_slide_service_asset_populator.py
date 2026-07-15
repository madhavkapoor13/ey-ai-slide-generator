from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

from pptx import Presentation

from backend.presentation_assets import asset_registry
from backend.services.slide_service import generate_slide_v2
from schemas.deck_execution import DeckExecutionResult, SlideExecutionResult
from schemas.pipeline_result import PipelineResult
from schemas.presentation import DeckSpec, SlidePlan
from schemas.slide_spec import SlideSpec
from schemas.validation import ValidationResult
from schemas.visual import VisualPatternSelection


def _asset_slide_spec(asset_id: str, family: str) -> SlideSpec:
    """Return a manifest-shaped SlideSpec for one of the pilot assets."""
    if asset_id == "TIMELINE-6STEP-001":
        content = {
            "title": "Pilot Timeline",
            "step_label": ["Discover", "Design", "Deliver", "Deploy", "Optimize", "Scale"],
        }
    elif asset_id == "PROCESS-7STEP-001":
        content = {
            "title": "Pilot Process",
            "subtitle": "Seven-step workflow",
            "step_label": [f"Step {i + 1}" for i in range(7)],
            "step_body": [f"Body for step {i + 1}" for i in range(7)],
        }
    elif asset_id == "LIST-6ITEM-001":
        content = {
            "title": "Pilot List",
            "item_label": [f"Item {i + 1}" for i in range(6)],
            "item_body": [f"Body for item {i + 1}" for i in range(6)],
        }
    else:
        content = {"title": "Asset Slide"}

    return SlideSpec(
        slide_type="operating_model",
        raw_spec=content,
        version="2.0",
        generated_by="test",
        asset_id=asset_id,
        visual_pattern_id="IG-02",
        visual_confidence=0.9,
    )


def _make_pipeline_result(asset_id: str, family: str) -> PipelineResult:
    slide_plan = SlidePlan(
        slide_number=1,
        slide_role="Roadmap",
        purpose="Roadmap slide.",
        required_inputs=[],
        dependencies=[],
        visualization_type="Roadmap",
    )
    slide_spec = _asset_slide_spec(asset_id, family)
    slide_result = SlideExecutionResult(
        slide_plan=slide_plan,
        slide_spec=slide_spec,
        validation_result=ValidationResult(is_valid=True, issues=[], claims=[], validated_spec=slide_spec),
        success=True,
    )
    deck_result = DeckExecutionResult(
        deck_spec=DeckSpec(
            presentation_type="Transformation Proposal",
            objective="Test asset rendering.",
            audience="Board",
            narrative="Roadmap",
            estimated_slide_count=1,
            slides=[slide_plan],
        ),
        slides=[slide_result],
        successful_slides=[slide_spec],
        failed_slides=[],
        all_succeeded=True,
        partial_success=False,
    )
    return PipelineResult(
        status="COMPLETED",
        needs_clarification=False,
        deck_execution_result=deck_result,
        clarification_result=None,
    )


class SlideServiceAssetPopulatorTests(unittest.TestCase):
    """Tests for Sprint F: slide_service uses the Asset Populator for asset_id slides."""

    def setUp(self):
        for path in ["generated_slide_v2.pptx"]:
            if os.path.exists(path):
                os.remove(path)
        asset_registry.clear_cache()
        asset_registry.load_assets()

    def tearDown(self):
        for path in ["generated_slide_v2.pptx"]:
            if os.path.exists(path):
                os.remove(path)
        asset_registry.clear_cache()

    def test_asset_slide_renders_via_populator(self):
        """A slide carrying asset_id is populated from the Presentation Asset library."""
        pipeline_result = _make_pipeline_result("TIMELINE-6STEP-001", "timeline")

        with patch("backend.orchestrator.run_pipeline", return_value=pipeline_result):
            path = generate_slide_v2("title", "content")

        self.assertTrue(os.path.exists(path))
        prs = Presentation(path)
        self.assertEqual(len(prs.slides), 1)

    def test_asset_populator_failure_falls_back_to_legacy_renderer(self):
        """When populate_asset_slide raises, the legacy renderer is used as fallback."""
        pipeline_result = _make_pipeline_result("TIMELINE-6STEP-001", "timeline")

        mock_renderer = MagicMock()

        with patch("backend.orchestrator.run_pipeline", return_value=pipeline_result):
            with patch("backend.services.slide_service.asset_populator.populate_asset_slide") as mock_populate:
                mock_populate.side_effect = RuntimeError("asset missing")
                with patch("backend.services.slide_service._select_renderer", return_value=mock_renderer):
                    generate_slide_v2("title", "content")

        mock_populate.assert_called_once()
        mock_renderer.render.assert_called_once()

    def test_legacy_slide_without_asset_id_uses_renderer(self):
        """A slide without asset_id follows the existing renderer path."""
        slide_plan = SlidePlan(
            slide_number=1,
            slide_role="Executive Summary",
            purpose="Summary.",
            required_inputs=[],
            dependencies=[],
            visualization_type="Executive Summary",
        )
        slide_spec = SlideSpec(
            slide_type="operating_model",
            raw_spec={
                "title": "Executive Summary",
                "subtitle": "Subtitle",
                "description": "Description.",
                "executive_summary": "Summary one. Summary two.",
                "stages": [],
                "pain_points": [],
                "risks": [],
                "metadata": {"slide_role": "Executive Summary"},
            },
            version="2.0",
            generated_by="test",
        )
        slide_result = SlideExecutionResult(
            slide_plan=slide_plan,
            slide_spec=slide_spec,
            validation_result=ValidationResult(is_valid=True, issues=[], claims=[], validated_spec=slide_spec),
            success=True,
        )
        deck_result = DeckExecutionResult(
            deck_spec=DeckSpec(
                presentation_type="Transformation Proposal",
                objective="Test.",
                audience="Board",
                narrative="Executive Summary",
                estimated_slide_count=1,
                slides=[slide_plan],
            ),
            slides=[slide_result],
            successful_slides=[slide_spec],
            failed_slides=[],
            all_succeeded=True,
            partial_success=False,
        )
        pipeline_result = PipelineResult(
            status="COMPLETED",
            needs_clarification=False,
            deck_execution_result=deck_result,
            clarification_result=None,
        )

        mock_renderer = MagicMock()

        with patch("backend.orchestrator.run_pipeline", return_value=pipeline_result):
            with patch("backend.services.slide_service.asset_populator.populate_asset_slide") as mock_populate:
                with patch("backend.services.slide_service._select_renderer", return_value=mock_renderer):
                    generate_slide_v2("title", "content")

        mock_populate.assert_not_called()
        mock_renderer.render.assert_called_once()


if __name__ == "__main__":
    unittest.main()

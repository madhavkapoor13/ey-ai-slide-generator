import unittest
from typing import Optional
from unittest.mock import MagicMock, patch

from backend.modules.deck_executor import (
    _asset_compatibility_score,
    _gate_deck_plan,
    execute_deck,
)
from schemas.presentation_asset import AssetManifest, AssetSelection
from schemas.context import EnterpriseContext
from schemas.intent import IntentResult
from schemas.presentation import DeckSpec, SlidePlan
from schemas.process import ProcessResult
from schemas.slide_spec import SlideSpec
from schemas.validation import ValidationResult
from schemas.visual import VisualBrief, VisualPatternSelection


def _intent() -> IntentResult:
    return IntentResult(
        slide_type="operating_model",
        raw_title="Current State",
        raw_content="Procure-to-Pay process for Toyota.",
        company="Toyota",
        industry="Automotive",
        business_function="Procurement",
    )


def _context() -> EnterpriseContext:
    return EnterpriseContext(
        company="Toyota",
        industry="Automotive",
        business_function="Procurement",
    )


def _process() -> ProcessResult:
    return ProcessResult(
        process_name="Procure-to-Pay",
        process_family="Procurement",
        confidence=0.94,
        reasoning="test",
        stages=["Requisition", "Sourcing", "Purchase Order", "Goods Receipt", "Invoice Processing", "Payment"],
    )


def _slide_spec(slide_number: int, slide_role: str) -> SlideSpec:
    return SlideSpec(
        slide_type="operating_model",
        raw_spec={
            "title": slide_role,
            "subtitle": f"Toyota Procurement — slide {slide_number}",
            "description": f"Content for {slide_role}",
            "executive_summary": "Summary one. Summary two.",
            "summary": {"headline": "Procure-to-Pay", "description": "Summary one. Summary two.", "metrics": []},
            "stages": [],
            "pain_points": [],
            "risks": [],
            "metadata": {"company": "Toyota", "industry": "Automotive", "process": "Procure-to-Pay"},
        },
        version="2.0",
        generated_by="test",
    )


def _valid_result(slide_spec: SlideSpec) -> ValidationResult:
    return ValidationResult(is_valid=True, issues=[], claims=[], validated_spec=slide_spec)


def _invalid_result(slide_spec: Optional[SlideSpec], issues: list[str]) -> ValidationResult:
    return ValidationResult(is_valid=False, issues=issues, claims=[], validated_spec=slide_spec)


def _deck(slide_roles: list[str]) -> DeckSpec:
    return DeckSpec(
        presentation_type="Transformation Proposal",
        objective="Align stakeholders.",
        audience="Senior leadership",
        narrative="Current State → Opportunities → Future State → Roadmap → Next Steps",
        estimated_slide_count=len(slide_roles),
        slides=[
            SlidePlan(
                slide_number=index + 1,
                slide_role=role,
                purpose=f"Communicate the {role} message.",
                required_inputs=[],
                dependencies=[],
                visualization_type="Executive Summary" if role == "Executive Summary" else "Process Flow",
            )
            for index, role in enumerate(slide_roles)
        ],
    )


class DeckExecutorTests(unittest.TestCase):
    def test_one_slide_deck(self):
        deck = _deck(["Executive Summary"])

        def fake_generate(intent, context, process_result, slide_plan, **kwargs):
            return _slide_spec(slide_plan.slide_number, slide_plan.slide_role)

        def fake_validate(spec):
            return _valid_result(spec)

        with patch("backend.modules.deck_executor.generate_slide_content", side_effect=fake_generate):
            with patch("backend.modules.deck_executor.validate_content", side_effect=fake_validate):
                result = execute_deck(deck, _intent(), _context(), _process())

        self.assertTrue(result.all_succeeded)
        self.assertFalse(result.partial_success)
        self.assertEqual(len(result.successful_slides), 1)
        self.assertEqual(len(result.failed_slides), 0)
        self.assertEqual(result.successful_slides[0].raw_spec["title"], "Executive Summary")

    def test_six_slide_deck(self):
        roles = ["Executive Summary", "Current State", "Opportunities", "Future State", "Roadmap", "Next Steps"]
        deck = _deck(roles)

        def fake_generate(intent, context, process_result, slide_plan, **kwargs):
            return _slide_spec(slide_plan.slide_number, slide_plan.slide_role)

        def fake_validate(spec):
            return _valid_result(spec)

        with patch("backend.modules.deck_executor.generate_slide_content", side_effect=fake_generate):
            with patch("backend.modules.deck_executor.validate_content", side_effect=fake_validate):
                result = execute_deck(deck, _intent(), _context(), _process())

        self.assertTrue(result.all_succeeded)
        self.assertFalse(result.partial_success)
        self.assertEqual(len(result.successful_slides), 6)
        self.assertEqual(len(result.failed_slides), 0)
        self.assertEqual([slide.raw_spec["title"] for slide in result.successful_slides], roles)

    def test_ten_slide_deck(self):
        roles = [f"Slide {i}" for i in range(1, 11)]
        deck = _deck(roles)

        def fake_generate(intent, context, process_result, slide_plan, **kwargs):
            return _slide_spec(slide_plan.slide_number, slide_plan.slide_role)

        with patch("backend.modules.deck_executor.generate_slide_content", side_effect=fake_generate):
            with patch("backend.modules.deck_executor.validate_content", side_effect=_valid_result):
                result = execute_deck(deck, _intent(), _context(), _process())

        self.assertTrue(result.all_succeeded)
        self.assertEqual(len(result.successful_slides), 10)
        self.assertEqual(len(result.slides), 10)

    def test_empty_deck(self):
        deck = DeckSpec(
            presentation_type="Transformation Proposal",
            objective="Align stakeholders.",
            audience="Senior leadership",
            narrative="Executive Summary only",
            estimated_slide_count=1,
            slides=[],
        )

        with patch("backend.modules.deck_executor.generate_slide_content") as mock_generate:
            with patch("backend.modules.deck_executor.validate_content") as mock_validate:
                result = execute_deck(deck, _intent(), _context(), _process())

        self.assertFalse(result.all_succeeded)
        self.assertFalse(result.partial_success)
        self.assertEqual(len(result.successful_slides), 0)
        self.assertEqual(len(result.failed_slides), 0)
        mock_generate.assert_not_called()
        mock_validate.assert_not_called()

    def test_deck_plan_gate_drops_duplicate_canonical_roles(self):
        deck = _deck([
            "Executive Summary",
            "AI Procurement Transformation Executive Summary",
            "KPIs for Success",
            "KPI Maturity Assessment",
            "Implementation Risks",
        ])

        gated = _gate_deck_plan(deck)

        self.assertEqual(
            [slide.slide_role for slide in gated.slides],
            ["Executive Summary", "KPIs for Success", "Implementation Risks"],
        )
        self.assertEqual([slide.slide_number for slide in gated.slides], [1, 2, 3])

    def test_risk_slide_rejects_kpi_asset_family(self):
        slide_plan = SlidePlan(
            slide_number=1,
            slide_role="Implementation Risks",
            purpose="Assess implementation risks and mitigations.",
            required_inputs=[],
            dependencies=[],
            visualization_type="Risk Matrix",
        )
        manifest = AssetManifest(
            asset_id="KPI-4METRIC-001",
            schema_version="1.0.0",
            family="kpi",
            family_aliases=["kpi_dashboard"],
            purpose="KPI scorecard",
            audience_tags=[],
            style_tags=[],
            recommended_for=[],
            avoid_for=[],
            density=4,
            density_range=[1, 4],
            fits_content_kinds=["KPI Dashboard"],
            supports_images=False,
            placeholders=[],
        )
        selection = AssetSelection(
            asset_id=manifest.asset_id,
            family="kpi",
            manifest=manifest,
            confidence=0.9,
            score_breakdown={},
            reasoning="test",
            candidate_ids=[manifest.asset_id],
        )

        brief = VisualBrief(
            message_type="risk_matrix",
            information_shape="matrix",
            content_units=4,
            audience="board",
            density="balanced",
        )

        score, reasons = _asset_compatibility_score(slide_plan, brief, selection)

        self.assertLess(score, 0.35)
        self.assertEqual(reasons, ["no_metadata_overlap"])

    def test_risk_slide_accepts_matrix_asset_family(self):
        slide_plan = SlidePlan(
            slide_number=1,
            slide_role="Implementation Risks",
            purpose="Assess implementation risks and mitigations.",
            required_inputs=[],
            dependencies=[],
            visualization_type="Risk Matrix",
        )
        manifest = AssetManifest(
            asset_id="RISK-MATRIX-4ITEM-001",
            schema_version="1.0.0",
            family="matrix",
            family_aliases=["risk_matrix"],
            purpose="Risk matrix",
            audience_tags=[],
            style_tags=[],
            recommended_for=[],
            avoid_for=[],
            density=4,
            density_range=[1, 4],
            fits_content_kinds=["Risk Matrix"],
            supports_images=False,
            placeholders=[],
            message_type="risk_matrix",
            information_shape="matrix",
        )
        selection = AssetSelection(
            asset_id=manifest.asset_id,
            family="matrix",
            manifest=manifest,
            confidence=0.9,
            score_breakdown={},
            reasoning="test",
            candidate_ids=[manifest.asset_id],
        )

        brief = VisualBrief(
            message_type="risk_matrix",
            information_shape="matrix",
            content_units=4,
            audience="board",
            density="balanced",
        )

        score, reasons = _asset_compatibility_score(slide_plan, brief, selection)

        self.assertGreaterEqual(score, 0.35)
        self.assertIn("message_type", reasons)
        self.assertIn("information_shape", reasons)

    def test_failed_slide_generation(self):
        deck = _deck(["Executive Summary", "Current State"])

        def fake_generate(intent, context, process_result, slide_plan, **kwargs):
            if slide_plan.slide_role == "Current State":
                raise RuntimeError("LLM unavailable")
            return _slide_spec(slide_plan.slide_number, slide_plan.slide_role)

        with patch("backend.modules.deck_executor.generate_slide_content", side_effect=fake_generate):
            with patch("backend.modules.deck_executor.validate_content", side_effect=_valid_result):
                result = execute_deck(deck, _intent(), _context(), _process())

        self.assertFalse(result.all_succeeded)
        self.assertTrue(result.partial_success)
        self.assertEqual(len(result.successful_slides), 1)
        self.assertEqual(len(result.failed_slides), 1)
        self.assertEqual(result.failed_slides[0].slide_plan.slide_role, "Current State")
        self.assertIn("LLM unavailable", result.failed_slides[0].error or "")

    def test_partial_deck_generation_with_validation_failure(self):
        deck = _deck(["Executive Summary", "Current State", "Future State"])

        def fake_generate(intent, context, process_result, slide_plan, **kwargs):
            return _slide_spec(slide_plan.slide_number, slide_plan.slide_role)

        def fake_validate(spec):
            if spec.raw_spec["title"] == "Current State":
                return _invalid_result(spec, ["Missing executive summary."])
            return _valid_result(spec)

        with patch("backend.modules.deck_executor.generate_slide_content", side_effect=fake_generate):
            with patch("backend.modules.deck_executor.validate_content", side_effect=fake_validate):
                result = execute_deck(deck, _intent(), _context(), _process())

        self.assertFalse(result.all_succeeded)
        self.assertTrue(result.partial_success)
        self.assertEqual(len(result.successful_slides), 2)
        self.assertEqual(len(result.failed_slides), 1)
        self.assertEqual(result.failed_slides[0].slide_plan.slide_role, "Current State")
        self.assertIn("Missing executive summary", result.failed_slides[0].error or "")

    def test_sequential_execution_preserves_order(self):
        roles = ["Executive Summary", "Current State", "Future State"]
        deck = _deck(roles)
        generated_order: list[int] = []

        def fake_generate(intent, context, process_result, slide_plan, **kwargs):
            generated_order.append(slide_plan.slide_number)
            return _slide_spec(slide_plan.slide_number, slide_plan.slide_role)

        with patch("backend.modules.deck_executor.generate_slide_content", side_effect=fake_generate):
            with patch("backend.modules.deck_executor.validate_content", side_effect=_valid_result):
                result = execute_deck(deck, _intent(), _context(), _process())

        self.assertEqual(generated_order, [1, 2, 3])
        self.assertTrue(result.all_succeeded)

    def test_visual_rhythm_avoids_consecutive_same_family(self):
        deck = _deck(["Executive Summary", "Current State"])

        def fake_generate(intent, context, process_result, slide_plan, **kwargs):
            return _slide_spec(slide_plan.slide_number, slide_plan.slide_role)

        calls: list[tuple[int, str | None]] = []

        def fake_plan_visual_pattern(slide_plan, slide_spec, exclude_category=None):
            calls.append((slide_plan.slide_number, exclude_category))
            # First slide creative; second would also be creative without guard.
            family = "creative_listing" if slide_plan.slide_number == 1 else "infographic"
            return VisualPatternSelection(
                pattern_id="CL-01" if family == "creative_listing" else "IG-01",
                category=family,
                confidence=0.9,
                reasoning="test",
                recommended_variant=None,
            )

        with patch("backend.modules.deck_executor.generate_slide_content", side_effect=fake_generate):
            with patch("backend.modules.deck_executor.validate_content", side_effect=_valid_result):
                with patch("backend.modules.deck_executor.plan_visual_pattern", side_effect=fake_plan_visual_pattern):
                    execute_deck(deck, _intent(), _context(), _process())

        self.assertEqual(calls, [(1, None), (2, "creative_listing")])


if __name__ == "__main__":
    unittest.main()

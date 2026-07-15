import unittest

from backend.modules.content_generator import _apply_visual_pattern_shape, _to_renderer_ready_spec
from backend.modules.consulting_language import validate_consulting_language
from backend.modules.deck_executor import _apply_post_generation_quality_gate
from backend.modules.visual_planner import plan_visual_pattern
from schemas.context import EnterpriseContext
from schemas.intent import IntentResult
from schemas.presentation import SlidePlan
from schemas.process import ProcessResult
from schemas.slide_spec import SlideSpec
from schemas.visual import VisualPatternSelection
from schemas.validation import ValidationResult


class ConsultingLanguageTests(unittest.TestCase):
    def test_rejects_generic_roadmap_phase_labels(self):
        raw = {
            "title": "Implementation Roadmap",
            "executive_summary": "The program should sequence adoption through accountable delivery waves.",
            "phases": [{"name": "Step 1"}, {"name": "Step 2"}],
        }
        result = validate_consulting_language(raw, "Implementation Roadmap")

        self.assertFalse(result.passed)
        self.assertTrue(any("roadmap phases" in issue for issue in result.issues))

    def test_warns_on_generic_ai_filler(self):
        raw = {
            "title": "AI Use Cases",
            "executive_summary": "AI use cases should connect workflow redesign to measurable business outcomes.",
            "cards": [
                {"title": "Leverage AI", "description": "Enhance collaboration and improve compliance."}
            ],
        }
        result = validate_consulting_language(raw, "AI Use Cases")

        self.assertTrue(result.warnings)
        self.assertTrue(any("leverage ai" in warning for warning in result.warnings))

    def test_asset_shaped_content_can_satisfy_so_what_without_so_what_key(self):
        raw = {
            "title": "Manual approvals slow supplier decisions and weaken spend control",
            "step_label": [
                "Fragmented intake",
                "Manual approval routing",
                "Invoice exception handling",
            ],
        }

        result = validate_consulting_language(raw, "Current Procurement Process")

        self.assertNotIn("missing board-level so-what.", result.issues)

    def test_next_steps_accepts_day_based_timing_and_decision_language(self):
        raw = {
            "title": "Board approval unlocks a 90-day controlled AI procurement pilot",
            "row_1_priority": "Approve pilot scope",
            "row_1_next_step": "Authorize procurement sponsor to launch value-control pilot",
            "row_1_when": "30 days",
            "row_1_who": "Procurement owner",
        }

        result = validate_consulting_language(raw, "Next Steps")

        self.assertNotIn("next steps require a board decision.", result.issues)
        self.assertNotIn("next steps require timing.", result.issues)
        self.assertFalse(any("unsupported numeric claim: '30 days'" in warning for warning in result.warnings))

    def test_action_register_shape_suppresses_30_day_numeric_warning(self):
        raw = {
            "title": "Board decisions launch the procurement AI pilot",
            "row_1_next_step": "Approve pilot launch",
            "row_1_when": "30 days",
            "row_1_who": "Procurement sponsor",
        }

        result = validate_consulting_language(raw, "Action Register")

        self.assertFalse(any("unsupported numeric claim: '30 days'" in warning for warning in result.warnings))

    def test_action_register_contract_satisfies_next_step_quality_gate(self):
        raw = {
            "title": "Next Steps",
            "row_1_next_step": "Launch controlled pilot",
            "row_1_when": "30 days",
            "row_1_who": "Procurement sponsor",
        }

        result = validate_consulting_language(raw, "Action Register")

        self.assertNotIn("missing board-level so-what.", result.issues)
        self.assertNotIn("next steps require a board decision.", result.issues)
        self.assertNotIn("next steps require timing.", result.issues)
        self.assertFalse(any("unsupported numeric claim: '30 days'" in warning for warning in result.warnings))

    def test_nested_action_register_timing_is_not_unsupported_numeric_claim(self):
        raw = {
            "title": "Next Steps",
            "actions": [
                {
                    "next_step": "Launch controlled pilot",
                    "timing": "30 days",
                    "owner": "Procurement sponsor",
                }
            ],
        }

        result = validate_consulting_language(raw, "Action Register")

        self.assertNotIn("missing board-level so-what.", result.issues)
        self.assertNotIn("next steps require a board decision.", result.issues)
        self.assertNotIn("next steps require timing.", result.issues)
        self.assertFalse(any("unsupported numeric claim: '30 days'" in warning for warning in result.warnings))

    def test_risks_accepts_driver_response_and_owner_language(self):
        raw = {
            "title": "Data-quality dependency creates adoption risk without accountable controls",
            "risk_title": ["Supplier master data dependency"],
            "risk_description": ["Driver: fragmented supplier records create adoption exposure."],
            "risk_assessment": ["Impact: delayed rollout; response owned by Procurement data sponsor."],
        }

        result = validate_consulting_language(raw, "Implementation Risks")

        self.assertNotIn("risks require cause.", result.issues)
        self.assertNotIn("risks require mitigation and ownership.", result.issues)

    def test_use_cases_accepts_value_and_visibility_as_outcome(self):
        raw = {
            "title": "AI sourcing agents improve spend visibility before award decisions",
            "pillar_title": ["Supplier sourcing workflow"],
            "pillar_body": ["AI agent screens supplier options to increase spend visibility and control value leakage."],
        }

        result = validate_consulting_language(raw, "AI Use Cases")

        self.assertNotIn("use cases require business outcome.", result.issues)

    def test_kpi_metric_value_does_not_warn_as_unsupported_numeric_claim(self):
        raw = {
            "title": "AI Procurement Transformation success measured through key performance indicators",
            "category": ["Purchase order cycle time"],
            "value": ["30 days"],
            "right_label": ["Target"],
        }

        result = validate_consulting_language(raw, "KPIs for Success")

        self.assertFalse(any("unsupported numeric claim: '30 days'" in warning for warning in result.warnings))

    def test_post_generation_gate_rejects_role_drift(self):
        plan = SlidePlan(
            slide_number=8,
            slide_role="Next Steps",
            purpose="Define board decisions, owners, and timing.",
            required_inputs=[],
            dependencies=[],
            visualization_type="Board Decisions",
        )
        spec = SlideSpec(
            slide_type="operating_model",
            raw_spec={
                "title": "AI Procurement Transformation Executive Summary",
                "executive_summary": "The board should approve immediate next actions with clear owners.",
            },
        )
        validation = ValidationResult(is_valid=True, issues=[], claims=[], validated_spec=spec)

        gated = _apply_post_generation_quality_gate(plan, spec, validation)

        self.assertFalse(gated.is_valid)
        self.assertTrue(any("role-title mismatch" in issue for issue in gated.issues))

    def test_visual_planner_role_overrides_for_golden_roles(self):
        cases = [
            ("Business Benefits", "Benefits Stack", "IG-14"),
            ("AI Use Cases", "Use Case Portfolio", "CL-02"),
            ("Implementation Risks", "Risk Matrix", "IG-12"),
            ("Next Steps / Decisions", "Action Register", "IG-15"),
        ]
        for index, (role, visualization, expected) in enumerate(cases, start=1):
            plan = SlidePlan(
                slide_number=index,
                slide_role=role,
                purpose=f"Communicate {role}.",
                required_inputs=[],
                dependencies=[],
                visualization_type=visualization,
            )
            spec = SlideSpec(slide_type="operating_model", raw_spec={"title": role, "subtitle": "x"})

            selection = plan_visual_pattern(plan, spec)

            self.assertEqual(selection.pattern_id, expected)

    def test_risk_matrix_preserves_quadrants(self):
        raw = {"metadata": {}}
        payload = {
            "cells": [
                {"value": "Adoption risk", "quadrant": {"impact": "Critical", "likelihood": "High"}},
                {"value": "Data risk", "impact": "Medium", "likelihood": "Low"},
            ]
        }

        shaped = _apply_visual_pattern_shape(raw, payload, "IG-04")

        self.assertEqual(shaped["cells"][0]["quadrant"]["impact"], "High")
        self.assertEqual(shaped["cells"][1]["quadrant"]["likelihood"], "Low")

    def test_non_asset_content_title_is_locked_to_slide_plan(self):
        intent = IntentResult(slide_type="operating_model", raw_title="", raw_content="")
        context = EnterpriseContext(company="Microsoft", industry="Technology", business_function="Procurement")
        process = ProcessResult(
            process_name="Procure-to-Pay",
            process_family="Procurement",
            confidence=0.9,
            reasoning="test",
            stages=[],
        )
        plan = SlidePlan(
            slide_number=9,
            slide_role="Next Steps / Decisions",
            purpose="Clarify decisions, owners, and timing.",
            required_inputs=[],
            dependencies=[],
            visualization_type="Board Decisions",
        )

        raw = _to_renderer_ready_spec(
            {"title": "AI Procurement Transformation Executive Summary", "executive_summary": "Approve the pilot. Owners act in Q1."},
            intent,
            context,
            process,
            slide_plan=plan,
            visual_pattern_selection=VisualPatternSelection(
                pattern_id="CL-06",
                category="creative_listing",
                confidence=0.9,
                reasoning="test",
            ),
        )

        self.assertEqual(raw["title"], "Next Steps / Decisions")


if __name__ == "__main__":
    unittest.main()

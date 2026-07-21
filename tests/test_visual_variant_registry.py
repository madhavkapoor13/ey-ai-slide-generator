import unittest

from backend.presentation_assets.visual_variant_registry import resolve_variant_for_slide
from backend.modules.presentation_planner import _canonical_role_for_text
from schemas.presentation import SlidePlan
from schemas.visual import VisualBrief


class VisualVariantRegistryTests(unittest.TestCase):
    def test_investment_terms_resolve_to_investment_case_asset(self):
        plan = SlidePlan(
            slide_number=1,
            slide_role="ROI and Payback Summary",
            purpose="Summarize the budget, economics, and value case for approval.",
            required_inputs=[],
            dependencies=[],
            visualization_type="Investment summary",
        )
        brief = VisualBrief(
            message_type="investment_case",
            information_shape="business_case",
            content_units=4,
            audience="board",
            density="balanced",
        )

        selection = resolve_variant_for_slide(plan, brief, require_certified=True)

        self.assertIsNotNone(selection)
        self.assertEqual(selection.asset_id, "INVESTMENT-CASE-SUMMARY-001")

    def test_value_case_topic_is_not_canonicalized_as_benefits(self):
        self.assertEqual(_canonical_role_for_text("value case and ROI"), "investment case")

    def test_value_realization_roadmap_resolves_to_value_roadmap_asset(self):
        plan = SlidePlan(
            slide_number=1,
            slide_role="Value Realization Roadmap",
            purpose="Show four benefit pools, time-phased value capture, owners, milestones, and takeaway.",
            required_inputs=[],
            dependencies=[],
            visualization_type="Value Realization Roadmap",
        )
        brief = VisualBrief(
            message_type="implementation_roadmap",
            information_shape="benefit_timeline",
            content_units=4,
            audience="board",
            density="balanced",
        )

        selection = resolve_variant_for_slide(plan, brief, require_certified=True)

        self.assertIsNotNone(selection)
        self.assertEqual(selection.asset_id, "VALUE-REALIZATION-ROADMAP-001")

    def test_value_realization_topic_is_not_canonicalized_as_benefits(self):
        self.assertEqual(
            _canonical_role_for_text("Value Realization Roadmap with benefit pools"),
            "value realization roadmap",
        )

    def test_kpi_scorecard_table_resolves_to_scorecard_asset(self):
        plan = SlidePlan(
            slide_number=1,
            slide_role="KPI Scorecard Table",
            purpose="Include priority KPIs, current baseline, target, owner, reporting cadence, and management summary.",
            required_inputs=[],
            dependencies=[],
            visualization_type="KPI Scorecard Table",
        )
        brief = VisualBrief(
            message_type="kpi_scorecard",
            information_shape="scorecard_table",
            content_units=6,
            audience="audit committee",
            density="dense",
        )

        selection = resolve_variant_for_slide(plan, brief, require_certified=True)

        self.assertIsNotNone(selection)
        self.assertEqual(selection.asset_id, "KPI-SCORECARD-TABLE-001")

    def test_kpi_scorecard_topic_is_not_canonicalized_as_generic_kpis(self):
        self.assertEqual(
            _canonical_role_for_text("KPI Scorecard Table with baseline and owner"),
            "kpi scorecard table",
        )

    def test_risk_register_resolves_to_risk_register_asset(self):
        plan = SlidePlan(
            slide_number=1,
            slide_role="Risk Register",
            purpose="Include seven implementation risks with likelihood, impact, mitigation, owner, status, and summary counts.",
            required_inputs=[],
            dependencies=[],
            visualization_type="Risk Register",
        )
        brief = VisualBrief(
            message_type="risk_register",
            information_shape="risk_table",
            content_units=7,
            audience="board risk committee",
            density="dense",
        )

        selection = resolve_variant_for_slide(plan, brief, require_certified=True)

        self.assertIsNotNone(selection)
        self.assertEqual(selection.asset_id, "RISK-REGISTER-7ITEM-001")

    def test_risk_register_topic_is_not_canonicalized_as_generic_risks(self):
        self.assertEqual(
            _canonical_role_for_text("Risk Register with mitigation owner and status"),
            "risk register",
        )

    def test_current_future_comparison_resolves_to_comparison_asset(self):
        plan = SlidePlan(
            slide_number=1,
            slide_role="Current State vs Future State Comparison",
            purpose="Show five transformation shifts from current ways of working to the future operating model.",
            required_inputs=[],
            dependencies=[],
            visualization_type="Current State vs Future State Comparison",
        )
        brief = VisualBrief(
            message_type="comparison",
            information_shape="comparison",
            content_units=5,
            audience="executive committee",
            density="balanced",
        )

        selection = resolve_variant_for_slide(plan, brief, require_certified=True)

        self.assertIsNotNone(selection)
        self.assertEqual(selection.asset_id, "CURRENT-FUTURE-COMPARISON-5SHIFT-001")

    def test_current_future_topic_is_not_canonicalized_as_current_state(self):
        self.assertEqual(
            _canonical_role_for_text("Current State vs Future State Comparison"),
            "current state vs future state",
        )

    def test_six_step_current_process_resolves_to_six_step_asset(self):
        plan = SlidePlan(
            slide_number=1,
            slide_role="Current State Process",
            purpose="Show a current process with activities, pain points, and overall business impact.",
            required_inputs=[],
            dependencies=[],
            visualization_type="Process Flow",
        )
        brief = VisualBrief(
            message_type="process_flow",
            information_shape="sequence",
            content_units=6,
            audience="board",
            density="dense",
        )

        selection = resolve_variant_for_slide(plan, brief, require_certified=True)

        self.assertIsNotNone(selection)
        self.assertEqual(selection.asset_id, "CURRENT-STATE-PROCESS-6STEP-001")

    def test_dark_section_divider_resolves_to_dark_divider_asset(self):
        plan = SlidePlan(
            slide_number=1,
            slide_role="Section Divider",
            purpose="Introduce the requested section using a dark section divider slide.",
            required_inputs=[],
            dependencies=[],
            visualization_type="Dark Section Divider",
        )
        brief = VisualBrief(
            message_type="section_divider",
            information_shape="section_break",
            content_units=1,
            audience="board",
            density="sparse",
        )

        selection = resolve_variant_for_slide(plan, brief, require_certified=True)

        self.assertIsNotNone(selection)
        self.assertEqual(selection.asset_id, "SECTION-DIVIDER-DARK-001")

    def test_next_steps_section_divider_resolves_to_standard_divider_asset(self):
        plan = SlidePlan(
            slide_number=1,
            slide_role="Section Divider",
            purpose="Introduce the requested section using a section divider slide.",
            required_inputs=[],
            dependencies=[],
            visualization_type="Section Divider",
        )
        brief = VisualBrief(
            message_type="section_divider",
            information_shape="section_break",
            content_units=1,
            audience="board",
            density="sparse",
        )

        selection = resolve_variant_for_slide(plan, brief, require_certified=True)

        self.assertIsNotNone(selection)
        self.assertEqual(selection.asset_id, "SECTION-NEXT-STEPS-001")


if __name__ == "__main__":
    unittest.main()

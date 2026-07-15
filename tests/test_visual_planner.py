import unittest

from backend.modules.visual_planner import (
    load_pattern_registry,
    plan_visual_pattern,
    score_pattern,
)
from schemas.presentation import SlidePlan
from schemas.slide_spec import SlideSpec
from schemas.visual import VisualPatternSelection


def _slide_plan(
    slide_role: str,
    purpose: str,
    visualization_type: str,
) -> SlidePlan:
    return SlidePlan(
        slide_number=1,
        slide_role=slide_role,
        purpose=purpose,
        required_inputs=[],
        dependencies=[],
        visualization_type=visualization_type,
    )


def _slide_spec(raw_spec: dict) -> SlideSpec:
    return SlideSpec(
        slide_type="operating_model",
        raw_spec=raw_spec,
        version="2.0",
        generated_by="test",
    )


class VisualPlannerTests(unittest.TestCase):

    def test_executive_summary_selects_executive_summary_cards(self):
        plan = _slide_plan(
            slide_role="Executive Summary",
            purpose="Summarize the key takeaways for leadership",
            visualization_type="Executive Summary",
        )
        spec = _slide_spec({"cards": [
            {"title": "Cost reduction", "description": "..."},
            {"title": "Risk mitigation", "description": "..."},
            {"title": "Revenue growth", "description": "..."},
        ]})

        result = plan_visual_pattern(plan, spec)

        self.assertIsInstance(result, VisualPatternSelection)
        self.assertEqual(result.pattern_id, "CL-06")
        self.assertEqual(result.category, "creative_listing")
        self.assertGreater(result.confidence, 0.6)
        self.assertIn("Executive Summary Cards", result.reasoning)

    def test_business_benefits_selects_benefits_list(self):
        plan = _slide_plan(
            slide_role="Business Benefits",
            purpose="Outline the key benefits of the transformation",
            visualization_type="Benefits List",
        )
        spec = _slide_spec({"factors": [
            {"label": "Efficiency", "description": "..."},
            {"label": "Compliance", "description": "..."},
            {"label": "Agility", "description": "..."},
            {"label": "Visibility", "description": "..."},
        ]})

        result = plan_visual_pattern(plan, spec)

        self.assertEqual(result.pattern_id, "IG-14")
        self.assertEqual(result.category, "infographic")

    def test_current_vs_future_selects_comparison_cards(self):
        plan = _slide_plan(
            slide_role="Current vs Future",
            purpose="Compare the current state with the future state",
            visualization_type="Comparison",
        )
        spec = _slide_spec({"columns": [
            {"label": "Current", "items": [{"title": "Manual"}, {"title": "Siloed"}]},
            {"label": "Future", "items": [{"title": "Automated"}, {"title": "Integrated"}]},
        ]})

        result = plan_visual_pattern(plan, spec)

        self.assertEqual(result.pattern_id, "CL-04")
        self.assertEqual(result.category, "creative_listing")

    def test_process_overview_selects_process_flow(self):
        plan = _slide_plan(
            slide_role="Process Overview",
            purpose="Show the steps in the process",
            visualization_type="Process Flow",
        )
        spec = _slide_spec({"steps": [
            {"id": "1", "label": "Receive"},
            {"id": "2", "label": "Validate"},
            {"id": "3", "label": "Approve"},
            {"id": "4", "label": "Pay"},
        ]})

        result = plan_visual_pattern(plan, spec)

        self.assertEqual(result.pattern_id, "IG-03")
        self.assertEqual(result.category, "infographic")

    def test_implementation_roadmap_selects_roadmap(self):
        plan = _slide_plan(
            slide_role="Implementation Roadmap",
            purpose="Lay out the implementation phases and deliverables",
            visualization_type="Roadmap",
        )
        spec = _slide_spec({"phases": [
            {"name": "Discovery", "activities": ["Assess"]},
            {"name": "Design", "activities": [" architect"]},
            {"name": "Deploy", "activities": ["Roll out"]},
        ]})

        result = plan_visual_pattern(plan, spec)

        self.assertEqual(result.pattern_id, "IG-02")
        self.assertEqual(result.category, "infographic")

    def test_board_procurement_roles_map_to_distinct_visual_families(self):
        cases = [
            ("Current Procurement Process", "Process Flow", "IG-03"),
            ("Future-State Operating Model", "Operating Model", "IG-06"),
            ("AI Use Cases", "Use Case Portfolio", "CL-02"),
            ("Business Benefits", "Benefits Stack", "IG-14"),
            ("Implementation Roadmap", "Roadmap", "IG-02"),
            ("KPIs for Success", "KPI Dashboard", "CL-03"),
            ("Implementation Risks", "Risk Matrix", "IG-12"),
            ("Next Steps", "Action Register", "IG-15"),
        ]

        for role, visualization, expected_pattern in cases:
            with self.subTest(role=role):
                plan = _slide_plan(
                    slide_role=role,
                    purpose=f"Communicate {role.lower()} for the board.",
                    visualization_type=visualization,
                )
                spec = _slide_spec({"title": role, "subtitle": "Test"})

                result = plan_visual_pattern(plan, spec)

                self.assertEqual(result.pattern_id, expected_pattern)

    def test_transformation_journey_selects_journey(self):
        plan = _slide_plan(
            slide_role="Transformation Journey",
            purpose="Describe the customer journey across touchpoints",
            visualization_type="Journey",
        )
        spec = _slide_spec({"stages": [
            {"name": "Aware", "touchpoints": ["Campaign"]},
            {"name": "Engage", "touchpoints": ["Workshop"]},
            {"name": "Adopt", "touchpoints": ["Training"]},
            {"name": "Optimize", "touchpoints": ["Review"]},
        ]})

        result = plan_visual_pattern(plan, spec)

        self.assertEqual(result.pattern_id, "IG-05")
        self.assertEqual(result.category, "infographic")

    def test_unknown_slide_falls_back_gracefully(self):
        plan = _slide_plan(
            slide_role="Miscellaneous",
            purpose="Some content that does not match any pattern",
            visualization_type="Unknown",
        )
        spec = _slide_spec({"unstructured": "text"})

        result = plan_visual_pattern(plan, spec)

        self.assertEqual(result.pattern_id, "CL-06")
        self.assertEqual(result.category, "creative_listing")
        self.assertEqual(result.confidence, 0.5)
        self.assertIn("No strong visual pattern match", result.reasoning)

    def test_registry_loads_all_patterns(self):
        registry = load_pattern_registry()

        self.assertIn("CL-01", registry)
        self.assertIn("CL-08", registry)
        self.assertIn("IG-01", registry)
        self.assertIn("IG-11", registry)
        self.assertEqual(registry["CL-01"]["category"], "creative_listing")
        self.assertEqual(registry["IG-03"]["category"], "infographic")
        self.assertGreaterEqual(len(registry), 19)

    def test_confidence_scoring(self):
        registry = load_pattern_registry()
        plan = _slide_plan(
            slide_role="KPI Dashboard",
            purpose="Display key performance metrics",
            visualization_type="KPI Cards",
        )
        spec = _slide_spec({"kpis": [
            {"label": "Cost", "value": "12%"},
            {"label": "Quality", "value": "98%"},
            {"label": "Speed", "value": "5 days"},
        ]})

        pattern = registry["CL-03"]
        score, reasons = score_pattern(
            pattern,
            plan.slide_role,
            plan.purpose,
            plan.visualization_type,
            spec.raw_spec,
        )

        # Role, purpose, visualization type, content key, and count all match.
        self.assertAlmostEqual(score, 1.0, places=2)
        self.assertEqual(len(reasons), 5)

    def test_tie_breaking_by_pattern_id(self):
        """
        When two patterns score equally, the lower pattern_id must win.

        This scenario deliberately gives CL-01 (Four Insight Cards) and
        CL-06 (Executive Summary Cards) the same matched signals, forcing a
        tie that should be broken by pattern_id order.
        """
        plan = _slide_plan(
            slide_role="Recommendations",
            purpose="List the key recommendations",
            visualization_type="Cards",
        )
        spec = _slide_spec({
            "cards": [
                {"title": "A", "description": "..."},
                {"title": "B", "description": "..."},
                {"title": "C", "description": "..."},
                {"title": "D", "description": "..."},
            ],
        })

        result = plan_visual_pattern(plan, spec)

        # Both CL-01 and CL-06 match role, purpose, content key, and item
        # count. The lower pattern ID (CL-01) must be selected.
        self.assertEqual(result.pattern_id, "CL-01")


if __name__ == "__main__":
    unittest.main()

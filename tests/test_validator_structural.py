from __future__ import annotations

import unittest

from backend.modules.validator import validate_content
from schemas.slide_spec import SlideSpec


def _spec(raw_spec: dict, pattern: str | None = None) -> SlideSpec:
    metadata = raw_spec.setdefault("metadata", {})
    if pattern is not None:
        metadata["visual_pattern"] = pattern
    return SlideSpec(slide_type="operating_model", raw_spec=raw_spec, version="2.0")


def _base_raw_spec(**overrides) -> dict:
    raw = {
        "title": "Current State",
        "subtitle": "Toyota Procurement Operating Model",
        "description": "Current-state operating model.",
        "executive_summary": "Summary one. Summary two.",
    }
    raw.update(overrides)
    return raw


class ValidatorStructuralTests(unittest.TestCase):
    def test_valid_base_spec_without_visual_pattern(self):
        result = validate_content(_spec(_base_raw_spec()))
        self.assertTrue(result.is_valid)
        self.assertEqual(result.issues, [])
        self.assertIsNotNone(result.validated_spec)

    def test_missing_title_fails(self):
        raw = _base_raw_spec()
        raw["title"] = ""
        result = validate_content(_spec(raw))
        self.assertFalse(result.is_valid)
        self.assertIn("title is missing or empty.", result.issues)
        self.assertIsNone(result.validated_spec)

    def test_missing_executive_summary_fails(self):
        raw = _base_raw_spec()
        raw["executive_summary"] = ""
        result = validate_content(_spec(raw))
        self.assertFalse(result.is_valid)
        self.assertIn("executive_summary is missing or empty.", result.issues)

    def test_unsupported_metric_literal_fails(self):
        raw = _base_raw_spec()
        raw["executive_summary"] = "unsupported metric placeholder."
        result = validate_content(_spec(raw))
        self.assertFalse(result.is_valid)
        self.assertTrue(any("unsupported metric" in issue for issue in result.issues))

    def test_placeholder_leakage_literal_text_fails(self):
        raw = _base_raw_spec(cards=[{"title": "AI sourcing", "description": "Text"}])
        result = validate_content(_spec(raw, "CL-01"))
        self.assertFalse(result.is_valid)
        self.assertTrue(any("placeholder leakage" in issue for issue in result.issues))

    def test_placeholder_leakage_item_label_fails(self):
        raw = _base_raw_spec(steps=[{"label": "Item 1"}, {"label": "Sourcing"}])
        result = validate_content(_spec(raw, "IG-03"))
        self.assertFalse(result.is_valid)
        self.assertTrue(any("Item 1" in issue for issue in result.issues))

    def test_placeholder_leakage_step_label_fails(self):
        raw = _base_raw_spec(phases=[{"name": "Step 1", "duration": "Q1", "deliverables": ["Baseline"]}])
        result = validate_content(_spec(raw, "IG-02"))
        self.assertFalse(result.is_valid)
        self.assertTrue(any("Step 1" in issue for issue in result.issues))

    # ── CL-01 ──────────────────────────────────────────────────────────────
    def test_cl01_four_cards_pass(self):
        raw = _base_raw_spec(cards=[{"title": f"C{i}", "description": "d"} for i in range(4)])
        result = validate_content(_spec(raw, "CL-01"))
        self.assertTrue(result.is_valid)

    def test_cl01_three_cards_pass(self):
        # Adaptive layouts: fewer than canonical 4 cards is allowed.
        raw = _base_raw_spec(cards=[{"title": f"C{i}", "description": "d"} for i in range(3)])
        result = validate_content(_spec(raw, "CL-01"))
        self.assertTrue(result.is_valid)

    def test_cl01_empty_card_title_fails(self):
        raw = _base_raw_spec(
            cards=[
                {"title": "Good", "description": "d"},
                {"title": "", "description": "d"},
                {"title": "Also Good", "description": "d"},
            ]
        )
        result = validate_content(_spec(raw, "CL-01"))
        self.assertFalse(result.is_valid)
        self.assertTrue(any("empty title" in issue for issue in result.issues))

    def test_cl01_missing_cards_field_fails(self):
        raw = _base_raw_spec()
        result = validate_content(_spec(raw, "CL-01"))
        self.assertFalse(result.is_valid)
        self.assertTrue(any("'cards'" in issue for issue in result.issues))

    # ── CL-02 / CL-06 ──────────────────────────────────────────────────────
    def test_cl02_three_cards_pass(self):
        raw = _base_raw_spec(cards=[{"title": f"C{i}", "description": "d"} for i in range(3)])
        result = validate_content(_spec(raw, "CL-02"))
        self.assertTrue(result.is_valid)

    def test_cl02_two_cards_pass(self):
        # Adaptive layouts: fewer than canonical 3 cards is allowed.
        raw = _base_raw_spec(cards=[{"title": f"C{i}", "description": "d"} for i in range(2)])
        result = validate_content(_spec(raw, "CL-02"))
        self.assertTrue(result.is_valid)

    def test_cl06_three_cards_pass(self):
        raw = _base_raw_spec(cards=[{"title": f"C{i}", "description": "d"} for i in range(3)])
        result = validate_content(_spec(raw, "CL-06"))
        self.assertTrue(result.is_valid)

    # ── CL-03 ──────────────────────────────────────────────────────────────
    def test_cl03_three_kpis_with_values_pass(self):
        raw = _base_raw_spec(
            kpis=[{"label": f"K{i}", "value": str(i * 100), "trend": "up", "description": "d"} for i in range(3)]
        )
        result = validate_content(_spec(raw, "CL-03"))
        self.assertTrue(result.is_valid)

    def test_cl03_empty_kpi_value_fails(self):
        raw = _base_raw_spec(
            kpis=[
                {"label": "K1", "value": "100", "trend": "", "description": ""},
                {"label": "K2", "value": "", "trend": "", "description": ""},
                {"label": "K3", "value": "300", "trend": "", "description": ""},
            ]
        )
        result = validate_content(_spec(raw, "CL-03"))
        self.assertFalse(result.is_valid)
        self.assertTrue(any("empty value" in issue for issue in result.issues))

    def test_cl03_two_kpis_pass(self):
        # Adaptive layouts: fewer than canonical 3 KPIs is allowed.
        raw = _base_raw_spec(
            kpis=[{"label": f"K{i}", "value": "1", "trend": "", "description": ""} for i in range(2)]
        )
        result = validate_content(_spec(raw, "CL-03"))
        self.assertTrue(result.is_valid)

    def test_cl03_empty_kpi_label_fails(self):
        raw = _base_raw_spec(
            kpis=[
                {"label": "", "value": "100", "trend": "", "description": ""},
                {"label": "K2", "value": "200", "trend": "", "description": ""},
                {"label": "K3", "value": "300", "trend": "", "description": ""},
            ]
        )
        result = validate_content(_spec(raw, "CL-03"))
        self.assertFalse(result.is_valid)
        self.assertTrue(any("empty label" in issue for issue in result.issues))

    # ── IG-04 (matrix) ────────────────────────────────────────────────────
    def test_ig04_risk_cells_valid_quadrant_pass(self):
        raw = _base_raw_spec(
            cells=[
                {"value": "Risk A", "quadrant": {"impact": "High", "likelihood": "Medium"}},
                {"value": "Risk B", "quadrant": {"impact": "Low", "likelihood": "High"}},
            ],
        )
        raw.setdefault("metadata", {})["slide_role"] = "Implementation Risks"
        result = validate_content(_spec(raw, "IG-04"))
        self.assertTrue(result.is_valid)

    def test_ig04_risk_cells_invalid_quadrant_fails(self):
        raw = _base_raw_spec(
            cells=[
                {"value": "Risk A", "quadrant": {"impact": "Critical", "likelihood": "Medium"}},
                {"value": "Risk B", "quadrant": {"impact": "Low", "likelihood": "High"}},
            ],
        )
        raw.setdefault("metadata", {})["slide_role"] = "Implementation Risks"
        result = validate_content(_spec(raw, "IG-04"))
        self.assertFalse(result.is_valid)
        self.assertTrue(any("invalid impact" in issue for issue in result.issues))

    def test_ig04_risk_cells_missing_quadrant_fails(self):
        raw = _base_raw_spec(
            cells=[
                {"value": "Risk A"},
                {"value": "Risk B"},
            ],
        )
        raw.setdefault("metadata", {})["slide_role"] = "Implementation Risks"
        result = validate_content(_spec(raw, "IG-04"))
        self.assertFalse(result.is_valid)
        self.assertTrue(any("quadrant" in issue for issue in result.issues))

    # ── Infographic counts ───────────────────────────────────────────────
    def test_ig03_missing_steps_fails(self):
        raw = _base_raw_spec()
        result = validate_content(_spec(raw, "IG-03"))
        self.assertFalse(result.is_valid)
        self.assertTrue(any("'steps'" in issue for issue in result.issues))

    def test_ig01_empty_events_fails(self):
        raw = _base_raw_spec(events=[])
        result = validate_content(_spec(raw, "IG-01"))
        self.assertFalse(result.is_valid)
        self.assertTrue(any("'events' is empty" in issue for issue in result.issues))

    def test_ig03_empty_step_label_fails(self):
        raw = _base_raw_spec(steps=[{"label": "Step 1"}, {"label": ""}, {"label": "Step 3"}])
        result = validate_content(_spec(raw, "IG-03"))
        self.assertFalse(result.is_valid)
        self.assertTrue(any("empty label" in issue for issue in result.issues))


if __name__ == "__main__":
    unittest.main()

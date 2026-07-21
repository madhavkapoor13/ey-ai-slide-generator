import unittest
from unittest.mock import MagicMock, patch

from backend.modules.content_generator import (
    generate_slide_content,
    _repair_current_future_comparison,
    _repair_current_process_6step,
    _repair_governance_model_labels,
    _repair_investment_case_labels,
    _repair_kpi_scorecard_table,
    _repair_risk_register,
    _repair_title_so_what,
    _repair_value_realization_roadmap,
)
from backend.modules.consulting_language import validate_consulting_language
from backend.presentation_assets import asset_registry
from backend.presentation_assets.text_fit import check_text_fit
from backend.modules.deck_executor import execute_deck
from backend.modules.validator import validate_content
from schemas.context import EnterpriseContext
from schemas.intent import IntentResult
from schemas.presentation import SlidePlan
from schemas.presentation import DeckSpec
from schemas.presentation_asset import AssetManifest, AssetSelection
from schemas.process import ProcessResult
from schemas.slide_spec import SlideSpec
from schemas.validation import ValidationResult
from schemas.visual import VisualPatternSelection
from tests._asset_factory import build_roadmap_manifest


def _intent() -> IntentResult:
    return IntentResult(
        company="TestCo",
        industry="Technology",
        business_function="Operations",
        slide_type="Roadmap",
    )


def _context() -> EnterpriseContext:
    return EnterpriseContext(
        company="TestCo",
        industry="Technology",
        business_function="Operations",
    )


def _process() -> ProcessResult:
    return ProcessResult(
        process_name="Order-to-Cash",
        process_family="Operations",
        confidence=0.9,
        reasoning="test",
        stages=["Intake", "Process", "Ship", "Bill", "Collect"],
    )


def _slide_plan() -> SlidePlan:
    return SlidePlan(
        slide_number=3,
        slide_role="Roadmap",
        purpose="Three-phase transformation roadmap.",
        required_inputs=[],
        dependencies=[],
        visualization_type="Roadmap",
    )


def _visual_selection() -> VisualPatternSelection:
    return VisualPatternSelection(
        pattern_id="IG-02",
        category="infographic",
        confidence=0.85,
        reasoning="Roadmap fits IG-02.",
    )


class ManifestContentGeneratorTests(unittest.TestCase):
    def test_governance_repair_backfills_optional_glance_fields(self):
        manifest = asset_registry.get("GOVERNANCE-MODEL-001")
        self.assertIsNotNone(manifest)

        repaired = _repair_governance_model_labels(
            {
                "title": "Governance model ensures clear decision rights",
                "steering_responsibility_1": "Review project milestones and approve strategic direction across the program",
            },
            manifest,
        )

        self.assertEqual(repaired["steering_responsibility_1"], "Set priorities")
        self.assertEqual(repaired["forum_name"], ["SteerCo", "PMO", "Workstreams"])
        self.assertEqual(repaired["forum_cadence"], ["Monthly", "Weekly", "Biweekly"])
        self.assertEqual(repaired["decision_right_label"], ["Recommend", "Approve", "Escalate"])
        self.assertEqual(repaired["decision_right_description"], ["Frame options", "Make final call", "Raise key risks"])

    def test_investment_repair_compacts_overflowing_fields(self):
        manifest = asset_registry.get("INVESTMENT-CASE-SUMMARY-001")
        self.assertIsNotNone(manifest)

        repaired = _repair_investment_case_labels(
            {
                "investment_scope": "Covers technology upgrades, training, and process reengineering",
                "value_drivers": "Annual value at steady state from automation, reduced manual errors, and faster decisions",
                "phased_approach": "Phased rollout in three phases: Assessment, Development, and Scale",
                "investment_component_label": ["Item 1", "Item 2", "Item 3", "Item 4"],
                "value_component_label": ["Item 1", "Item 2", "Item 3"],
                "bridge_description": [
                    "Item 1",
                    "Item 2",
                    "Item 3",
                    "Item 4",
                ],
                "recommendation": "Approve the $5M investment to realize significant operational improvements and ROI.",
            },
            manifest,
        )

        self.assertEqual(repaired["investment_scope"], "Phase 1 funding")
        self.assertEqual(repaired["value_drivers"], "Positive")
        self.assertEqual(repaired["timing_value"], "12")
        self.assertEqual(repaired["payback_value"], "18")
        self.assertEqual(repaired["value_investment_value"], "3x")
        self.assertEqual(repaired["phased_approach"], "Pilot, automate, scale")
        self.assertEqual(repaired["investment_component_label"], ["Technology", "Training", "Process redesign", "Contingency"])
        self.assertEqual(repaired["value_component_label"], ["Cost takeout", "Productivity", "Control uplift"])
        self.assertEqual(
            repaired["bridge_description"],
            [
                "Approve initial funding",
                "Build priority capabilities",
                "Validate benefits in pilot",
                "Scale proven use cases",
            ],
        )
        self.assertEqual(repaired["recommendation"], "Approve Phase 1 funding and review benefits monthly.")

    def test_investment_title_repair_does_not_become_case_for_change(self):
        repaired = _repair_title_so_what(
            {"title": "Case for change centers on resilience, speed, and control"},
            SlidePlan(
                slide_number=1,
                slide_role="Investment Case",
                purpose="Summarize required investment and payback.",
                required_inputs=[],
                dependencies=[],
                visualization_type="Investment Case",
            ),
        )

        self.assertEqual(repaired["title"], "Investment case supports disciplined AI scale-up")

    def test_value_realization_roadmap_repair_populates_bottom_milestones(self):
        manifest = asset_registry.get("VALUE-REALIZATION-ROADMAP-001")
        self.assertIsNotNone(manifest)

        repaired = _repair_value_realization_roadmap(
            {
                "milestone_value": ["Item 1"],
                "milestone_description": ["Item 1", "", "Full value realized through scaled adoption"],
                "total_value": "",
            },
            manifest,
        )

        self.assertEqual(repaired["milestone_value"], ["10%", "45%", "100%"])
        self.assertEqual(
            repaired["milestone_description"],
            ["Quick wins captured", "Automation benefits ramp", "Full value at scale"],
        )
        self.assertEqual(repaired["total_value"], "$50M total projected value")

    def test_current_future_comparison_repair_locks_comparison_language(self):
        manifest = asset_registry.get("CURRENT-FUTURE-COMPARISON-5SHIFT-001")
        self.assertIsNotNone(manifest)

        repaired = _repair_current_future_comparison(
            {
                "title": "Future-state model enables accountable capabilities",
                "current_state": ["Item 1"],
            },
            manifest,
        )

        self.assertIn("Current-to-future shifts", repaired["title"])
        self.assertIn("from fragmented work to a future-ready", repaired["subtitle"])
        self.assertEqual(len(repaired["current_state"]), 5)
        self.assertEqual(len(repaired["future_state"]), 5)
        self.assertEqual(repaired["current_state"][0], "Local HR intake and routing")
        self.assertEqual(repaired["future_state"][0], "Digital front door with clear ownership")
        self.assertIn("reactive service delivery", repaired["takeaway"])

    def test_current_process_six_step_repair_populates_business_impact(self):
        manifest = asset_registry.get("CURRENT-STATE-PROCESS-6STEP-001")
        self.assertIsNotNone(manifest)

        repaired = _repair_current_process_6step({}, manifest)

        self.assertEqual(repaired["title"], "Current supply chain friction constrains growth")
        self.assertEqual(
            repaired["subtitle"],
            "Six process steps expose delays, exceptions and fragmented ownership",
        )
        self.assertIn("Business impact:", repaired["takeaway"])
        self.assertIn("service, cost and resilience", repaired["takeaway"])

    def test_kpi_scorecard_repair_populates_table_cells(self):
        manifest = asset_registry.get("KPI-SCORECARD-TABLE-001")
        self.assertIsNotNone(manifest)

        repaired = _repair_kpi_scorecard_table(
            {
                "kpi_name_1": "Item 1",
                "baseline_1": "Item 1",
            },
            manifest,
        )

        self.assertEqual(repaired["kpi_name_1"], "Close Cycle Time Days to close")
        self.assertEqual(repaired["baseline_1"], "8 days")
        self.assertEqual(repaired["owner_1"], "Controllership")
        self.assertEqual(repaired["kpi_name_7"], "AI Adoption % priority users active")
        self.assertEqual(repaired["on_track_description"], "Two KPIs meeting plan")

    def test_risk_register_repair_populates_rows_and_summary(self):
        manifest = asset_registry.get("RISK-REGISTER-7ITEM-001")
        self.assertIsNotNone(manifest)

        repaired = _repair_risk_register(
            {
                "risk_1_description": "Driver: fragmented data",
                "summary_count": [],
            },
            manifest,
        )

        self.assertEqual(repaired["title"], "Implementation risks require accountable mitigation before scale")
        self.assertIn("Seven priority risks", repaired["subtitle"])
        self.assertEqual(repaired["risk_id"][0], "R1")
        self.assertNotIn("Driver:", repaired["risk_description"][0])
        self.assertEqual(repaired["risk_owner"][6], "PMO")
        self.assertIn("review KPIs monthly", repaired["risk_mitigation"][6])
        self.assertEqual(repaired["summary_count"], ["3", "3", "1", "0"])
        self.assertEqual(repaired["summary_label"][0], "Critical / high")
        self.assertEqual(repaired["summary_description"][2], "Monitor through PMO")

    """Tests for Sprint D: manifest-aware content generation."""

    def setUp(self):
        self.manifest = build_roadmap_manifest(asset_id="TEST-ROADMAP-001")
        self.conformant_payload = {
            "title": "Roadmap",
            "subtitle": "TestCo Operations — Transformation Roadmap",
            "phase_label": ["Phase One", "Phase Two", "Phase Three"],
        }

    def test_manifest_path_returns_placeholder_keyed_spec(self):
        with patch(
            "backend.modules.content_generator._call_manifest_content_llm",
            return_value=self.conformant_payload,
        ):
            spec = generate_slide_content(
                _intent(),
                _context(),
                _process(),
                _slide_plan(),
                visual_pattern_selection=_visual_selection(),
                asset_id="TEST-ROADMAP-001",
                asset_manifest=self.manifest,
            )

        self.assertIsInstance(spec, SlideSpec)
        self.assertEqual(spec.asset_id, "TEST-ROADMAP-001")
        self.assertEqual(spec.visual_pattern_id, "IG-02")
        self.assertEqual(spec.visual_confidence, 0.85)
        self.assertEqual(set(spec.raw_spec.keys()), {"title", "subtitle", "phase_label"})

    def test_manifest_path_uses_llm_payload_when_conformant(self):
        with patch(
            "backend.modules.content_generator._call_manifest_content_llm",
            return_value=self.conformant_payload,
        ):
            spec = generate_slide_content(
                _intent(),
                _context(),
                _process(),
                _slide_plan(),
                visual_pattern_selection=_visual_selection(),
                asset_id="TEST-ROADMAP-001",
                asset_manifest=self.manifest,
            )

        self.assertEqual(
            spec.raw_spec["title"],
            "Implementation roadmap sequences pilot, scale, and governance",
        )
        self.assertEqual(spec.raw_spec["subtitle"], "TestCo Operations — Transformation Roadmap")
        self.assertEqual(spec.raw_spec["phase_label"], ["Phase One", "Phase Two", "Phase Three"])

    def test_manifest_path_preserves_insight_title_when_role_compatible(self):
        payload = dict(self.conformant_payload)
        payload["title"] = "Sequenced pilots reduce delivery risk before scaled rollout"
        with patch(
            "backend.modules.content_generator._call_manifest_content_llm",
            return_value=payload,
        ):
            spec = generate_slide_content(
                _intent(),
                _context(),
                _process(),
                _slide_plan(),
                visual_pattern_selection=_visual_selection(),
                asset_id="TEST-ROADMAP-001",
                asset_manifest=self.manifest,
            )

        self.assertEqual(
            spec.raw_spec["title"],
            "Sequenced pilots reduce delivery risk before scaled rollout",
        )

    def test_manifest_path_locks_title_only_on_role_drift(self):
        payload = dict(self.conformant_payload)
        payload["title"] = "AI Procurement Transformation Executive Summary"
        with patch(
            "backend.modules.content_generator._call_manifest_content_llm",
            return_value=payload,
        ):
            spec = generate_slide_content(
                _intent(),
                _context(),
                _process(),
                _slide_plan(),
                visual_pattern_selection=_visual_selection(),
                asset_id="TEST-ROADMAP-001",
                asset_manifest=self.manifest,
            )

        self.assertEqual(
            spec.raw_spec["title"],
            "Implementation roadmap sequences pilot, scale, and governance",
        )

    def test_current_process_title_is_repaired_to_board_level_so_what(self):
        plan = SlidePlan(
            slide_number=2,
            slide_role="Current Procurement Process",
            purpose="Explain current-state bottlenecks.",
            required_inputs=[],
            dependencies=[],
            visualization_type="Process",
        )
        payload = dict(self.conformant_payload)
        payload["title"] = "Current Procurement Process"
        with patch(
            "backend.modules.content_generator._call_manifest_content_llm",
            return_value=payload,
        ):
            spec = generate_slide_content(
                _intent(),
                _context(),
                _process(),
                plan,
                visual_pattern_selection=_visual_selection(),
                asset_id="TEST-ROADMAP-001",
                asset_manifest=self.manifest,
            )

        self.assertEqual(
            spec.raw_spec["title"],
            "Current process friction slows decisions and weakens control",
        )

    def test_role_specific_title_repair_prevents_generic_transformation_repeats(self):
        cases = [
            ("Case For Change", "Case for change centers on resilience, speed, and control"),
            ("Roadmap", "Implementation roadmap sequences pilot, scale, and governance"),
        ]
        for role, expected_title in cases:
            plan = SlidePlan(
                slide_number=3,
                slide_role=role,
                purpose=f"Communicate {role}.",
                required_inputs=[],
                dependencies=[],
                visualization_type="Roadmap",
            )
            payload = dict(self.conformant_payload)
            payload["title"] = "Transforming Toyota's Manufacturing Model for Enhanced Efficiency"
            with patch(
                "backend.modules.content_generator._call_manifest_content_llm",
                return_value=payload,
            ):
                spec = generate_slide_content(
                    _intent(),
                    _context(),
                    _process(),
                    plan,
                    visual_pattern_selection=_visual_selection(),
                    asset_id="TEST-ROADMAP-001",
                    asset_manifest=self.manifest,
                )

            self.assertEqual(spec.raw_spec["title"], expected_title)

    def test_manifest_path_repairs_generic_roadmap_phase_labels(self):
        payload = dict(self.conformant_payload)
        payload["phase_label"] = ["Phase 1", "Step 2", "Item 3"]
        with patch(
            "backend.modules.content_generator._call_manifest_content_llm",
            return_value=payload,
        ):
            spec = generate_slide_content(
                _intent(),
                _context(),
                _process(),
                _slide_plan(),
                visual_pattern_selection=_visual_selection(),
                asset_id="TEST-ROADMAP-001",
                asset_manifest=self.manifest,
            )

        self.assertEqual(spec.raw_spec["phase_label"], ["Diagnose", "Design", "Pilot"])

    def test_manifest_path_repairs_generic_ai_filler(self):
        payload = dict(self.conformant_payload)
        payload["subtitle"] = "Leverage AI to improve compliance"
        with patch(
            "backend.modules.content_generator._call_manifest_content_llm",
            return_value=payload,
        ):
            spec = generate_slide_content(
                _intent(),
                _context(),
                _process(),
                _slide_plan(),
                visual_pattern_selection=_visual_selection(),
                asset_id="TEST-ROADMAP-001",
                asset_manifest=self.manifest,
            )

        self.assertNotIn("Leverage AI", spec.raw_spec["subtitle"])
        self.assertIn("apply AI to procurement decisions", spec.raw_spec["subtitle"])

    def test_risk_repair_preserves_text_fit(self):
        manifest = asset_registry.get("RISK-ASSESSMENT-001")
        self.assertIsNotNone(manifest)
        plan = SlidePlan(
            slide_number=8,
            slide_role="Implementation Risks",
            purpose="Identify causes, impacts, mitigations, and owners.",
            required_inputs=[],
            dependencies=[],
            visualization_type="Risk Matrix",
        )
        payload = {
            "title": "Transformation Timeline",
            "header_findings": "Findings",
            "header_assessment": "Assessment",
            "header_confidence": "Confidence",
            "risk_title": ["Data risk", "Adoption risk", "Supplier risk", "Control risk"],
            "risk_description": ["Thin risk text"] * 4,
            "risk_assessment": ["Long assessment that would overflow badly"] * 4,
            "risk_confidence": ["Long confidence field that would overflow"] * 4,
        }
        with patch(
            "backend.modules.content_generator._call_manifest_content_llm",
            return_value=payload,
        ):
            spec = generate_slide_content(
                _intent(),
                _context(),
                _process(),
                plan,
                visual_pattern_selection=VisualPatternSelection(
                    pattern_id="IG-12",
                    category="infographic",
                    confidence=0.9,
                    reasoning="Risk asset.",
                ),
                asset_id=manifest.asset_id,
                asset_manifest=manifest,
        )

        self.assertTrue(check_text_fit(spec.raw_spec, manifest).passed)
        self.assertNotIn("Timeline", spec.raw_spec["title"])
        self.assertIn("risk", spec.raw_spec["title"].lower())
        joined = " ".join(spec.raw_spec["risk_description"]).lower()
        self.assertNotIn("response owner set", joined)

    def test_next_step_repair_preserves_text_fit(self):
        manifest = asset_registry.get("NEXTSTEPS-REGISTER-001")
        self.assertIsNotNone(manifest)
        plan = SlidePlan(
            slide_number=9,
            slide_role="Next Steps",
            purpose="Clarify decisions, owners, and timing.",
            required_inputs=[],
            dependencies=[],
            visualization_type="Action Register",
        )
        payload = {placeholder.id: "Needs work" for placeholder in manifest.placeholders}
        payload["title"] = "Next Steps"
        with patch(
            "backend.modules.content_generator._call_manifest_content_llm",
            return_value=payload,
        ):
            spec = generate_slide_content(
                _intent(),
                _context(),
                _process(),
                plan,
                visual_pattern_selection=VisualPatternSelection(
                    pattern_id="IG-15",
                    category="infographic",
                    confidence=0.9,
                    reasoning="Action register.",
                ),
                asset_id=manifest.asset_id,
                asset_manifest=manifest,
            )

        self.assertTrue(check_text_fit(spec.raw_spec, manifest).passed)
        self.assertEqual(spec.raw_spec["header_priority"], "Priority")
        self.assertEqual(spec.raw_spec["header_next_step"], "Action")
        self.assertIn("board", spec.raw_spec["title"].lower())

    def test_next_step_asset_repairs_contract_even_when_role_label_is_generic(self):
        manifest = asset_registry.get("NEXTSTEPS-REGISTER-001")
        self.assertIsNotNone(manifest)
        plan = SlidePlan(
            slide_number=9,
            slide_role="Opportunities",
            purpose="Clarify decisions, owners, and timing.",
            required_inputs=[],
            dependencies=[],
            visualization_type="Action Register",
        )
        payload = {placeholder.id: "Needs work" for placeholder in manifest.placeholders}
        payload["title"] = "Next Steps"
        with patch(
            "backend.modules.content_generator._call_manifest_content_llm",
            return_value=payload,
        ):
            spec = generate_slide_content(
                _intent(),
                _context(),
                _process(),
                plan,
                visual_pattern_selection=VisualPatternSelection(
                    pattern_id="IG-15",
                    category="infographic",
                    confidence=0.9,
                    reasoning="Action register.",
                ),
                asset_id=manifest.asset_id,
                asset_manifest=manifest,
            )

        language = validate_consulting_language(spec.raw_spec, "Action Register")

        self.assertTrue(check_text_fit(spec.raw_spec, manifest).passed)
        self.assertNotIn("next steps require a board decision.", language.issues)
        self.assertNotIn("next steps require timing.", language.issues)
        self.assertFalse(any("unsupported numeric claim: '30 days'" in warning for warning in language.warnings))

    def test_next_step_asset_backfills_optional_action_register_fields(self):
        manifest = asset_registry.get("NEXTSTEPS-REGISTER-001")
        self.assertIsNotNone(manifest)
        plan = SlidePlan(
            slide_number=9,
            slide_role="Next Steps",
            purpose="Clarify decisions, owners, and timing.",
            required_inputs=[],
            dependencies=[],
            visualization_type="Action Register",
        )
        payload = {
            placeholder.id: "Needs work"
            for placeholder in manifest.placeholders
            if placeholder.required
        }
        payload["title"] = "Next Steps"
        payload["row_1_instrument"] = "30 days"
        with patch(
            "backend.modules.content_generator._call_manifest_content_llm",
            return_value=payload,
        ):
            spec = generate_slide_content(
                _intent(),
                _context(),
                _process(),
                plan,
                visual_pattern_selection=VisualPatternSelection(
                    pattern_id="IG-15",
                    category="infographic",
                    confidence=0.9,
                    reasoning="Action register.",
                ),
                asset_id=manifest.asset_id,
                asset_manifest=manifest,
            )

        language = validate_consulting_language(spec.raw_spec, "Next Steps")

        self.assertEqual(spec.raw_spec["row_1_next_step"], "Approve controlled pilot launch")
        self.assertEqual(spec.raw_spec["row_1_when"], "30 days")
        self.assertEqual(spec.raw_spec["row_1_who"], "Procurement sponsor")
        self.assertNotIn("next steps require a board decision.", language.issues)
        self.assertNotIn("next steps require timing.", language.issues)
        self.assertFalse(any("unsupported numeric claim: '30 days'" in warning for warning in language.warnings))

    def test_decision_request_asset_replaces_placeholder_leakage_with_board_decisions(self):
        manifest = asset_registry.get("DECISION-REQUEST-3CARD-001")
        self.assertIsNotNone(manifest)
        plan = SlidePlan(
            slide_number=1,
            slide_role="Next Steps",
            purpose="Define three board decisions required to proceed.",
            required_inputs=[],
            dependencies=[],
            visualization_type="Board Decision Request",
        )
        payload = {placeholder.id: "Item 1" for placeholder in manifest.placeholders}
        payload["title"] = "Generation placeholder"
        with patch(
            "backend.modules.content_generator._call_manifest_content_llm",
            return_value=payload,
        ):
            spec = generate_slide_content(
                _intent(),
                _context(),
                _process(),
                plan,
                visual_pattern_selection=VisualPatternSelection(
                    pattern_id="IG-15",
                    category="infographic",
                    confidence=0.9,
                    reasoning="Board decision request.",
                ),
                asset_id=manifest.asset_id,
                asset_manifest=manifest,
            )

        language = validate_consulting_language(spec.raw_spec, "Next Steps")

        self.assertEqual(spec.raw_spec["decision_title"][0], "Approve pilot scope")
        self.assertEqual(spec.raw_spec["decision_1_request_detail"], "Approve pilot scope")
        self.assertEqual(spec.raw_spec["delay_1_title"], "Pilot delay")
        self.assertNotIn("next steps require an owner.", language.issues)
        self.assertNotIn("next steps require timing.", language.issues)

    def test_manifest_path_falls_back_when_missing_required_placeholder(self):
        bad_payload = {
            "subtitle": "Missing title",
            "phase_label": ["Phase One", "Phase Two", "Phase Three"],
        }
        with patch(
            "backend.modules.content_generator._call_manifest_content_llm",
            return_value=bad_payload,
        ):
            spec = generate_slide_content(
                _intent(),
                _context(),
                _process(),
                _slide_plan(),
                visual_pattern_selection=_visual_selection(),
                asset_id="TEST-ROADMAP-001",
                asset_manifest=self.manifest,
            )

        # Fallback supplies a title and preserves the subtitle from the LLM is not
        # guaranteed; we only assert the fallback is conformant and contains expected keys.
        self.assertIn("title", spec.raw_spec)
        self.assertTrue(spec.raw_spec["title"])
        self.assertIn("subtitle", spec.raw_spec)
        self.assertIn("phase_label", spec.raw_spec)
        self.assertIsInstance(spec.raw_spec["phase_label"], list)

    def test_manifest_path_falls_back_on_extra_keys(self):
        bad_payload = dict(self.conformant_payload)
        bad_payload["executive_summary"] = "Extra field not in manifest."
        with patch(
            "backend.modules.content_generator._call_manifest_content_llm",
            return_value=bad_payload,
        ):
            spec = generate_slide_content(
                _intent(),
                _context(),
                _process(),
                _slide_plan(),
                visual_pattern_selection=_visual_selection(),
                asset_id="TEST-ROADMAP-001",
                asset_manifest=self.manifest,
            )

        self.assertNotIn("executive_summary", spec.raw_spec)
        self.assertEqual(set(spec.raw_spec.keys()), {"title", "subtitle", "phase_label"})

    def test_manifest_path_uses_fallback_when_llm_returns_non_object(self):
        with patch(
            "backend.modules.content_generator._call_manifest_content_llm",
            return_value=["not", "a", "dict"],
        ):
            spec = generate_slide_content(
                _intent(),
                _context(),
                _process(),
                _slide_plan(),
                visual_pattern_selection=_visual_selection(),
                asset_id="TEST-ROADMAP-001",
                asset_manifest=self.manifest,
            )

        self.assertIn("title", spec.raw_spec)
        self.assertIn("subtitle", spec.raw_spec)
        self.assertIn("phase_label", spec.raw_spec)

    def test_legacy_path_unchanged_without_manifest(self):
        legacy_payload = {
            "title": "Roadmap",
            "subtitle": "TestCo Operations — Roadmap",
            "description": "Roadmap description.",
            "executive_summary": "Summary one. Summary two.",
            "phases": [
                {"name": "Phase 1", "duration": "Q1", "deliverables": ["Deliverable 1"]},
                {"name": "Phase 2", "duration": "Q2", "deliverables": ["Deliverable 2"]},
            ],
            "metadata": {"company": "TestCo", "industry": "Technology", "process": "Order-to-Cash"},
        }
        with patch(
            "backend.modules.content_generator._call_content_llm",
            return_value=legacy_payload,
        ):
            spec = generate_slide_content(
                _intent(),
                _context(),
                _process(),
                _slide_plan(),
                visual_pattern_selection=_visual_selection(),
            )

        self.assertIn("title", spec.raw_spec)
        self.assertIn("executive_summary", spec.raw_spec)
        self.assertIn("phases", spec.raw_spec)
        self.assertNotIn("phase_label", spec.raw_spec)


class ManifestValidatorTests(unittest.TestCase):
    """Tests for Sprint D: validator manifest-conformance path."""

    def setUp(self):
        self.manifest = build_roadmap_manifest(asset_id="TEST-ROADMAP-001")

    def _spec(self, raw_spec: dict) -> SlideSpec:
        return SlideSpec(
            slide_type="operating_model",
            raw_spec=raw_spec,
            version="2.0",
            asset_id="TEST-ROADMAP-001",
        )

    def test_validator_uses_manifest_conformance_when_asset_present(self):
        raw_spec = {
            "title": "Roadmap",
            "subtitle": "TestCo Operations — Roadmap",
            "phase_label": ["Phase One", "Phase Two", "Phase Three"],
        }
        with patch("backend.modules.validator.asset_registry.get", return_value=self.manifest):
            result = validate_content(self._spec(raw_spec))

        self.assertTrue(result.is_valid)
        self.assertEqual(result.issues, [])

    def test_validator_fails_when_required_placeholder_missing(self):
        raw_spec = {
            "subtitle": "TestCo Operations — Roadmap",
            "phase_label": ["Phase One", "Phase Two", "Phase Three"],
        }
        with patch("backend.modules.validator.asset_registry.get", return_value=self.manifest):
            result = validate_content(self._spec(raw_spec))

        self.assertFalse(result.is_valid)
        self.assertTrue(any("title" in issue for issue in result.issues))

    def test_validator_fails_when_density_exceeded(self):
        raw_spec = {
            "title": "Roadmap",
            "subtitle": "TestCo Operations — Roadmap",
            "phase_label": ["Phase One"] * 7,  # density_range [3, 6]
        }
        with patch("backend.modules.validator.asset_registry.get", return_value=self.manifest):
            result = validate_content(self._spec(raw_spec))

        self.assertFalse(result.is_valid)
        self.assertTrue(any("exceeds density" in issue for issue in result.issues))

    def test_validator_falls_back_to_legacy_checks_when_asset_not_found(self):
        raw_spec = {
            "title": "Roadmap",
            "subtitle": "TestCo Operations — Roadmap",
            "executive_summary": "Summary one. Summary two.",
            "phases": [
                {"name": "Diagnose", "duration": "Q1", "deliverables": ["A"]},
            ],
            "metadata": {"visual_pattern": "IG-02"},
        }
        with patch("backend.modules.validator.asset_registry.get", return_value=None):
            result = validate_content(
                SlideSpec(
                    slide_type="operating_model",
                    raw_spec=raw_spec,
                    version="2.0",
                    asset_id="UNKNOWN-ASSET-001",
                )
            )

        self.assertTrue(result.is_valid)


class DeckExecutorManifestTests(unittest.TestCase):
    """Tests that Deck Executor threads the selected manifest into Content Generator."""

    def test_deck_executor_passes_asset_manifest_to_content_generator(self):
        from backend.modules import deck_executor

        manifest = build_roadmap_manifest(asset_id="TEST-ROADMAP-001")
        selection = AssetSelection(
            asset_id="TEST-ROADMAP-001",
            family="roadmap",
            manifest=manifest,
            confidence=0.9,
            reasoning="test selection",
        )

        captured = {}

        def fake_generate(intent, context, process_result, slide_plan, **kwargs):
            captured.update(kwargs)
            return SlideSpec(
                slide_type="operating_model",
                raw_spec={
                    "title": slide_plan.slide_role,
                    "subtitle": "subtitle",
                    "phase_label": ["A", "B", "C"],
                },
                version="2.0",
                asset_id=kwargs.get("asset_id"),
            )

        def fake_validate(spec):
            return ValidationResult(is_valid=True, issues=[], claims=[], validated_spec=spec)

        deck = DeckSpec(
            presentation_type="Transformation Proposal",
            objective="Test.",
            audience="Board",
            narrative="Roadmap",
            estimated_slide_count=1,
            slides=[
                SlidePlan(
                    slide_number=1,
                    slide_role="Roadmap",
                    purpose="Show roadmap.",
                    required_inputs=[],
                    dependencies=[],
                    visualization_type="Roadmap",
                )
            ],
        )

        with patch.object(deck_executor, "_select_asset_for_slide", return_value=selection):
            with patch.object(deck_executor, "generate_slide_content", side_effect=fake_generate):
                with patch.object(deck_executor, "validate_content", side_effect=fake_validate):
                    result = execute_deck(deck, _intent(), _context(), _process())

        self.assertTrue(result.all_succeeded)
        self.assertEqual(captured.get("asset_id"), "TEST-ROADMAP-001")
        self.assertIsInstance(captured.get("asset_manifest"), AssetManifest)
        self.assertEqual(captured["asset_manifest"].asset_id, "TEST-ROADMAP-001")


if __name__ == "__main__":
    unittest.main()

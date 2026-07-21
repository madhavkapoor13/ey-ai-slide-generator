import json
import unittest
from unittest.mock import patch

from backend.modules.content_generator import generate_content, generate_slide_content
from schemas.context import EnterpriseContext, ResearchFact, ResearchSource
from schemas.intent import IntentResult
from schemas.presentation import SlidePlan
from schemas.process import ProcessResult
from schemas.slide_spec import SlideSpec
from schemas.visual import VisualPatternSelection


def _context(company: str, industry: str, business_function: str) -> EnterpriseContext:
    return EnterpriseContext(
        company=company,
        industry=industry,
        business_function=business_function,
        company_summary=f"{company} is represented by grounded public company context.",
        facts=[
            ResearchFact(
                statement=f"{company} publishes public business information.",
                source=f"{company} Official Website",
                url=f"https://example.com/{company.lower()}",
                type="company_fact",
            )
        ],
        sources=[
            ResearchSource(
                source=f"{company} Official Website",
                url=f"https://example.com/{company.lower()}",
                type="official_website",
            )
        ],
    )


def _process(process_name: str, family: str) -> ProcessResult:
    return ProcessResult(
        process_name=process_name,
        process_family=family,
        confidence=0.94,
        reasoning=f"{family} maps to {process_name}.",
        stages=[
            "Intake",
            "Preparation",
            "Execution",
            "Control Review",
            "Reporting",
            "Governance",
        ],
    )


def _llm_payload(company: str, family: str, process_name: str) -> dict:
    stages = []
    pain_points = []
    for label in ["Intake", "Preparation", "Execution", "Control Review", "Reporting", "Governance"]:
        stages.append(
            {
                "label": label,
                "activities": [
                    f"Coordinate {label.lower()} inputs with accountable owners.",
                    f"Validate {label.lower()} readiness against policy expectations.",
                    f"Resolve {label.lower()} exceptions through defined ownership.",
                    f"Maintain {label.lower()} documentation for management visibility.",
                    f"Prepare {label.lower()} handoffs for the next process stage.",
                ],
            }
        )
        pain_points.append(
            {
                "stage": label,
                "text": f"Fragmented ownership can slow {label.lower()} decisions.",
            }
        )

    return {
        "title": "Current State",
        "subtitle": f"{company} {family} Operating Model",
        "executive_summary": f"{company} {family} current state is organized around the {process_name} process.",
        "stages": stages,
        "pain_points": pain_points,
        "metadata": {
            "company": company,
            "industry": "Test Industry",
            "process": process_name,
        },
    }


class ContentGeneratorTests(unittest.TestCase):
    def test_requested_cases_generate_complete_slide_spec(self):
        cases = [
            ("Nike", "Retail", "Finance", "Record-to-Report"),
            ("Toyota", "Automotive", "Procurement", "Procure-to-Pay"),
            ("Microsoft", "Technology", "Human Resources", "Hire-to-Retire"),
            ("Apple", "Technology", "Supply Chain", "Plan-Source-Make-Deliver"),
            ("EY", "Professional Services", "Human Resources", "Hire-to-Retire"),
        ]

        def fake_call(_intent, context, process_result, _domain_knowledge, _slide_plan=None):
            return _llm_payload(context.company, process_result.process_family, process_result.process_name)

        with patch("backend.modules.content_generator._call_content_llm", side_effect=fake_call):
            for company, industry, family, process_name in cases:
                with self.subTest(company=company, family=family):
                    spec = generate_content(
                        IntentResult(
                            company=company,
                            industry=industry,
                            business_function=family,
                            slide_type="Current State",
                        ),
                        _context(company, industry, family),
                        _process(process_name, family),
                    )

                    SlideSpec.model_validate(spec.model_dump())
                    raw = spec.raw_spec
                    self.assertTrue(raw["executive_summary"])
                    # Current State is a process role, so stages are present but
                    # no longer fixed at exactly 6 / 5 activities.
                    self.assertGreaterEqual(len(raw["stages"]), 4)
                    self.assertLessEqual(len(raw["stages"]), 7)
                    self.assertEqual(raw["metadata"]["company"], company)
                    self.assertEqual(raw["metadata"]["industry"], industry)
                    self.assertEqual(raw["metadata"]["process"], process_name)
                    self.assertEqual(raw["summary"]["metrics"], [])
                    self.assertLessEqual(_sentence_count(raw["executive_summary"]), 2)
                    for stage in raw["stages"]:
                        self.assertTrue(_consulting_stage_name(stage["title"]))
                        for activity in stage["activities"]:
                            self.assertGreaterEqual(len(activity.split()), 3)
                            self.assertLessEqual(len(activity.split()), 7)
                            self.assertFalse(activity.lower().startswith("responsible for"))
                    for pain_point in raw["pain_points"]:
                        self.assertTrue(_has_business_impact(pain_point["text"]))

    def test_unsupported_numeric_claims_are_tagged_illustrative(self):
        payload = _llm_payload("Nike", "Finance", "Record-to-Report")
        payload["executive_summary"] = "Close cycle improves by 25% with $5M ROI."
        payload["stages"][0]["activities"][0] = "Reduce cycle time by 10 days."
        payload["pain_points"][0]["text"] = "Manual work creates 15% error rates."

        with patch("backend.modules.content_generator._call_content_llm", return_value=payload):
            spec = generate_content(
                IntentResult(company="Nike", industry="Retail", business_function="Finance", slide_type="Current State"),
                _context("Nike", "Retail", "Finance"),
                _process("Record-to-Report", "Finance"),
            )

        raw_text = json.dumps(spec.raw_spec)
        # Numeric claims are preserved and tagged as illustrative.
        self.assertIn("25% (illustrative)", raw_text)
        self.assertIn("$5M (illustrative)", raw_text)
        self.assertIn("10 days (illustrative)", raw_text)
        self.assertIn("15% (illustrative)", raw_text)
        # The bare, untagged forms no longer appear.
        self.assertNotIn('"25%"', raw_text)
        self.assertNotIn('"$5M"', raw_text)
        self.assertNotIn('10 days."', raw_text)
        self.assertNotIn('15% error', raw_text)

    def test_knowledge_grounding_is_retrieved_for_content_generation(self):
        """
        The Content Generator should call the Knowledge Manager with industry
        and business function, and pass the resulting DomainKnowledge into the
        LLM workflow.
        """
        from schemas.knowledge import DomainKnowledge

        finance_knowledge = DomainKnowledge(
            domain="Finance",
            aliases=["finance"],
            common_kpis=["Days to close"],
            common_pain_points=["Manual reconciliation"],
            transformation_themes=["Automated close"],
            common_risks=["Misstatement"],
        )

        with patch("backend.modules.content_generator.get_knowledge") as mock_knowledge:
            mock_knowledge.return_value = finance_knowledge
            with patch(
                "backend.modules.content_generator._call_content_llm",
                return_value=_llm_payload("Nike", "Finance", "Record-to-Report"),
            ):
                spec = generate_content(
                    IntentResult(
                        company="Nike",
                        industry="Retail",
                        business_function="Finance",
                        slide_type="Current State",
                    ),
                    _context("Nike", "Retail", "Finance"),
                    _process("Record-to-Report", "Finance"),
                )

        mock_knowledge.assert_called_once_with("Retail", "Finance")
        self.assertEqual(spec.slide_type, "operating_model")
        self.assertEqual(spec.raw_spec["metadata"]["company"], "Nike")

    def test_generate_slide_content_uses_slide_plan(self):
        """
        generate_slide_content() should produce a SlideSpec influenced by the
        SlidePlan while preserving the renderer contract.
        """
        slide_plan = SlidePlan(
            slide_number=2,
            slide_role="Current State",
            purpose="Describe Toyota's current procurement operating model.",
            required_inputs=["process map"],
            dependencies=["Executive Summary"],
            visualization_type="Process Flow",
        )

        with patch(
            "backend.modules.content_generator._call_content_llm",
            return_value=_llm_payload("Toyota", "Procurement", "Procure-to-Pay"),
        ) as mock_call:
            spec = generate_slide_content(
                IntentResult(
                    company="Toyota",
                    industry="Automotive",
                    business_function="Procurement",
                    slide_type="Current State",
                ),
                _context("Toyota", "Automotive", "Procurement"),
                _process("Procure-to-Pay", "Procurement"),
                slide_plan,
            )

        self.assertEqual(spec.slide_type, "operating_model")
        self.assertEqual(spec.raw_spec["title"], "Current State")
        self.assertIn("Toyota", spec.raw_spec["subtitle"])
        self.assertIn("Procurement", spec.raw_spec["subtitle"])
        self.assertIn("slide_role", spec.raw_spec["metadata"])
        self.assertEqual(spec.raw_spec["metadata"]["slide_role"], "Current State")
        self.assertEqual(spec.raw_spec["metadata"]["slide_number"], "2")

        # Verify the slide plan was passed into the LLM prompt.
        mock_call.assert_called_once()
        _, _, _, domain_knowledge, passed_slide_plan = mock_call.call_args.args
        self.assertIsNotNone(passed_slide_plan)
        self.assertEqual(passed_slide_plan.slide_role, "Current State")

    def test_quality_rules_normalize_generic_llm_output(self):
        payload = _llm_payload("Toyota", "Procurement", "Procure-to-Pay")
        payload["executive_summary"] = (
            "Toyota is a global company with a long history. "
            "The procurement model covers purchasing. "
            "This sentence should be removed."
        )
        payload["stages"][0]["label"] = "Create Purchase Order"
        payload["stages"][0]["activities"] = [
            "Responsible for validating supplier quotations across multiple approval workflows",
            "Approving purchase requisitions",
            "Monitor inventory availability for all production teams",
            "Execute invoice reconciliation with accountable owners",
            "Forecast production demand",
        ]
        payload["pain_points"][0]["text"] = "Poor communication."

        with patch("backend.modules.content_generator._call_content_llm", return_value=payload):
            spec = generate_content(
                IntentResult(
                    company="Toyota",
                    industry="Automotive",
                    business_function="Procurement",
                    slide_type="Current State",
                ),
                _context("Toyota", "Automotive", "Procurement"),
                _process("Procure-to-Pay", "Procurement"),
            )

        raw = spec.raw_spec
        self.assertEqual(_sentence_count(raw["executive_summary"]), 2)
        self.assertNotEqual(raw["stages"][0]["title"], "Create Purchase Order")
        for activity in raw["stages"][0]["activities"]:
            self.assertGreaterEqual(len(activity.split()), 3)
            self.assertLessEqual(len(activity.split()), 7)
            self.assertFalse(activity.lower().startswith("responsible for"))
        self.assertTrue(_has_business_impact(raw["pain_points"][0]["text"]))


class VisualAwareContentGeneratorTests(unittest.TestCase):
    """Tests for Sprint I4: visual-pattern-aware content generation."""

    def _selection(self, pattern_id: str, category: str = "creative_listing") -> VisualPatternSelection:
        return VisualPatternSelection(
            pattern_id=pattern_id,
            category=category,
            confidence=0.9,
            reasoning=f"{pattern_id} fits the slide intent.",
        )

    def _base_payload(self) -> dict:
        payload = _llm_payload("Nike", "Finance", "Record-to-Report")
        payload["cards"] = [
            {"title": "Card 1", "description": "First insight."},
            {"title": "Card 2", "description": "Second insight."},
            {"title": "Card 3", "description": "Third insight."},
            {"title": "Card 4", "description": "Fourth insight."},
        ]
        payload["kpis"] = [
            {"label": "KPI 1", "value": "100", "trend": "up", "description": "First KPI."},
            {"label": "KPI 2", "value": "200", "trend": "down", "description": "Second KPI."},
            {"label": "KPI 3", "value": "300", "trend": "flat", "description": "Third KPI."},
        ]
        payload["columns"] = [
            {"label": "Current", "items": [{"name": "A", "text": "Current A"}]},
            {"label": "Future", "items": [{"name": "B", "text": "Future B"}]},
        ]
        payload["events"] = [
            {"title": "Event 1", "description": "First event.", "date": "Q1"},
            {"title": "Event 2", "description": "Second event.", "date": "Q2"},
            {"title": "Event 3", "description": "Third event.", "date": "Q3"},
            {"title": "Event 4", "description": "Fourth event.", "date": "Q4"},
        ]
        payload["steps"] = [
            {"name": "Step 1", "description": "First step.", "owner": "Team A"},
            {"name": "Step 2", "description": "Second step.", "owner": "Team B"},
            {"name": "Step 3", "description": "Third step.", "owner": "Team C"},
            {"name": "Step 4", "description": "Fourth step.", "owner": "Team D"},
            {"name": "Step 5", "description": "Fifth step.", "owner": "Team E"},
        ]
        payload["domains"] = [
            {"name": "Domain 1", "capabilities": [{"name": "Cap 1"}]},
            {"name": "Domain 2", "capabilities": [{"name": "Cap 2"}]},
            {"name": "Domain 3", "capabilities": [{"name": "Cap 3"}]},
            {"name": "Domain 4", "capabilities": [{"name": "Cap 4"}]},
        ]
        return payload

    def test_cl01_generates_four_cards(self):
        payload = self._base_payload()
        with patch(
            "backend.modules.content_generator._call_content_llm",
            return_value=payload,
        ):
            spec = generate_slide_content(
                IntentResult(company="Nike", industry="Retail", business_function="Finance", slide_type="Business Benefits"),
                _context("Nike", "Retail", "Finance"),
                _process("Record-to-Report", "Finance"),
                SlidePlan(
                    slide_number=1,
                    slide_role="Business Benefits",
                    purpose="Show four business benefits.",
                    required_inputs=[],
                    dependencies=[],
                    visualization_type="Cards",
                ),
                visual_pattern_selection=self._selection("CL-01"),
            )
        self.assertIn("cards", spec.raw_spec)
        self.assertEqual(len(spec.raw_spec["cards"]), 4)
        self.assertEqual(spec.raw_spec["metadata"]["visual_pattern"], "CL-01")
        self.assertEqual(spec.raw_spec["cards"][0]["title"], "Card 1")

    def test_cl03_generates_three_kpis(self):
        payload = self._base_payload()
        with patch(
            "backend.modules.content_generator._call_content_llm",
            return_value=payload,
        ):
            spec = generate_slide_content(
                IntentResult(company="Nike", industry="Retail", business_function="Finance", slide_type="KPIs"),
                _context("Nike", "Retail", "Finance"),
                _process("Record-to-Report", "Finance"),
                SlidePlan(
                    slide_number=1,
                    slide_role="KPIs",
                    purpose="Show three KPIs.",
                    required_inputs=[],
                    dependencies=[],
                    visualization_type="KPIs",
                ),
                visual_pattern_selection=self._selection("CL-03"),
            )
        self.assertIn("kpis", spec.raw_spec)
        self.assertEqual(len(spec.raw_spec["kpis"]), 3)
        self.assertEqual(spec.raw_spec["kpis"][0]["label"], "KPI 1")

    def test_cl04_generates_two_columns(self):
        payload = self._base_payload()
        with patch(
            "backend.modules.content_generator._call_content_llm",
            return_value=payload,
        ):
            spec = generate_slide_content(
                IntentResult(company="Nike", industry="Retail", business_function="Finance", slide_type="Comparison"),
                _context("Nike", "Retail", "Finance"),
                _process("Record-to-Report", "Finance"),
                SlidePlan(
                    slide_number=1,
                    slide_role="Comparison",
                    purpose="Compare current vs future.",
                    required_inputs=[],
                    dependencies=[],
                    visualization_type="Comparison",
                ),
                visual_pattern_selection=self._selection("CL-04"),
            )
        self.assertIn("columns", spec.raw_spec)
        self.assertEqual(len(spec.raw_spec["columns"]), 2)
        self.assertEqual(spec.raw_spec["columns"][0]["label"], "Current")

    def test_ig01_generates_events(self):
        payload = self._base_payload()
        with patch(
            "backend.modules.content_generator._call_content_llm",
            return_value=payload,
        ):
            spec = generate_slide_content(
                IntentResult(company="Nike", industry="Retail", business_function="Finance", slide_type="Roadmap"),
                _context("Nike", "Retail", "Finance"),
                _process("Record-to-Report", "Finance"),
                SlidePlan(
                    slide_number=1,
                    slide_role="Roadmap",
                    purpose="Show timeline.",
                    required_inputs=[],
                    dependencies=[],
                    visualization_type="Timeline",
                ),
                visual_pattern_selection=self._selection("IG-01", "infographic"),
            )
        self.assertIn("events", spec.raw_spec)
        self.assertEqual(len(spec.raw_spec["events"]), 4)
        self.assertEqual(spec.raw_spec["events"][0]["label"], "Event 1")

    def test_ig03_generates_steps(self):
        payload = self._base_payload()
        with patch(
            "backend.modules.content_generator._call_content_llm",
            return_value=payload,
        ):
            spec = generate_slide_content(
                IntentResult(company="Nike", industry="Retail", business_function="Finance", slide_type="Process Flow"),
                _context("Nike", "Retail", "Finance"),
                _process("Record-to-Report", "Finance"),
                SlidePlan(
                    slide_number=1,
                    slide_role="Process Flow",
                    purpose="Show process flow.",
                    required_inputs=[],
                    dependencies=[],
                    visualization_type="Process Flow",
                ),
                visual_pattern_selection=self._selection("IG-03", "infographic"),
            )
        self.assertIn("steps", spec.raw_spec)
        # Padding removed: the layout engine adapts to the actual emitted count.
        self.assertEqual(len(spec.raw_spec["steps"]), 5)
        self.assertEqual(spec.raw_spec["steps"][0]["label"], "Step 1")

    def test_ig06_generates_domains(self):
        payload = self._base_payload()
        with patch(
            "backend.modules.content_generator._call_content_llm",
            return_value=payload,
        ):
            spec = generate_slide_content(
                IntentResult(company="Nike", industry="Retail", business_function="Finance", slide_type="Capabilities"),
                _context("Nike", "Retail", "Finance"),
                _process("Record-to-Report", "Finance"),
                SlidePlan(
                    slide_number=1,
                    slide_role="Capabilities",
                    purpose="Show capability map.",
                    required_inputs=[],
                    dependencies=[],
                    visualization_type="Capability Map",
                ),
                visual_pattern_selection=self._selection("IG-06", "infographic"),
            )
        self.assertIn("domains", spec.raw_spec)
        # Padding removed: the layout engine adapts to the actual emitted count.
        self.assertEqual(len(spec.raw_spec["domains"]), 4)
        self.assertEqual(spec.raw_spec["domains"][0]["name"], "Domain 1")

    def test_visual_pattern_instruction_is_passed_to_llm(self):
        payload = self._base_payload()
        with patch(
            "backend.modules.content_generator._call_content_llm",
            return_value=payload,
        ) as mock_call:
            generate_slide_content(
                IntentResult(company="Nike", industry="Retail", business_function="Finance", slide_type="Business Benefits"),
                _context("Nike", "Retail", "Finance"),
                _process("Record-to-Report", "Finance"),
                SlidePlan(
                    slide_number=1,
                    slide_role="Business Benefits",
                    purpose="Show four business benefits.",
                    required_inputs=[],
                    dependencies=[],
                    visualization_type="Cards",
                ),
                visual_pattern_selection=self._selection("CL-01"),
            )
        mock_call.assert_called_once()
        kwargs = mock_call.call_args.kwargs
        self.assertIn("visual_pattern_selection", kwargs)
        self.assertEqual(kwargs["visual_pattern_selection"].pattern_id, "CL-01")

    def test_missing_pattern_fields_left_empty(self):
        """When pattern-specific fields are absent the native array is left empty
        rather than derived from stages. No crash should occur."""
        payload = _llm_payload("Nike", "Finance", "Record-to-Report")
        # No cards/kpis/columns/etc. in payload; only stages exist.
        with patch(
            "backend.modules.content_generator._call_content_llm",
            return_value=payload,
        ):
            spec = generate_slide_content(
                IntentResult(company="Nike", industry="Retail", business_function="Finance", slide_type="KPIs"),
                _context("Nike", "Retail", "Finance"),
                _process("Record-to-Report", "Finance"),
                SlidePlan(
                    slide_number=1,
                    slide_role="KPIs",
                    purpose="Show KPIs.",
                    required_inputs=[],
                    dependencies=[],
                    visualization_type="KPIs",
                ),
                visual_pattern_selection=self._selection("CL-03"),
            )
        self.assertIn("kpis", spec.raw_spec)
        # Padding removed: native array stays empty when the LLM omits it.
        self.assertEqual(len(spec.raw_spec["kpis"]), 0)

    def test_section_divider_spec_bypasses_llm(self):
        """Section divider slides produce a deterministic spec without calling the LLM."""
        with patch("backend.modules.content_generator._call_content_llm") as mock_call:
            spec = generate_slide_content(
                IntentResult(company="Nike", industry="Retail", business_function="Finance", slide_type="Section Divider"),
                _context("Nike", "Retail", "Finance"),
                _process("Record-to-Report", "Finance"),
                SlidePlan(
                    slide_number=5,
                    slide_role="Section Divider",
                    purpose="Transition to Implementation Roadmap.",
                    required_inputs=[],
                    dependencies=[],
                    visualization_type="Section Divider",
                ),
                visual_pattern_selection=self._selection("SECTION-DIVIDER"),
            )
        mock_call.assert_not_called()
        self.assertEqual(spec.visual_pattern_id, "SECTION-DIVIDER")
        self.assertEqual(spec.raw_spec.get("section_title"), "Implementation Sequence")
        self.assertEqual(spec.raw_spec["metadata"].get("visual_pattern"), "SECTION-DIVIDER")

    def test_dark_section_divider_asset_uses_manifest_keys(self):
        """Dark section divider assets return placeholder-keyed content."""
        with patch("backend.modules.content_generator._call_content_llm") as mock_call:
            spec = generate_slide_content(
                IntentResult(
                    company="Microsoft",
                    industry="Technology",
                    business_function="Procurement",
                    slide_type="Section Divider",
                    raw_content="Create only one dark Section Divider slide introducing the Implementation Roadmap section.",
                ),
                _context("Microsoft", "Technology", "Procurement"),
                _process("Source-to-Pay", "Procurement"),
                SlidePlan(
                    slide_number=1,
                    slide_role="Section Divider",
                    purpose="Introduce the requested section using a dark section divider slide.",
                    required_inputs=[],
                    dependencies=[],
                    visualization_type="Dark Section Divider",
                ),
                visual_pattern_selection=self._selection("SECTION-DIVIDER"),
                asset_id="SECTION-DIVIDER-DARK-001",
            )

        mock_call.assert_not_called()
        self.assertEqual(spec.asset_id, "SECTION-DIVIDER-DARK-001")
        self.assertEqual(spec.raw_spec["section_number"], "SECTION 01")
        self.assertEqual(spec.raw_spec["title"], "Implementation Roadmap")
        self.assertEqual(
            spec.raw_spec["subtitle"],
            "Microsoft procurement transformation roadmap",
        )
        self.assertNotIn("section_title", spec.raw_spec)
        self.assertNotIn("metadata", spec.raw_spec)

    def test_next_steps_section_divider_asset_uses_manifest_keys(self):
        """Standard next-steps divider assets return their manifest keys."""
        with patch("backend.modules.content_generator._call_content_llm") as mock_call:
            spec = generate_slide_content(
                IntentResult(
                    company="HSBC",
                    industry="Financial Services",
                    business_function="Finance",
                    slide_type="Section Divider",
                    raw_content="Create only one Next Steps Section Divider slide for Finance AI Transformation.",
                ),
                _context("HSBC", "Financial Services", "Finance"),
                _process("Record-to-Report", "Finance"),
                SlidePlan(
                    slide_number=1,
                    slide_role="Section Divider",
                    purpose="Introduce the requested section using a section divider slide.",
                    required_inputs=[],
                    dependencies=[],
                    visualization_type="Section Divider",
                ),
                visual_pattern_selection=self._selection("SECTION-DIVIDER"),
                asset_id="SECTION-NEXT-STEPS-001",
            )

        mock_call.assert_not_called()
        self.assertEqual(spec.asset_id, "SECTION-NEXT-STEPS-001")
        self.assertEqual(spec.raw_spec["section_number"], "SECTION 01")
        self.assertEqual(spec.raw_spec["section_title"], "NEXT STEPS\n& ACTIONS")
        self.assertIn("Decisions, accountabilities and actions", spec.raw_spec["section_subtitle"])
        self.assertNotIn("metadata", spec.raw_spec)

    def test_carries_visual_pattern_id_on_spec(self):
        """The carried pattern is stamped on the SlideSpec so slide_service can
        read it as the single source of truth instead of re-scoring."""
        payload = self._base_payload()
        with patch(
            "backend.modules.content_generator._call_content_llm",
            return_value=payload,
        ):
            spec = generate_slide_content(
                IntentResult(company="Nike", industry="Retail", business_function="Finance", slide_type="Roadmap"),
                _context("Nike", "Retail", "Finance"),
                _process("Record-to-Report", "Finance"),
                SlidePlan(
                    slide_number=1,
                    slide_role="Roadmap",
                    purpose="Show timeline.",
                    required_inputs=[],
                    dependencies=[],
                    visualization_type="Timeline",
                ),
                visual_pattern_selection=self._selection("IG-01", "infographic"),
            )
        self.assertEqual(spec.visual_pattern_id, "IG-01")
        self.assertEqual(spec.visual_confidence, 0.9)

    def test_no_carried_pattern_when_selection_omitted(self):
        """When no selection is supplied the auto-select still produces a
        carried pattern_id (backward-compatible auto path for direct callers;
        production supplies the selection via the Deck Executor)."""
        selection = self._selection("CL-01")
        with patch(
            "backend.modules.content_generator.plan_visual_pattern",
            return_value=selection,
        ):
            with patch(
                "backend.modules.content_generator._call_content_llm",
                return_value=self._base_payload(),
            ):
                spec = generate_slide_content(
                    IntentResult(company="Nike", industry="Retail", business_function="Finance", slide_type="Business Benefits"),
                    _context("Nike", "Retail", "Finance"),
                    _process("Record-to-Report", "Finance"),
                    SlidePlan(
                        slide_number=1,
                        slide_role="Business Benefits",
                        purpose="Show benefits.",
                        required_inputs=[],
                        dependencies=[],
                        visualization_type="Cards",
                    ),
                )
        self.assertEqual(spec.visual_pattern_id, "CL-01")
        self.assertEqual(spec.visual_confidence, 0.9)

    def test_auto_selects_visual_pattern_when_not_provided(self):
        """Content Generator calls the Visual Planner when no selection is supplied."""
        payload = self._base_payload()
        selection = self._selection("CL-01")
        with patch(
            "backend.modules.content_generator.plan_visual_pattern",
            return_value=selection,
        ) as mock_planner:
            with patch(
                "backend.modules.content_generator._call_content_llm",
                return_value=payload,
            ):
                spec = generate_slide_content(
                    IntentResult(company="Nike", industry="Retail", business_function="Finance", slide_type="Business Benefits"),
                    _context("Nike", "Retail", "Finance"),
                    _process("Record-to-Report", "Finance"),
                    SlidePlan(
                        slide_number=1,
                        slide_role="Business Benefits",
                        purpose="Show benefits.",
                        required_inputs=[],
                        dependencies=[],
                        visualization_type="Cards",
                    ),
                )
        mock_planner.assert_called_once()
        self.assertIn("cards", spec.raw_spec)
        self.assertEqual(len(spec.raw_spec["cards"]), 4)

def _sentence_count(text: str) -> int:
    return len([part for part in text.replace("!", ".").replace("?", ".").split(".") if part.strip()])


def _consulting_stage_name(text: str) -> bool:
    terms = [
        "Management",
        "Governance",
        "Control",
        "Visibility",
        "Administration",
        "Validation",
        "Support",
    ]
    return any(term in text for term in terms)


def _has_business_impact(text: str) -> bool:
    terms = [
        "delays",
        "reduces",
        "limits",
        "increases",
        "impacts",
        "constrains",
        "creates",
        "weakens",
        "disrupts",
        "erodes",
    ]
    return any(term in text.lower() for term in terms)


if __name__ == "__main__":
    unittest.main()

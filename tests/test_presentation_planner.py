import unittest
from unittest.mock import patch

from backend.modules.presentation_planner import (
    _extract_enumerated_topics,
    _reconcile_enumerated_slides,
    plan_presentation,
)
from schemas.intent import IntentResult
from schemas.presentation import DeckSpec, SlidePlan


class PresentationPlannerTests(unittest.TestCase):
    def test_enumerated_topics_extracted_from_include_clause(self):
        prompt = (
            "Create a consulting presentation for Microsoft's AI Procurement "
            "Transformation initiative. The audience is the Board of Directors. "
            "Include an Executive Summary, current procurement challenges, "
            "future-state operating model, key business benefits, AI use cases, "
            "implementation roadmap, transformation timeline, implementation "
            "risks, KPIs for success, and next steps."
        )
        topics = _extract_enumerated_topics(prompt)
        self.assertIn("Executive Summary", topics)
        self.assertIn("current procurement challenges", topics)
        self.assertIn("AI use cases", topics)
        self.assertIn("KPIs for success", topics)
        self.assertEqual(len(topics), 10)

    def test_single_slide_current_process_preserves_six_step_constraint(self):
        prompt = (
            "Create only one Current State Process slide for Amazon Supply Chain Modernization. "
            "Audience: COO and Board. Show a six-step current process with activities, "
            "pain points, and overall business impact. Do not create any other slides."
        )
        intent = IntentResult(
            slide_type="process_flow",
            raw_title="Amazon Supply Chain Modernization",
            raw_content=prompt,
            company="Amazon",
            industry="Retail",
            business_function="Supply Chain",
        )

        with patch(
            "backend.modules.presentation_planner._call_presentation_planner_llm",
            return_value=_toyota_procurement_deck(),
        ):
            deck = plan_presentation(prompt, intent)

        self.assertEqual(deck.estimated_slide_count, 1)
        self.assertEqual(deck.slides[0].slide_role, "Current Procurement Process")
        self.assertIn("Use exactly six process steps.", deck.slides[0].purpose)
        self.assertIn("Include activities.", deck.slides[0].purpose)
        self.assertIn("Include pain points.", deck.slides[0].purpose)
        self.assertIn("Include overall business impact.", deck.slides[0].purpose)

    def test_single_slide_dark_section_divider_preserves_divider_role(self):
        prompt = (
            "Create only one dark Section Divider slide introducing the Implementation Roadmap "
            "section for Microsoft Procurement Transformation. Audience: Board of Directors. "
            "Do not create any other slides."
        )
        intent = IntentResult(
            slide_type="section_divider",
            raw_title="Microsoft Procurement Transformation",
            raw_content=prompt,
            company="Microsoft",
            industry="Technology",
            business_function="Procurement",
        )

        with patch(
            "backend.modules.presentation_planner._call_presentation_planner_llm",
            return_value=_toyota_procurement_deck(),
        ):
            deck = plan_presentation(prompt, intent)

        self.assertEqual(deck.estimated_slide_count, 1)
        self.assertEqual(deck.slides[0].slide_role, "Section Divider")
        self.assertEqual(deck.slides[0].visualization_type, "Section Divider")
        self.assertIn("dark section divider", deck.slides[0].purpose.lower())

    def test_single_slide_next_steps_section_divider_uses_standard_divider_hint(self):
        prompt = (
            "Create only one Next Steps Section Divider slide for Finance AI Transformation. "
            "Audience: CFO and Board Investment Committee. It should introduce the decisions "
            "and actions required after the transformation proposal. Do not create any other slides."
        )
        intent = IntentResult(
            slide_type="section_divider",
            raw_title="Finance AI Transformation",
            raw_content=prompt,
            company="HSBC",
            industry="Financial Services",
            business_function="Finance",
        )

        with patch(
            "backend.modules.presentation_planner._call_presentation_planner_llm",
            return_value=_toyota_procurement_deck(),
        ):
            deck = plan_presentation(prompt, intent)

        self.assertEqual(deck.estimated_slide_count, 1)
        self.assertEqual(deck.slides[0].slide_role, "Section Divider")
        self.assertEqual(deck.slides[0].visualization_type, "Section Divider")
        self.assertNotIn("dark section divider", deck.slides[0].purpose.lower())

    def test_reconcile_appends_missing_enumerated_topics(self):
        # LLM omitted AI Use Cases, Transformation Timeline, and KPIs for
        # Success — the exact defect seen in Presentation4.pptx.
        incomplete = DeckSpec(
            presentation_type="Transformation Proposal",
            objective="o",
            audience="a",
            narrative="n",
            estimated_slide_count=8,
            slides=[
                SlidePlan(slide_number=i + 1, slide_role=role, purpose="p",
                          required_inputs=[], dependencies=[], visualization_type="Executive Summary")
                for i, role in enumerate([
                    "Executive Summary", "Current State", "Opportunities",
                    "Future State", "Business Benefits", "Roadmap",
                    "Implementation Risks", "Next Steps",
                ])
            ],
        )
        prompt = (
            "Include an Executive Summary, current procurement challenges, "
            "future-state operating model, key business benefits, AI use cases, "
            "implementation roadmap, transformation timeline, implementation "
            "risks, KPIs for success, and next steps."
        )
        reconciled = _reconcile_enumerated_slides(prompt, incomplete)
        roles = [s.slide_role for s in reconciled.slides]
        self.assertIn("AI Use Cases", roles)
        self.assertIn("Transformation Timeline", roles)
        self.assertIn("KPIs for Success", roles)
        self.assertEqual(reconciled.estimated_slide_count, len(reconciled.slides))
        self.assertEqual(reconciled.estimated_slide_count, 11)

    def test_reconcile_noop_when_all_topics_present(self):
        complete = DeckSpec(
            presentation_type="Transformation Proposal",
            objective="o", audience="a", narrative="n",
            estimated_slide_count=8, slides=[
                SlidePlan(slide_number=i + 1, slide_role=role, purpose="p",
                          required_inputs=[], dependencies=[], visualization_type="Executive Summary")
                for i, role in enumerate([
                    "Executive Summary", "Current State", "Future State",
                    "Business Benefits", "AI Use Cases", "Roadmap",
                    "Implementation Risks", "Next Steps",
                ])
            ],
        )
        prompt = "Include an Executive Summary, current state, and next steps."
        reconciled = _reconcile_enumerated_slides(prompt, complete)
        self.assertEqual(len(reconciled.slides), len(complete.slides))

    def test_reconcile_noop_when_no_enumeration(self):
        deck = DeckSpec(
            presentation_type="Transformation Proposal",
            objective="o", audience="a", narrative="n",
            estimated_slide_count=1, slides=[
                SlidePlan(slide_number=1, slide_role="Executive Summary", purpose="p",
                          required_inputs=[], dependencies=[], visualization_type="Executive Summary")
            ],
        )
        reconciled = _reconcile_enumerated_slides("Build a deck summary.", deck)
        self.assertEqual(len(reconciled.slides), 1)

    def test_single_investment_slide_prompt_does_not_expand_to_story_template(self):
        prompt = (
            "Create only an Investment Case slide for Finance AI Transformation. "
            "Audience: CFO and Board Investment Committee. "
            "Do not create any other slides."
        )
        payload = {
            "presentation_type": "Transformation Proposal",
            "objective": "Finance AI Transformation",
            "audience": "CFO and Board Investment Committee",
            "narrative": "Investment case",
            "estimated_slide_count": 8,
            "slides": [
                {
                    "slide_number": 1,
                    "slide_role": "Executive Summary",
                    "purpose": "Summarize the transformation.",
                    "required_inputs": [],
                    "dependencies": [],
                    "visualization_type": "Executive Summary",
                },
                {
                    "slide_number": 2,
                    "slide_role": "Investment Case",
                    "purpose": "Summarize the value case.",
                    "required_inputs": [],
                    "dependencies": [],
                    "visualization_type": "Investment Case",
                },
            ],
        }
        with patch(
            "backend.modules.presentation_planner._call_presentation_planner_llm",
            return_value=payload,
        ):
            deck = plan_presentation(
                prompt,
                IntentResult(company="", industry="", business_function="Finance", slide_type="Investment Case"),
            )

        self.assertEqual(deck.estimated_slide_count, 1)
        self.assertEqual(len(deck.slides), 1)
        self.assertEqual(deck.slides[0].slide_role, "Investment Case")

    def test_reconcile_orders_slides_to_enumerated_sequence(self):
        # LLM returns slides out of order; reconciliation must reorder them.
        out_of_order = DeckSpec(
            presentation_type="Transformation Proposal",
            objective="o", audience="a", narrative="n",
            estimated_slide_count=4,
            slides=[
                SlidePlan(slide_number=2, slide_role="Current State", purpose="p",
                          required_inputs=[], dependencies=[], visualization_type="Process Flow"),
                SlidePlan(slide_number=4, slide_role="Next Steps", purpose="p",
                          required_inputs=[], dependencies=[], visualization_type="Executive Summary"),
                SlidePlan(slide_number=3, slide_role="Future State", purpose="p",
                          required_inputs=[], dependencies=[], visualization_type="Capability Map"),
                SlidePlan(slide_number=1, slide_role="Executive Summary", purpose="p",
                          required_inputs=[], dependencies=[], visualization_type="Executive Summary"),
            ],
        )
        prompt = (
            "Include an Executive Summary, current state, future state, and next steps."
        )
        reconciled = _reconcile_enumerated_slides(prompt, out_of_order)
        roles = [s.slide_role for s in reconciled.slides]
        self.assertEqual(roles, ["Executive Summary", "Current State", "Future State", "Next Steps"])

    def test_microsoft_procurement_prompt_gets_distinct_board_deck_roles(self):
        incomplete = DeckSpec(
            presentation_type="Transformation Proposal",
            objective="o",
            audience="Board of Directors",
            narrative="n",
            estimated_slide_count=4,
            slides=[
                SlidePlan(slide_number=1, slide_role="Executive Summary", purpose="p",
                          required_inputs=[], dependencies=[], visualization_type="Executive Summary"),
                SlidePlan(slide_number=2, slide_role="Transformation Overview", purpose="p",
                          required_inputs=[], dependencies=[], visualization_type="Executive Summary"),
                SlidePlan(slide_number=3, slide_role="Roadmap", purpose="p",
                          required_inputs=[], dependencies=[], visualization_type="Roadmap"),
                SlidePlan(slide_number=4, slide_role="KPIs", purpose="p",
                          required_inputs=[], dependencies=[], visualization_type="KPI Dashboard"),
            ],
        )
        prompt = (
            "Create a consulting presentation for Microsoft's AI Procurement Transformation initiative. "
            "The audience is the Board of Directors. Include an Executive Summary, current procurement "
            "process, future-state operating model, key business benefits, AI use cases, implementation "
            "roadmap, KPIs for success, implementation risks, and next steps."
        )

        reconciled = _reconcile_enumerated_slides(prompt, incomplete)

        roles = [s.slide_role for s in reconciled.slides]
        self.assertEqual(
            roles,
            [
                "Executive Summary",
                "Current Procurement Process",
                "Future-State Operating Model",
                "Business Benefits",
                "AI Use Cases",
                "Implementation Roadmap",
                "KPIs for Success",
                "Implementation Risks",
                "Next Steps",
            ],
        )
        self.assertEqual(len(roles), len(set(roles)))
        visualizations = {s.slide_role: s.visualization_type for s in reconciled.slides}
        self.assertEqual(visualizations["Current Procurement Process"], "Process Flow")
        self.assertEqual(visualizations["Future-State Operating Model"], "Operating Model")
        self.assertEqual(visualizations["AI Use Cases"], "Use Case Portfolio")
        self.assertEqual(visualizations["Implementation Risks"], "Risk Matrix")

    def test_board_decisions_prompt_keeps_decisions_at_the_close(self):
        incomplete = DeckSpec(
            presentation_type="Transformation Proposal",
            objective="o",
            audience="Board of Directors",
            narrative="n",
            estimated_slide_count=4,
            slides=[
                SlidePlan(slide_number=1, slide_role="Board Decisions", purpose="p",
                          required_inputs=[], dependencies=[], visualization_type="Board Decisions"),
                SlidePlan(slide_number=2, slide_role="KPIs for Success", purpose="p",
                          required_inputs=[], dependencies=[], visualization_type="KPI Dashboard"),
                SlidePlan(slide_number=3, slide_role="AI Use Cases", purpose="p",
                          required_inputs=[], dependencies=[], visualization_type="Use Case Portfolio"),
                SlidePlan(slide_number=4, slide_role="Opportunities", purpose="p",
                          required_inputs=[], dependencies=[], visualization_type="Creative Listing"),
            ],
        )
        prompt = (
            "Create a consulting presentation for Microsoft Procurement Transformation. "
            "Include board decisions, KPI success metrics, AI use case shortlist, "
            "opportunity areas, risks, and next steps."
        )

        reconciled = _reconcile_enumerated_slides(prompt, incomplete)
        roles = [s.slide_role for s in reconciled.slides]

        self.assertNotEqual(roles[0], "Board Decisions")
        self.assertEqual(roles[-1], "Next Steps")
        self.assertIn("Next Steps", roles[-2:])

    def test_transformation_proposal_uses_story_template_without_client_hardcoding(self):
        user_prompt = "Create a transformation proposal for Unilever HR."
        intent = IntentResult(
            slide_type="operating_model",
            raw_title="HR Transformation",
            raw_content=user_prompt,
            company="Unilever",
            industry="Consumer Goods",
            business_function="Human Resources",
        )
        llm_payload = {
            "presentation_type": "Transformation Proposal",
            "objective": "Align leadership on HR transformation.",
            "audience": "Executive leadership",
            "narrative": "Short draft narrative",
            "estimated_slide_count": 3,
            "slides": [
                {
                    "slide_number": 1,
                    "slide_role": "Executive Summary",
                    "purpose": "Frame the recommendation.",
                    "required_inputs": [],
                    "dependencies": [],
                    "visualization_type": "Executive Summary",
                },
                {
                    "slide_number": 2,
                    "slide_role": "Current State",
                    "purpose": "Describe the current HR model.",
                    "required_inputs": [],
                    "dependencies": ["Executive Summary"],
                    "visualization_type": "Process Flow",
                },
                {
                    "slide_number": 3,
                    "slide_role": "Roadmap",
                    "purpose": "Sequence the implementation.",
                    "required_inputs": [],
                    "dependencies": ["Current State"],
                    "visualization_type": "Roadmap",
                },
            ],
        }

        with patch(
            "backend.modules.presentation_planner._call_presentation_planner_llm",
            return_value=llm_payload,
        ):
            deck = plan_presentation(user_prompt, intent)

        roles = [slide.slide_role for slide in deck.slides]
        self.assertEqual(
            roles,
            [
                "Executive Summary",
                "Current State",
                "Case for Change",
                "Future State",
                "Capabilities / Use Cases",
                "Business Benefits",
                "Roadmap",
                "KPIs for Success",
                "Risks & Mitigations",
                "Next Steps / Decisions",
            ],
        )
        self.assertTrue(all(slide.confidence > 0 for slide in deck.slides))
        self.assertIn("Executive Summary -> Current State", deck.narrative)

    def test_reconcile_dedups_duplicate_canonical_roles(self):
        # LLM emits both an Executive Summary and a "Transformation Overview"
        # (same canonical bucket). The duplicate should be dropped.
        duplicate = DeckSpec(
            presentation_type="Transformation Proposal",
            objective="o", audience="a", narrative="n",
            estimated_slide_count=3,
            slides=[
                SlidePlan(slide_number=1, slide_role="Executive Summary", purpose="p",
                          required_inputs=[], dependencies=[], visualization_type="Executive Summary"),
                SlidePlan(slide_number=2, slide_role="Transformation Overview", purpose="p",
                          required_inputs=[], dependencies=[], visualization_type="Executive Summary"),
                SlidePlan(slide_number=3, slide_role="Current State", purpose="p",
                          required_inputs=[], dependencies=[], visualization_type="Process Flow"),
            ],
        )
        prompt = "Include an Executive Summary, current state, and next steps."
        reconciled = _reconcile_enumerated_slides(prompt, duplicate)
        roles = [s.slide_role for s in reconciled.slides]
        self.assertEqual(roles, ["Executive Summary", "Current State", "Next Steps"])

    def test_reconcile_places_distinct_extras_after_nearest_neighbor(self):
        # A genuinely distinct extra slide (e.g. "Change Management") with no
        # enumerated match is kept and appended after enumerated slides.
        with_extra = DeckSpec(
            presentation_type="Transformation Proposal",
            objective="o", audience="a", narrative="n",
            estimated_slide_count=3,
            slides=[
                SlidePlan(slide_number=1, slide_role="Executive Summary", purpose="p",
                          required_inputs=[], dependencies=[], visualization_type="Executive Summary"),
                SlidePlan(slide_number=2, slide_role="Change Management", purpose="p",
                          required_inputs=[], dependencies=[], visualization_type="Executive Summary"),
                SlidePlan(slide_number=3, slide_role="Current State", purpose="p",
                          required_inputs=[], dependencies=[], visualization_type="Process Flow"),
            ],
        )
        prompt = "Include an Executive Summary, current state, and next steps."
        reconciled = _reconcile_enumerated_slides(prompt, with_extra)
        roles = [s.slide_role for s in reconciled.slides]
        self.assertEqual(roles, ["Executive Summary", "Current State", "Change Management", "Next Steps"])

    def test_procurement_transformation_proposal_for_toyota(self):
        user_prompt = "Build a procurement transformation proposal for Toyota."
        intent = IntentResult(
            slide_type="operating_model",
            raw_title="Current State",
            raw_content=user_prompt,
            company="Toyota",
            industry="Automotive",
            business_function="Procurement",
        )

        with patch(
            "backend.modules.presentation_planner._call_presentation_planner_llm",
            return_value=_toyota_procurement_deck(),
        ):
            deck = plan_presentation(user_prompt, intent)

        self.assertEqual(deck.presentation_type, "Transformation Proposal")
        self.assertIn("procurement", deck.objective.lower())
        self.assertIn("Toyota", deck.audience)
        self.assertIn("Current State", deck.narrative)
        self.assertEqual(deck.estimated_slide_count, len(deck.slides))
        self.assertEqual(deck.slides[0].slide_role, "Executive Summary")
        self._assert_slide_dependencies_reference_roles(deck)

    def test_ai_strategy_presentation_for_coca_cola_finance(self):
        user_prompt = "Create an AI strategy presentation for Coca-Cola Finance."
        intent = IntentResult(
            slide_type="process_flow",
            raw_title="AI Strategy",
            raw_content=user_prompt,
            company="Coca-Cola",
            industry="Consumer Goods",
            business_function="Finance",
        )

        with patch(
            "backend.modules.presentation_planner._call_presentation_planner_llm",
            return_value=_coca_cola_ai_strategy_deck(),
        ):
            deck = plan_presentation(user_prompt, intent)

        self.assertEqual(deck.presentation_type, "AI Strategy")
        self.assertIn("AI", deck.objective)
        self.assertIn("Finance", deck.audience)
        self.assertIn("AI", deck.narrative)
        self.assertEqual(deck.estimated_slide_count, len(deck.slides))
        self.assertEqual(deck.slides[0].slide_role, "Executive Summary")
        self._assert_slide_dependencies_reference_roles(deck)

    def test_board_update_on_hr_transformation(self):
        user_prompt = "Prepare a board update on HR transformation."
        intent = IntentResult(
            slide_type="current_future",
            raw_title="HR Transformation Board Update",
            raw_content=user_prompt,
            company="Unknown",
            industry="Unknown",
            business_function="Human Resources",
        )

        with patch(
            "backend.modules.presentation_planner._call_presentation_planner_llm",
            return_value=_hr_board_update_deck(),
        ):
            deck = plan_presentation(user_prompt, intent)

        self.assertEqual(deck.presentation_type, "Board Update")
        self.assertIn("board", deck.audience.lower())
        self.assertIn("HR", deck.narrative)
        self.assertEqual(deck.estimated_slide_count, len(deck.slides))
        self._assert_slide_dependencies_reference_roles(deck)

    def test_supply_chain_modernization_uses_transformation_taxonomy(self):
        """
        Modernization proposals are not a top-level taxonomy type; they should
        be classified and scaffolded as Transformation Proposals.
        """
        user_prompt = "Build a supply chain modernization proposal."
        intent = IntentResult(
            slide_type="operating_model",
            raw_title="Supply Chain Modernization",
            raw_content=user_prompt,
            company="Unknown",
            industry="Unknown",
            business_function="Supply Chain",
        )

        with patch(
            "backend.modules.presentation_planner._call_presentation_planner_llm",
            return_value=_supply_chain_transformation_deck(),
        ):
            deck = plan_presentation(user_prompt, intent)

        self.assertEqual(deck.presentation_type, "Transformation Proposal")
        self.assertIn("supply chain", deck.objective.lower())
        self.assertEqual(deck.estimated_slide_count, len(deck.slides))
        self._assert_slide_dependencies_reference_roles(deck)

    def test_digital_transformation_roadmap(self):
        user_prompt = "Create a digital transformation roadmap."
        intent = IntentResult(
            slide_type="process_flow",
            raw_title="Digital Transformation Roadmap",
            raw_content=user_prompt,
            company="Unknown",
            industry="Unknown",
            business_function="Unknown",
        )

        with patch(
            "backend.modules.presentation_planner._call_presentation_planner_llm",
            return_value=_digital_transformation_roadmap_deck(),
        ):
            deck = plan_presentation(user_prompt, intent)

        self.assertEqual(deck.presentation_type, "Roadmap")
        self.assertIn("digital transformation", deck.objective.lower())
        self.assertIn("Roadmap", deck.narrative)
        self.assertEqual(deck.estimated_slide_count, len(deck.slides))
        self._assert_slide_dependencies_reference_roles(deck)

    def test_llm_failure_returns_taxonomy_fallback_deck(self):
        user_prompt = "Build a procurement transformation proposal for Toyota."
        intent = IntentResult(
            slide_type="operating_model",
            company="Toyota",
            industry="Automotive",
            business_function="Procurement",
        )

        with patch(
            "backend.modules.presentation_planner._call_presentation_planner_llm",
            side_effect=RuntimeError("LLM unavailable"),
        ):
            deck = plan_presentation(user_prompt, intent)

        self.assertEqual(deck.presentation_type, "Transformation Proposal")
        self.assertIn("Toyota", deck.objective)
        self.assertTrue(deck.slides)
        self.assertEqual(deck.estimated_slide_count, len(deck.slides))
        # Fallback should follow the taxonomy default sequence.
        self.assertEqual(deck.slides[0].slide_role, "Executive Summary")
        self.assertEqual(deck.slides[1].slide_role, "Current State")
        self._assert_slide_dependencies_reference_roles(deck)

    def test_taxonomy_fallback_personalizes_objective_and_audience(self):
        user_prompt = "Create an AI strategy for Coca-Cola Finance."
        intent = IntentResult(
            slide_type="process_flow",
            raw_title="AI Strategy",
            raw_content=user_prompt,
            company="Coca-Cola",
            industry="Consumer Goods",
            business_function="Finance",
        )

        with patch(
            "backend.modules.presentation_planner._call_presentation_planner_llm",
            side_effect=RuntimeError("LLM unavailable"),
        ):
            deck = plan_presentation(user_prompt, intent)

        self.assertEqual(deck.presentation_type, "AI Strategy")
        # The taxonomy objective should be personalized with company/function.
        self.assertIn("Coca-Cola", deck.audience)
        self.assertIn("Finance", deck.audience)
        # Slides should use the AI Strategy taxonomy sequence.
        roles = [slide.slide_role for slide in deck.slides]
        self.assertIn("Executive Summary", roles)
        self.assertIn("AI Vision", roles)
        self.assertIn("Roadmap", roles)

    def _assert_slide_dependencies_reference_roles(self, deck):
        roles = {slide.slide_role for slide in deck.slides}
        for slide in deck.slides:
            for dependency in slide.dependencies:
                self.assertIn(
                    dependency,
                    roles,
                    f"Dependency '{dependency}' is not a slide role in the deck.",
                )


def _toyota_procurement_deck():
    return {
        "presentation_type": "Transformation Proposal",
        "objective": "Secure approval for Toyota's procurement transformation program.",
        "audience": "Toyota procurement leadership and executive sponsors",
        "narrative": "Current State → Opportunities → Future State → Roadmap → Next Steps",
        "estimated_slide_count": 6,
        "slides": [
            {
                "slide_number": 1,
                "slide_role": "Executive Summary",
                "purpose": "Frame the procurement transformation recommendation.",
                "required_inputs": [],
                "dependencies": [],
                "visualization_type": "Executive Summary",
            },
            {
                "slide_number": 2,
                "slide_role": "Current State",
                "purpose": "Describe the current procurement operating model.",
                "required_inputs": ["process map"],
                "dependencies": ["Executive Summary"],
                "visualization_type": "Process Flow",
            },
            {
                "slide_number": 3,
                "slide_role": "Opportunities",
                "purpose": "Identify improvement opportunities.",
                "required_inputs": [],
                "dependencies": ["Current State"],
                "visualization_type": "Matrix",
            },
            {
                "slide_number": 4,
                "slide_role": "Future State",
                "purpose": "Articulate the target procurement operating model.",
                "required_inputs": [],
                "dependencies": ["Opportunities"],
                "visualization_type": "Capability Map",
            },
            {
                "slide_number": 5,
                "slide_role": "Roadmap",
                "purpose": "Outline the implementation timeline.",
                "required_inputs": [],
                "dependencies": ["Future State"],
                "visualization_type": "Roadmap",
            },
            {
                "slide_number": 6,
                "slide_role": "Next Steps",
                "purpose": "Define immediate actions and decisions required.",
                "required_inputs": [],
                "dependencies": ["Roadmap"],
                "visualization_type": "Executive Summary",
            },
        ],
    }


def _coca_cola_ai_strategy_deck():
    return {
        "presentation_type": "AI Strategy",
        "objective": "Align Coca-Cola Finance on an AI-enabled finance roadmap.",
        "audience": "Coca-Cola Finance leadership",
        "narrative": "Opportunity → AI Vision → Use Cases → Roadmap → Governance",
        "estimated_slide_count": 5,
        "slides": [
            {
                "slide_number": 1,
                "slide_role": "Executive Summary",
                "purpose": "Summarize the AI strategy recommendation.",
                "required_inputs": [],
                "dependencies": [],
                "visualization_type": "Executive Summary",
            },
            {
                "slide_number": 2,
                "slide_role": "Opportunity",
                "purpose": "Frame the AI opportunity for Finance.",
                "required_inputs": [],
                "dependencies": ["Executive Summary"],
                "visualization_type": "Matrix",
            },
            {
                "slide_number": 3,
                "slide_role": "AI Vision",
                "purpose": "Describe the future finance operating model.",
                "required_inputs": [],
                "dependencies": ["Opportunity"],
                "visualization_type": "Capability Map",
            },
            {
                "slide_number": 4,
                "slide_role": "Roadmap",
                "purpose": "Sequence AI use cases and milestones.",
                "required_inputs": [],
                "dependencies": ["AI Vision"],
                "visualization_type": "Roadmap",
            },
            {
                "slide_number": 5,
                "slide_role": "Governance",
                "purpose": "Define data, risk, and operating governance.",
                "required_inputs": [],
                "dependencies": ["Roadmap"],
                "visualization_type": "Executive Summary",
            },
        ],
    }


def _hr_board_update_deck():
    return {
        "presentation_type": "Board Update",
        "objective": "Inform the board on HR transformation progress and decisions required.",
        "audience": "Board of Directors",
        "narrative": "HR Progress → Risks → Decisions → Next Steps",
        "estimated_slide_count": 4,
        "slides": [
            {
                "slide_number": 1,
                "slide_role": "Executive Summary",
                "purpose": "Summarize the HR transformation status.",
                "required_inputs": [],
                "dependencies": [],
                "visualization_type": "Executive Summary",
            },
            {
                "slide_number": 2,
                "slide_role": "Progress",
                "purpose": "Highlight milestones achieved.",
                "required_inputs": ["program status"],
                "dependencies": ["Executive Summary"],
                "visualization_type": "Timeline",
            },
            {
                "slide_number": 3,
                "slide_role": "Risks",
                "purpose": "Surface key risks and mitigations.",
                "required_inputs": [],
                "dependencies": ["Progress"],
                "visualization_type": "Matrix",
            },
            {
                "slide_number": 4,
                "slide_role": "Decisions",
                "purpose": "List decisions required from the board.",
                "required_inputs": [],
                "dependencies": ["Risks"],
                "visualization_type": "Executive Summary",
            },
        ],
    }


def _supply_chain_transformation_deck():
    return {
        "presentation_type": "Transformation Proposal",
        "objective": "Define a prioritized supply chain transformation path.",
        "audience": "Supply chain leadership",
        "narrative": "Current State → Opportunities → Future State → Roadmap",
        "estimated_slide_count": 5,
        "slides": [
            {
                "slide_number": 1,
                "slide_role": "Executive Summary",
                "purpose": "Frame the supply chain transformation proposal.",
                "required_inputs": [],
                "dependencies": [],
                "visualization_type": "Executive Summary",
            },
            {
                "slide_number": 2,
                "slide_role": "Current State",
                "purpose": "Describe the current supply chain model.",
                "required_inputs": ["process map"],
                "dependencies": ["Executive Summary"],
                "visualization_type": "Process Flow",
            },
            {
                "slide_number": 3,
                "slide_role": "Opportunities",
                "purpose": "Identify improvement opportunities.",
                "required_inputs": [],
                "dependencies": ["Current State"],
                "visualization_type": "Matrix",
            },
            {
                "slide_number": 4,
                "slide_role": "Future State",
                "purpose": "Articulate the target supply chain vision.",
                "required_inputs": [],
                "dependencies": ["Opportunities"],
                "visualization_type": "Capability Map",
            },
            {
                "slide_number": 5,
                "slide_role": "Roadmap",
                "purpose": "Sequence modernization initiatives.",
                "required_inputs": [],
                "dependencies": ["Future State"],
                "visualization_type": "Roadmap",
            },
        ],
    }


def _digital_transformation_roadmap_deck():
    return {
        "presentation_type": "Roadmap",
        "objective": "Communicate the digital transformation roadmap and sequencing.",
        "audience": "Executive leadership",
        "narrative": "Strategic Context → Initiatives → Sequencing → Roadmap → Outcomes",
        "estimated_slide_count": 5,
        "slides": [
            {
                "slide_number": 1,
                "slide_role": "Executive Summary",
                "purpose": "Summarize the digital transformation roadmap.",
                "required_inputs": [],
                "dependencies": [],
                "visualization_type": "Executive Summary",
            },
            {
                "slide_number": 2,
                "slide_role": "Strategic Context",
                "purpose": "Set the strategic drivers for digital transformation.",
                "required_inputs": [],
                "dependencies": ["Executive Summary"],
                "visualization_type": "Executive Summary",
            },
            {
                "slide_number": 3,
                "slide_role": "Initiatives",
                "purpose": "Outline the transformation initiatives.",
                "required_inputs": [],
                "dependencies": ["Strategic Context"],
                "visualization_type": "Capability Map",
            },
            {
                "slide_number": 4,
                "slide_role": "Roadmap",
                "purpose": "Present the sequenced transformation roadmap.",
                "required_inputs": [],
                "dependencies": ["Initiatives"],
                "visualization_type": "Roadmap",
            },
            {
                "slide_number": 5,
                "slide_role": "Outcomes",
                "purpose": "Define expected business outcomes.",
                "required_inputs": [],
                "dependencies": ["Roadmap"],
                "visualization_type": "Matrix",
            },
        ],
    }


if __name__ == "__main__":
    unittest.main()

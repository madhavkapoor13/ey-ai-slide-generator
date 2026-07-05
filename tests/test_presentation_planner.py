import json
import unittest
from unittest.mock import patch

from backend.modules.presentation_planner import plan_presentation
from schemas.intent import IntentResult


class PresentationPlannerTests(unittest.TestCase):
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
            return_value=json.dumps(_toyota_procurement_deck()),
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
            return_value=json.dumps(_coca_cola_ai_strategy_deck()),
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
            return_value=json.dumps(_hr_board_update_deck()),
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
            return_value=json.dumps(_supply_chain_transformation_deck()),
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
            return_value=json.dumps(_digital_transformation_roadmap_deck()),
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

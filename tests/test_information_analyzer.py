import unittest

from backend.modules.information_analyzer import analyze_information
from schemas.intent import IntentResult
from schemas.presentation import DeckSpec, SlidePlan


class InformationAnalyzerTests(unittest.TestCase):
    def _deck(self, objective: str = "", audience: str = "") -> DeckSpec:
        return DeckSpec(
            presentation_type="Transformation Proposal",
            objective=objective or "Align stakeholders on the path forward.",
            audience=audience or "Senior leadership",
            narrative="Current State → Future State → Roadmap",
            estimated_slide_count=1,
            slides=[
                SlidePlan(
                    slide_number=1,
                    slide_role="Executive Summary",
                    purpose="Summarize the proposal.",
                    required_inputs=[],
                    dependencies=[],
                    visualization_type="Executive Summary",
                )
            ],
        )

    def test_build_a_strategy_deck_missing_most_fields(self):
        intent = IntentResult(slide_type="unknown")
        result = analyze_information("Build a strategy deck.", intent, self._deck())

        self.assertFalse(result.has_enough_information)
        self.assertEqual(result.confidence, "low")
        self.assertIn("company", result.missing_fields)
        self.assertIn("industry", result.missing_fields)
        self.assertIn("business_function", result.missing_fields)
        self.assertIn("objective", result.analysis)

    def test_create_an_ai_proposal_missing_company_and_function(self):
        intent = IntentResult(
            slide_type="process_flow",
            industry="Technology",
        )
        deck = self._deck(objective="Define an AI-enabled roadmap.", audience="Executives")
        result = analyze_information("Create an AI proposal.", intent, deck)

        self.assertFalse(result.has_enough_information)
        self.assertIn("company", result.missing_fields)
        self.assertIn("business_function", result.missing_fields)
        self.assertNotIn("industry", result.missing_fields)
        self.assertNotIn("audience", result.missing_fields)
        self.assertNotIn("objective", result.missing_fields)
        self.assertIn("analysis", result.model_dump())

    def test_toyota_procurement_transformation_has_company_and_function(self):
        intent = IntentResult(
            slide_type="operating_model",
            company="Toyota",
            business_function="Procurement",
        )
        deck = self._deck(
            objective="Transform Toyota's procurement operating model.",
            audience="Procurement leadership",
        )
        result = analyze_information("Toyota Procurement transformation.", intent, deck)

        self.assertFalse(result.has_enough_information)
        self.assertIn("industry", result.missing_fields)
        self.assertNotIn("company", result.missing_fields)
        self.assertNotIn("business_function", result.missing_fields)
        self.assertNotIn("audience", result.missing_fields)
        self.assertNotIn("objective", result.missing_fields)
        self.assertEqual(result.confidence, "medium")

    def test_board_update_for_hr_has_audience_and_function(self):
        intent = IntentResult(
            slide_type="current_future",
            business_function="Human Resources",
        )
        deck = self._deck(
            objective="Update the board on HR transformation progress.",
            audience="Board of Directors",
        )
        result = analyze_information("Board update for HR.", intent, deck)

        self.assertFalse(result.has_enough_information)
        self.assertIn("company", result.missing_fields)
        self.assertIn("industry", result.missing_fields)
        self.assertNotIn("business_function", result.missing_fields)
        self.assertNotIn("audience", result.missing_fields)
        self.assertNotIn("objective", result.missing_fields)

    def test_complete_request_has_enough_information(self):
        intent = IntentResult(
            slide_type="operating_model",
            company="Toyota",
            industry="Automotive",
            business_function="Procurement",
        )
        deck = self._deck(
            objective="Transform procurement operations over three years.",
            audience="Toyota procurement executives",
        )
        result = analyze_information(
            "Build a procurement transformation proposal for Toyota.",
            intent,
            deck,
        )

        self.assertTrue(result.has_enough_information)
        self.assertEqual(result.confidence, "high")
        self.assertEqual(result.missing_fields, [])
        self.assertIn("All required fields are present", result.analysis)

    def test_company_extracted_from_prompt_when_intent_empty(self):
        intent = IntentResult(slide_type="unknown")
        deck = self._deck(
            objective="Modernize the supply chain.",
            audience="Leadership",
        )
        result = analyze_information(
            "Build a supply chain modernization proposal for Coca-Cola.",
            intent,
            deck,
        )

        self.assertNotIn("company", result.missing_fields)
        self.assertNotIn("business_function", result.missing_fields)
        self.assertIn("industry", result.missing_fields)

    def test_unknown_values_treated_as_missing(self):
        intent = IntentResult(
            slide_type="operating_model",
            company="Unknown",
            industry="Unknown",
            business_function="Unknown",
        )
        deck = self._deck(objective="TBD", audience="Unknown")
        result = analyze_information("Build a deck.", intent, deck)

        self.assertFalse(result.has_enough_information)
        self.assertEqual(result.confidence, "low")
        self.assertIn("company", result.missing_fields)
        self.assertIn("industry", result.missing_fields)
        self.assertIn("business_function", result.missing_fields)
        self.assertIn("audience", result.missing_fields)
        self.assertIn("objective", result.missing_fields)


if __name__ == "__main__":
    unittest.main()

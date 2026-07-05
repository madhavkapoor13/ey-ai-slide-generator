import unittest
from unittest.mock import patch

from backend.modules.presentation_classifier import classify_presentation
from schemas.intent import IntentResult


class PresentationClassifierTests(unittest.TestCase):
    def test_transformation_proposal_for_procurement(self):
        user_prompt = "Build a procurement transformation proposal for Toyota."
        intent = IntentResult(
            slide_type="operating_model",
            raw_title="Current State",
            raw_content=user_prompt,
            company="Toyota",
            industry="Automotive",
            business_function="Procurement",
        )

        result = classify_presentation(user_prompt, intent)

        self.assertEqual(result.presentation_type, "Transformation Proposal")
        self.assertGreaterEqual(result.confidence, 0.25)
        self.assertIn("Transformation Proposal", result.reasoning_summary)
        self.assertIn("procurement", result.reasoning_summary.lower())

    def test_ai_strategy_for_finance(self):
        user_prompt = "Create an AI strategy presentation for Coca-Cola Finance."
        intent = IntentResult(
            slide_type="process_flow",
            raw_title="AI Strategy",
            raw_content=user_prompt,
            company="Coca-Cola",
            industry="Consumer Goods",
            business_function="Finance",
        )

        result = classify_presentation(user_prompt, intent)

        self.assertEqual(result.presentation_type, "AI Strategy")
        self.assertGreaterEqual(result.confidence, 0.25)
        self.assertIn("AI Strategy", result.reasoning_summary)
        self.assertIn("ai", result.reasoning_summary.lower())

    def test_due_diligence_for_acquisition(self):
        user_prompt = "Prepare commercial due diligence for the acquisition of a retail target."
        intent = IntentResult(
            slide_type="comparison",
            raw_title="Due Diligence",
            raw_content=user_prompt,
            company="Unknown",
            industry="Retail",
            business_function="Commercial",
        )

        result = classify_presentation(user_prompt, intent)

        self.assertEqual(result.presentation_type, "Due Diligence")
        self.assertGreaterEqual(result.confidence, 0.25)
        self.assertIn("Due Diligence", result.reasoning_summary)

    def test_board_update(self):
        user_prompt = "Prepare a board update on HR transformation."
        intent = IntentResult(
            slide_type="current_future",
            raw_title="HR Transformation Board Update",
            raw_content=user_prompt,
            company="Unknown",
            industry="Unknown",
            business_function="Human Resources",
        )

        result = classify_presentation(user_prompt, intent)

        self.assertEqual(result.presentation_type, "Board Update")
        self.assertGreaterEqual(result.confidence, 0.25)
        self.assertIn("Board Update", result.reasoning_summary)

    def test_capability_overview(self):
        user_prompt = "Create a capability overview for the finance function."
        intent = IntentResult(
            slide_type="operating_model",
            raw_title="Capability Overview",
            raw_content=user_prompt,
            company="Unknown",
            industry="Unknown",
            business_function="Finance",
        )

        result = classify_presentation(user_prompt, intent)

        self.assertEqual(result.presentation_type, "Capability Overview")
        self.assertGreaterEqual(result.confidence, 0.25)
        self.assertIn("Capability Overview", result.reasoning_summary)

    def test_low_confidence_triggers_llm_fallback(self):
        user_prompt = "Make a nice deck about work stuff."
        intent = IntentResult(
            slide_type="unknown",
            raw_title="",
            raw_content=user_prompt,
            company="Unknown",
            industry="Unknown",
            business_function="Unknown",
        )

        with patch(
            "backend.modules.presentation_classifier._llm_classify",
            return_value=_llm_classification("Transformation Proposal"),
        ) as mock_llm:
            result = classify_presentation(user_prompt, intent)

        mock_llm.assert_called_once()
        self.assertEqual(result.presentation_type, "Transformation Proposal")
        self.assertEqual(result.confidence, 0.75)
        self.assertEqual(result.reasoning_summary, "Classified via LLM fallback.")

    def test_llm_failure_returns_deterministic_result(self):
        user_prompt = "Something about transformation and AI."
        intent = IntentResult(
            slide_type="unknown",
            raw_title="",
            raw_content=user_prompt,
            company="Unknown",
            industry="Unknown",
            business_function="Unknown",
        )

        with patch(
            "backend.modules.presentation_classifier._llm_classify",
            side_effect=RuntimeError("LLM unavailable"),
        ):
            result = classify_presentation(user_prompt, intent)

        self.assertIsNotNone(result.presentation_type)
        self.assertGreaterEqual(result.confidence, 0.0)
        self.assertLessEqual(result.confidence, 1.0)


def _llm_classification(presentation_type: str):
    from schemas.presentation import PresentationClassification

    return PresentationClassification(
        presentation_type=presentation_type,
        confidence=0.75,
        reasoning_summary="Classified via LLM fallback.",
    )


if __name__ == "__main__":
    unittest.main()

import unittest

from backend.modules.clarification import generate_clarifications
from schemas.information import InformationResult
from schemas.presentation import DeckSpec, SlidePlan


class ClarificationEngineTests(unittest.TestCase):
    def _deck(self, presentation_type: str = "Transformation Proposal") -> DeckSpec:
        return DeckSpec(
            presentation_type=presentation_type,
            objective="Align stakeholders.",
            audience="Senior leadership",
            narrative="Current State → Future State → Roadmap",
            estimated_slide_count=1,
            slides=[
                SlidePlan(
                    slide_number=1,
                    slide_role="Executive Summary",
                    purpose="Summarize.",
                    required_inputs=[],
                    dependencies=[],
                    visualization_type="Executive Summary",
                )
            ],
        )

    def test_strategy_deck_generates_minimum_content_questions(self):
        info = InformationResult(
            has_enough_information=False,
            missing_fields=["company", "industry", "business_function", "audience", "objective"],
            analysis="Missing all fields.",
            confidence="low",
        )
        result = generate_clarifications("Build a strategy deck.", self._deck(), info)

        self.assertTrue(result.needs_clarification)
        self.assertEqual(len(result.content_questions), 5)
        self.assertEqual(len(result.visualization_questions), 0)
        categories = {q.category for q in result.content_questions}
        self.assertEqual(categories, {"content"})

    def test_ai_proposal_generates_only_missing_content_questions(self):
        info = InformationResult(
            has_enough_information=False,
            missing_fields=["company", "business_function"],
            analysis="Missing company and business function.",
            confidence="medium",
        )
        result = generate_clarifications("Create an AI proposal.", self._deck(), info)

        self.assertTrue(result.needs_clarification)
        question_ids = {q.id for q in result.content_questions}
        self.assertEqual(question_ids, {"company", "business_function"})
        self.assertEqual(len(result.visualization_questions), 0)

    def test_toyota_procurement_generates_single_missing_question(self):
        info = InformationResult(
            has_enough_information=False,
            missing_fields=["industry"],
            analysis="Missing industry.",
            confidence="medium",
        )
        result = generate_clarifications(
            "Toyota Procurement transformation.",
            self._deck(),
            info,
        )

        self.assertTrue(result.needs_clarification)
        self.assertEqual(len(result.content_questions), 1)
        self.assertEqual(result.content_questions[0].id, "industry")
        self.assertEqual(len(result.visualization_questions), 0)

    def test_visualization_question_only_when_ambiguous(self):
        info = InformationResult(
            has_enough_information=False,
            missing_fields=["industry"],
            analysis="Missing industry.",
            confidence="medium",
        )
        result = generate_clarifications(
            "Toyota Procurement transformation with process flow and roadmap.",
            self._deck(),
            info,
        )

        self.assertTrue(result.needs_clarification)
        self.assertEqual(len(result.content_questions), 1)
        self.assertEqual(len(result.visualization_questions), 1)
        self.assertEqual(result.visualization_questions[0].category, "visualization")
        self.assertFalse(result.visualization_questions[0].required)

    def test_no_visualization_question_when_single_signal_clear(self):
        info = InformationResult(
            has_enough_information=False,
            missing_fields=["industry"],
            analysis="Missing industry.",
            confidence="medium",
        )
        result = generate_clarifications(
            "Toyota Procurement transformation process flow.",
            self._deck(),
            info,
        )

        self.assertTrue(result.needs_clarification)
        self.assertEqual(len(result.content_questions), 1)
        self.assertEqual(len(result.visualization_questions), 0)

    def test_no_clarification_when_information_complete(self):
        info = InformationResult(
            has_enough_information=True,
            missing_fields=[],
            analysis="All fields present.",
            confidence="high",
        )
        result = generate_clarifications(
            "Build a procurement transformation proposal for Toyota.",
            self._deck(),
            info,
        )

        self.assertFalse(result.needs_clarification)
        self.assertEqual(len(result.content_questions), 0)
        self.assertEqual(len(result.visualization_questions), 0)

    def test_content_and_visualization_questions_separated(self):
        info = InformationResult(
            has_enough_information=False,
            missing_fields=["company", "business_function"],
            analysis="Missing company and business function.",
            confidence="medium",
        )
        result = generate_clarifications(
            "Build a roadmap or timeline for transformation.",
            self._deck(presentation_type="Roadmap"),
            info,
        )

        self.assertTrue(result.needs_clarification)
        for q in result.content_questions:
            self.assertEqual(q.category, "content")
        for q in result.visualization_questions:
            self.assertEqual(q.category, "visualization")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest
from unittest.mock import patch

from backend.orchestrator import run_pipeline
from schemas.deck_execution import DeckExecutionResult
from schemas.intent import IntentResult
from schemas.pipeline_result import PipelineResult
from schemas.presentation import DeckSpec, SlidePlan
from schemas.slide_spec import SlideSpec


class PipelineClarificationTests(unittest.TestCase):
    """End-to-end orchestrator tests for the Sprint H.1 clarification gate."""

    def _deck(
        self,
        objective: str | None = None,
        audience: str | None = None,
        presentation_type: str = "Transformation Proposal",
    ) -> DeckSpec:
        return DeckSpec(
            presentation_type=presentation_type,
            objective=objective if objective is not None else "Align stakeholders on the path forward.",
            audience=audience if audience is not None else "Senior leadership",
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

    def _minimal_deck_result(self, deck: DeckSpec) -> DeckExecutionResult:
        spec = SlideSpec(
            slide_type="operating_model",
            raw_spec={"title": "Executive Summary"},
            version="2.0",
            generated_by="test",
        )
        return DeckExecutionResult(
            deck_spec=deck,
            slides=[],
            successful_slides=[spec],
            failed_slides=[],
            all_succeeded=True,
            partial_success=False,
        )

    def _run_with_real_analyzer(
        self,
        user_prompt: str,
        intent: IntentResult,
        deck: DeckSpec,
    ) -> PipelineResult:
        """Run pipeline using the real analyzer/clarification engine and mocked downstream modules."""
        deck_result = self._minimal_deck_result(deck)

        with patch("backend.orchestrator.extract_intent", return_value=intent), \
             patch("backend.orchestrator.plan_presentation", return_value=deck), \
             patch("backend.orchestrator.build_context") as mock_context, \
             patch("backend.orchestrator.identify_process") as mock_process, \
             patch("backend.orchestrator.execute_deck", return_value=deck_result) as mock_execute:

            result = run_pipeline("Title", user_prompt)

            # Capture whether downstream generation modules were invoked.
            result._downstream_called = (  # type: ignore[attr-defined]
                mock_context.called or mock_process.called or mock_execute.called
            )
            return result

    def test_complete_prompt_completes_pipeline(self):
        intent = IntentResult(
            slide_type="operating_model",
            company="Toyota",
            industry="Automotive",
            business_function="Procurement",
        )
        deck = self._deck(
            objective="Transform Toyota's procurement operating model.",
            audience="Procurement leadership",
        )

        result = self._run_with_real_analyzer(
            "Build a procurement transformation proposal for Toyota.",
            intent,
            deck,
        )

        self.assertEqual(result.status, "COMPLETED")
        self.assertFalse(result.needs_clarification)
        self.assertIsNone(result.clarification_result)
        self.assertIsNotNone(result.deck_execution_result)
        self.assertTrue(result._downstream_called)

    def test_missing_company_triggers_content_question(self):
        intent = IntentResult(
            slide_type="operating_model",
            industry="Automotive",
            business_function="Procurement",
        )
        deck = self._deck(
            objective="Transform the procurement operating model.",
            audience="Procurement leadership",
        )

        result = self._run_with_real_analyzer(
            "Build a procurement transformation proposal.",
            intent,
            deck,
        )

        self.assertEqual(result.status, "WAITING_FOR_USER")
        self.assertTrue(result.needs_clarification)
        question_ids = {q.id for q in result.clarification_result.content_questions}
        self.assertIn("company", question_ids)
        self.assertFalse(result._downstream_called)

    def test_missing_audience_triggers_content_question(self):
        intent = IntentResult(
            slide_type="operating_model",
            company="Toyota",
            industry="Automotive",
            business_function="Procurement",
        )
        deck = self._deck(
            objective="Transform Toyota's procurement operating model.",
            audience="",
        )

        result = self._run_with_real_analyzer(
            "Build a procurement transformation proposal for Toyota.",
            intent,
            deck,
        )

        self.assertEqual(result.status, "WAITING_FOR_USER")
        question_ids = {q.id for q in result.clarification_result.content_questions}
        self.assertIn("audience", question_ids)
        self.assertFalse(result._downstream_called)

    def test_missing_objective_triggers_content_question(self):
        intent = IntentResult(
            slide_type="operating_model",
            company="Toyota",
            industry="Automotive",
            business_function="Procurement",
        )
        deck = self._deck(
            objective="",
            audience="Procurement leadership",
        )

        result = self._run_with_real_analyzer(
            "Build a procurement transformation proposal for Toyota.",
            intent,
            deck,
        )

        self.assertEqual(result.status, "WAITING_FOR_USER")
        question_ids = {q.id for q in result.clarification_result.content_questions}
        self.assertIn("objective", question_ids)
        self.assertFalse(result._downstream_called)

    def test_multiple_missing_fields_triggers_multiple_questions(self):
        intent = IntentResult(slide_type="unknown")
        deck = DeckSpec(
            presentation_type="Transformation Proposal",
            objective="",
            audience="",
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

        result = self._run_with_real_analyzer(
            "Build a strategy deck.",
            intent,
            deck,
        )

        self.assertEqual(result.status, "WAITING_FOR_USER")
        question_ids = {q.id for q in result.clarification_result.content_questions}
        self.assertIn("company", question_ids)
        self.assertIn("industry", question_ids)
        self.assertIn("business_function", question_ids)
        self.assertIn("audience", question_ids)
        self.assertIn("objective", question_ids)
        self.assertEqual(len(result.clarification_result.visualization_questions), 0)
        self.assertFalse(result._downstream_called)

    def test_no_visualization_ambiguity_when_single_signal(self):
        intent = IntentResult(
            slide_type="operating_model",
            company="Toyota",
            industry="Automotive",
            business_function="Procurement",
        )
        deck = self._deck(
            objective="Transform Toyota's procurement operating model.",
            audience="Procurement leadership",
        )

        result = self._run_with_real_analyzer(
            "Toyota Procurement transformation process flow.",
            intent,
            deck,
        )

        self.assertEqual(result.status, "COMPLETED")
        self.assertIsNotNone(result.deck_execution_result)

    def test_visualization_ambiguity_adds_visualization_question(self):
        # Industry is missing so the analyzer triggers clarification; with both
        # "process flow" and "roadmap" in the prompt, the engine adds a
        # visualization question as well.
        intent = IntentResult(
            slide_type="operating_model",
            company="Toyota",
            business_function="Procurement",
        )
        deck = self._deck(
            objective="Transform Toyota's procurement operating model.",
            audience="Procurement leadership",
        )

        result = self._run_with_real_analyzer(
            "Toyota Procurement transformation with process flow and roadmap.",
            intent,
            deck,
        )

        self.assertEqual(result.status, "WAITING_FOR_USER")
        self.assertEqual(len(result.clarification_result.content_questions), 1)
        self.assertEqual(result.clarification_result.content_questions[0].id, "industry")
        self.assertEqual(len(result.clarification_result.visualization_questions), 1)
        viz_question = result.clarification_result.visualization_questions[0]
        self.assertEqual(viz_question.category, "visualization")
        self.assertIn("process flow", viz_question.question)
        self.assertIn("roadmap", viz_question.question)
        self.assertFalse(result._downstream_called)

    def test_content_and_visualization_questions_separated(self):
        intent = IntentResult(
            slide_type="operating_model",
            company="Toyota",
            business_function="Procurement",
        )
        deck = self._deck(
            objective="Transform Toyota's procurement operating model.",
            audience="Procurement leadership",
        )

        result = self._run_with_real_analyzer(
            "Toyota Procurement transformation with process flow and roadmap.",
            intent,
            deck,
        )

        self.assertEqual(result.status, "WAITING_FOR_USER")
        for q in result.clarification_result.content_questions:
            self.assertEqual(q.category, "content")
        for q in result.clarification_result.visualization_questions:
            self.assertEqual(q.category, "visualization")
        self.assertFalse(result._downstream_called)

    def test_clarification_stops_pipeline(self):
        """When clarification is required, context/process/deck modules are not called."""
        intent = IntentResult(slide_type="unknown")
        deck = self._deck()

        result = self._run_with_real_analyzer(
            "Build a strategy deck.",
            intent,
            deck,
        )

        self.assertEqual(result.status, "WAITING_FOR_USER")
        self.assertTrue(result.needs_clarification)
        self.assertIsNone(result.deck_execution_result)
        self.assertFalse(result._downstream_called)

    def test_completed_pipeline_bypasses_clarification(self):
        """When information is complete, no clarification questions are generated."""
        intent = IntentResult(
            slide_type="operating_model",
            company="Toyota",
            industry="Automotive",
            business_function="Procurement",
        )
        deck = self._deck(
            objective="Transform Toyota's procurement operating model.",
            audience="Procurement leadership",
        )

        result = self._run_with_real_analyzer(
            "Build a procurement transformation proposal for Toyota.",
            intent,
            deck,
        )

        self.assertEqual(result.status, "COMPLETED")
        self.assertFalse(result.needs_clarification)
        self.assertIsNone(result.clarification_result)


if __name__ == "__main__":
    unittest.main()

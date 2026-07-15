import unittest
from unittest.mock import patch

from backend.orchestrator import run_pipeline
from schemas.clarification import ClarificationQuestion, ClarificationResult
from schemas.context import EnterpriseContext
from schemas.deck_execution import DeckExecutionResult, SlideExecutionResult
from schemas.information import InformationResult
from schemas.intent import IntentResult
from schemas.pipeline_result import PipelineResult
from schemas.presentation import DeckSpec, SlidePlan
from schemas.process import ProcessResult
from schemas.slide_spec import SlideSpec


class OrchestratorTests(unittest.TestCase):
    def _intent(self) -> IntentResult:
        return IntentResult(
            slide_type="operating_model",
            raw_title="Current State",
            raw_content="Procure-to-Pay process for Toyota.",
            company="Toyota",
            industry="Automotive",
            business_function="Procurement",
        )

    def _deck_spec(self) -> DeckSpec:
        return DeckSpec(
            presentation_type="Transformation Proposal",
            objective="Transform Toyota procurement.",
            audience="Procurement leadership",
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

    def _context(self) -> EnterpriseContext:
        return EnterpriseContext(
            company="Toyota",
            industry="Automotive",
            business_function="Procurement",
        )

    def _process_result(self) -> ProcessResult:
        return ProcessResult(
            process_name="Procure-to-Pay",
            process_family="Procurement",
            confidence=0.94,
            reasoning="Procurement maps to Procure-to-Pay.",
            stages=["Requisition", "Sourcing", "Purchase Order"],
        )

    def _slide_spec(self) -> SlideSpec:
        return SlideSpec(
            slide_type="operating_model",
            raw_spec={"title": "Current State"},
            version="2.0",
            generated_by="test",
        )

    def _execution_result(self) -> DeckExecutionResult:
        spec = self._slide_spec()
        deck_spec = self._deck_spec()
        slide_result = SlideExecutionResult(
            slide_plan=deck_spec.slides[0],
            slide_spec=spec,
            validation_result=None,
            success=True,
        )
        return DeckExecutionResult(
            deck_spec=deck_spec,
            slides=[slide_result],
            successful_slides=[spec],
            failed_slides=[],
            all_succeeded=True,
            partial_success=False,
        )

    def _information_result(self, has_enough: bool = True) -> InformationResult:
        return InformationResult(
            has_enough_information=has_enough,
            missing_fields=[] if has_enough else ["industry"],
            analysis="All fields present." if has_enough else "Missing industry.",
            confidence="high" if has_enough else "medium",
        )

    def test_planner_is_invoked_and_pipeline_result_returned(self):
        intent = self._intent()
        deck_spec = self._deck_spec()
        information_result = self._information_result(True)
        context = self._context()
        process_result = self._process_result()
        execution_result = self._execution_result()

        with patch("backend.orchestrator.extract_intent", return_value=intent) as mock_intent, \
             patch("backend.orchestrator.plan_presentation", return_value=deck_spec) as mock_planner, \
             patch("backend.orchestrator.analyze_information", return_value=information_result) as mock_analyzer, \
             patch("backend.orchestrator.build_context", return_value=context) as mock_context, \
             patch("backend.orchestrator.identify_process", return_value=process_result) as mock_process, \
             patch("backend.orchestrator.execute_deck", return_value=execution_result) as mock_execute:

            result = run_pipeline("Current State", "Toyota Procurement transformation.")

            self.assertIsInstance(result, PipelineResult)
            self.assertEqual(result.status, "COMPLETED")
            self.assertFalse(result.needs_clarification)
            self.assertIsNone(result.clarification_result)
            self.assertEqual(result.deck_execution_result, execution_result)

            mock_intent.assert_called_once_with("Current State", "Toyota Procurement transformation.")
            mock_planner.assert_called_once_with("Toyota Procurement transformation.", intent)
            mock_analyzer.assert_called_once_with("Toyota Procurement transformation.", intent, deck_spec)
            mock_context.assert_called_once_with(intent)
            mock_process.assert_called_once_with(intent, context)
            mock_execute.assert_called_once_with(deck_spec, intent, context, process_result)

    def test_downstream_modules_receive_original_signatures(self):
        """DeckSpec is kept local to the orchestrator; downstream interfaces unchanged."""
        intent = self._intent()
        deck_spec = self._deck_spec()
        information_result = self._information_result(True)
        context = self._context()
        process_result = self._process_result()
        execution_result = self._execution_result()

        with patch("backend.orchestrator.extract_intent", return_value=intent), \
             patch("backend.orchestrator.plan_presentation", return_value=deck_spec), \
             patch("backend.orchestrator.analyze_information", return_value=information_result), \
             patch("backend.orchestrator.build_context", return_value=context) as mock_context, \
             patch("backend.orchestrator.identify_process", return_value=process_result) as mock_process, \
             patch("backend.orchestrator.execute_deck", return_value=execution_result) as mock_execute:

            run_pipeline("Current State", "Toyota Procurement transformation.")

            _, kwargs = mock_context.call_args
            self.assertNotIn("deck_spec", kwargs)
            self.assertEqual(len(mock_context.call_args.args), 1)

            _, kwargs = mock_process.call_args
            self.assertNotIn("deck_spec", kwargs)
            self.assertEqual(len(mock_process.call_args.args), 2)

            args, kwargs = mock_execute.call_args
            self.assertEqual(args, (deck_spec, intent, context, process_result))
            self.assertEqual(len(kwargs), 0)

    def test_clarification_stops_pipeline(self):
        """When information is missing, the pipeline stops before context/process/deck execution."""
        intent = self._intent()
        deck_spec = self._deck_spec()
        information_result = self._information_result(False)
        clarification_result = ClarificationResult(
            needs_clarification=True,
            content_questions=[
                ClarificationQuestion(
                    id="industry",
                    category="content",
                    question="Which industry or sector does this relate to?",
                    required=True,
                    reason="The request does not specify an industry or sector.",
                )
            ],
            visualization_questions=[],
        )

        with patch("backend.orchestrator.extract_intent", return_value=intent), \
             patch("backend.orchestrator.plan_presentation", return_value=deck_spec), \
             patch("backend.orchestrator.analyze_information", return_value=information_result), \
             patch("backend.orchestrator.generate_clarifications", return_value=clarification_result) as mock_clarification, \
             patch("backend.orchestrator.build_context") as mock_context, \
             patch("backend.orchestrator.identify_process") as mock_process, \
             patch("backend.orchestrator.execute_deck") as mock_execute:

            result = run_pipeline("Current State", "Toyota Procurement transformation.")

            self.assertIsInstance(result, PipelineResult)
            self.assertEqual(result.status, "WAITING_FOR_USER")
            self.assertTrue(result.needs_clarification)
            self.assertEqual(result.clarification_result, clarification_result)
            self.assertIsNone(result.deck_execution_result)

            mock_clarification.assert_called_once_with(
                "Toyota Procurement transformation.", deck_spec, information_result
            )
            mock_context.assert_not_called()
            mock_process.assert_not_called()
            mock_execute.assert_not_called()

    def test_completed_pipeline_bypasses_clarification(self):
        """When information is sufficient, no clarification questions are generated."""
        intent = self._intent()
        deck_spec = self._deck_spec()
        information_result = self._information_result(True)
        execution_result = self._execution_result()

        with patch("backend.orchestrator.extract_intent", return_value=intent), \
             patch("backend.orchestrator.plan_presentation", return_value=deck_spec), \
             patch("backend.orchestrator.analyze_information", return_value=information_result), \
             patch("backend.orchestrator.generate_clarifications") as mock_clarification, \
             patch("backend.orchestrator.build_context", return_value=self._context()), \
             patch("backend.orchestrator.identify_process", return_value=self._process_result()), \
             patch("backend.orchestrator.execute_deck", return_value=execution_result):

            result = run_pipeline("Current State", "Toyota Procurement transformation.")

            self.assertEqual(result.status, "COMPLETED")
            self.assertFalse(result.needs_clarification)
            self.assertIsNone(result.clarification_result)
            mock_clarification.assert_not_called()


if __name__ == "__main__":
    unittest.main()

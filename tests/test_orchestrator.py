import unittest
from unittest.mock import MagicMock, patch

from backend.orchestrator import run_pipeline
from schemas.context import EnterpriseContext
from schemas.intent import IntentResult
from schemas.presentation import DeckSpec, SlidePlan
from schemas.process import ProcessResult
from schemas.slide_spec import SlideSpec
from schemas.validation import ValidationResult


class OrchestratorTests(unittest.TestCase):
    def _intent(self) -> IntentResult:
        return IntentResult(
            slide_type="operating_model",
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
            estimated_slide_count=6,
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

    def _validation_result(self, spec: SlideSpec) -> ValidationResult:
        return ValidationResult(
            is_valid=True,
            issues=[],
            claims=[],
            validated_spec=spec,
        )

    def test_planner_is_invoked_and_deck_spec_flows_through_pipeline(self):
        intent = self._intent()
        deck_spec = self._deck_spec()
        context = self._context()
        process_result = self._process_result()
        slide_spec = self._slide_spec()
        validation_result = self._validation_result(slide_spec)

        with patch("backend.orchestrator.extract_intent", return_value=intent) as mock_intent, \
             patch("backend.orchestrator.plan_presentation", return_value=deck_spec) as mock_planner, \
             patch("backend.orchestrator.build_context", return_value=context) as mock_context, \
             patch("backend.orchestrator.identify_process", return_value=process_result) as mock_process, \
             patch("backend.orchestrator.generate_content", return_value=slide_spec) as mock_content, \
             patch("backend.orchestrator.validate_content", return_value=validation_result) as mock_validate:

            result = run_pipeline("Current State", "Toyota Procurement transformation.")

            self.assertEqual(result, validation_result)
            mock_intent.assert_called_once_with("Current State", "Toyota Procurement transformation.")
            mock_planner.assert_called_once_with("Toyota Procurement transformation.", intent)
            mock_context.assert_called_once_with(intent)
            mock_process.assert_called_once_with(intent, context)
            mock_content.assert_called_once_with(intent, context, process_result)
            mock_validate.assert_called_once_with(slide_spec)

    def test_downstream_modules_receive_original_signatures(self):
        """DeckSpec is kept local to the orchestrator; downstream interfaces unchanged."""
        intent = self._intent()
        deck_spec = self._deck_spec()
        context = self._context()
        process_result = self._process_result()
        slide_spec = self._slide_spec()
        validation_result = self._validation_result(slide_spec)

        with patch("backend.orchestrator.extract_intent", return_value=intent), \
             patch("backend.orchestrator.plan_presentation", return_value=deck_spec), \
             patch("backend.orchestrator.build_context", return_value=context) as mock_context, \
             patch("backend.orchestrator.identify_process", return_value=process_result) as mock_process, \
             patch("backend.orchestrator.generate_content", return_value=slide_spec) as mock_content, \
             patch("backend.orchestrator.validate_content", return_value=validation_result):

            run_pipeline("Current State", "Toyota Procurement transformation.")

            # Verify no deck_spec is passed to downstream modules.
            _, kwargs = mock_context.call_args
            self.assertNotIn("deck_spec", kwargs)
            self.assertEqual(len(mock_context.call_args.args), 1)

            _, kwargs = mock_process.call_args
            self.assertNotIn("deck_spec", kwargs)
            self.assertEqual(len(mock_process.call_args.args), 2)

            _, kwargs = mock_content.call_args
            self.assertNotIn("deck_spec", kwargs)
            self.assertEqual(len(mock_content.call_args.args), 3)

    def test_pipeline_returns_invalid_result_when_validation_fails(self):
        intent = self._intent()
        deck_spec = self._deck_spec()
        context = self._context()
        process_result = self._process_result()
        slide_spec = self._slide_spec()
        validation_result = ValidationResult(
            is_valid=False,
            issues=["Spec failed validation."],
            claims=[],
            validated_spec=None,
        )

        with patch("backend.orchestrator.extract_intent", return_value=intent), \
             patch("backend.orchestrator.plan_presentation", return_value=deck_spec), \
             patch("backend.orchestrator.build_context", return_value=context), \
             patch("backend.orchestrator.identify_process", return_value=process_result), \
             patch("backend.orchestrator.generate_content", return_value=slide_spec), \
             patch("backend.orchestrator.validate_content", return_value=validation_result):

            result = run_pipeline("Current State", "Toyota Procurement transformation.")

            self.assertFalse(result.is_valid)
            self.assertEqual(result.issues, ["Spec failed validation."])


if __name__ == "__main__":
    unittest.main()

"""
Sprint H.2 — Intelligent Intent Extraction tests.

These tests exercise the deterministic entity extractor and the hybrid
LLM-fallback path in ``backend/modules/intent.py``. All LLM calls are mocked.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from backend.modules import intent
from backend.modules.intent import extract_intent


class IntentExtractionTests(unittest.TestCase):
    """End-to-end tests for the hybrid intent extraction module."""

    def _extract(self, content: str, title: str = "Current State") -> intent.IntentResult:
        """Run extraction with the LLM fallback disabled to guarantee no API calls."""
        with patch.object(intent, "_extract_intent_llm", return_value={}):
            return extract_intent(title, content)

    def test_microsoft_procurement(self):
        """Full extraction for the success-criteria prompt."""
        content = (
            "Create an Executive Summary slide for Microsoft's AI Procurement "
            "Transformation proposal for the board."
        )
        result = self._extract(content)

        self.assertEqual(result.company, "Microsoft")
        self.assertEqual(result.industry, "Technology")
        self.assertEqual(result.business_function, "Procurement")
        self.assertEqual(result.audience, "Senior Leadership")
        self.assertEqual(result.objective, "AI Procurement Transformation proposal")
        self.assertEqual(result.slide_type, "operating_model")
        self.assertGreaterEqual(result.confidence, 0.75)
        self.assertEqual(result.metadata.get("extraction_source"), "deterministic")

    def test_ey_hr_transformation(self):
        """Known company + Human Resources + board audience."""
        content = "Create a board update deck for EY's Human Resources transformation."
        result = self._extract(content)

        self.assertEqual(result.company, "EY")
        self.assertEqual(result.industry, "Financial Services")
        self.assertEqual(result.business_function, "Human Resources")
        self.assertEqual(result.audience, "Board of Directors")
        self.assertEqual(result.objective, "Human Resources transformation")

    def test_amazon_supply_chain(self):
        """Known company + supply chain function."""
        content = "Build a supply chain modernization proposal for Amazon's leadership."
        result = self._extract(content)

        self.assertEqual(result.company, "Amazon")
        self.assertEqual(result.industry, "Retail")
        self.assertEqual(result.business_function, "Supply Chain")
        self.assertEqual(result.audience, "Senior Leadership")

    def test_banking_finance(self):
        """Industry and business function from sector/function words."""
        content = "Prepare a finance strategy for the banking sector."
        result = self._extract(content)

        self.assertIsNone(result.company)
        self.assertEqual(result.industry, "Financial Services")
        self.assertEqual(result.business_function, "Finance")

    def test_healthcare_operations(self):
        """Industry and operations function."""
        content = "Build an operating model for Healthcare operations."
        result = self._extract(content)

        self.assertIsNone(result.company)
        self.assertEqual(result.industry, "Healthcare")
        self.assertEqual(result.business_function, "Operations")
        self.assertEqual(result.objective, "Healthcare operations")

    def test_unknown_company(self):
        """Company regex works for names not in the known-companies table."""
        content = "Create a slide for AcmeCorp's procurement process for the leadership team."
        result = self._extract(content)

        self.assertEqual(result.company, "AcmeCorp")
        self.assertIsNone(result.industry)
        self.assertEqual(result.business_function, "Procurement")
        self.assertEqual(result.audience, "Senior Leadership")

    def test_missing_industry(self):
        """Function and audience detected; company and industry missing."""
        content = "Create a procurement proposal for the board."
        result = self._extract(content)

        self.assertIsNone(result.company)
        self.assertIsNone(result.industry)
        self.assertEqual(result.business_function, "Procurement")
        self.assertEqual(result.audience, "Board of Directors")

    def test_audience_extraction(self):
        """Audience aliases are normalized to canonical values."""
        content = "Create an executive summary for the Executive Committee."
        result = self._extract(content)

        self.assertEqual(result.audience, "Board of Directors")

    def test_objective_extraction(self):
        """Objective is extracted from the phrase after the company."""
        content = "Create a slide for Microsoft's AI Procurement Transformation proposal."
        result = self._extract(content)

        self.assertEqual(result.objective, "AI Procurement Transformation proposal")

    def test_low_confidence_llm_fallback(self):
        """When deterministic extraction is weak, the LLM fallback fills gaps."""
        content = "Build a deck."
        llm_values = {
            "company": "Fallback Co",
            "industry": "Technology",
            "business_function": "Finance",
            "audience": "Board of Directors",
            "objective": "Fallback objective",
            "slide_type": "process_flow",
            "confidence": 0.82,
        }

        with patch.object(intent, "_extract_intent_llm", return_value=llm_values) as mock_llm:
            result = extract_intent("Current State", content)
            mock_llm.assert_called_once()

        self.assertEqual(result.company, "Fallback Co")
        self.assertEqual(result.industry, "Technology")
        self.assertEqual(result.business_function, "Finance")
        self.assertEqual(result.audience, "Board of Directors")
        self.assertEqual(result.objective, "Fallback objective")
        self.assertEqual(result.slide_type, "process_flow")
        self.assertEqual(result.metadata.get("extraction_source"), "hybrid")

    def test_alias_matching(self):
        """Aliases such as 'cloud' and 'sourcing' map to canonical values."""
        content = "Create a slide for cloud sourcing."
        result = self._extract(content)

        self.assertEqual(result.industry, "Technology")
        self.assertEqual(result.business_function, "Procurement")

    def test_frontend_prompt_in_title_field(self):
        """Regression: the Office.js add-in sends the full prompt as title with empty content.

        The deterministic extractor must still find company, industry, and function
        so the pipeline does not stop with a clarification slide.
        """
        prompt = (
            "Create a transformation timeline for Microsoft's AI Procurement "
            "Transformation from Q1 2026 to Q4 2027 with six major milestones."
        )
        result = self._extract(content="", title=prompt)

        self.assertEqual(result.company, "Microsoft")
        self.assertEqual(result.industry, "Technology")
        self.assertEqual(result.business_function, "Procurement")
        self.assertIn("AI Procurement Transformation", result.objective)
        self.assertIsNotNone(result.objective)

    def test_curly_possessive_unilever_prompt(self):
        """Regression: curly apostrophes should not hide the company name."""
        content = (
            "Create a consulting presentation for Unilever’s HR Transformation using AI. "
            "The audience is the CHRO and Executive Committee."
        )
        result = self._extract(content)

        self.assertEqual(result.company, "Unilever")
        self.assertEqual(result.industry, "Retail")
        self.assertEqual(result.business_function, "Human Resources")
        self.assertEqual(result.audience, "Board of Directors")

    def test_structured_clarification_company_answer(self):
        """Regression: plan-preview clarification answers are keyed by field id."""
        content = (
            "Create a consulting presentation for HR Transformation using AI.\n\n"
            "Clarification answers:\n"
            "- company: hindustan uniliver"
        )
        result = self._extract(content)

        self.assertEqual(result.company, "Hindustan Unilever")
        self.assertEqual(result.industry, "Retail")
        self.assertEqual(result.business_function, "Human Resources")


if __name__ == "__main__":
    unittest.main()

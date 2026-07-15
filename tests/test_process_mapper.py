import unittest
from unittest.mock import patch

from backend.modules.process_mapper import identify_process
from schemas.context import EnterpriseContext
from schemas.intent import IntentResult


class ProcessMapperTests(unittest.TestCase):
    def test_requested_business_functions_map_to_expected_processes(self):
        cases = [
            ("Nike", "Retail", "Finance", "Record-to-Report", "Finance"),
            ("Toyota", "Automotive", "Procurement", "Procure-to-Pay", "Procurement"),
            ("Microsoft", "Technology", "HR", "Hire-to-Retire", "Human Resources"),
            ("Amazon", "Retail", "Sales", "Order-to-Cash", "Sales"),
            ("Unknown", "Manufacturing", "Manufacturing", "Manufacturing Operations", "Manufacturing"),
        ]

        with patch("backend.modules.process_mapper._call_process_mapper_llm") as llm_call:
            for company, industry, function, expected_process, expected_family in cases:
                with self.subTest(company=company, business_function=function):
                    result = identify_process(
                        IntentResult(
                            company=company,
                            industry=industry,
                            business_function=function,
                            slide_type="Current State",
                        ),
                        EnterpriseContext(
                            company=company,
                            industry=industry,
                            business_function=function,
                            company_summary=f"{company} context.",
                        ),
                    )

                    self.assertEqual(result.process_name, expected_process)
                    self.assertEqual(result.process_family, expected_family)
                    self.assertGreater(result.confidence, 0)
                    self.assertTrue(result.stages)

            llm_call.assert_not_called()

    def test_sparse_intent_can_map_from_raw_content(self):
        with patch("backend.modules.process_mapper._call_process_mapper_llm") as llm_call:
            result = identify_process(
                IntentResult(
                    slide_type="Current State",
                    raw_title="Current State",
                    raw_content="Create a finance view for Nike.",
                ),
                EnterpriseContext(company="Nike", industry="Retail"),
            )

            self.assertEqual(result.process_name, "Record-to-Report")
            self.assertTrue(result.stages)
            llm_call.assert_not_called()


if __name__ == "__main__":
    unittest.main()

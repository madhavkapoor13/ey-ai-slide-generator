import json
import unittest
from unittest.mock import patch

from backend.modules.context import build_context
from schemas.intent import IntentResult


def _gemini_payload(company: str) -> dict:
    slug = company.lower().replace(" ", "-").replace("&", "and")
    return {
        "text": json.dumps(
            {
                "company": company,
                "industry": "Technology" if company in {"Microsoft", "Apple"} else "Retail",
                "business_function": "Finance",
                "company_summary": f"{company} is a publicly documented enterprise with global operations.",
                "facts": [
                    {
                        "statement": f"{company} publishes investor information for public stakeholders.",
                        "source": f"{company} Investor Relations",
                        "url": f"https://example.com/{slug}/investors",
                        "type": "company_fact",
                    },
                    {
                        "statement": f"{company} reports business information through annual reporting channels.",
                        "source": f"{company} Annual Report",
                        "url": f"https://example.com/{slug}/annual-report",
                        "type": "company_fact",
                    },
                    {
                        "statement": f"{company} maintains an official public website.",
                        "source": f"{company} Official Website",
                        "url": f"https://example.com/{slug}",
                        "type": "company_fact",
                    },
                ],
                "sources": [
                    {
                        "source": f"{company} Investor Relations",
                        "url": f"https://example.com/{slug}/investors",
                        "type": "investor_relations",
                    },
                    {
                        "source": f"{company} Annual Report",
                        "url": f"https://example.com/{slug}/annual-report",
                        "type": "annual_report",
                    },
                    {
                        "source": f"{company} Official Website",
                        "url": f"https://example.com/{slug}",
                        "type": "official_website",
                    },
                ],
                "warnings": [],
            }
        ),
        "citations": [],
        "model": "gemini-test",
    }


def _parsed_payload(company: str) -> dict:
    """Return the parsed JSON payload that the router path expects."""
    raw = _gemini_payload(company)
    return json.loads(raw["text"])


class ContextBuilderTests(unittest.TestCase):
    def test_requested_company_contexts_are_structured_and_grounded(self):
        companies = ["Nike", "Microsoft", "Toyota", "EY", "Apple"]

        def fake_call(_intent, company, _industry, _business_function):
            return _parsed_payload(company)

        with patch("backend.modules.context._call_context_llm", side_effect=fake_call):
            for company in companies:
                with self.subTest(company=company):
                    context = build_context(
                        IntentResult(
                            company=company,
                            industry="Retail",
                            business_function="Finance",
                            slide_type="Current State",
                        )
                    )

                    self.assertEqual(context.company, company)
                    self.assertTrue(context.company_summary)
                    self.assertGreaterEqual(len(context.facts), 3)
                    self.assertTrue(context.sources)
                    for fact in context.facts:
                        self.assertTrue(fact.statement)
                        self.assertTrue(fact.source)
                        self.assertTrue(fact.url)

    def test_missing_company_returns_warning_context(self):
        context = build_context(IntentResult(slide_type="Current State"))

        self.assertEqual(context.company, "Unknown")
        self.assertTrue(context.warnings)
        self.assertEqual(context.facts, [])


if __name__ == "__main__":
    unittest.main()

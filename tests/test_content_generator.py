import json
import unittest
from unittest.mock import patch

from backend.modules.content_generator import generate_content
from schemas.context import EnterpriseContext, ResearchFact, ResearchSource
from schemas.intent import IntentResult
from schemas.process import ProcessResult
from schemas.slide_spec import SlideSpec


def _context(company: str, industry: str, business_function: str) -> EnterpriseContext:
    return EnterpriseContext(
        company=company,
        industry=industry,
        business_function=business_function,
        company_summary=f"{company} is represented by grounded public company context.",
        facts=[
            ResearchFact(
                statement=f"{company} publishes public business information.",
                source=f"{company} Official Website",
                url=f"https://example.com/{company.lower()}",
                type="company_fact",
            )
        ],
        sources=[
            ResearchSource(
                source=f"{company} Official Website",
                url=f"https://example.com/{company.lower()}",
                type="official_website",
            )
        ],
    )


def _process(process_name: str, family: str) -> ProcessResult:
    return ProcessResult(
        process_name=process_name,
        process_family=family,
        confidence=0.94,
        reasoning=f"{family} maps to {process_name}.",
        stages=[
            "Intake",
            "Preparation",
            "Execution",
            "Control Review",
            "Reporting",
            "Governance",
        ],
    )


def _llm_payload(company: str, family: str, process_name: str) -> str:
    stages = []
    pain_points = []
    for label in ["Intake", "Preparation", "Execution", "Control Review", "Reporting", "Governance"]:
        stages.append(
            {
                "label": label,
                "activities": [
                    f"Coordinate {label.lower()} inputs with accountable owners.",
                    f"Validate {label.lower()} readiness against policy expectations.",
                    f"Resolve {label.lower()} exceptions through defined ownership.",
                    f"Maintain {label.lower()} documentation for management visibility.",
                    f"Prepare {label.lower()} handoffs for the next process stage.",
                ],
            }
        )
        pain_points.append(
            {
                "stage": label,
                "text": f"Fragmented ownership can slow {label.lower()} decisions.",
            }
        )

    return json.dumps(
        {
            "title": "Current State",
            "subtitle": f"{company} {family} Operating Model",
            "executive_summary": f"{company} {family} current state is organized around the {process_name} process.",
            "stages": stages,
            "pain_points": pain_points,
            "metadata": {
                "company": company,
                "industry": "Test Industry",
                "process": process_name,
            },
        }
    )


class ContentGeneratorTests(unittest.TestCase):
    def test_requested_cases_generate_complete_slide_spec(self):
        cases = [
            ("Nike", "Retail", "Finance", "Record-to-Report"),
            ("Toyota", "Automotive", "Procurement", "Procure-to-Pay"),
            ("Microsoft", "Technology", "Human Resources", "Hire-to-Retire"),
            ("Apple", "Technology", "Supply Chain", "Plan-Source-Make-Deliver"),
            ("EY", "Professional Services", "Human Resources", "Hire-to-Retire"),
        ]

        def fake_call(_intent, context, process_result):
            return _llm_payload(context.company, process_result.process_family, process_result.process_name)

        with patch("backend.modules.content_generator._call_content_llm", side_effect=fake_call):
            for company, industry, family, process_name in cases:
                with self.subTest(company=company, family=family):
                    spec = generate_content(
                        IntentResult(
                            company=company,
                            industry=industry,
                            business_function=family,
                            slide_type="Current State",
                        ),
                        _context(company, industry, family),
                        _process(process_name, family),
                    )

                    SlideSpec.model_validate(spec.model_dump())
                    raw = spec.raw_spec
                    self.assertTrue(raw["executive_summary"])
                    self.assertEqual(len(raw["stages"]), 6)
                    self.assertTrue(all(len(stage["activities"]) == 5 for stage in raw["stages"]))
                    self.assertEqual(len(raw["pain_points"]), 6)
                    self.assertEqual(len(raw["risks"]), 6)
                    self.assertEqual(raw["metadata"]["company"], company)
                    self.assertEqual(raw["metadata"]["industry"], industry)
                    self.assertEqual(raw["metadata"]["process"], process_name)
                    self.assertEqual(raw["summary"]["metrics"], [])
                    self.assertLessEqual(_sentence_count(raw["executive_summary"]), 2)
                    for stage in raw["stages"]:
                        self.assertTrue(_consulting_stage_name(stage["title"]))
                        for activity in stage["activities"]:
                            self.assertGreaterEqual(len(activity.split()), 3)
                            self.assertLessEqual(len(activity.split()), 7)
                            self.assertFalse(activity.lower().startswith("responsible for"))
                    for pain_point in raw["pain_points"]:
                        self.assertTrue(_has_business_impact(pain_point["text"]))

    def test_unsupported_numeric_claims_are_removed(self):
        payload = json.loads(_llm_payload("Nike", "Finance", "Record-to-Report"))
        payload["executive_summary"] = "Close cycle improves by 25% with $5M ROI."
        payload["stages"][0]["activities"][0] = "Reduce cycle time by 10 days."
        payload["pain_points"][0]["text"] = "Manual work creates 15% error rates."

        with patch("backend.modules.content_generator._call_content_llm", return_value=json.dumps(payload)):
            spec = generate_content(
                IntentResult(company="Nike", industry="Retail", business_function="Finance", slide_type="Current State"),
                _context("Nike", "Retail", "Finance"),
                _process("Record-to-Report", "Finance"),
            )

        raw_text = json.dumps(spec.raw_spec)
        self.assertNotIn("25%", raw_text)
        self.assertNotIn("$5M", raw_text)
        self.assertNotIn("10 days", raw_text)
        self.assertNotIn("15%", raw_text)

    def test_quality_rules_normalize_generic_llm_output(self):
        payload = json.loads(_llm_payload("Toyota", "Procurement", "Procure-to-Pay"))
        payload["executive_summary"] = (
            "Toyota is a global company with a long history. "
            "The procurement model covers purchasing. "
            "This sentence should be removed."
        )
        payload["stages"][0]["label"] = "Create Purchase Order"
        payload["stages"][0]["activities"] = [
            "Responsible for validating supplier quotations across multiple approval workflows",
            "Approving purchase requisitions",
            "Monitor inventory availability for all production teams",
            "Execute invoice reconciliation with accountable owners",
            "Forecast production demand",
        ]
        payload["pain_points"][0]["text"] = "Poor communication."

        with patch("backend.modules.content_generator._call_content_llm", return_value=json.dumps(payload)):
            spec = generate_content(
                IntentResult(
                    company="Toyota",
                    industry="Automotive",
                    business_function="Procurement",
                    slide_type="Current State",
                ),
                _context("Toyota", "Automotive", "Procurement"),
                _process("Procure-to-Pay", "Procurement"),
            )

        raw = spec.raw_spec
        self.assertEqual(_sentence_count(raw["executive_summary"]), 2)
        self.assertNotEqual(raw["stages"][0]["title"], "Create Purchase Order")
        for activity in raw["stages"][0]["activities"]:
            self.assertGreaterEqual(len(activity.split()), 3)
            self.assertLessEqual(len(activity.split()), 7)
            self.assertFalse(activity.lower().startswith("responsible for"))
        self.assertTrue(_has_business_impact(raw["pain_points"][0]["text"]))

def _sentence_count(text: str) -> int:
    return len([part for part in text.replace("!", ".").replace("?", ".").split(".") if part.strip()])


def _consulting_stage_name(text: str) -> bool:
    terms = [
        "Management",
        "Governance",
        "Control",
        "Visibility",
        "Administration",
        "Validation",
        "Support",
    ]
    return any(term in text for term in terms)


def _has_business_impact(text: str) -> bool:
    terms = [
        "delays",
        "reduces",
        "limits",
        "increases",
        "impacts",
        "constrains",
        "creates",
        "weakens",
        "disrupts",
        "erodes",
    ]
    return any(term in text.lower() for term in terms)


if __name__ == "__main__":
    unittest.main()

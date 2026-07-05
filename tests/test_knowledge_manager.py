import unittest
from unittest.mock import MagicMock, patch

from backend.modules import knowledge_manager
from backend.modules.knowledge_manager import get_knowledge
from schemas.knowledge import DomainKnowledge


class KnowledgeManagerTests(unittest.TestCase):
    def test_finance_knowledge_retrieval(self):
        knowledge = get_knowledge("Technology", "Finance")

        self.assertEqual(knowledge.domain, "Finance")
        self.assertTrue(knowledge.common_kpis)
        self.assertTrue(knowledge.common_pain_points)
        self.assertTrue(knowledge.transformation_themes)
        self.assertTrue(knowledge.common_risks)
        self.assertIn("Days to close", knowledge.common_kpis)
        self.assertIn("Manual reconciliation across multiple systems", knowledge.common_pain_points)

    def test_procurement_knowledge_retrieval(self):
        knowledge = get_knowledge("Retail", "Procurement")

        self.assertEqual(knowledge.domain, "Procurement")
        self.assertIn("Purchase order cycle time", knowledge.common_kpis)
        self.assertIn("Maverick spend outside contracted suppliers", knowledge.common_pain_points)
        self.assertIn("Supplier collaboration portals and digital catalogs", knowledge.transformation_themes)

    def test_alias_matching_record_to_report(self):
        knowledge = get_knowledge("Unknown", "Record-to-Report")

        self.assertEqual(knowledge.domain, "Finance")
        self.assertIn("record-to-report", knowledge.aliases)

    def test_human_resources_knowledge_retrieval(self):
        knowledge = get_knowledge("Unknown", "Human Resources")

        self.assertEqual(knowledge.domain, "Human Resources")
        self.assertIn("Employee turnover rate", knowledge.common_kpis)
        self.assertIn("Time to fill open positions", knowledge.common_kpis)

    def test_supply_chain_knowledge_retrieval(self):
        knowledge = get_knowledge("Automotive", "Supply Chain")

        self.assertEqual(knowledge.domain, "Supply Chain")
        self.assertIn("Perfect order rate", knowledge.common_kpis)

    def test_manufacturing_knowledge_retrieval(self):
        knowledge = get_knowledge("Industrial", "Manufacturing")

        self.assertEqual(knowledge.domain, "Manufacturing")
        self.assertIn("Overall equipment effectiveness", knowledge.common_kpis)

    def test_ai_knowledge_retrieval(self):
        knowledge = get_knowledge("Technology", "AI")

        self.assertEqual(knowledge.domain, "AI")
        self.assertIn("Model accuracy and precision", knowledge.common_kpis)
        self.assertIn("Siloed data and inconsistent data quality", knowledge.common_pain_points)

    def test_fallback_behavior_for_unknown_function(self):
        knowledge = get_knowledge("Unknown", "Quantum Computing")

        self.assertEqual(knowledge.domain, "General Enterprise")
        self.assertFalse(knowledge.common_kpis)
        self.assertTrue(knowledge.common_pain_points)
        self.assertTrue(knowledge.transformation_themes)
        self.assertTrue(knowledge.common_risks)

    def test_single_domain_match_no_merging(self):
        """
        Even if the prompt conceptually touches AI, the business function is the
        primary retrieval key and only one domain is returned.
        """
        knowledge = get_knowledge("Technology", "Finance")

        self.assertEqual(knowledge.domain, "Finance")
        self.assertNotEqual(knowledge.domain, "AI")

    def test_caching_reuses_loaded_data(self):
        # Reset cache to ensure a fresh load, then verify the file is read only once.
        knowledge_manager._knowledge_cache._data = None
        original_path = knowledge_manager._KNOWLEDGE_PATH
        original_text = original_path.read_text(encoding="utf-8")

        mock_path = MagicMock()
        mock_path.read_text.return_value = original_text

        with patch.object(knowledge_manager, "_KNOWLEDGE_PATH", mock_path):
            first = get_knowledge("Unknown", "Finance")
            second = get_knowledge("Unknown", "Procurement")

            mock_path.read_text.assert_called_once()
            self.assertEqual(first.domain, "Finance")
            self.assertEqual(second.domain, "Procurement")


if __name__ == "__main__":
    unittest.main()

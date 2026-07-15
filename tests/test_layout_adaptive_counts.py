from __future__ import annotations

import unittest

from backend.layout_engine.layout_engine import generate_layout
from schemas.visual import VisualPatternSelection


def _selection(pattern_id: str, category: str = "creative_listing") -> VisualPatternSelection:
    return VisualPatternSelection(
        pattern_id=pattern_id,
        category=category,
        confidence=0.9,
        reasoning="test",
    )


class LayoutAdaptiveCountsTests(unittest.TestCase):
    def test_cl01_synthesizes_two_cards(self):
        layout = generate_layout(_selection("CL-01"), item_count=2)
        self.assertEqual(len(layout.components), 2)
        self.assertEqual(layout.components[0].type, "executive_card")
        self.assertEqual(layout.components[0].placeholder, "card_1")

    def test_cl01_keeps_canonical_four_cards(self):
        layout = generate_layout(_selection("CL-01"), item_count=4)
        self.assertEqual(len(layout.components), 4)

    def test_ig01_synthesizes_seven_events(self):
        layout = generate_layout(_selection("IG-01", "infographic"), item_count=7)
        # 7 nodes + 6 connectors.
        nodes = [c for c in layout.components if c.type == "node"]
        connectors = [c for c in layout.components if c.type == "connector"]
        self.assertEqual(len(nodes), 7)
        self.assertEqual(len(connectors), 6)
        self.assertEqual(layout.components[0].type, "node")
        self.assertEqual(layout.components[0].placeholder, "event_1")

    def test_ig03_synthesizes_five_steps(self):
        layout = generate_layout(_selection("IG-03", "infographic"), item_count=5)
        nodes = [c for c in layout.components if c.type == "node"]
        connectors = [c for c in layout.components if c.type == "connector"]
        self.assertEqual(len(nodes), 5)
        self.assertEqual(len(connectors), 4)
        self.assertEqual(layout.components[0].type, "node")
        self.assertEqual(layout.components[0].placeholder, "step_1")

    def test_ig04_synthesizes_square_matrix_for_five_cells(self):
        layout = generate_layout(_selection("IG-04", "infographic"), item_count=5)
        cells = [c for c in layout.components if c.type == "cell"]
        labels = [c for c in layout.components if c.type == "label"]
        self.assertEqual(len(cells), 5)
        self.assertEqual(cells[0].type, "cell")
        # Axis labels from the canonical layout are preserved.
        self.assertGreater(len(labels), 0)
        # 5 items -> 3 cols, 2 rows
        self.assertEqual(layout.metadata.get("synthesized_item_count"), 5)

    def test_cl04_synthesizes_two_column_rows(self):
        layout = generate_layout(_selection("CL-04"), item_count=3)
        placeholders = [c.placeholder for c in layout.components]
        self.assertIn("left_label", placeholders)
        self.assertIn("right_label", placeholders)
        self.assertIn("left_item_3", placeholders)
        self.assertIn("right_item_3", placeholders)

    def test_single_row_cells_respect_max_cell_height(self):
        # IG-03 has max_cell_height=0.28; a single row of 3 nodes should not
        # stretch to the full body height (~0.60 normalized).
        layout = generate_layout(_selection("IG-03", "infographic"), item_count=3)
        nodes = [c for c in layout.components if c.type == "node"]
        self.assertEqual(len(nodes), 3)
        self.assertLess(nodes[0].height, 0.40)
        self.assertGreater(nodes[0].height, 0.20)

    def test_unknown_pattern_uses_fallback(self):
        layout = generate_layout(_selection("UNKNOWN"), item_count=3)
        self.assertEqual(len(layout.components), 1)


if __name__ == "__main__":
    unittest.main()

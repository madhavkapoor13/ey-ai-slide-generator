import unittest

from backend.layout_engine import layout_registry
from backend.layout_engine.layout_engine import generate_layout
from backend.layout_engine.loader import clear_cache, load_layouts
from schemas.layout import LayoutSpecification
from schemas.visual import VisualPatternSelection


class LayoutEngineTests(unittest.TestCase):

    def tearDown(self):
        clear_cache()

    def test_registry_loading(self):
        layouts = load_layouts()

        self.assertIsInstance(layouts, dict)
        self.assertIn("CL01", layouts)
        self.assertIn("CL06", layouts)
        self.assertIn("IG01", layouts)
        self.assertIn("IG06", layouts)
        self.assertIn("SECTION_DIVIDER", layouts)
        self.assertIn("GENERIC", layouts)

        for layout in layouts.values():
            self.assertIsInstance(layout, LayoutSpecification)

    def test_layout_lookup_by_id(self):
        layout = layout_registry.get_layout("CL01")

        self.assertEqual(layout.layout_id, "CL01")
        self.assertEqual(layout.visual_pattern, "CL-01")
        self.assertEqual(layout.category, "creative_listing")

    def test_find_by_pattern(self):
        layout = layout_registry.find_by_pattern("IG-03")

        self.assertIsNotNone(layout)
        self.assertEqual(layout.layout_id, "IG03")
        self.assertEqual(layout.visual_pattern, "IG-03")

    def test_unknown_pattern_fallback(self):
        selection = VisualPatternSelection(
            pattern_id="IG-99",
            category="infographic",
            confidence=0.9,
            reasoning="Unknown pattern",
        )

        layout = generate_layout(selection)

        self.assertEqual(layout.layout_id, "GENERIC")
        self.assertEqual(layout.visual_pattern, "*")

    def test_layout_validation(self):
        layouts = load_layouts()

        for layout in layouts.values():
            self.assertGreaterEqual(layout.header.height, 0.0)
            self.assertLessEqual(layout.header.height, 1.0)
            self.assertGreaterEqual(layout.footer.height, 0.0)
            self.assertLessEqual(layout.footer.height, 1.0)

            body = layout.body
            self.assertGreaterEqual(body.x, 0.0)
            self.assertLessEqual(body.x + body.width, 1.0)
            self.assertGreaterEqual(body.y, 0.0)
            self.assertLessEqual(body.y + body.height, 1.0)

    def test_coordinate_normalization(self):
        layout = layout_registry.get_layout("CL02")

        for component in layout.components:
            self.assertGreaterEqual(component.x, 0.0)
            self.assertLessEqual(component.x, 1.0)
            self.assertGreaterEqual(component.y, 0.0)
            self.assertLessEqual(component.y, 1.0)
            self.assertGreaterEqual(component.width, 0.0)
            self.assertLessEqual(component.width, 1.0)
            self.assertGreaterEqual(component.height, 0.0)
            self.assertLessEqual(component.height, 1.0)
            self.assertLessEqual(component.x + component.width, 1.0)
            self.assertLessEqual(component.y + component.height, 1.0)

    def test_component_count(self):
        cl01 = layout_registry.get_layout("CL01")
        self.assertEqual(len(cl01.components), 4)

        ig04 = layout_registry.get_layout("IG04")
        # IG-04 now includes 9 cells plus x/y axis labels.
        cells = [c for c in ig04.components if c.type == "cell"]
        self.assertEqual(len(cells), 9)

        generic = layout_registry.get_layout("GENERIC")
        self.assertEqual(len(generic.components), 1)

    def test_header_body_footer_structure(self):
        layout = layout_registry.get_layout("IG02")

        self.assertIsNotNone(layout.header)
        self.assertIsNotNone(layout.body)
        self.assertIsNotNone(layout.footer)
        self.assertGreater(len(layout.components), 0)

        # Header + body + footer should not overlap beyond the canvas.
        used_height = layout.header.height + layout.body.height + layout.footer.height
        self.assertLessEqual(used_height, 1.0)

    def test_creative_layout(self):
        selection = VisualPatternSelection(
            pattern_id="CL-04",
            category="creative_listing",
            confidence=0.9,
            reasoning="Comparison pattern",
        )

        layout = generate_layout(selection)

        self.assertEqual(layout.layout_id, "CL04")
        self.assertEqual(layout.category, "creative_listing")
        self.assertTrue(layout.supports_percentages)
        self.assertGreater(len(layout.components), 0)

    def test_infographic_layout(self):
        selection = VisualPatternSelection(
            pattern_id="IG-05",
            category="infographic",
            confidence=0.9,
            reasoning="Journey pattern",
        )

        layout = generate_layout(selection)

        self.assertEqual(layout.layout_id, "IG05")
        self.assertEqual(layout.category, "infographic")

    def test_cached_loading(self):
        first = load_layouts()
        second = load_layouts()

        self.assertIs(first, second)

    def test_generate_layout_returns_layout_specification(self):
        selection = VisualPatternSelection(
            pattern_id="CL-06",
            category="creative_listing",
            confidence=0.9,
            reasoning="Executive summary",
        )

        layout = generate_layout(selection)

        self.assertIsInstance(layout, LayoutSpecification)
        self.assertEqual(layout.layout_id, "CL06")


if __name__ == "__main__":
    unittest.main()

import unittest

from backend.design_system.theme import DesignTheme
from backend.design_system.theme_loader import (
    clear_cache,
    get_current_theme,
    load_theme,
    set_active_theme,
)
from pptx.dml.color import RGBColor
from pptx.util import Inches, Pt


class ThemeEngineTests(unittest.TestCase):

    def tearDown(self):
        clear_cache()
        set_active_theme("ey_blue")

    def test_theme_loading(self):
        theme = load_theme("ey_blue")

        self.assertIsInstance(theme, DesignTheme)
        self.assertEqual(theme.name, "ey_blue")
        self.assertEqual(theme.version, "1.0")

    def test_color_retrieval(self):
        theme = load_theme("ey_blue")

        yellow = theme.color("ey_yellow")
        self.assertIsInstance(yellow, RGBColor)
        self.assertEqual(yellow, RGBColor(255, 230, 0))

        ink = theme.color("ink")
        self.assertEqual(ink, RGBColor(31, 35, 40))

    def test_typography_retrieval(self):
        theme = load_theme("ey_blue")

        self.assertEqual(theme.font("body"), "Aptos")
        self.assertEqual(theme.font("title"), "Arial")
        self.assertIsInstance(theme.size("title"), Pt)
        self.assertEqual(theme.size("title").pt, 24.0)

    def test_spacing_retrieval(self):
        theme = load_theme("ey_blue")

        self.assertIsInstance(theme.space("left_margin"), Inches)
        self.assertAlmostEqual(theme.space("left_margin").inches, 0.6, places=5)

    def test_unknown_theme_fallback(self):
        theme = load_theme("nonexistent_theme")

        self.assertEqual(theme.name, "ey_blue")

    def test_theme_switching(self):
        set_active_theme("ey_parthenon")
        theme = get_current_theme()

        self.assertEqual(theme.name, "ey_parthenon")
        self.assertEqual(theme.color("accent"), RGBColor(31, 132, 119))

        # Switch back.
        set_active_theme("ey_blue")
        self.assertEqual(get_current_theme().name, "ey_blue")

    def test_default_active_theme(self):
        theme = get_current_theme()

        self.assertEqual(theme.name, "ey_blue")


if __name__ == "__main__":
    unittest.main()

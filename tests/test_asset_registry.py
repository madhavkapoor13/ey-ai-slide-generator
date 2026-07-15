"""
tests/test_asset_registry.py
=============================
Tests for the Presentation Asset Registry auto-discovery.

Fixtures are built at test time under ``tempfile.TemporaryDirectory()``
using ``_asset_factory``. No committed binary assets; hermetic and
offline. The default-dir cache is reset in ``tearDown`` so tests never
leak state to each other.
"""

import json
import tempfile
import unittest

from backend.presentation_assets import asset_registry
from schemas.presentation_asset import (
    AssetManifest,
    AssetPlaceholder,
    PlaceholderBinding,
    PlaceholderKind,
)
from _asset_factory import build_roadmap_manifest, write_asset_manifest, write_full_asset


class AssetRegistryTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        asset_registry.clear_cache()

    def tearDown(self):
        asset_registry.clear_cache()
        self._tmp.cleanup()

    def test_load_empty_dir(self):
        loaded = asset_registry.load_assets(self.root)
        self.assertEqual(loaded, {})

    def test_load_missing_dir(self):
        loaded = asset_registry.load_assets("/nonexistent/path/xyz")
        self.assertEqual(loaded, {})

    def test_auto_discovery_single_asset(self):
        write_full_asset(self.root, "roadmap", "ROADMAP-3PHASE-001")
        loaded = asset_registry.load_assets(self.root)

        self.assertEqual(len(loaded), 1)
        manifest = loaded["ROADMAP-3PHASE-001"]
        self.assertIsInstance(manifest, AssetManifest)
        self.assertEqual(manifest.family, "roadmap")
        self.assertEqual(manifest.density, 3)
        self.assertEqual(manifest.density_range, [3, 6])
        self.assertEqual(len(manifest.placeholders), 3)
        self.assertIsNotNone(manifest.repeating)

    def test_auto_discovery_multiple_families(self):
        write_full_asset(self.root, "roadmap", "ROADMAP-3PHASE-001")
        write_full_asset(
            self.root, "executive_summary", "EXEC-SUMMARY-001",
            manifest=build_roadmap_manifest(
                asset_id="EXEC-SUMMARY-001", family="executive_summary"
            ),
        )
        loaded = asset_registry.load_assets(self.root)

        self.assertEqual(len(loaded), 2)
        self.assertIn("ROADMAP-3PHASE-001", loaded)
        self.assertIn("EXEC-SUMMARY-001", loaded)

    def test_get_by_id(self):
        write_full_asset(self.root, "roadmap", "ROADMAP-3PHASE-001")

        found = asset_registry.get("ROADMAP-3PHASE-001", assets_dir=self.root)
        self.assertIsNotNone(found)
        self.assertEqual(found.family, "roadmap")

        missing = asset_registry.get("DOES-NOT-EXIST", assets_dir=self.root)
        self.assertIsNone(missing)

    def test_by_family_exact_and_alias(self):
        write_full_asset(self.root, "roadmap", "ROADMAP-3PHASE-001")

        exact = asset_registry.by_family("roadmap", assets_dir=self.root)
        self.assertEqual(len(exact), 1)
        self.assertEqual(exact[0].asset_id, "ROADMAP-3PHASE-001")

        alias = asset_registry.by_family("phased plan", assets_dir=self.root)
        self.assertEqual(len(alias), 1, "family_aliases should match by alias")

        no_match = asset_registry.by_family("matrix", assets_dir=self.root)
        self.assertEqual(no_match, [])

    def test_malformed_manifest_skipped(self):
        asset_dir_good = write_full_asset(self.root, "roadmap", "ROADMAP-001")

        bad_family_dir = f"{self.root}/roadmap/BAD-001"
        import os
        os.makedirs(bad_family_dir, exist_ok=True)
        with open(f"{bad_family_dir}/asset.json", "w") as f:
            f.write("{not valid json")

        loaded = asset_registry.load_assets(self.root)
        self.assertEqual(len(loaded), 1)
        self.assertIn("ROADMAP-001", loaded)
        self.assertNotIn("BAD-001", loaded)

    def test_duplicate_asset_id_keeps_first(self):
        first = write_full_asset(self.root, "roadmap", "DUP-001")
        second_family_dir = f"{self.root}/timeline/DUP-001"
        import os
        os.makedirs(second_family_dir, exist_ok=True)
        write_asset_manifest(
            second_family_dir,
            build_roadmap_manifest(asset_id="DUP-001", family="timeline"),
        )

        loaded = asset_registry.load_assets(self.root)
        self.assertEqual(len(loaded), 1)
        kept = loaded["DUP-001"]
        self.assertEqual(kept.family, "roadmap", "first occurrence should win")

    def test_get_asset_path_default_cached(self):
        write_full_asset(self.root, "roadmap", "ROADMAP-3PHASE-001")

        path = asset_registry.get_asset_path("ROADMAP-3PHASE-001", assets_dir=self.root)
        self.assertIsNotNone(path)
        self.assertTrue((path / "asset.pptx").exists())

        missing = asset_registry.get_asset_path("NOPE", assets_dir=self.root)
        self.assertIsNone(missing)

    def test_count(self):
        self.assertEqual(asset_registry.count(self.root), 0)
        write_full_asset(self.root, "roadmap", "ROADMAP-001")
        write_full_asset(
            self.root, "executive_summary", "EXEC-001",
            manifest=build_roadmap_manifest(asset_id="EXEC-001", family="executive_summary"),
        )
        self.assertEqual(asset_registry.count(self.root), 2)

    def test_explicit_dir_does_not_pollute_default_cache(self):
        write_full_asset(self.root, "roadmap", "ROADMAP-3PHASE-001")

        # Establish the default cache baseline (may contain real assets from
        # presentation_assets/ when the project has committed assets).
        default_before = asset_registry.load_assets()

        explicit = asset_registry.load_assets(self.root)
        self.assertEqual(len(explicit), 1)

        default_after = asset_registry.load_assets()
        self.assertIs(
            default_before,
            default_after,
            "explicit-dir loads must not populate or alter the default cache",
        )

    def test_default_dir_is_cached(self):
        first = asset_registry.load_assets()
        second = asset_registry.load_assets()
        self.assertIs(first, second, "default-dir loads should return the cached object")


if __name__ == "__main__":
    unittest.main()
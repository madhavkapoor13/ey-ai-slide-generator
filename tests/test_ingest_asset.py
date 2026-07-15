"""
tests/test_ingest_asset.py
============================
Tests for the offline ingestion CLI: writes a draft asset.json into the
.pptx's directory, idempotent skip without --force, --force overwrites,
directory resolution, error handling.

Hermetic: all .pptx files are created at test time via _asset_factory.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from scripts.ingest_asset import main as ingest_main
from _asset_factory import write_asset_pptx


class IngestAssetCLITests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def _read_manifest(self, asset_dir: Path | str) -> dict:
        with (Path(asset_dir) / "asset.json").open("r") as f:
            return json.load(f)

    def test_ingest_writes_draft_manifest_for_pptx_file(self):
        out_dir = os.path.join(self.root, "ROADMAP-3PHASE-001")
        os.makedirs(out_dir, exist_ok=True)
        pptx_path = os.path.join(out_dir, "asset.pptx")
        write_asset_pptx(pptx_path)

        rc = ingest_main([pptx_path])

        self.assertEqual(rc, 0)
        manifest = self._read_manifest(out_dir)
        self.assertEqual(manifest["asset_id"], "ROADMAP-3PHASE-001")
        self.assertEqual(manifest["density"], 3)
        self.assertGreater(len(manifest["placeholders"]), 0)
        self.assertIsNotNone(manifest["repeating"])

    def test_ingest_creates_asset_json_if_missing(self):
        out_dir = os.path.join(self.root, "EXEC-001")
        os.makedirs(out_dir, exist_ok=True)
        pptx_path = os.path.join(out_dir, "asset.pptx")
        write_asset_pptx(pptx_path)

        self.assertFalse(os.path.exists(os.path.join(out_dir, "asset.json")))
        ingest_main([pptx_path])
        self.assertTrue(os.path.exists(os.path.join(out_dir, "asset.json")))

    def test_ingest_idempotent_skip_without_force(self):
        out_dir = os.path.join(self.root, "ASSET-001")
        os.makedirs(out_dir, exist_ok=True)
        pptx_path = os.path.join(out_dir, "asset.pptx")
        write_asset_pptx(pptx_path)

        ingest_main([pptx_path])
        first = self._read_manifest(out_dir)

        # Manually simulate human edits to verify they are preserved.
        first["purpose"] = "Curated by Madhav"
        first["audience_tags"] = ["board", "executive"]
        with open(os.path.join(out_dir, "asset.json"), "w") as f:
            json.dump(first, f)

        # Second run (no --force) should skip.
        rc = ingest_main([pptx_path])
        self.assertEqual(rc, 0)
        second = self._read_manifest(out_dir)
        self.assertEqual(second["purpose"], "Curated by Madhav")
        self.assertEqual(second["audience_tags"], ["board", "executive"])

    def test_ingest_force_overwrites(self):
        out_dir = os.path.join(self.root, "ASSET-001")
        os.makedirs(out_dir, exist_ok=True)
        pptx_path = os.path.join(out_dir, "asset.pptx")
        write_asset_pptx(pptx_path)

        ingest_main([pptx_path])
        first = self._read_manifest(out_dir)
        first["purpose"] = "Curated"
        with open(os.path.join(out_dir, "asset.json"), "w") as f:
            json.dump(first, f)

        ingest_main([pptx_path, "--force"])
        second = self._read_manifest(out_dir)
        self.assertEqual(second["purpose"], "", "force should reset the draft")

    def test_ingest_resolves_directory_path(self):
        out_dir = os.path.join(self.root, "ROADMAP-XYZ-001")
        os.makedirs(out_dir, exist_ok=True)
        write_asset_pptx(os.path.join(out_dir, "asset.pptx"))

        rc = ingest_main([out_dir])  # directory, not the .pptx file

        self.assertEqual(rc, 0)
        manifest = self._read_manifest(out_dir)
        self.assertEqual(manifest["asset_id"], "ROADMAP-XYZ-001")

    def test_ingest_asset_id_arg_overrides(self):
        out_dir = os.path.join(self.root, "random_name")
        os.makedirs(out_dir, exist_ok=True)
        pptx_path = os.path.join(out_dir, "asset.pptx")
        write_asset_pptx(pptx_path)

        ingest_main([pptx_path, "--asset-id", "EXEC-SUMMARY-042"])
        manifest = self._read_manifest(out_dir)
        self.assertEqual(manifest["asset_id"], "EXEC-SUMMARY-042")

    def test_ingest_family_arg_overrides(self):
        out_dir = os.path.join(self.root, "misc")
        os.makedirs(out_dir, exist_ok=True)
        pptx_path = os.path.join(out_dir, "asset.pptx")
        write_asset_pptx(pptx_path)

        ingest_main([pptx_path, "--family", "timeline"])
        manifest = self._read_manifest(out_dir)
        self.assertEqual(manifest["family"], "timeline")

    def test_ingest_family_auto_detected_from_known_grandparent(self):
        out_dir = os.path.join(self.root, "presentation_assets", "roadmap", "ROADMAP-3PHASE-001")
        os.makedirs(out_dir, exist_ok=True)
        pptx_path = os.path.join(out_dir, "asset.pptx")
        write_asset_pptx(pptx_path)

        ingest_main([pptx_path])
        manifest = self._read_manifest(out_dir)
        self.assertEqual(manifest["family"], "roadmap")

    def test_ingest_missing_pptx_in_directory_errors(self):
        empty_dir = os.path.join(self.root, "empty")
        os.makedirs(empty_dir, exist_ok=True)
        with self.assertRaises(FileNotFoundError):
            ingest_main([empty_dir])


if __name__ == "__main__":
    unittest.main()
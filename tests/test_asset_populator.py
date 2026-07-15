import tempfile
import unittest
from pathlib import Path

from pptx import Presentation

from backend.presentation_assets.asset_loader import enumerate_shapes, open_for_population
from backend.presentation_assets.asset_populator import (
    PopulatorError,
    populate_asset_slide,
    populate_slide,
)
from backend.presentation_assets.asset_registry import clear_cache
from schemas.presentation_asset import (
    AssetManifest,
    AssetPlaceholder,
    PlaceholderBinding,
    PlaceholderKind,
    RepeatingGroup,
)
from schemas.slide_spec import SlideSpec
from tests._asset_factory import build_roadmap_manifest, write_full_asset


def _shape_text(slide, name: str) -> str:
    """Return the current text of the shape named ``name`` on ``slide``."""
    for shape in slide.shapes:
        if shape.name == name:
            return shape.text_frame.text if shape.has_text_frame else ""
        if shape.shape_type == 6:  # GROUP
            for child in shape.shapes:
                if child.name == name:
                    return child.text_frame.text if child.has_text_frame else ""
    return ""


class AssetPopulatorTests(unittest.TestCase):
    """Tests for Sprint E — Asset Populator."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.assets_root = Path(self.temp_dir.name) / "presentation_assets"
        write_full_asset(self.assets_root, "roadmap", "ROADMAP-3PHASE-001")
        # Ensure the default registry cache is cleared so the temp assets can be
        # discovered when tests run in arbitrary order.
        clear_cache()

    def test_populate_slide_sets_title_and_subtitle(self):
        _, slide = open_for_population(
            "ROADMAP-3PHASE-001", assets_dir=self.assets_root
        )
        manifest = build_roadmap_manifest(asset_id="ROADMAP-3PHASE-001")
        content = {
            "title": "Transformation Roadmap",
            "subtitle": "TestCo Operations — Three-Phase Journey",
        }
        populate_slide(slide, content, manifest)

        self.assertEqual(_shape_text(slide, "Title 1"), "Transformation Roadmap")
        self.assertEqual(_shape_text(slide, "SubtitleShape"), "TestCo Operations — Three-Phase Journey")

    def test_populate_slide_expands_repeating_group(self):
        _, slide = open_for_population(
            "ROADMAP-3PHASE-001", assets_dir=self.assets_root
        )
        manifest = build_roadmap_manifest(asset_id="ROADMAP-3PHASE-001")
        content = {
            "title": "Roadmap",
            "subtitle": "Subtitle",
            "phase_label": ["Discover", "Design", "Deliver"],
        }
        populate_slide(slide, content, manifest)

        self.assertEqual(_shape_text(slide, "Phase1Label"), "Discover")
        self.assertEqual(_shape_text(slide, "Phase2Label"), "Design")
        self.assertEqual(_shape_text(slide, "Phase3Label"), "Deliver")

    def test_populate_slide_clears_unused_repeating_shapes(self):
        _, slide = open_for_population(
            "ROADMAP-3PHASE-001", assets_dir=self.assets_root
        )
        manifest = build_roadmap_manifest(asset_id="ROADMAP-3PHASE-001")
        content = {
            "title": "Roadmap",
            "subtitle": "Subtitle",
            "phase_label": ["Discover", "Design"],
        }
        populate_slide(slide, content, manifest)

        self.assertEqual(_shape_text(slide, "Phase1Label"), "Discover")
        self.assertEqual(_shape_text(slide, "Phase2Label"), "Design")
        self.assertEqual(_shape_text(slide, "Phase3Label"), "")

    def test_populate_asset_slide_copies_into_target_presentation(self):
        target_prs = Presentation()
        manifest = build_roadmap_manifest(asset_id="ROADMAP-3PHASE-001")
        slide_spec = SlideSpec(
            slide_type="operating_model",
            raw_spec={
                "title": "Roadmap",
                "subtitle": "Subtitle",
                "phase_label": ["Q1", "Q2", "Q3"],
            },
            version="2.0",
            asset_id="ROADMAP-3PHASE-001",
        )

        new_slide = populate_asset_slide(
            target_prs, slide_spec, manifest, assets_dir=self.assets_root
        )

        self.assertEqual(len(target_prs.slides), 1)
        self.assertIs(new_slide, target_prs.slides[0])
        self.assertEqual(_shape_text(new_slide, "Title 1"), "Roadmap")
        self.assertEqual(_shape_text(new_slide, "Phase2Label"), "Q2")

    def test_populate_slide_looks_up_manifest_when_not_supplied(self):
        target_prs = Presentation()
        slide_spec = SlideSpec(
            slide_type="operating_model",
            raw_spec={
                "title": "Roadmap",
                "subtitle": "Subtitle",
                "phase_label": ["Alpha", "Beta", "Gamma"],
            },
            version="2.0",
            asset_id="ROADMAP-3PHASE-001",
        )

        new_slide = populate_asset_slide(
            target_prs, slide_spec, assets_dir=self.assets_root
        )

        self.assertEqual(_shape_text(new_slide, "Title 1"), "Roadmap")
        self.assertEqual(_shape_text(new_slide, "Phase1Label"), "Alpha")

    def test_populate_slide_coerces_structured_dict_content(self):
        manifest = AssetManifest(
            asset_id="STRUCTURED-001",
            family="roadmap",
            purpose="Structured phases.",
            density=2,
            density_range=[2, 4],
            placeholders=[
                AssetPlaceholder(
                    id="phase_label",
                    role="phase",
                    kind=PlaceholderKind.BODY,
                    cardinality="N",
                    binding=PlaceholderBinding(shape_name="Phase{N}Label"),
                    content_schema={"phase": "string", "owner": "string?"},
                )
            ],
            repeating=RepeatingGroup(
                group_template="Phase{N}Group",
                placeholders_per_group=["phase_label"],
                index_token="{N}",
                count=2,
            ),
        )
        _, slide = open_for_population(
            "ROADMAP-3PHASE-001", assets_dir=self.assets_root
        )
        content = {
            "phase_label": [
                {"phase": "Discover", "owner": "Alice"},
                {"phase": "Design", "owner": "Bob"},
            ],
        }
        populate_slide(slide, content, manifest)

        self.assertEqual(_shape_text(slide, "Phase1Label"), "Discover")
        self.assertEqual(_shape_text(slide, "Phase2Label"), "Design")

    def test_populate_slide_missing_shape_does_not_crash(self):
        manifest = AssetManifest(
            asset_id="MISSING-001",
            family="roadmap",
            purpose="Missing shape test.",
            density=1,
            density_range=[1, 1],
            placeholders=[
                AssetPlaceholder(
                    id="ghost",
                    role="ghost",
                    kind=PlaceholderKind.BODY,
                    binding=PlaceholderBinding(shape_name="GhostShape"),
                )
            ],
        )
        _, slide = open_for_population(
            "ROADMAP-3PHASE-001", assets_dir=self.assets_root
        )
        content = {"ghost": "Boo"}
        # Should not raise.
        populate_slide(slide, content, manifest)

    def test_populate_asset_slide_raises_when_asset_id_missing(self):
        target_prs = Presentation()
        slide_spec = SlideSpec(
            slide_type="operating_model",
            raw_spec={},
            version="2.0",
            asset_id="UNKNOWN-ASSET-999",
        )
        with self.assertRaises(PopulatorError):
            populate_asset_slide(target_prs, slide_spec)

    def test_populate_asset_slide_raises_when_manifest_missing(self):
        target_prs = Presentation()
        slide_spec = SlideSpec(
            slide_type="operating_model",
            raw_spec={},
            version="2.0",
            asset_id="UNKNOWN-ASSET-999",
        )
        with self.assertRaises(PopulatorError):
            populate_asset_slide(target_prs, slide_spec, manifest=None)


class RealAssetIngestionTests(unittest.TestCase):
    """Smoke tests for the pilot assets ingested from the EYP template deck."""

    def setUp(self):
        from backend.presentation_assets.asset_registry import clear_cache, load_assets

        clear_cache()
        self.manifests = load_assets()

    def test_pilot_assets_are_registered(self):
        for asset_id in ["TIMELINE-6STEP-001", "PROCESS-7STEP-001", "LIST-6ITEM-001"]:
            self.assertIn(asset_id, self.manifests, f"{asset_id} should be registered")

    def test_pilot_assets_populate_without_error(self):
        from backend.presentation_assets.asset_loader import open_for_population

        for asset_id in ["TIMELINE-6STEP-001", "PROCESS-7STEP-001", "LIST-6ITEM-001"]:
            manifest = self.manifests[asset_id]
            _, slide = open_for_population(asset_id)
            content = {"title": f"{asset_id} Title"}
            for placeholder in manifest.placeholders:
                if placeholder.cardinality == "N":
                    count = manifest.density
                    if placeholder.content_schema:
                        content[placeholder.id] = [
                            {k: f"{asset_id} {i + 1}" for k in placeholder.content_schema}
                            for i in range(count)
                        ]
                    else:
                        content[placeholder.id] = [f"{asset_id} {i + 1}" for i in range(count)]
            # Should not raise.
            populate_slide(slide, content, manifest)


if __name__ == "__main__":
    unittest.main()

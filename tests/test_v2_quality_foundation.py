import tempfile
import unittest

from backend.modules.deck_executor import _visual_brief_for_slide
from backend.presentation_assets import asset_registry, asset_selector
from backend.presentation_assets.asset_certifier import certify_asset
from backend.presentation_assets.fallbacks import resolve_fallback_asset_id
from backend.presentation_assets.text_fit import check_text_fit, shorten_to_fit_once
from schemas.intent import IntentResult
from schemas.presentation import SlidePlan
from schemas.presentation_asset import AssetSelectionQuery
from schemas.visual import VisualPatternSelection
from tests._asset_factory import build_roadmap_manifest, write_full_asset


class V2QualityFoundationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.assets_root = self.temp_dir.name
        asset_registry.clear_cache()

    def tearDown(self):
        asset_registry.clear_cache()

    def test_text_fit_shortens_once_then_passes(self):
        manifest = build_roadmap_manifest(asset_id="ROADMAP-TEXTFIT-001")
        manifest.placeholders[1].constraints = {"max_chars": 12, "overflow_policy": "regenerate"}
        content = {
            "title": "Roadmap",
            "subtitle": "This subtitle is far too long",
            "phase_label": ["Phase 1", "Phase 2", "Phase 3"],
        }

        initial = check_text_fit(content, manifest)
        retry = shorten_to_fit_once(content, manifest)

        self.assertFalse(initial.passed)
        self.assertTrue(retry.passed)
        self.assertEqual(retry.content["subtitle"], "This")

    def test_visual_brief_maps_roadmap_to_sequence(self):
        plan = SlidePlan(
            slide_number=1,
            slide_role="Implementation Roadmap",
            purpose="Show four implementation phases",
            required_inputs=[],
            dependencies=[],
            visualization_type="Roadmap",
        )
        selection = VisualPatternSelection(
            pattern_id="IG-02",
            category="infographic",
            confidence=0.9,
            reasoning="roadmap",
        )
        intent = IntentResult(slide_type="operating_model", audience="board")

        brief = _visual_brief_for_slide(plan, selection, intent)

        self.assertEqual(brief.message_type, "implementation_roadmap")
        self.assertEqual(brief.information_shape, "sequence")
        self.assertEqual(brief.content_units, 4)
        self.assertEqual(brief.audience, "board")

    def test_visual_brief_maps_next_steps_to_board_decisions(self):
        plan = SlidePlan(
            slide_number=1,
            slide_role="Next Steps / Decisions",
            purpose="Clarify immediate actions, owners, timing, and board decisions.",
            required_inputs=[],
            dependencies=[],
            visualization_type="Board Decisions",
        )
        selection = VisualPatternSelection(
            pattern_id="CL-06",
            category="creative_listing",
            confidence=0.9,
            reasoning="decisions",
        )
        intent = IntentResult(slide_type="operating_model", audience="board")

        brief = _visual_brief_for_slide(plan, selection, intent)

        self.assertEqual(brief.message_type, "board_decisions")
        self.assertEqual(brief.information_shape, "actions")

    def test_visual_brief_maps_future_state_to_operating_model(self):
        plan = SlidePlan(
            slide_number=1,
            slide_role="Future State",
            purpose="Describe the target-state capabilities and operating model.",
            required_inputs=[],
            dependencies=[],
            visualization_type="Capability Map",
        )
        selection = VisualPatternSelection(
            pattern_id="IG-06",
            category="infographic",
            confidence=0.9,
            reasoning="capability map",
        )
        intent = IntentResult(slide_type="operating_model", audience="board")

        brief = _visual_brief_for_slide(plan, selection, intent)

        self.assertEqual(brief.message_type, "operating_model")
        self.assertEqual(brief.information_shape, "capability_map")

    def test_selector_uses_visual_brief_manifest_fields(self):
        weak = build_roadmap_manifest(asset_id="ROADMAP-WEAK-001")
        strong = build_roadmap_manifest(asset_id="ROADMAP-STRONG-001")
        strong.message_type = "implementation_roadmap"
        strong.information_shape = "sequence"
        write_full_asset(self.assets_root, "roadmap", "ROADMAP-WEAK-001", manifest=weak)
        write_full_asset(self.assets_root, "roadmap", "ROADMAP-STRONG-001", manifest=strong)

        selection = asset_selector.select(
            AssetSelectionQuery(
                family="roadmap",
                message_type="implementation_roadmap",
                information_shape="sequence",
                content_count=3,
            ),
            assets_dir=self.assets_root,
        )

        self.assertEqual(selection.asset_id, "ROADMAP-STRONG-001")
        self.assertEqual(selection.score_breakdown["message_type"], 1.0)
        self.assertEqual(selection.score_breakdown["information_shape"], 1.0)

    def test_registry_enriches_legacy_manifest_selection_metadata(self):
        manifest = build_roadmap_manifest(asset_id="ROADMAP-LEGACY-META-001")
        manifest.message_type = None
        manifest.information_shape = None
        write_full_asset(self.assets_root, "roadmap", "ROADMAP-LEGACY-META-001", manifest=manifest)

        loaded = asset_registry.get("ROADMAP-LEGACY-META-001", assets_dir=self.assets_root)

        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.message_type, "implementation_roadmap")
        self.assertEqual(loaded.information_shape, "sequence")

    def test_asset_certification_reports_metadata(self):
        write_full_asset(self.assets_root, "roadmap", "ROADMAP-CERT-001")

        result = certify_asset("ROADMAP-CERT-001", assets_dir=self.assets_root)

        self.assertTrue(result.certified, result.errors)
        self.assertIsNotNone(result.certified_at)
        self.assertIsNotNone(result.preview_hash)

    def test_family_fallback_resolution_prefers_certified_family_asset(self):
        manifest = build_roadmap_manifest(
            asset_id="FALLBACK-ROADMAP-001",
            family="roadmap",
        )
        manifest.certification.certified = True
        write_full_asset(self.assets_root, "roadmap", "FALLBACK-ROADMAP-001", manifest=manifest)

        # Populate the default registry cache from this temp tree for fallback lookup.
        from backend.presentation_assets import fallbacks

        original_get = asset_registry.get
        try:
            asset_registry.get = lambda asset_id, assets_dir=None: original_get(asset_id, assets_dir=self.assets_root)
            self.assertEqual(resolve_fallback_asset_id("roadmap"), "FALLBACK-ROADMAP-001")
        finally:
            asset_registry.get = original_get


if __name__ == "__main__":
    unittest.main()

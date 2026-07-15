"""
tests/test_asset_selector.py
==============================
Tests for the Presentation Asset Selector — deterministic metadata-only scoring.

Covers family resolution (data map + fallback), single/multi-asset scoring,
audience/style/keyword/capacity signals, recommended_for boost, avoid_for
penalty, deterministic tie-breaking, fallback-asset sentinel when no
candidate matches, and the UserPreferences → query assembly path used by
the Deck Executor.
"""

from __future__ import annotations

import os
import tempfile
import unittest

from backend.presentation_assets import asset_registry, asset_selector
from schemas.presentation_asset import (
    AssetManifest,
    AssetPlaceholder,
    PlaceholderBinding,
    PlaceholderKind,
    AssetSelectionQuery,
    RepeatingGroup,
    UserPreferences,
)
from _asset_factory import write_full_asset, build_roadmap_manifest, write_asset_manifest


def _manifest(
    asset_id: str,
    family: str,
    *,
    audience_tags=None,
    style_tags=None,
    recommended_for=None,
    avoid_for=None,
    purpose="asset",
    family_aliases=None,
    density=3,
    density_range=None,
    certified=False,
) -> AssetManifest:
    manifest = AssetManifest(
        asset_id=asset_id,
        family=family,
        family_aliases=family_aliases or [],
        purpose=purpose,
        audience_tags=audience_tags or [],
        style_tags=style_tags or [],
        recommended_for=recommended_for or [],
        avoid_for=avoid_for or [],
        density=density,
        density_range=density_range or [density, density],
        fits_content_kinds=[],
        supports_images=False,
        placeholders=[
            AssetPlaceholder(
                id="title", role="title", kind=PlaceholderKind.TITLE,
                binding=PlaceholderBinding(native_placeholder_idx=0),
            )
        ],
    )
    manifest.certification.certified = certified
    return manifest


class AssetSelectorTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        asset_registry.clear_cache()
        asset_selector.clear_family_map_cache()

    def tearDown(self):
        asset_registry.clear_cache()
        asset_selector.clear_family_map_cache()
        self._tmp.cleanup()

    # ── Family resolution (data-driven) ──────────────────────────────────

    def test_family_for_known_pattern(self):
        self.assertEqual(asset_selector.family_for_pattern("IG-02"), "roadmap")
        self.assertEqual(asset_selector.family_for_pattern("CL-03"), "kpi")
        self.assertEqual(asset_selector.family_for_pattern("IG-04"), "comparison")
        self.assertEqual(asset_selector.family_for_pattern("CL-01"), "list")
        self.assertEqual(asset_selector.family_for_pattern("SECTION-DIVIDER"), "executive_summary")

    def test_family_for_unknown_pattern_falls_back_to_default(self):
        self.assertEqual(
            asset_selector.family_for_pattern("XX-99"),
            "executive_summary",
            "unknown pattern should fall back to the data map's _default_for_unknown",
        )

    # ── Selection with no candidates → fallback ─────────────────────────

    def test_select_returns_fallback_when_no_candidates(self):
        query = AssetSelectionQuery(family="roadmap")
        sel = asset_selector.select(query, assets_dir=self.root)
        self.assertEqual(sel.asset_id, "FALLBACK-001")
        self.assertEqual(sel.confidence, 0.0)
        self.assertEqual(sel.family, "roadmap")
        self.assertEqual(sel.candidate_ids, [])
        self.assertIn("fallback", sel.reasoning.lower())

    # ── Single candidate → selected ─────────────────────────────────────

    def test_select_single_candidate(self):
        write_full_asset(self.root, "roadmap", "ROADMAP-001")
        sel = asset_selector.select(
            AssetSelectionQuery(family="roadmap"), assets_dir=self.root
        )
        self.assertEqual(sel.asset_id, "ROADMAP-001")
        self.assertEqual(sel.family, "roadmap")
        self.assertGreater(sel.confidence, 0.0)

    # ── Scoring signals ─────────────────────────────────────────────────

    def test_audience_match_beats_no_audience(self):
        write_full_asset(
            self.root, "roadmap", "ROADMAP-A",
            manifest=_manifest("ROADMAP-A", "roadmap", audience_tags=["board"]),
        )
        write_full_asset(
            self.root, "roadmap", "ROADMAP-B",
            manifest=_manifest("ROADMAP-B", "roadmap", audience_tags=[]),
        )
        sel = asset_selector.select(
            AssetSelectionQuery(family="roadmap", audience=["board"]),
            assets_dir=self.root,
        )
        self.assertEqual(sel.asset_id, "ROADMAP-A")

    def test_style_match_beats_no_style(self):
        write_full_asset(
            self.root, "roadmap", "ROADMAP-MIN",
            manifest=_manifest("ROADMAP-MIN", "roadmap", style_tags=["minimal"]),
        )
        write_full_asset(
            self.root, "roadmap", "ROADMAP-DET",
            manifest=_manifest("ROADMAP-DET", "roadmap", style_tags=["detailed"]),
        )
        sel = asset_selector.select(
            AssetSelectionQuery(family="roadmap", style=["minimal"]),
            assets_dir=self.root,
        )
        self.assertEqual(sel.asset_id, "ROADMAP-MIN")

    def test_capacity_fit_in_range_beats_out_of_range(self):
        write_full_asset(
            self.root, "roadmap", "ROADMAP-3PH",
            manifest=_manifest("ROADMAP-3PH", "roadmap", density=3, density_range=[3, 5]),
        )
        write_full_asset(
            self.root, "roadmap", "ROADMAP-2PH",
            manifest=_manifest("ROADMAP-2PH", "roadmap", density=2, density_range=[2, 2]),
        )
        sel = asset_selector.select(
            AssetSelectionQuery(family="roadmap", content_count=4),
            assets_dir=self.root,
        )
        self.assertEqual(sel.asset_id, "ROADMAP-3PH", "4 phases fits density [3,5] better than [2,2]")

    def test_recommended_for_boost_helps_win(self):
        write_full_asset(
            self.root, "roadmap", "ROADMAP-REC",
            manifest=_manifest(
                "ROADMAP-REC", "roadmap",
                recommended_for=["Transformation Roadmap", "Strategy"],
            ),
        )
        write_full_asset(
            self.root, "roadmap", "ROADMAP-PLAIN",
            manifest=_manifest("ROADMAP-PLAIN", "roadmap", recommended_for=[]),
        )
        sel = asset_selector.select(
            AssetSelectionQuery(family="roadmap", keywords=["Transformation Roadmap"]),
            assets_dir=self.root,
        )
        self.assertEqual(sel.asset_id, "ROADMAP-REC")

    def test_avoid_for_penalty_makes_a_different_asset_win(self):
        write_full_asset(
            self.root, "roadmap", "ROADMAP-AVOID",
            manifest=_manifest(
                "ROADMAP-AVOID", "roadmap",
                avoid_for=["Technical Architecture"],
            ),
        )
        write_full_asset(
            self.root, "roadmap", "ROADMAP-OK",
            manifest=_manifest("ROADMAP-OK", "roadmap", avoid_for=[]),
        )
        sel = asset_selector.select(
            AssetSelectionQuery(family="roadmap", keywords=["Technical Architecture"]),
            assets_dir=self.root,
        )
        self.assertEqual(sel.asset_id, "ROADMAP-OK", "avoid_for hit should penalise ROADMAP-AVOID")

    # ── Tie-breaking ───────────────────────────────────────────────────

    def test_tie_break_by_lower_asset_id(self):
        # Two identical-roadmap assets → only difference is asset_id.
        write_full_asset(
            self.root, "roadmap", "ROADMAP-ZZZ",
            manifest=_manifest("ROADMAP-ZZZ", "roadmap", audience_tags=["board"]),
        )
        write_full_asset(
            self.root, "roadmap", "ROADMAP-AAA",
            manifest=_manifest("ROADMAP-AAA", "roadmap", audience_tags=["board"]),
        )
        sel = asset_selector.select(
            AssetSelectionQuery(family="roadmap", audience=["board"]),
            assets_dir=self.root,
        )
        self.assertEqual(sel.asset_id, "ROADMAP-AAA", "tie should resolve to lexicographically lower asset_id")

    # ── Candidate list exposure ──────────────────────────────────────────

    def test_candidate_ids_top_n_exposed(self):
        for i in range(7):
            write_full_asset(
                self.root, "roadmap", f"ROADMAP-{i:02d}",
                manifest=_manifest(f"ROADMAP-{i:02d}", "roadmap"),
            )
        sel = asset_selector.select(
            AssetSelectionQuery(family="roadmap"), assets_dir=self.root
        )
        self.assertEqual(len(sel.candidate_ids), 5, "top-N should be 5")
        self.assertEqual(sel.candidate_ids, sorted(sel.candidate_ids), "candidates should be sorted by tiebreak")

    # ── Confidence in [0, 1] ─────────────────────────────────────────────

    def test_confidence_in_unit_interval(self):
        write_full_asset(
            self.root, "roadmap", "ROADMAP-001",
            manifest=_manifest(
                "ROADMAP-001", "roadmap",
                audience_tags=["board"], style_tags=["minimal"],
                recommended_for=["Transformation Roadmap"],
            ),
        )
        sel = asset_selector.select(
            AssetSelectionQuery(
                family="roadmap", audience=["board"], style=["minimal"],
                keywords=["Transformation Roadmap"],
            ),
            assets_dir=self.root,
        )
        self.assertGreaterEqual(sel.confidence, 0.0)
        self.assertLessEqual(sel.confidence, 1.0)

    # ── Family aliases filter candidates by alias too ───────────────────

    def test_family_alias_matches_expanded_candidate_pool(self):
        write_full_asset(
            self.root, "roadmap", "ROADMAP-001",
            manifest=_manifest(
                "ROADMAP-001", "roadmap", family_aliases=["phased plan"],
            ),
        )
        # Querying by the alias name should still find the asset.
        sel = asset_selector.select(
            AssetSelectionQuery(family="phased plan"), assets_dir=self.root
        )
        self.assertEqual(sel.asset_id, "ROADMAP-001")

    def test_exact_family_beats_alias_candidate_pool(self):
        write_full_asset(
            self.root, "roadmap", "ROADMAP-ALIAS",
            manifest=_manifest(
                "ROADMAP-ALIAS",
                "roadmap",
                family_aliases=["next_steps"],
                recommended_for=["next steps"],
                density=3,
                density_range=[3, 4],
            ),
        )
        write_full_asset(
            self.root, "next_steps", "NEXTSTEPS-EXACT",
            manifest=_manifest(
                "NEXTSTEPS-EXACT",
                "next_steps",
                recommended_for=["next steps"],
                density=8,
                density_range=[4, 8],
            ),
        )

        sel = asset_selector.select(
            AssetSelectionQuery(family="next_steps", keywords=["next steps"], content_count=3),
            assets_dir=self.root,
        )

        self.assertEqual(sel.asset_id, "NEXTSTEPS-EXACT")

    def test_require_certified_never_selects_uncertified_asset(self):
        write_full_asset(
            self.root, "roadmap", "ROADMAP-DRAFT",
            manifest=_manifest("ROADMAP-DRAFT", "roadmap", certified=False),
        )

        sel = asset_selector.select(
            AssetSelectionQuery(family="roadmap", require_certified=True),
            assets_dir=self.root,
        )

        self.assertEqual(sel.asset_id, "FALLBACK-001")

    # ── Empty query-side tags don't penalize ─────────────────────────────

    def test_empty_query_tags_dont_penalize(self):
        write_full_asset(
            self.root, "roadmap", "ROADMAP-001",
            manifest=_manifest("ROADMAP-001", "roadmap", audience_tags=["board"]),
        )
        sel = asset_selector.select(
            AssetSelectionQuery(family="roadmap", audience=[], style=[]),
            assets_dir=self.root,
        )
        self.assertEqual(sel.asset_id, "ROADMAP-001")
        # audience=0 but capacity=neutral (0.5) so confidence > 0
        self.assertGreater(sel.confidence, 0.0)


class UserPreferencesTests(unittest.TestCase):

    def test_user_preferences_defaults(self):
        p = UserPreferences()
        self.assertEqual(p.audience, [])
        self.assertEqual(p.style, [])
        self.assertIsNone(p.density)
        self.assertIsNone(p.allow_images)

    def test_user_preferences_construction(self):
        p = UserPreferences(audience=["board"], style=["minimal"], density="comfortable")
        self.assertEqual(p.audience, ["board"])
        self.assertEqual(p.style, ["minimal"])
        self.assertEqual(p.density, "comfortable")


if __name__ == "__main__":
    unittest.main()

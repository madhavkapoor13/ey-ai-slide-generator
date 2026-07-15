"""
tests/test_asset_manifest_conformance.py
==========================================
Tests for the Manifest Conformance checker.

Validates that a content dict (``SlideSpec.raw_spec`` keyed by manifest
placeholder ids) conforms to an ``AssetManifest``: required placeholders
present and non-empty, repeating cardinalities within ``density_range``,
``content_schema`` structurally satisfied, and unknown keys flagged.
"""

from __future__ import annotations

import unittest

from backend.presentation_assets.manifest_conformance import check_conformance
from schemas.presentation_asset import (
    AssetManifest,
    AssetPlaceholder,
    PlaceholderBinding,
    PlaceholderKind,
    RepeatingGroup,
)


def _manifest(
    *,
    placeholders: list[AssetPlaceholder],
    density_range: list[int] = (3, 6),
    repeating: RepeatingGroup | None = None,
) -> AssetManifest:
    return AssetManifest(
        asset_id="TEST-001",
        family="roadmap",
        purpose="test",
        density=density_range[0],
        density_range=list(density_range),
        placeholders=placeholders,
        repeating=repeating,
    )


def _ph(
    pid: str,
    *,
    role: str = "x",
    kind: PlaceholderKind = PlaceholderKind.BODY,
    cardinality: str = "1",
    required: bool = True,
    content_schema: dict | None = None,
) -> AssetPlaceholder:
    return AssetPlaceholder(
        id=pid,
        role=role,
        kind=kind,
        cardinality=cardinality,
        required=required,
        content_schema=content_schema or {},
        binding=PlaceholderBinding(shape_name=pid),
    )


class ManifestConformanceTests(unittest.TestCase):

    def test_conforms_ok(self):
        manifest = _manifest(
            placeholders=[
                _ph("title"),
                _ph("subtitle", required=True),
                _ph("phase_label", cardinality="N", required=False),
            ],
        )
        content = {"title": "Board Update", "subtitle": "FY26", "phase_label": ["P1", "P2"]}
        self.assertEqual(check_conformance(content, manifest), [])

    def test_missing_required_single(self):
        manifest = _manifest(placeholders=[_ph("title")])
        issues = check_conformance({}, manifest)
        self.assertEqual(len(issues), 1)
        self.assertIn("'title'", issues[0])

    def test_empty_required_single_flagged(self):
        manifest = _manifest(placeholders=[_ph("title")])
        issues = check_conformance({"title": ""}, manifest)
        self.assertEqual(len(issues), 1)
        self.assertIn("missing or empty", issues[0])

    def test_optional_missing_ok(self):
        manifest = _manifest(placeholders=[_ph("subtitle", required=False)])
        self.assertEqual(check_conformance({}, manifest), [])

    def test_repeating_too_many(self):
        manifest = _manifest(
            placeholders=[_ph("phase_label", cardinality="N", required=False)],
            density_range=(3, 3),
        )
        issues = check_conformance({"phase_label": ["P1", "P2", "P3", "P4"]}, manifest)
        self.assertTrue(any("exceeds density max 3" in i for i in issues), issues)

    def test_repeating_too_few_required(self):
        manifest = _manifest(
            placeholders=[_ph("phase_label", cardinality="N", required=True)],
            density_range=(3, 6),
        )
        issues = check_conformance({"phase_label": ["P1"]}, manifest)
        self.assertTrue(any("below density min 3" in i for i in issues), issues)

    def test_repeating_must_be_list(self):
        manifest = _manifest(
            placeholders=[_ph("phase_label", cardinality="N", required=False)],
            density_range=(1, 6),
        )
        issues = check_conformance({"phase_label": "not a list"}, manifest)
        self.assertTrue(any("must be a list" in i for i in issues), issues)

    def test_repeating_missing_optional_ok(self):
        manifest = _manifest(
            placeholders=[_ph("phase_label", cardinality="N", required=False)],
            density_range=(3, 6),
        )
        self.assertEqual(check_conformance({}, manifest), [])

    def test_repeating_missing_required_flagged(self):
        manifest = _manifest(
            placeholders=[_ph("phase_label", cardinality="N", required=True)],
            density_range=(3, 6),
        )
        issues = check_conformance({}, manifest)
        self.assertTrue(any("'phase_label' is missing" in i for i in issues), issues)

    def test_unknown_content_keys_flagged(self):
        manifest = _manifest(placeholders=[_ph("title")])
        issues = check_conformance({"title": "OK", "extra_field": "x"}, manifest)
        self.assertTrue(any("keys not declared in manifest" in i for i in issues), issues)

    def test_structured_content_schema_missing_required_field(self):
        manifest = _manifest(
            placeholders=[
                _ph(
                    "phase_label",
                    cardinality="N",
                    required=False,
                    content_schema={"label": "string", "owner": "string?"},
                )
            ],
            density_range=(1, 6),
        )
        # "owner" is optional (suffix "?"), but "label" is required.
        issues = check_conformance(
            {"phase_label": [{"owner": "Alice"}]},  # missing required "label"
            manifest,
        )
        self.assertTrue(any("missing required content field 'label'" in i for i in issues), issues)

    def test_structured_content_schema_wrong_type(self):
        manifest = _manifest(
            placeholders=[
                _ph(
                    "kpi",
                    cardinality="N",
                    required=False,
                    content_schema={"value": "string"},
                )
            ],
            density_range=(1, 6),
        )
        issues = check_conformance({"kpi": [{"value": 42}]}, manifest)
        self.assertTrue(any("must be string" in i for i in issues), issues)

    def test_structured_content_schema_list_type(self):
        manifest = _manifest(
            placeholders=[
                _ph(
                    "phase",
                    cardinality="N",
                    required=False,
                    content_schema={"deliverables": "string[]?"},
                )
            ],
            density_range=(1, 6),
        )
        # deliverables is optional list, but if provided must be a list
        issues = check_conformance(
            {"phase": [{"deliverables": "not a list"}]},
            manifest,
        )
        self.assertTrue(any("must be string[]" in i for i in issues), issues)

    def test_structured_content_schema_optional_present_ok(self):
        manifest = _manifest(
            placeholders=[
                _ph(
                    "phase",
                    cardinality="N",
                    required=False,
                    content_schema={"label": "string", "owner": "string?"},
                )
            ],
            density_range=(1, 6),
        )
        self.assertEqual(
            check_conformance(
                {"phase": [{"label": "Discover", "owner": "Alice"}]},
                manifest,
            ),
            [],
        )

    def test_structured_item_not_dict(self):
        manifest = _manifest(
            placeholders=[
                _ph("phase", cardinality="N", required=False, content_schema={"label": "string"})
            ],
            density_range=(1, 6),
        )
        issues = check_conformance({"phase": ["not a dict"]}, manifest)
        self.assertTrue(any("must be an object" in i for i in issues), issues)


if __name__ == "__main__":
    unittest.main()
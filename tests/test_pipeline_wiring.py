"""
tests/test_pipeline_wiring.py
===============================
Sprint C wiring tests — verify the reversed per-slide ordering in the Deck
Executor and that the chosen asset_id is carried onto the produced SlideSpec.

The Deck Executor now does (per slide):

  1. plan_visual_pattern        → VisualPatternSelection
  2. _select_asset_for_slide   → AssetSelection        (NEW SIBLING, before content gen)
  3. generate_slide_content(..., asset_id=...)
  4. validate_content

These tests mock the Selector and the Content Generator to assert (a) the
Selector is invoked exactly once per slide, (b) BEFORE content generation,
and (c) the asset_id returned by the Selector is the one stamped onto the
generated SlideSpec. Reasoning modules remain byte-identical.
"""

from __future__ import annotations

import unittest
from unittest import mock

from backend.modules import deck_executor
from schemas.context import EnterpriseContext
from schemas.intent import IntentResult
from schemas.presentation import DeckSpec, SlidePlan
from schemas.process import ProcessResult
from schemas.slide_spec import SlideSpec
from schemas.validation import ValidationResult


def _constructs():
    intent = IntentResult(
        slide_type="operating_model",
        raw_title="Board Update",
        raw_content="Create a minimal board-level roadmap for Microsoft Procurement.",
        company="Microsoft",
        industry="Technology",
        business_function="Procurement",
        audience="board",
        objective="secure alignment",
        confidence=0.9,
        metadata={},
    )
    ctx = EnterpriseContext(
        company="Microsoft",
        industry="Technology",
        business_function="Procurement",
        company_summary="summary",
        facts=[],
        sources=[],
        warnings=[],
    )
    process = ProcessResult(
        process_name="Procure-to-Pay",
        process_family="P2P",
        confidence=0.9,
        reasoning="inferred",
        stages=["S1", "S2"],
    )
    deck = DeckSpec(
        presentation_type="roadmap",
        objective="align",
        audience="board",
        narrative="narrative",
        estimated_slide_count=2,
        slides=[
            SlidePlan(
                slide_number=1, slide_role="Roadmap",
                purpose="Phased transformation", required_inputs=[], dependencies=[],
                visualization_type="Roadmap",
            ),
            SlidePlan(
                slide_number=2, slide_role="KPIs",
                purpose="Success metrics", required_inputs=[], dependencies=[],
                visualization_type="KPI",
            ),
        ],
    )
    return intent, ctx, process, deck


def _ok_raw_spec():
    return {
        "title": "t", "subtitle": "s", "description": "d",
        "summary": {"headline": "h", "description": "d", "metrics": []},
        "stages": [], "pain_points": [], "risks": [], "metadata": {},
    }


def _validation_result(spec: SlideSpec) -> ValidationResult:
    return ValidationResult(is_valid=True, issues=[], claims=[], validated_spec=spec)


class PipelineWiringTests(unittest.TestCase):

    def test_asset_selector_called_before_content_generator_per_slide(self):
        intent, ctx, process, deck = _constructs()

        call_log: list[tuple[str, int]] = []
        counter = {"n": 0}

        def fake_select(slide_plan, visual_selection, intent, user_preferences=None):
            counter["n"] += 1
            call_log.append(("select", counter["n"]))
            return mock.MagicMock(asset_id=f"ASSET-{slide_plan.slide_number}")

        def fake_generate(*args, **kwargs):
            counter["n"] += 1
            call_log.append(("content", counter["n"]))
            self.assertIsNotNone(kwargs.get("asset_id"))
            return SlideSpec(
                slide_type="operating_model",
                raw_spec=_ok_raw_spec(),
                asset_id=kwargs.get("asset_id"),
            )

        def fake_validate(spec):
            return _validation_result(spec)

        with mock.patch.object(deck_executor, "_select_asset_for_slide", side_effect=fake_select), \
             mock.patch.object(deck_executor, "generate_slide_content", side_effect=fake_generate), \
             mock.patch.object(deck_executor, "validate_content", side_effect=fake_validate):
            deck_executor.execute_deck(deck, intent, ctx, process)

        # Selector fires BEFORE content gen for each slide — strict alternating order.
        self.assertEqual(call_log, [
            ("select", 1), ("content", 2),
            ("select", 3), ("content", 4),
        ])

    def test_asset_id_carried_onto_successful_slides(self):
        intent, ctx, process, deck = _constructs()

        def fake_select(slide_plan, visual_selection, intent, user_preferences=None):
            return mock.MagicMock(asset_id=f"CHOSEN-{slide_plan.slide_number}")

        seen_asset_ids: list[str | None] = []

        def fake_generate(*args, **kwargs):
            seen_asset_ids.append(kwargs.get("asset_id"))
            return SlideSpec(
                slide_type="operating_model",
                raw_spec=_ok_raw_spec(),
                asset_id=kwargs.get("asset_id"),
            )

        def fake_validate(spec):
            return _validation_result(spec)

        with mock.patch.object(deck_executor, "_select_asset_for_slide", side_effect=fake_select), \
             mock.patch.object(deck_executor, "generate_slide_content", side_effect=fake_generate), \
             mock.patch.object(deck_executor, "validate_content", side_effect=fake_validate):
            result = deck_executor.execute_deck(deck, intent, ctx, process)

        self.assertEqual(seen_asset_ids, ["CHOSEN-1", "CHOSEN-2"])
        self.assertTrue(result.all_succeeded)
        self.assertEqual(len(result.successful_slides), 2)

    def test_asset_selection_returning_none_does_not_abort_slide(self):
        intent, ctx, process, deck = _constructs()
        deck.slides = [deck.slides[0]]  # one slide only

        # The real _select_asset_for_slide wraps the call in try/except and
        # returns None on internal failure so the slide continues. Simulate
        # that protective behavior by returning None (NOT raising).
        def safe_select_returns_none(*args, **kwargs):
            return None

        def fake_generate(*args, **kwargs):
            self.assertIsNone(kwargs.get("asset_id"),
                              "when selector returns None, asset_id must be None — slide still proceeds")
            return SlideSpec(
                slide_type="operating_model",
                raw_spec=_ok_raw_spec(),
                asset_id=kwargs.get("asset_id"),
            )

        with mock.patch.object(deck_executor, "_select_asset_for_slide", side_effect=safe_select_returns_none), \
             mock.patch.object(deck_executor, "generate_slide_content", side_effect=fake_generate), \
             mock.patch.object(deck_executor, "validate_content", side_effect=(lambda spec: _validation_result(spec))):
            result = deck_executor.execute_deck(deck, intent, ctx, process)

        self.assertTrue(result.all_succeeded, "selector returning None must NOT abort the slide")
        self.assertEqual(len(result.successful_slides), 1)

    def test_no_visual_selection_skips_asset_selection(self):
        intent, ctx, process, deck = _constructs()
        deck.slides = [deck.slides[0]]

        selector_calls: list[int] = []

        def fake_plan_visual(slide_plan, previous_family):
            return None  # simulate visual planning failure

        def fake_select(slide_plan, visual_selection, intent, user_preferences=None):
            selector_calls.append(slide_plan.slide_number)
            return None

        def fake_generate(*args, **kwargs):
            self.assertIsNone(kwargs.get("asset_id"))
            return SlideSpec(slide_type="operating_model", raw_spec=_ok_raw_spec())

        with mock.patch.object(deck_executor, "_plan_visual_for_slide", side_effect=fake_plan_visual), \
             mock.patch.object(deck_executor, "_select_asset_for_slide", side_effect=fake_select), \
             mock.patch.object(deck_executor, "generate_slide_content", side_effect=fake_generate), \
             mock.patch.object(deck_executor, "validate_content", side_effect=(lambda spec: _validation_result(spec))):
            deck_executor.execute_deck(deck, intent, ctx, process)

        self.assertEqual(selector_calls, [], "selector must NOT be called when visual selection is None")

    def test_user_preferences_passed_through_to_selector(self):
        """user_preferences kwarg on execute_deck flows into _select_asset_for_slide."""
        from schemas.presentation_asset import UserPreferences

        intent, ctx, process, deck = _constructs()
        deck.slides = [deck.slides[0]]
        prefs = UserPreferences(audience=["board"], style=["minimal"])

        captured_prefs = []

        def fake_select(slide_plan, visual_selection, intent, user_preferences=None):
            captured_prefs.append(user_preferences)
            return mock.MagicMock(asset_id="ASSET-1")

        def fake_generate(*args, **kwargs):
            return SlideSpec(slide_type="operating_model", raw_spec=_ok_raw_spec(), asset_id=kwargs.get("asset_id"))

        with mock.patch.object(deck_executor, "_select_asset_for_slide", side_effect=fake_select), \
             mock.patch.object(deck_executor, "generate_slide_content", side_effect=fake_generate), \
             mock.patch.object(deck_executor, "validate_content", side_effect=(lambda spec: _validation_result(spec))):
            deck_executor.execute_deck(deck, intent, ctx, process, user_preferences=prefs)

        self.assertEqual(len(captured_prefs), 1)
        self.assertIs(captured_prefs[0], prefs, "user_preferences must be passed through to selector")


if __name__ == "__main__":
    unittest.main()
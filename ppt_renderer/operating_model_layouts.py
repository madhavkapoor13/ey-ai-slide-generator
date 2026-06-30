from __future__ import annotations

from collections import defaultdict
from typing import Any

from pptx.util import Inches

from ppt_renderer.operating_model_theme import OperatingModelTheme as Theme


class OperatingModelLayout:
    """Calculates all geometry for an operating model slide."""

    @classmethod
    def calculate(cls, spec: dict[str, Any]) -> dict[str, Any]:
        stages = spec.get("stages", [])
        metrics = spec.get("summary", {}).get("metrics", [])
        stage_layouts = cls._stage_layouts(stages)

        return {
            "header": cls._header_layout(),
            "summary": cls._summary_layout(metrics),
            "stages": stage_layouts,
            "connectors": cls._connector_layouts(stage_layouts),
            "risks": cls._risk_layouts(spec.get("risks", []), stage_layouts),
            "footer": cls._footer_layout(),
        }

    @classmethod
    def _header_layout(cls) -> dict[str, Any]:
        content_w = Theme.SLIDE_WIDTH_IN - Theme.LEFT_MARGIN_IN - Theme.RIGHT_MARGIN_IN
        return {
            "title": cls._rect(Theme.LEFT_MARGIN_IN, Theme.HEADER_TITLE_Y_IN, content_w, 0.38),
            "subtitle": cls._rect(Theme.LEFT_MARGIN_IN, Theme.HEADER_SUBTITLE_Y_IN, content_w * 0.7, 0.22),
            "description": cls._rect(Theme.LEFT_MARGIN_IN, Theme.HEADER_DESCRIPTION_Y_IN, content_w * 0.82, 0.22),
            "divider": cls._rect(Theme.LEFT_MARGIN_IN, Theme.HEADER_DIVIDER_Y_IN, content_w, Theme.HEADER_DIVIDER_H_IN),
        }

    @classmethod
    def _summary_layout(cls, metrics: list[dict[str, str]]) -> dict[str, Any]:
        content_w = Theme.SLIDE_WIDTH_IN - Theme.LEFT_MARGIN_IN - Theme.RIGHT_MARGIN_IN
        metric_count = len(metrics)
        metric_area_w = 0
        if metric_count:
            metric_area_w = min(
                content_w * 0.48,
                metric_count * Theme.RIBBON_METRIC_W_IN + (metric_count - 1) * Theme.RIBBON_METRIC_GAP_IN,
            )

        summary_w = content_w - metric_area_w - Theme.RIBBON_PADDING_IN * 3
        metric_w = 0
        if metric_count:
            metric_w = (metric_area_w - (metric_count - 1) * Theme.RIBBON_METRIC_GAP_IN) / metric_count

        metric_layouts = []
        start_x = Theme.LEFT_MARGIN_IN + content_w - Theme.RIBBON_PADDING_IN - metric_area_w
        for index, metric in enumerate(metrics):
            x = start_x + index * (metric_w + Theme.RIBBON_METRIC_GAP_IN)
            metric_layouts.append(
                {
                    "metric": metric,
                    **cls._rect(x, Theme.RIBBON_Y_IN + 0.16, metric_w, Theme.RIBBON_H_IN - 0.32),
                }
            )

        return {
            "ribbon": cls._rect(Theme.LEFT_MARGIN_IN, Theme.RIBBON_Y_IN, content_w, Theme.RIBBON_H_IN),
            "summary_text": cls._rect(
                Theme.LEFT_MARGIN_IN + Theme.RIBBON_PADDING_IN,
                Theme.RIBBON_Y_IN + 0.12,
                summary_w,
                Theme.RIBBON_H_IN - 0.24,
            ),
            "metrics": metric_layouts,
        }

    @classmethod
    def _stage_layouts(cls, stages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        stage_count = len(stages)
        if stage_count == 0:
            return []

        content_w = Theme.SLIDE_WIDTH_IN - Theme.LEFT_MARGIN_IN - Theme.RIGHT_MARGIN_IN
        gap = Theme.STAGE_GAP_IN
        stage_w = (content_w - gap * (stage_count - 1)) / stage_count

        layouts = []
        for index, stage in enumerate(stages):
            x = Theme.LEFT_MARGIN_IN + index * (stage_w + gap)
            layouts.append(cls._stage_layout(stage, x, stage_w))

        return layouts

    @classmethod
    def _stage_layout(cls, stage: dict[str, Any], x: float, stage_w: float) -> dict[str, Any]:
        activities = stage.get("activities", [])
        activity_count = len(activities)
        available_h = (
            Theme.STAGES_H_IN
            - Theme.STAGE_HEADER_H_IN
            - Theme.STAGE_PADDING_IN * 2
            - max(activity_count - 1, 0) * Theme.ACTIVITY_GAP_IN
        )
        activity_h = Theme.ACTIVITY_MAX_H_IN
        if activity_count:
            activity_h = max(
                Theme.ACTIVITY_MIN_H_IN,
                min(Theme.ACTIVITY_MAX_H_IN, available_h / activity_count),
            )

        activity_layouts = []
        activity_y = Theme.STAGES_Y_IN + Theme.STAGE_HEADER_H_IN + Theme.STAGE_PADDING_IN
        for activity in activities:
            activity_layouts.append(
                {
                    "text": activity,
                    **cls._rect(
                        x + Theme.STAGE_PADDING_IN,
                        activity_y,
                        stage_w - Theme.STAGE_PADDING_IN * 2,
                        activity_h,
                    ),
                }
            )
            activity_y += activity_h + Theme.ACTIVITY_GAP_IN

        return {
            "stage": stage,
            "container": cls._rect(x, Theme.STAGES_Y_IN, stage_w, Theme.STAGES_H_IN),
            "header": cls._rect(x, Theme.STAGES_Y_IN, stage_w, Theme.STAGE_HEADER_H_IN),
            "number": cls._rect(x + Theme.STAGE_PADDING_IN, Theme.STAGES_Y_IN + 0.075, 0.3, 0.3),
            "title": cls._rect(x + 0.42, Theme.STAGES_Y_IN + 0.09, stage_w - 0.48, 0.27),
            "activities": activity_layouts,
            "center_y": Inches(Theme.STAGES_Y_IN + Theme.STAGE_HEADER_H_IN / 2),
            "left": Inches(x),
            "right": Inches(x + stage_w),
            "center_x": Inches(x + stage_w / 2),
        }

    @classmethod
    def _connector_layouts(cls, stages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        connectors = []
        for index in range(len(stages) - 1):
            current_stage = stages[index]
            next_stage = stages[index + 1]
            connectors.append(
                {
                    "start_x": current_stage["right"] + Inches(Theme.CONNECTOR_STUB_IN),
                    "start_y": current_stage["center_y"],
                    "end_x": next_stage["left"] - Inches(Theme.CONNECTOR_STUB_IN),
                    "end_y": next_stage["center_y"],
                }
            )
        return connectors

    @classmethod
    def _risk_layouts(
        cls,
        risks: list[dict[str, Any]],
        stages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        risks_by_stage = defaultdict(list)
        for risk in risks:
            risks_by_stage[risk.get("stage")].append(risk.get("text", ""))

        cells = []
        for stage in stages:
            stage_number = stage["stage"].get("number")
            risk_texts = risks_by_stage.get(stage_number, [])
            cells.append(
                {
                    "texts": risk_texts,
                    "x": stage["container"]["x"],
                    "y": Inches(Theme.RISK_Y_IN),
                    "width": stage["container"]["width"],
                    "height": Inches(Theme.RISK_H_IN),
                }
            )

        return {
            "strip": cls._rect(
                Theme.LEFT_MARGIN_IN,
                Theme.RISK_Y_IN,
                Theme.SLIDE_WIDTH_IN - Theme.LEFT_MARGIN_IN - Theme.RIGHT_MARGIN_IN,
                Theme.RISK_H_IN,
            ),
            "label": cls._rect(Theme.LEFT_MARGIN_IN, Theme.RISK_Y_IN - 0.18, Theme.RISK_LABEL_W_IN + 0.35, 0.16),
            "cells": cells,
        }

    @classmethod
    def _footer_layout(cls) -> dict[str, Any]:
        content_w = Theme.SLIDE_WIDTH_IN - Theme.LEFT_MARGIN_IN - Theme.RIGHT_MARGIN_IN
        return {
            "rule": cls._rect(Theme.LEFT_MARGIN_IN, Theme.FOOTER_RULE_Y_IN, content_w, 0.006),
            "left": cls._rect(Theme.LEFT_MARGIN_IN, Theme.FOOTER_Y_IN, 3.5, Theme.FOOTER_H_IN),
            "center": cls._rect(5.65, Theme.FOOTER_Y_IN, 2.0, Theme.FOOTER_H_IN),
            "right": cls._rect(Theme.SLIDE_WIDTH_IN - Theme.RIGHT_MARGIN_IN - 1.0, Theme.FOOTER_Y_IN, 1.0, Theme.FOOTER_H_IN),
        }

    @staticmethod
    def _rect(x: float, y: float, width: float, height: float) -> dict[str, int]:
        return {
            "x": Inches(x),
            "y": Inches(y),
            "width": Inches(width),
            "height": Inches(height),
        }

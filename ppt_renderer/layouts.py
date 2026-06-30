from __future__ import annotations

from typing import Any

from pptx.util import Inches

from ppt_renderer.theme import EYTheme


class ProcessLayout:
    """Computes geometry for a single-row process flow slide."""

    @classmethod
    def calculate(
        cls,
        nodes: list[dict[str, Any]],
        connections: list[dict[str, str]] | None = None,
        pain_points: list[dict[str, str]] | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        node_layouts = cls._calculate_nodes(nodes)
        node_by_id = {node["id"]: node for node in node_layouts}

        return {
            "nodes": node_layouts,
            "connectors": cls._calculate_connectors(node_layouts, connections),
            "pain_points": cls._calculate_pain_points(pain_points or [], node_by_id),
        }

    @classmethod
    def _calculate_nodes(cls, nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        node_count = len(nodes)
        if node_count == 0:
            return []

        usable_width = (
            EYTheme.SLIDE_WIDTH_IN
            - cls._inches(EYTheme.LEFT_MARGIN)
            - cls._inches(EYTheme.RIGHT_MARGIN)
        )

        if node_count == 1:
            box_width = min(EYTheme.BOX_MAX_WIDTH_IN, usable_width)
            gap = 0
            start_x = cls._inches(EYTheme.LEFT_MARGIN) + (usable_width - box_width) / 2
        else:
            gap = EYTheme.BOX_MIN_GAP_IN
            box_width = (usable_width - gap * (node_count - 1)) / node_count
            box_width = max(EYTheme.BOX_MIN_WIDTH_IN, min(EYTheme.BOX_MAX_WIDTH_IN, box_width))
            total_width = box_width * node_count + gap * (node_count - 1)
            start_x = cls._inches(EYTheme.LEFT_MARGIN) + max((usable_width - total_width) / 2, 0)

        box_height = cls._box_height(node_count)
        y = cls._inches(EYTheme.PROCESS_Y)

        layout = []
        for index, node in enumerate(nodes):
            x = start_x + index * (box_width + gap)
            layout.append(
                {
                    "id": node["id"],
                    "node": node,
                    "x": Inches(x),
                    "y": Inches(y),
                    "width": Inches(box_width),
                    "height": Inches(box_height),
                    "center_x": Inches(x + box_width / 2),
                    "center_y": Inches(y + box_height / 2),
                    "right": Inches(x + box_width),
                    "bottom": Inches(y + box_height),
                }
            )

        return layout

    @classmethod
    def _calculate_connectors(
        cls,
        nodes: list[dict[str, Any]],
        connections: list[dict[str, str]] | None,
    ) -> list[dict[str, Any]]:
        if not nodes:
            return []

        node_by_id = {node["id"]: node for node in nodes}
        resolved_connections = connections or [
            {"from": nodes[index]["id"], "to": nodes[index + 1]["id"]}
            for index in range(len(nodes) - 1)
        ]

        connector_layouts = []
        for connection in resolved_connections:
            start = node_by_id.get(connection.get("from"))
            end = node_by_id.get(connection.get("to"))
            if not start or not end:
                continue

            connector_layouts.append(
                {
                    "start_x": start["right"] + EYTheme.CONNECTOR_STUB,
                    "start_y": start["center_y"],
                    "end_x": end["x"] - EYTheme.CONNECTOR_STUB,
                    "end_y": end["center_y"],
                }
            )

        return connector_layouts

    @classmethod
    def _calculate_pain_points(
        cls,
        pain_points: list[dict[str, str]],
        node_by_id: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        layouts = []
        for pain in pain_points:
            node = node_by_id.get(pain.get("node_id"))
            if not node:
                continue

            callout_width = min(EYTheme.PAIN_CALLOUT_WIDTH, node["width"] + Inches(0.55))
            callout_x = node["center_x"] - callout_width // 2
            callout_x = max(EYTheme.LEFT_MARGIN, callout_x)
            max_x = EYTheme.SLIDE_WIDTH - EYTheme.RIGHT_MARGIN - callout_width
            callout_x = min(callout_x, max_x)

            layouts.append(
                {
                    "x": callout_x,
                    "y": node["bottom"] + EYTheme.PAIN_CALLOUT_GAP,
                    "width": callout_width,
                    "height": EYTheme.PAIN_CALLOUT_HEIGHT,
                    "text": pain.get("text", ""),
                    "anchor_x": node["center_x"],
                    "anchor_y": node["bottom"],
                }
            )

        return layouts

    @staticmethod
    def _box_height(node_count: int) -> float:
        if node_count >= 8:
            return EYTheme.BOX_MAX_HEIGHT_IN
        return EYTheme.BOX_BASE_HEIGHT_IN

    @staticmethod
    def _inches(value: int) -> float:
        return value / 914400

from __future__ import annotations

from typing import Any

from pptx import Presentation
from pptx.enum.shapes import MSO_AUTO_SHAPE_TYPE

from ppt_renderer.operating_model_components import (
    ConnectorComponent,
    FooterComponent,
    HeaderComponent,
    RiskStripComponent,
    StageComponent,
    SummaryRibbonComponent,
)
from ppt_renderer.operating_model_layouts import OperatingModelLayout
from ppt_renderer.operating_model_theme import OperatingModelTheme as Theme


class OperatingModelRenderer:
    """Generates editable consulting-style operating model PowerPoint slides."""

    def __init__(self):
        self.prs = Presentation()
        self.prs.slide_width = Theme.SLIDE_WIDTH
        self.prs.slide_height = Theme.SLIDE_HEIGHT

    def render(self, slide_spec: dict[str, Any], output_path: str = "operating_model.pptx") -> None:
        slide = self.prs.slides.add_slide(self.prs.slide_layouts[6])
        layout = OperatingModelLayout.calculate(slide_spec)

        self._draw_background(slide)

        HeaderComponent.draw(slide, slide_spec, layout["header"])
        SummaryRibbonComponent.draw(slide, slide_spec.get("summary", {}), layout["summary"])

        for stage in layout["stages"]:
            StageComponent.draw(slide, stage)

        for connector in layout["connectors"]:
            ConnectorComponent.draw(slide, connector)

        RiskStripComponent.draw(slide, layout["risks"])
        FooterComponent.draw(slide, layout["footer"], len(self.prs.slides))

        self.prs.save(output_path)

    @staticmethod
    def _draw_background(slide) -> None:
        background = slide.shapes.add_shape(
            MSO_AUTO_SHAPE_TYPE.RECTANGLE,
            0,
            0,
            Theme.SLIDE_WIDTH,
            Theme.SLIDE_HEIGHT,
        )
        background.fill.solid()
        background.fill.fore_color.rgb = Theme.BACKGROUND
        background.line.fill.background()

from pptx import Presentation

from ppt_renderer.theme import EYTheme
from ppt_renderer.components import SlideComponents
from ppt_renderer.layouts import ProcessLayout


class ProcessFlowRenderer:

    def __init__(self):

        self.prs = Presentation()

        # Widescreen 16:9
        self.prs.slide_width = EYTheme.SLIDE_WIDTH
        self.prs.slide_height = EYTheme.SLIDE_HEIGHT

    def render(self, slide_spec, output_path="output.pptx"):

        slide = self.prs.slides.add_slide(
            self.prs.slide_layouts[6]
        )

        # -------------------------
        # Title
        # -------------------------

        SlideComponents.draw_title(
            slide,
            slide_spec.get("title", ""),
            slide_spec.get("subtitle", ""),
            slide_spec.get("description", ""),
        )

        # -------------------------
        # Layout Calculation
        # -------------------------

        layout = ProcessLayout.calculate(
            slide_spec.get("nodes", []),
            slide_spec.get("connections", []),
            slide_spec.get("pain_points", []),
        )

        # -------------------------
        # Draw Process Boxes
        # -------------------------

        for item in layout["nodes"]:

            SlideComponents.draw_process_box(
                slide,
                item["node"],
                item["x"],
                item["y"],
                item["width"],
                item["height"],
            )

        # -------------------------
        # Draw Connectors
        # -------------------------

        for connector in layout["connectors"]:

            SlideComponents.draw_connector(
                slide,
                connector["start_x"],
                connector["start_y"],
                connector["end_x"],
                connector["end_y"],
            )

        # -------------------------
        # Draw Pain Points
        # -------------------------

        for pain in layout["pain_points"]:

            SlideComponents.draw_pain_point(
                slide,
                pain["x"],
                pain["y"],
                pain["width"],
                pain["height"],
                pain["text"],
                pain["anchor_x"],
                pain["anchor_y"],
            )

        # -------------------------
        # Footer
        # -------------------------

        SlideComponents.draw_footer(slide, len(self.prs.slides))

        # -------------------------
        # Save
        # -------------------------

        self.prs.save(output_path)

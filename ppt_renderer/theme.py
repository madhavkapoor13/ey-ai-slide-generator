from pptx.dml.color import RGBColor
from pptx.util import Inches, Pt


class EYTheme:
    """Central visual system for the editable consulting-slide prototype."""

    # ---------- SLIDE ----------

    SLIDE_WIDTH_IN = 13.333
    SLIDE_HEIGHT_IN = 7.5

    SLIDE_WIDTH = Inches(SLIDE_WIDTH_IN)
    SLIDE_HEIGHT = Inches(SLIDE_HEIGHT_IN)

    # ---------- BRAND COLORS ----------
    EY_YELLOW = RGBColor(255, 230, 0)

    INK = RGBColor(31, 35, 40)
    DARK = INK

    CHARCOAL = RGBColor(45, 48, 52)
    GREY = RGBColor(101, 109, 118)
    MID_GREY = RGBColor(151, 158, 166)

    LIGHT_GREY = RGBColor(247, 248, 250)
    PANEL_GREY = RGBColor(242, 244, 247)

    BORDER = RGBColor(216, 222, 228)
    CONNECTOR = RGBColor(138, 145, 153)

    RED = RGBColor(186, 45, 45)

    LIGHT_RED = RGBColor(253, 241, 241)

    GREEN = RGBColor(35, 150, 85)

    LIGHT_GREEN = RGBColor(235, 248, 240)

    # ---------- TYPOGRAPHY ----------
    FONT_FAMILY = "Aptos"
    TITLE_FONT_FAMILY = "Arial"

    TITLE_SIZE = Pt(24)

    SUBTITLE_SIZE = Pt(12)

    DESCRIPTION_SIZE = Pt(9.5)

    BODY_SIZE = Pt(10.5)

    SMALL_SIZE = Pt(10)

    CALLOUT_TITLE_SIZE = Pt(7.5)
    CALLOUT_BODY_SIZE = Pt(8.5)
    FOOTER_SIZE = Pt(7.5)

    # ---------- SPACING ----------
    LEFT_MARGIN = Inches(0.6)

    RIGHT_MARGIN = Inches(0.6)

    TOP_MARGIN = Inches(0.36)

    CONTENT_TOP = Inches(2.1)

    FOOTER_MARGIN = Inches(0.35)

    # ---------- BOX ----------
    BOX_MIN_WIDTH_IN = 0.95
    BOX_MAX_WIDTH_IN = 2.05
    BOX_BASE_HEIGHT_IN = 0.9
    BOX_MAX_HEIGHT_IN = 1.1
    BOX_MIN_GAP_IN = 0.14

    BOX_WIDTH = Inches(BOX_MAX_WIDTH_IN)

    BOX_HEIGHT = Inches(BOX_BASE_HEIGHT_IN)

    BOX_PADDING_X = Inches(0.1)

    BOX_PADDING_Y = Inches(0.07)

    BOX_BORDER_WIDTH = Pt(0.8)

    # ---------- PROCESS ----------
    PROCESS_Y = Inches(2.75)
    CONNECTOR_STUB = Inches(0.04)
    CONNECTOR_WIDTH = Pt(1.25)

    # ---------- FOOTER ----------
    FOOTER_Y = Inches(7.03)
    FOOTER_RULE_Y = Inches(6.9)

    # ---------- HEADER ----------
    HEADER_TITLE_X = LEFT_MARGIN
    HEADER_TITLE_Y = Inches(0.34)
    HEADER_TITLE_W = Inches(7.6)
    HEADER_TITLE_H = Inches(0.42)
    HEADER_SUBTITLE_W = Inches(8.8)
    HEADER_SUBTITLE_Y = Inches(0.86)
    HEADER_SUBTITLE_H = Inches(0.28)
    HEADER_DESCRIPTION_W = Inches(9.8)
    HEADER_DESCRIPTION_Y = Inches(1.18)
    HEADER_DESCRIPTION_H = Inches(0.42)
    HEADER_DIVIDER_Y = Inches(1.72)
    HEADER_DIVIDER_W = Inches(2.6)
    HEADER_DIVIDER_H = Inches(0.045)

    # ---------- PAIN POINTS ----------
    PAIN_CALLOUT_WIDTH_IN = 2.4
    PAIN_CALLOUT_HEIGHT_IN = 0.82
    PAIN_CALLOUT_GAP_IN = 0.28
    PAIN_CALLOUT_WIDTH = Inches(PAIN_CALLOUT_WIDTH_IN)
    PAIN_CALLOUT_HEIGHT = Inches(PAIN_CALLOUT_HEIGHT_IN)
    PAIN_CALLOUT_GAP = Inches(PAIN_CALLOUT_GAP_IN)
    PAIN_CALLOUT_PADDING = Inches(0.08)
    PAIN_CALLOUT_MARGIN_Y = Inches(0.05)
    PAIN_CALLOUT_BORDER_WIDTH = Pt(1)
    PAIN_ANCHOR_OFFSET = Inches(0.03)
    PAIN_ANCHOR_WIDTH = Pt(0.45)

    # ---------- FOOTER LAYOUT ----------
    FOOTER_RULE_H = Inches(0.006)
    FOOTER_TEXT_H = Inches(0.22)
    FOOTER_LEFT_W = Inches(3.4)
    FOOTER_CENTER_X = Inches(5.75)
    FOOTER_CENTER_W = Inches(1.8)
    FOOTER_RIGHT_W = Inches(1.0)

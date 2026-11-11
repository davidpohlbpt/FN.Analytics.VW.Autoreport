from enum import StrEnum


class ChartObjects(StrEnum):
    BOX = "Box"
    CHART = "Chart"
    HEADLINE = "Headline"
    TOTAL = "Total"


class SlideObjects(StrEnum):
    """Shapes that belong to a slide as a whole; matched by exact name, not suffix."""

    LEGEND = "Legend"


class Languages(StrEnum):
    DE = "DE"
    EN = "EN"


class TextAlignments(StrEnum):
    LEFT = "LEFT"
    CENTER = "CENTER"
    RIGHT = "RIGHT"
    JUSTIFY = "JUSTIFY"
    DISTRIBUTE = "DISTRIBUTE"
    JUSTIFY_LOW = "JUSTIFY_LOW"
    THAI_DISTRIBUTE = "THAI_DISTRIBUTE"
    MIXED = "MIXED"


class ChartType(StrEnum):
    DOUGHNUT = "doughnut"

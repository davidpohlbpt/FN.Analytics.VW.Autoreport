"""Static text boxes of a template slide, e.g. 'Targets' and the data source line.

The template shape is copied as is (position, fonts, underline, colours) and only its
``{placeholder}`` tokens are replaced. PowerPoint often splits a token over several
runs ("{", "brand", "}"), so substitution works on the paragraph text and the
replacement inherits the style of the run the token starts in.
"""

import copy
import re

from pptx.slide import Slide

from pptcreator.models.enum import ChartObjects, SlideObjects

# Tolerates doubled braces such as '{{week}' in the template
_PLACEHOLDER = re.compile(r"\{+(\w+)\}+")


def create_text_fields(slide: Slide, template_slide: Slide, values: dict[str, str]) -> None:
    for shape in template_slide.shapes:
        if not _is_text_field(shape):
            continue
        element = copy.deepcopy(shape._element)
        element.nvSpPr.cNvPr.id = slide.shapes._next_shape_id
        slide.shapes._spTree.append(element)
        for paragraph in slide.shapes[-1].text_frame.paragraphs:
            fill_placeholders(paragraph, values)


def _is_text_field(shape) -> bool:
    if shape.is_placeholder or not shape.has_text_frame or shape.has_chart:
        return False
    if not shape.text_frame.text.strip() or shape.name == SlideObjects.LEGEND.value:
        return False
    return not any(shape.name.endswith(role.value) for role in ChartObjects)


def fill_placeholders(paragraph, values: dict[str, str]) -> None:
    """Replace known tokens; unknown ones stay visible so template typos get noticed."""
    runs = paragraph.runs
    chars = [(char, index) for index, run in enumerate(runs) for char in run.text]
    text = "".join(char for char, _ in chars)

    matches = [m for m in _PLACEHOLDER.finditer(text) if m.group(1) in values]
    if not matches:
        return
    for match in reversed(matches):
        owner = chars[match.start()][1]
        replacement = [(char, owner) for char in str(values[match.group(1)])]
        chars[match.start() : match.end()] = replacement

    for index, run in enumerate(runs):
        run.text = "".join(char for char, owner in chars if owner == index)

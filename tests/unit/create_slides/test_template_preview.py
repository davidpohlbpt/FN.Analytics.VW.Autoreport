"""Local harness to validate a new .pptx template without DB or Config Center access.

Drop the template into tests/unit/test_data and run:
    $env:PREVIEW_TEMPLATE = "My_Template.pptx"; poetry run pytest tests/unit/create_slides/test_template_preview.py -s
The rendered deck is written to tests/result.
"""

import os
from pathlib import Path
from pprint import pformat

import pytest
from pptx import Presentation

from pptcreator.creator.create_ppt.graph_create_ppt import graph_create_ppt
from pptcreator.creator.get_config.get_template_config import get_template_config
from pptcreator.models.enum import ChartObjects, ChartType

TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "test_data"
RESULT_DIR = Path(__file__).resolve().parents[2] / "result"

TEMPLATE_NAME = os.getenv("PREVIEW_TEMPLATE", "Test_PPT.pptx")
HEADLINE_SUBSTRING = "Preview"
FILTER_VALUES = ["Project A", "Project B"]

# Category -> color. Any category used in the dummy data must appear here.
DUMMY_PALETTE = {
    "Done": "rgb(146, 208, 80)",
    "Open": "rgb(255, 0, 0)",
    "Not relevant": "rgb(127, 127, 127)",
}


def _discover_objects(prs) -> dict[str, set[str]]:
    """Mirrors the suffix matching in get_template_config to find template_object_names."""
    found: dict[str, set[str]] = {}
    for slide in prs.slides:
        for shape in slide.shapes:
            for role in ChartObjects:
                if shape.name.endswith(role.value):
                    name = shape.name.removesuffix(role.value).rstrip()
                    found.setdefault(name, set()).add(role.value)
                    break
    return found


def _dummy_data(object_index: int) -> dict[str, list[dict]]:
    data = {}
    for filter_index, filter_value in enumerate(FILTER_VALUES):
        data[filter_value] = [
            {
                "category": category,
                "value": float(10 + 5 * i + filter_index + object_index),
            }
            for i, category in enumerate(DUMMY_PALETTE)
        ]
    return data


@pytest.fixture
def template_bytes() -> bytes:
    path = TEMPLATE_DIR / TEMPLATE_NAME
    if not path.is_file():
        pytest.fail(f"Template not found: {path}")
    return path.read_bytes()


def test_template_preview(storage, cont, template_bytes):

    # -------------------------------- Arrange --------------------------------- #
    storage.write_blob(
        container_name=cont, blob_name=TEMPLATE_NAME, blob_data=template_bytes
    )

    prs = Presentation(TEMPLATE_DIR / TEMPLATE_NAME)
    discovered = _discover_objects(prs)

    print(f"\n--- Template: {TEMPLATE_NAME} ---")
    print(f"Slides in template: {len(prs.slides)}")
    print("All shape names on slide 1:")
    for shape in prs.slides[0].shapes:
        print(f"  - {shape.name!r}")

    assert discovered, (
        "No shapes ending in 'Box', 'Chart' or 'Headline' were found. "
        "Rename the shapes in PowerPoint via Home > Select > Selection Pane."
    )

    missing_chart = sorted(
        name
        for name, roles in discovered.items()
        if ChartObjects.CHART.value not in roles
    )
    assert not missing_chart, f"Template objects without a Chart shape: {missing_chart}"

    config_dict = {
        "charts": {name: {} for name in discovered},
        "file": TEMPLATE_NAME,
        "file_container": cont,
        "headline_substring": HEADLINE_SUBSTRING,
        "target_file_name": f"{Path(TEMPLATE_NAME).stem}_preview",
        "target_blob_container": cont,
        "filter": FILTER_VALUES,
    }

    config_dict = get_template_config(config_dict)

    for index, (name, object_config) in enumerate(config_dict["charts"].items()):
        object_config["chart_type"] = ChartType.DOUGHNUT
        object_config[ChartObjects.CHART.value]["fillColor"] = DUMMY_PALETTE
        object_config[ChartObjects.CHART.value]["data"] = _dummy_data(index)

        headline = object_config.get(ChartObjects.HEADLINE.value)
        if headline is not None:
            headline["translation"] = name

    print("\nExtracted template config:")
    print(pformat({name: cfg for name, cfg in config_dict["charts"].items()}))

    # ---------------------------------- Act ----------------------------------- #
    graph_create_ppt(config_dict)

    # -------------------------------- Assert ---------------------------------- #
    blob = storage.read_blob(
        container_name=cont,
        blob_name=f"{config_dict['target_file_name']}.pptx",
        decode=False,
    )

    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    result_file = RESULT_DIR / f"{config_dict['target_file_name']}.pptx"
    result_file.write_bytes(blob)
    print(f"\nWrote {result_file}")

    result = Presentation(result_file)
    assert len(result.slides) == len(FILTER_VALUES)
    for slide in result.slides:
        assert len([s for s in slide.shapes if s.has_chart]) == len(discovered)

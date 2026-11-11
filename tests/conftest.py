import datetime as dt
import json
import tempfile

import numpy as np
import pandas as pd
import pytest
from pycore.resources.file import FileStorage
from pycore.testing.unit import *

from pptcreator.config import settings
from pptcreator.models import enum as e


@pytest.fixture
def load_date():
    return dt.date(2020, 1, 1)


@pytest.fixture
def load_id():
    return 1000


@pytest.fixture
def entity_id():
    return 1


@pytest.fixture
def test_dir():
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield tmp_dir


@pytest.fixture
def storage(test_dir):
    return FileStorage(root_dir=test_dir)


@pytest.fixture
def cont(storage):
    cont = settings.storage_container
    (storage.root_dir / cont).mkdir()
    return cont


@pytest.fixture
def templates_data():
    container = settings.storage_container
    return pd.DataFrame(
        columns=[
            "id",
            "template_link",
            "language",
            "is_active",
            "filter_column",
            "target_file_name",
            "target_blob_container",
            "headline_substring",
        ],
        data=[
            [
                1,
                f"{container}/Test_PPT.pptx",
                e.Languages.DE,
                True,
                "project_name",
                "Customer_Report",
                f"{container}",
                "Test Headline Substring",
            ],
            [
                2,
                f"{container}/Test_PPT_2.pptx",
                e.Languages.EN,
                False,
                "project_name",
                "Customer_Report_2",
                f"{container}",
                "Test Headline Substring 2",
            ],
        ],
    )


@pytest.fixture
def mappings_data():
    return pd.DataFrame(
        columns=[
            "id",
            "template_object_name",
            "menu_item_id",
            "report_id",
            "tile_id",
            "chart_id",
            "template_id",
        ],
        data=[
            [1, "Chart 1", 704, 704, 7011, 70110, 1],
            [2, "Chart 4", 704, 704, 7014, 70140, 1],
        ],
    )


@pytest.fixture
def recipients_data():
    return pd.DataFrame(
        columns=["id", "recipient_email", "template_id", "is_active"],
        data=[
            [1, "prm.lead@example.com", 1, True],
            [2, "cmc.manager@example.com", 2, False],
        ],
    )

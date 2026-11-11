import datetime as dt

import pandas as pd
import pytest
from pycore.schemas import ProcessState, TrackerLoadInformation

from pptcreator.creator import graph_steer_creation_process as module
from pptcreator.creator.graph_steer_creation_process import (
    graph_steer_creation_process,
)
from pptcreator.models.models import Templates


@pytest.fixture
def load_info():
    return TrackerLoadInformation(
        loadID=10,
        entityID=1,
        scenID=1,
        timestamp_started=dt.datetime(2020, 1, 1),
        timestamp_finished=dt.datetime(2020, 1, 1),
        status=ProcessState.PROCESSING,
    )


@pytest.fixture
def mock_graphs(mocker):
    get_config = mocker.patch.object(
        module,
        "graph_get_config",
        return_value={"config": "from_get_config"},
    )
    create_ppt = mocker.patch.object(
        module,
        "graph_create_ppt",
        return_value={"config": "from_create_ppt"},
    )
    send_email = mocker.patch.object(module, "send_email", return_value=None)
    return get_config, create_ppt, send_email


def test_graph_steer_creation_process_processes_active_templates(
    data_repo, templates_data, mock_graphs, load_info
):
    # -------------------------------- Arrange --------------------------------- #
    data_repo.database.create_all_tables()
    data_repo.write_table(model=Templates, df=templates_data)
    get_config, create_ppt, send_email = mock_graphs

    # ---------------------------------- Act ----------------------------------- #
    graph_steer_creation_process(load_info)

    # -------------------------------- Assert ---------------------------------- #
    get_config.assert_called_once_with(1)
    create_ppt.assert_called_once_with({"config": "from_get_config"})
    send_email.assert_called_once_with({"config": "from_create_ppt"})

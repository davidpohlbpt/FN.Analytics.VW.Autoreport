import pandas as pd

from pptcreator.creator.get_config.get_database_config import get_database_config
from pptcreator.models.enum import Languages
from pptcreator.models.models import Mappings, Recipients, Templates


def test_get_database_config(data_repo, templates_data, mappings_data, recipients_data):

    # ---------------------------------- Arrange --------------------------------- #
    data_repo.database.create_all_tables()
    data_repo.write_table(model=Templates, df=templates_data)
    data_repo.write_table(model=Mappings, df=mappings_data)
    data_repo.write_table(model=Recipients, df=recipients_data)

    config_dict = {"charts": {}}

    # Expected data
    expected_data = {
        "charts": {
            "Chart 1": {"tile_id": 7011, "chart_id": 70110},
            "Chart 4": {"tile_id": 7014, "chart_id": 70140},
        },
        "file": "Test_PPT.pptx",
        "file_container": "ppt_creator",
        "headline_substring": "Test Headline Substring",
        "target_file_name": "Customer_Report",
        "target_blob_container": "ppt_creator",
        "filter_column": "project_name",
        "language": Languages.DE,
        "recipients": ["prm.lead@example.com"],
        "menu_item_id": 704,
        "report_id": 704,
    }
    # ------------------------------------ Act ----------------------------------- #
    actual_data = get_database_config(config_dict=config_dict, template_id=1)

    # ---------------------------------- Assert ---------------------------------- #
    assert actual_data == expected_data

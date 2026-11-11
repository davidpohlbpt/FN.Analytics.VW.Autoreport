from pathlib import PurePosixPath

from pptcreator.models.models import Mappings, Recipients, Templates
from pptcreator.utils.get_unique_value import get_unique_value
from pptcreator.utils.read_data import read_data


def get_database_config(config_dict: dict, template_id: int) -> dict | None:

    template = read_data(Templates, ["id", "is_active"], [template_id, True])

    mappings = read_data(Mappings, ["template_id"], [template_id])

    recipients = read_data(
        Recipients, ["template_id", "is_active"], [template_id, True]
    )

    if template.empty or mappings.empty or recipients.empty:
        return None

    template_path = PurePosixPath(
        template["template_link"].iloc[0].replace("\\", "/")
    )  # Fix wrong paths
    config_dict["file_container"] = str(template_path.parent)
    config_dict["file"] = template_path.name
    config_dict["headline_substring"] = template["headline_substring"].iloc[0]
    config_dict["target_file_name"] = template["target_file_name"].iloc[0]
    config_dict["target_blob_container"] = template["target_blob_container"].iloc[0]
    config_dict["filter_column"] = template["filter_column"].iloc[0]
    config_dict["language"] = template["language"].iloc[0]
    config_dict["recipients"] = recipients["recipient_email"].tolist()

    for column in ("menu_item_id", "report_id"):
        config_dict[column] = get_unique_value(mappings, column, template_id)

    if mappings["template_object_name"].duplicated().any():
        raise ValueError(f"Duplicate template_object_name for template {template_id}")

    config_dict["charts"] = {
        row["template_object_name"]: {
            "tile_id": row["tile_id"],
            "chart_id": row["chart_id"],
        }
        for row in mappings[["template_object_name", "tile_id", "chart_id"]].to_dict(
            orient="records"
        )
    }

    return config_dict

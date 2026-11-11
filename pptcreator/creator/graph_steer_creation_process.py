import logging

from pycore.schemas import TrackerLoadInformation

from pptcreator.creator.create_ppt.graph_create_ppt import graph_create_ppt
from pptcreator.creator.get_config.graph_get_config import graph_get_config
from pptcreator.creator.send_email.send_email import send_email
from pptcreator.models.models import Templates
from pptcreator.utils.read_data import read_data


def graph_steer_creation_process(load_info: TrackerLoadInformation):

    template_ids = _get_template_ids()
    logging.info(f"Found template ids: {template_ids} for load_info: {load_info}")

    if template_ids is None:
        return

    logging.info(
        f"Starting graph steer creation process for template_id: {template_ids} and load_info: {load_info}"
    )
    for template_id in template_ids:
        logging.info(
            f"Processing template_id: {template_id} and load_info: {load_info}"
        )

        # Extract_config
        config_dict = graph_get_config(template_id)
        logging.info(
            f"Extracted config for template_id: {template_id} and load_info: {load_info}"
        )

        # Create slides
        config_dict = graph_create_ppt(config_dict)
        logging.info(
            f"Created slides for template_id: {template_id} and load_info: {load_info}"
        )

        # Send email
        send_email(config_dict)
        logging.info(
            f"Sent email for template_id: {template_id} and load_info: {load_info}"
        )


def _get_template_ids():
    data = read_data(Templates, ["is_active"], [True])
    try:
        template_ids = data["id"].unique()
    except Exception as exc:
        logging.exception(f"Error getting duplicate template ids {list(data['id'])}")
        raise RuntimeError(
            f"Error getting duplicate template ids for {list(data['id'])}"
        ) from exc

    return template_ids

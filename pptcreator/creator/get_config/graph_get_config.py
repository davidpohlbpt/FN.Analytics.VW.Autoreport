import logging

from pptcreator.creator.get_config.get_config_center_config import (
    get_config_center_config,
)
from pptcreator.creator.get_config.get_database_config import get_database_config
from pptcreator.creator.get_config.get_template_config import get_template_config


def graph_get_config(template_id: int) -> dict:
    try:
        config_dict = {}

        ## Extract config from database
        logging.info(f"Fetching database config for template {template_id}")
        config_dict = get_database_config(config_dict, template_id)

        if config_dict is None:
            raise ValueError(
                f"Database config for template id {template_id} not found or inactive."
            )

        ## Extract relevant config from template
        logging.info(f"Fetching template config for template {template_id}")
        config_dict = get_template_config(config_dict)

        ## Gather report-specific config from config center
        logging.info(f"Fetching config center config for template {template_id}")
        config_dict = get_config_center_config(config_dict)

        logging.info(f"Successfully fetched all configs for template {template_id}")
        return config_dict

    except Exception as e:
        logging.exception(f"Error processing template {template_id}: {e}")
        raise ValueError(f"Error processing template {template_id}: {e}") from e

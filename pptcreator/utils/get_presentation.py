import io
from pathlib import PurePosixPath

from pptx import Presentation, presentation
from pycore.easy import storage


def get_presentation(config_dict: dict) -> presentation.Presentation:

    template_data = storage.read_blob(
        blob_name=config_dict["file"],
        container_name=config_dict["file_container"],
        decode=False,
    )
    prs = Presentation(io.BytesIO(template_data))
    return prs

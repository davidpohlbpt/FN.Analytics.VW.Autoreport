"""E-mail step of the legacy creation pipeline.

E-mails are sent only by the vw-autoreport-sendemail Lambda. The legacy pipeline keeps
this call for compatibility, but leaves the rendered deck in pycore storage.
"""

import logging


def send_email(config_dict: dict) -> None:
    logging.warning(
        f"Legacy pipeline did not e-mail {config_dict.get('target_file_name')}; "
        "use the vw-autoreport-sendemail Lambda."
    )

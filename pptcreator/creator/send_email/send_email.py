"""E-mail step of the creation pipeline.

Reads the rendered deck from pycore storage and sends it through Amazon SES. The
``config_dict`` contract is unchanged from the legacy pipeline: ``target_file_name``,
``target_blob_container`` and ``recipients`` are required; ``email_subject`` and
``email_intro`` are optional overrides used by the KPI deck process.
"""

import logging

from pycore.easy import storage

from pptcreator.infra import mailer


def send_email(config_dict: dict) -> str | None:
    """Send the deck referenced by ``config_dict``. Returns the SES MessageId or None."""
    try:
        target_file_name = f"{config_dict['target_file_name']}.pptx"
        target_blob_container = config_dict["target_blob_container"]
        ppt_file = storage.read_blob(
            blob_name=target_file_name,
            container_name=target_blob_container,
            decode=False,
        )

        recipients = list(config_dict["recipients"])
        subject = config_dict.get("email_subject") or f"Report: {config_dict['target_file_name']}"
        intro = config_dict.get("email_intro") or "Please find the attached PowerPoint report:"

        html_body = f"<p>{intro} <strong>{target_file_name}</strong>.</p>"
        text_body = f"{intro} {target_file_name}"

        message_id = mailer.send_pptx(
            recipients=recipients,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            attachment_name=target_file_name,
            attachment_bytes=ppt_file,  # type: ignore[arg-type]
        )
        logging.info(f"PPT email step done for {recipients} (file: {target_file_name})")
        return message_id
    except Exception as e:
        logging.exception(f"Failed to send PPT email: {e}")
        raise

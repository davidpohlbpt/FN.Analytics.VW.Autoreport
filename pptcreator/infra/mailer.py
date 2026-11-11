"""Sends the rendered deck as an e-mail attachment through Amazon SES.

Uses ``send_raw_email`` because the standard ``send_email`` API does not support
attachments. SES limits the whole raw message to 40 MB; the base64 encoding adds
roughly a third, so the attachment is checked against ``ses_max_attachment_mb``.
"""

import logging
import time
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from pptcreator.config import settings
from pptcreator.infra.aws_clients import ses_client

PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
_RETRYABLE = {"Throttling", "ThrottlingException", "ServiceUnavailable", "RequestTimeout"}


class MailError(RuntimeError):
    pass


def validate_recipients(recipients: list[str]) -> list[str]:
    cleaned = []
    for recipient in recipients or []:
        address = (recipient or "").strip()
        if not address:
            continue
        if "@" not in address or address.startswith("@") or address.endswith("@"):
            raise MailError(f"Invalid recipient address: {recipient!r}")
        if address not in cleaned:
            cleaned.append(address)
    if not cleaned:
        raise MailError("No valid recipients given.")
    return cleaned


def build_message(
    *,
    sender: str,
    recipients: list[str],
    subject: str,
    html_body: str,
    text_body: str,
    attachment_name: str,
    attachment_bytes: bytes,
    recipients_mode: str = "bcc",
) -> MIMEMultipart:
    size_mb = len(attachment_bytes) / (1024 * 1024)
    if size_mb > settings.ses_max_attachment_mb:
        raise MailError(
            f"Attachment '{attachment_name}' is {size_mb:.1f} MB, above the configured "
            f"limit of {settings.ses_max_attachment_mb} MB."
        )

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = sender
    if recipients_mode == "to":
        msg["To"] = ", ".join(recipients)
    else:
        # Bcc: no Bcc header is written; SES delivers to ``Destinations`` only.
        msg["To"] = "undisclosed-recipients:;"

    body = MIMEMultipart("alternative")
    body.attach(MIMEText(text_body, "plain", "utf-8"))
    body.attach(MIMEText(html_body, "html", "utf-8"))
    msg.attach(body)

    part = MIMEApplication(attachment_bytes, _subtype="octet-stream")
    part.set_type(PPTX_MIME)
    part.add_header("Content-Disposition", "attachment", filename=attachment_name)
    msg.attach(part)
    return msg


def send_pptx(
    *,
    recipients: list[str],
    subject: str,
    html_body: str,
    text_body: str,
    attachment_name: str,
    attachment_bytes: bytes,
    sender: str | None = None,
    max_attempts: int = 3,
) -> str | None:
    """Send the deck. Returns the SES MessageId, or None when mail is disabled."""
    recipients = validate_recipients(recipients)

    if not settings.mail_enabled:
        logging.info(
            f"Mail disabled; would send '{attachment_name}' "
            f"({len(attachment_bytes) / 1024:.0f} KB) to {recipients}"
        )
        return None

    sender = sender or settings.ses_sender
    if not sender:
        raise MailError("mail_enabled is true but ses_sender is not configured.")

    msg = build_message(
        sender=sender,
        recipients=recipients,
        subject=subject,
        html_body=html_body,
        text_body=text_body,
        attachment_name=attachment_name,
        attachment_bytes=attachment_bytes,
        recipients_mode=settings.ses_recipients_mode,
    )

    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = ses_client().send_raw_email(
                Source=sender,
                Destinations=recipients,
                RawMessage={"Data": msg.as_bytes()},
            )
            message_id = response.get("MessageId")
            logging.info(f"Sent '{attachment_name}' to {recipients} (MessageId={message_id})")
            return message_id
        except Exception as exc:  # botocore ClientError or network error
            last_error = exc
            code = getattr(exc, "response", {}).get("Error", {}).get("Code", "")
            if code in _RETRYABLE and attempt < max_attempts:
                wait = 2**attempt
                logging.warning(f"SES {code}, retrying in {wait}s (attempt {attempt}/{max_attempts})")
                time.sleep(wait)
                continue
            break

    raise MailError(f"Sending '{attachment_name}' to {recipients} failed: {last_error}") from last_error

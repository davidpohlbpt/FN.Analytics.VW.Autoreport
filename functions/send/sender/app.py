"""Lambda 3: e-mail one rendered deck.

in:  the RenderResult of the render Lambda (JSON):
     {"status": "rendered", "request": {...}, "file_name", "bucket", "s3_key",
      "email_subject", "email_intro", ...}; an optional top-level "recipients"
     overrides request.recipients.
out: {"status": "sent" | "skipped", "request", "recipients", "message_id", "error"}
Raises SendFailed on failure so that Step Functions retries / catches it. The run log
is written by the record Lambda after the Map, so no database access is needed here.
"""

from __future__ import annotations

import json
import logging

import boto3

from sender import config, mailer

logging.getLogger().setLevel(logging.INFO)

DEFAULT_INTRO = "Please find the attached PowerPoint report:"


class SendFailed(RuntimeError):
    """Raised so that Step Functions sees a task failure."""


def handler(event, context):
    if isinstance(event, str):
        event = json.loads(event)
    request_id = getattr(context, "aws_request_id", None)
    logging.info(f"Invocation {request_id} with event: {json.dumps(event, default=str)[:2000]}")

    result = send(event, event.get("recipients"))
    if result["status"] == "failed":
        raise SendFailed(result["error"] or "send failed")
    return result


def send(render: dict, recipients: list[str] | None = None, data: bytes | None = None) -> dict:
    """Send the deck described by ``render``. Never raises; failures are in the result.

    ``data``: the .pptx bytes when the caller already has them (local runs without S3);
    otherwise they are downloaded from ``render['bucket']``/``render['s3_key']``.
    """
    request = render.get("request") or {}
    recipients = list(recipients if recipients is not None else request.get("recipients") or [])
    file_name = render.get("file_name")

    def result(status: str, error: str | None = None, message_id: str | None = None) -> dict:
        return {
            "status": status,
            "request": request,
            "recipients": recipients,
            "message_id": message_id,
            "error": error,
        }

    if render.get("status") != "rendered" or not file_name:
        return result("skipped", f"Nothing to send: render status is {render.get('status')!r} ({render.get('error')}).")
    if not recipients:
        return result("skipped", "No recipients.")
    if not config.mail_enabled():
        logging.warning(f"MAIL_ENABLED is false; '{file_name}' not sent to {recipients}.")
        return result("skipped", "MAIL_ENABLED is false.")

    try:
        if data is None:
            data = _download(render)
        intro = render.get("email_intro") or DEFAULT_INTRO
        message_id = mailer.send_pptx(
            recipients=recipients,
            subject=render.get("email_subject") or f"Report: {file_name}",
            html_body=f"<p>{intro} <strong>{file_name}</strong>.</p>",
            text_body=f"{intro} {file_name}",
            attachment_name=file_name,
            attachment_bytes=data,
        )
    except Exception as exc:
        logging.exception(f"Send for {request.get('brand')} failed: {exc}")
        return result("failed", f"{type(exc).__name__}: {exc}")
    return result("sent", message_id=message_id)


def _download(render: dict) -> bytes:
    bucket, key = render.get("bucket"), render.get("s3_key")
    if not bucket or not key:
        raise mailer.MailError(f"'{render.get('file_name')}' is not in S3 (bucket/s3_key missing).")
    s3 = boto3.client("s3", region_name=config.aws_region())
    return s3.get_object(Bucket=bucket, Key=key)["Body"].read()

"""Process setup shared by all Lambdas; must be imported before anything that imports pycore."""

from __future__ import annotations

import json
import logging
import os

# pycore reads these at import; set sane Lambda defaults before importing it.
os.environ.setdefault("APP_NAME", "VwAutoreport")
os.environ.setdefault("RESOURCE_TYPE", "LOCAL")
if os.environ.get("AWS_LAMBDA_FUNCTION_NAME") and not os.environ.get("LOCAL_BLOB_DIR"):
    os.environ["LOCAL_BLOB_DIR"] = "/tmp/autoreport_data"

# Optional internal CA bundle baked into the image (deployment/certs/*.pem). Only
# activated when the file exists, so images without certs keep the system defaults.
_ca_bundle = os.environ.get("CA_BUNDLE_PATH")
if _ca_bundle and os.path.isfile(_ca_bundle):
    os.environ.setdefault("REQUESTS_CA_BUNDLE", _ca_bundle)
    os.environ.setdefault("SSL_CERT_FILE", _ca_bundle)

# Must run before pycore is imported (it reads LOCAL_SQLSERVER_CONN_STR at import).
from pptcreator.infra.sql_connection import configure_from_ssm  # noqa: E402

configure_from_ssm()

logging.getLogger().setLevel(logging.INFO)


def log_start(context, event) -> None:
    request_id = getattr(context, "aws_request_id", None)
    logging.info(f"Invocation {request_id} with event: {json.dumps(event, default=str)[:2000]}")


def normalise_event(event) -> dict:
    if event is None:
        return {}
    if isinstance(event, str):
        event = json.loads(event)
    if not isinstance(event, dict):
        raise ValueError(f"Unsupported event type {type(event).__name__}.")
    # EventBridge custom events carry the payload in "detail"; constant inputs do not.
    if "mode" not in event and "trigger" not in event and "brand" not in event and isinstance(event.get("detail"), dict):
        return event["detail"]
    return event

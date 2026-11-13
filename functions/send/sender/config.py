"""Settings of the send Lambda, read from the environment at call time.

Upper- and lower-case names are accepted, because local ``.env`` files use lower case.
"""

from __future__ import annotations

import os

_TRUE = {"1", "true", "yes", "on"}


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is None:
        value = os.environ.get(name.lower())
    if value is None or not value.strip():
        return default
    return value.strip()


def mail_enabled() -> bool:
    """When false, nothing is sent and the result is 'skipped'."""
    return (_env("MAIL_ENABLED", "false") or "").lower() in _TRUE


def ses_sender() -> str | None:
    """Verified SES sender, e.g. ``VW KPI Report <kpi-report@example.com>``."""
    return _env("SES_SENDER")


def recipients_mode() -> str:
    mode = (_env("SES_RECIPIENTS_MODE", "bcc") or "bcc").lower()
    if mode not in ("bcc", "to"):
        raise ValueError(f"SES_RECIPIENTS_MODE must be 'bcc' or 'to', got {mode!r}.")
    return mode


def max_attachment_mb() -> int:
    """SES hard limit is 40 MB for the whole raw message; keep a safety margin."""
    return int(_env("SES_MAX_ATTACHMENT_MB", "35"))


def aws_region() -> str | None:
    """``AWS_REGION_NAME`` if set; else boto3's default resolution (``AWS_REGION`` in Lambda)."""
    return _env("AWS_REGION_NAME")

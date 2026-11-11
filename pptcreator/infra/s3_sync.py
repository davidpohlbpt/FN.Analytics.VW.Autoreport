"""Moves files between S3 and pycore's storage.

pycore storage is the single storage abstraction used by the rendering code
(``get_presentation``, ``graph_create_ppt``, ``send_email``). In Lambda it is a
FileStorage under ``/tmp`` and is ephemeral, so the template is pulled from S3 before
rendering and the finished deck is pushed back afterwards. With ``s3_enabled=False``
(local runs, unit tests) both steps are no-ops and the files simply stay in storage.
"""

from __future__ import annotations

import logging

from pycore.easy import storage

from pptcreator.config import settings
from pptcreator.infra.aws_clients import s3_client

PPTX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


class S3SyncError(RuntimeError):
    pass


def ensure_container(container_name: str) -> None:
    if not storage.container_exists(container_name):
        storage.create_container(container_name)


# ------------------------------------------------------------------------------ #
# Template
# ------------------------------------------------------------------------------ #


def download_template(
    container_name: str | None = None,
    blob_name: str | None = None,
    *,
    bucket: str | None = None,
    key: str | None = None,
    force: bool = False,
) -> str:
    """Make sure the template exists in pycore storage, fetching it from S3 if needed.

    ``bucket``/``key`` default to the settings. Returns the blob name in the container.
    """
    container_name = container_name or settings.storage_container
    blob_name = blob_name or settings.template_file_name
    bucket = bucket or settings.s3_bucket
    key = key or settings.s3_template_key
    ensure_container(container_name)

    if not force and blob_exists(container_name, blob_name):
        logging.info(f"Template '{blob_name}' already present in storage, not fetched.")
        return blob_name

    if not settings.s3_enabled:
        raise S3SyncError(
            f"Template '{blob_name}' not found in storage container "
            f"'{container_name}' and S3 is disabled. Place the file there or enable S3."
        )
    if not bucket:
        raise S3SyncError("s3_enabled is true but no S3 bucket is configured for the template.")

    logging.info(f"Downloading template s3://{bucket}/{key} into storage {container_name}/{blob_name}")
    data = download_bytes(bucket, key)
    storage.write_blob(container_name=container_name, blob_name=blob_name, blob_data=data)
    return blob_name


def download_bytes(bucket: str, key: str) -> bytes:
    try:
        response = s3_client().get_object(Bucket=bucket, Key=key)
        return response["Body"].read()
    except Exception as exc:  # botocore exceptions are not worth importing here
        raise S3SyncError(f"Could not download s3://{bucket}/{key}: {exc}") from exc


# ------------------------------------------------------------------------------ #
# Output
# ------------------------------------------------------------------------------ #


def upload_output(
    container_name: str,
    blob_name: str,
    key_prefix: str | None = None,
    *,
    bucket: str | None = None,
) -> str | None:
    """Upload a rendered deck from pycore storage to S3. Returns the S3 key or None."""
    if not settings.s3_enabled:
        logging.info(f"S3 disabled; '{blob_name}' remains in storage {container_name}.")
        return None
    bucket = bucket or settings.s3_bucket
    if not bucket:
        raise S3SyncError("s3_enabled is true but no S3 bucket is configured for outputs.")

    data = storage.read_blob(container_name=container_name, blob_name=blob_name, decode=False)
    prefix = (key_prefix if key_prefix is not None else settings.s3_output_prefix).strip("/")
    key = f"{prefix}/{blob_name}" if prefix else blob_name
    upload_bytes(bucket, key, data, PPTX_CONTENT_TYPE)
    logging.info(f"Uploaded report to s3://{bucket}/{key}")
    return key


def upload_bytes(bucket: str, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
    try:
        s3_client().put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)
    except Exception as exc:
        raise S3SyncError(f"Could not upload to s3://{bucket}/{key}: {exc}") from exc


def blob_exists(container_name: str, blob_name: str) -> bool:
    try:
        return blob_name in storage.list_blobs(container_name=container_name)
    except Exception:
        return False

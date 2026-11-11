"""Moves files between S3 and pycore's storage.

pycore storage is the single storage abstraction used by the rendering code
(``get_presentation``, ``graph_create_ppt``, ``send_email``). In Lambda it is a
FileStorage under ``/tmp`` and is ephemeral, so the template is pulled from S3 before
rendering and the finished deck is pushed back afterwards. With ``s3_enabled=False``
(local runs, unit tests) both steps are no-ops and the files simply stay in storage.
"""

import logging

from pycore.easy import storage

from pptcreator.config import settings
from pptcreator.infra.aws_clients import s3_client


class S3SyncError(RuntimeError):
    pass


def ensure_container(container_name: str) -> None:
    if not storage.container_exists(container_name):
        storage.create_container(container_name)


def download_template(
    container_name: str | None = None,
    blob_name: str | None = None,
    *,
    force: bool = False,
) -> str:
    """Make sure the template exists in pycore storage, fetching it from S3 if needed.

    Returns the blob name inside the container.
    """
    container_name = container_name or settings.storage_container
    blob_name = blob_name or settings.template_file_name
    ensure_container(container_name)

    if not force and _blob_exists(container_name, blob_name):
        logging.info(f"Template '{blob_name}' already present in storage, not fetched.")
        return blob_name

    if not settings.s3_enabled:
        raise S3SyncError(
            f"Template '{blob_name}' not found in storage container "
            f"'{container_name}' and S3 is disabled. Place the file there or enable S3."
        )
    if not settings.s3_bucket:
        raise S3SyncError("s3_enabled is true but s3_bucket is not configured.")

    logging.info(
        f"Downloading template s3://{settings.s3_bucket}/{settings.s3_template_key} "
        f"into storage {container_name}/{blob_name}"
    )
    try:
        response = s3_client().get_object(
            Bucket=settings.s3_bucket, Key=settings.s3_template_key
        )
        data = response["Body"].read()
    except Exception as exc:  # botocore exceptions are not worth importing here
        raise S3SyncError(
            f"Could not download template from s3://{settings.s3_bucket}/"
            f"{settings.s3_template_key}: {exc}"
        ) from exc

    storage.write_blob(container_name=container_name, blob_name=blob_name, blob_data=data)
    return blob_name


def upload_output(container_name: str, blob_name: str, key_prefix: str | None = None) -> str | None:
    """Upload a rendered deck from pycore storage to S3. Returns the S3 key or None."""
    if not settings.s3_enabled:
        logging.info(f"S3 disabled; '{blob_name}' remains in storage {container_name}.")
        return None
    if not settings.s3_bucket:
        raise S3SyncError("s3_enabled is true but s3_bucket is not configured.")

    data = storage.read_blob(container_name=container_name, blob_name=blob_name, decode=False)
    prefix = (key_prefix or settings.s3_output_prefix).strip("/")
    key = f"{prefix}/{blob_name}" if prefix else blob_name

    try:
        s3_client().put_object(
            Bucket=settings.s3_bucket,
            Key=key,
            Body=data,
            ContentType=(
                "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            ),
        )
    except Exception as exc:
        raise S3SyncError(f"Could not upload '{blob_name}' to s3://{settings.s3_bucket}/{key}: {exc}") from exc

    logging.info(f"Uploaded report to s3://{settings.s3_bucket}/{key}")
    return key


def _blob_exists(container_name: str, blob_name: str) -> bool:
    try:
        return blob_name in storage.list_blobs(container_name=container_name)
    except Exception:
        return False

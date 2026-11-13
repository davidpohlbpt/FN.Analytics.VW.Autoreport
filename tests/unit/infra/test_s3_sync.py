import pytest

from pptcreator.config import settings
from pptcreator.infra import s3_sync
from tests.unit.infra.conftest import BUCKET


def test_download_template_from_s3(aws, easy_test):
    aws["s3"].put_object(Bucket=BUCKET, Key=settings.s3_template_key, Body=b"TEMPLATE")

    name = s3_sync.download_template("cont", "T.pptx")

    assert name == "T.pptx"
    assert easy_test.storage.read_blob(container_name="cont", blob_name="T.pptx", decode=False) == b"TEMPLATE"


def test_download_template_uses_cached_copy(aws, easy_test):
    easy_test.storage.create_container("cont")
    easy_test.storage.write_blob(container_name="cont", blob_name="T.pptx", blob_data=b"LOCAL")
    # Nothing in S3 -> would fail if it tried to download
    assert s3_sync.download_template("cont", "T.pptx") == "T.pptx"
    assert easy_test.storage.read_blob(container_name="cont", blob_name="T.pptx", decode=False) == b"LOCAL"


def test_download_template_missing_in_s3_raises(aws, easy_test):
    with pytest.raises(s3_sync.S3SyncError, match="Could not download"):
        s3_sync.download_template("cont", "T.pptx")


def test_download_template_s3_disabled_and_missing(easy_test, monkeypatch):
    monkeypatch.setattr(settings, "s3_enabled", False)
    with pytest.raises(s3_sync.S3SyncError, match="S3 is disabled"):
        s3_sync.download_template("cont", "T.pptx")


def test_upload_output(aws, easy_test):
    easy_test.storage.create_container("cont")
    easy_test.storage.write_blob(container_name="cont", blob_name="out.pptx", blob_data=b"DECK")

    key = s3_sync.upload_output("cont", "out.pptx")

    assert key == f"{settings.s3_output_prefix}/out.pptx"
    body = aws["s3"].get_object(Bucket=BUCKET, Key=key)["Body"].read()
    assert body == b"DECK"


def test_upload_output_disabled(easy_test, monkeypatch):
    monkeypatch.setattr(settings, "s3_enabled", False)
    assert s3_sync.upload_output("cont", "out.pptx") is None

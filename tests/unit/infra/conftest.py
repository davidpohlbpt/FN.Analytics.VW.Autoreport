import os

import boto3
import pytest
from moto import mock_aws

from pptcreator.config import settings
from pptcreator.infra import aws_clients

REGION = "eu-central-1"
BUCKET = "autoreport-test-bucket"
SENDER = "reporting@example.com"


@pytest.fixture
def aws(monkeypatch):
    """moto-backed S3 + SES with the project settings switched to AWS mode."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)
    for key in ("AWS_PROFILE", "AWS_SESSION_TOKEN"):
        monkeypatch.delenv(key, raising=False)

    monkeypatch.setattr(settings, "aws_region", REGION)
    monkeypatch.setattr(settings, "s3_enabled", True)
    monkeypatch.setattr(settings, "s3_bucket", BUCKET)
    # The send Lambda (functions/send/sender) reads its settings from the environment
    monkeypatch.setenv("AWS_REGION_NAME", REGION)
    monkeypatch.setenv("MAIL_ENABLED", "true")
    monkeypatch.setenv("SES_SENDER", SENDER)

    aws_clients.reset_clients()
    with mock_aws():
        s3 = boto3.client("s3", region_name=REGION)
        s3.create_bucket(
            Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": REGION}
        )
        ses = boto3.client("ses", region_name=REGION)
        ses.verify_email_identity(EmailAddress=SENDER)
        yield {"s3": s3, "ses": ses}
    aws_clients.reset_clients()

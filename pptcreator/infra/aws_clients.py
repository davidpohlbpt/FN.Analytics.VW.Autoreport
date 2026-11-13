"""Lazily created boto3 clients so that importing the package never needs AWS."""

import functools

from pptcreator.config import settings


@functools.lru_cache(maxsize=None)
def s3_client():
    import boto3

    return boto3.client("s3", region_name=settings.aws_region)


def reset_clients() -> None:
    """Drop cached clients, e.g. between moto-mocked tests."""
    s3_client.cache_clear()

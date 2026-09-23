"""Presigned URLs are minted against the internal MinIO endpoint; browsers get a same-origin path."""

from kanalchi.core import storage
from kanalchi.core.settings import get_settings


def test_presigned_url_becomes_same_origin_relative(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "s3_endpoint", "http://minio:9000")
    signed = "http://minio:9000/uploads/3/drafts/abc.png?X-Amz-Signature=deadbeef&X-Amz-Expires=900"
    assert (
        storage.public_presigned_url(signed)
        == "/uploads/3/drafts/abc.png?X-Amz-Signature=deadbeef&X-Amz-Expires=900"
    )


def test_urls_from_another_endpoint_are_left_alone(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "s3_endpoint", "http://minio:9000")
    other = "https://cdn.example.net/x.png?sig=1"
    assert storage.public_presigned_url(other) == other

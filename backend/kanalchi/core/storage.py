"""MinIO / S3 object storage helpers (async via aioboto3)."""

from __future__ import annotations

import mimetypes
from datetime import timedelta
from pathlib import Path

import aioboto3

from kanalchi.core.settings import get_settings

_session = aioboto3.Session()


def _client_kwargs() -> dict:
    s = get_settings()
    return {
        "service_name": "s3",
        "endpoint_url": s.s3_endpoint,
        "aws_access_key_id": s.s3_access_key,
        "aws_secret_access_key": s.s3_secret_key,
        "region_name": s.s3_region,
    }


async def upload_file(bucket: str, key: str, path: Path, content_type: str | None = None) -> None:
    ct = content_type or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    async with _session.client(**_client_kwargs()) as s3:
        await s3.upload_file(str(path), bucket, key, ExtraArgs={"ContentType": ct})


async def upload_bytes(bucket: str, key: str, data: bytes, content_type: str) -> None:
    async with _session.client(**_client_kwargs()) as s3:
        await s3.put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)


async def delete_object(bucket: str, key: str) -> None:
    async with _session.client(**_client_kwargs()) as s3:
        await s3.delete_object(Bucket=bucket, Key=key)


async def presigned_get(bucket: str, key: str, expires: timedelta = timedelta(hours=1)) -> str:
    async with _session.client(**_client_kwargs()) as s3:
        return await s3.generate_presigned_url(
            "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=int(expires.total_seconds())
        )


async def presigned_put(
    bucket: str, key: str, content_type: str, expires: timedelta = timedelta(minutes=15)
) -> str:
    async with _session.client(**_client_kwargs()) as s3:
        return await s3.generate_presigned_url(
            "put_object",
            Params={"Bucket": bucket, "Key": key, "ContentType": content_type},
            ExpiresIn=int(expires.total_seconds()),
        )


async def ping() -> bool:
    try:
        async with _session.client(**_client_kwargs()) as s3:
            await s3.head_bucket(Bucket=get_settings().s3_bucket_media)
        return True
    except Exception:
        return False


def public_media_url(host: str, key: str) -> str:
    """Media is served on the tenant's own domain under /media/<key> (Caddy → MinIO)."""
    s = get_settings()
    return f"{s.public_scheme}://{host}/media/{key}"


def public_presigned_url(presigned: str) -> str:
    """Rewrite a presigned URL so a browser can use it.

    Presigned URLs are minted against the internal endpoint (``http://minio:9000`` in
    production), which a browser cannot reach. Caddy (and the Next dev rewrite) proxy
    ``/<bucket>/…`` on the tenant host to MinIO and forward the internal ``Host`` header, so
    the signature — which covers host, path and query but not the scheme or origin the browser
    used — still verifies. The result is same-origin relative, which works on any tenant host
    and on the dev port alike.
    """
    endpoint = get_settings().s3_endpoint.rstrip("/")
    if not presigned.startswith(endpoint + "/"):
        return presigned
    return presigned[len(endpoint) :]

"""S3-хранилище (MinIO): файлы резюме и экспорта. Синхронный boto3 уходит в поток."""

from __future__ import annotations

import asyncio
from typing import Any

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError


class ObjectStorage:
    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        public_url: str | None = None,
    ):
        self.bucket = bucket
        kwargs: dict[str, Any] = {
            "aws_access_key_id": access_key,
            "aws_secret_access_key": secret_key,
            "region_name": "us-east-1",
            "config": Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        }
        self._client = boto3.client("s3", endpoint_url=endpoint, **kwargs)
        # presigned-ссылки подписываются публичным хостом, который видит браузер
        self._signer = (
            boto3.client("s3", endpoint_url=public_url, **kwargs) if public_url else self._client
        )

    async def ensure_bucket(self) -> None:
        try:
            await asyncio.to_thread(self._client.head_bucket, Bucket=self.bucket)
        except ClientError:
            await asyncio.to_thread(self._client.create_bucket, Bucket=self.bucket)

    async def put(self, key: str, data: bytes, content_type: str = "application/octet-stream"):
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )

    async def get(self, key: str) -> bytes:
        resp = await asyncio.to_thread(self._client.get_object, Bucket=self.bucket, Key=key)
        return await asyncio.to_thread(resp["Body"].read)

    async def exists(self, key: str) -> bool:
        try:
            await asyncio.to_thread(self._client.head_object, Bucket=self.bucket, Key=key)
        except ClientError:
            return False
        return True

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._client.delete_object, Bucket=self.bucket, Key=key)

    def presigned_get(self, key: str, expires: int = 300) -> str:
        return self._signer.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=expires
        )

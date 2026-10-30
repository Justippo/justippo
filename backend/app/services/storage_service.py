# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Storage Service — Interact with R2 storage using httpx.
"""

import datetime
import hashlib
import hmac
import os
from urllib.parse import quote

import httpx


class StorageService:
    def __init__(self) -> None:
        self.bucket_name = os.environ.get("R2_BUCKET_NAME", "evidence-eu-translations")
        self.endpoint_url = os.environ.get(
            "R2_ENDPOINT_URL", "https://example.r2.cloudflarestorage.com"
        )
        self.access_key = os.environ.get("R2_ACCESS_KEY_ID", "")
        self.secret_key = os.environ.get("R2_SECRET_ACCESS_KEY", "")
        self.region = "auto"
        self.service = "s3"

    def _sign(self, key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    def _get_signature_key(
        self, key: str, dateStamp: str, regionName: str, serviceName: str
    ) -> bytes:
        kDate = self._sign(("AWS4" + key).encode("utf-8"), dateStamp)
        kRegion = self._sign(kDate, regionName)
        kService = self._sign(kRegion, serviceName)
        kSigning = self._sign(kService, "aws4_request")
        return kSigning

    async def get_file(self, object_key: str) -> bytes:
        url = f"{self.endpoint_url.rstrip('/')}/{self.bucket_name}/{quote(object_key)}"
        method = "GET"

        t = datetime.datetime.now(datetime.UTC)
        amz_date = t.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = t.strftime("%Y%m%d")

        canonical_uri = f"/{self.bucket_name}/{quote(object_key)}"
        canonical_querystring = ""
        canonical_headers = f"host:{self.endpoint_url.replace('https://', '')}\nx-amz-content-sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855\nx-amz-date:{amz_date}\n"
        signed_headers = "host;x-amz-content-sha256;x-amz-date"
        payload_hash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

        canonical_request = f"{method}\n{canonical_uri}\n{canonical_querystring}\n{canonical_headers}\n{signed_headers}\n{payload_hash}"

        algorithm = "AWS4-HMAC-SHA256"
        credential_scope = f"{date_stamp}/{self.region}/{self.service}/aws4_request"
        string_to_sign = f"{algorithm}\n{amz_date}\n{credential_scope}\n{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"

        signing_key = self._get_signature_key(
            self.secret_key, date_stamp, self.region, self.service
        )
        signature = hmac.new(
            signing_key, string_to_sign.encode("utf-8"), hashlib.sha256
        ).hexdigest()

        authorization_header = f"{algorithm} Credential={self.access_key}/{credential_scope}, SignedHeaders={signed_headers}, Signature={signature}"

        headers = {
            "x-amz-date": amz_date,
            "x-amz-content-sha256": payload_hash,
            "Authorization": authorization_header,
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            if response.status_code != 200:
                raise RuntimeError(
                    f"Failed to fetch file from R2: {response.status_code} {response.text}"
                )
            return response.content

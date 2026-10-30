"""Contract tests for the BabelDOC sidecar HTTP boundary."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.runtime import (
    BabelDocConfigError,
    BabelDocInvalidInputError,
    BabelDocRuntimeError,
    BabelDocRuntimeResult,
    BabelDocTimeoutError,
)

from app.main import BabelDocRequest, ready, require_bearer_auth, translate, validate_glossary_csv


def encode(value: bytes | str) -> str:
    """Base64-encode bytes or UTF-8 text for request payloads."""
    if isinstance(value, str):
        value = value.encode("utf-8")
    return base64.b64encode(value).decode("ascii")


def response_payload(response) -> dict:
    """Decode a Starlette JSONResponse body."""
    return json.loads(response.body.decode("utf-8"))


class TranslateContractTests(unittest.TestCase):
    """Verify ADR-012 success and error envelope behavior."""

    def _request(self) -> BabelDocRequest:
        return BabelDocRequest(
            source_lang="en",
            target_lang="de",
            document_b64=encode(b"%PDF-1.4\n%%EOF\n"),
            glossary_csv_b64=encode(
                "term_en,term_de,term_fr\nresidence permit,Aufenthaltserlaubnis,titre de séjour\n"
            ),
        )

    def test_valid_request_returns_translated_reference_pdf(self) -> None:
        runtime_result = BabelDocRuntimeResult(
            translated_b64=encode(b"%PDF-1.7 translated"),
            source_lang="en",
            target_lang="de",
            detected_lang="en",
            processing_time_ms=1250.0,
            layout_preserved=True,
            pages_processed=2,
            warnings=[],
        )
        with patch(
            "app.main.run_babeldoc_translation",
            new=AsyncMock(return_value=runtime_result),
        ) as runtime:
            response = asyncio.run(translate(self._request()))

        payload = response_payload(response)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["translated_b64"], runtime_result.translated_b64)
        self.assertEqual(payload["source_lang"], "en")
        self.assertEqual(payload["target_lang"], "de")
        self.assertTrue(payload["layout_preserved"])
        self.assertEqual(payload["pages_processed"], 2)
        runtime.assert_awaited_once()

    def test_invalid_document_base64_returns_invalid_input(self) -> None:
        request = BabelDocRequest(
            source_lang="en",
            target_lang="de",
            document_b64="not-base64",
        )

        response = asyncio.run(translate(request))
        payload = response_payload(response)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(payload["error"]["code"], "INVALID_INPUT")
        self.assertEqual(payload["error"]["message"], "document_b64 must be valid base64")

    def test_non_pdf_bytes_are_rejected_before_runtime(self) -> None:
        request = BabelDocRequest(
            source_lang="en",
            target_lang="de",
            document_b64=encode(b"not a PDF"),
        )
        with patch("app.main.run_babeldoc_translation", new=AsyncMock()) as runtime:
            response = asyncio.run(translate(request))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response_payload(response)["error"]["code"], "INVALID_INPUT")
        runtime.assert_not_awaited()

    def test_unsupported_language_returns_unsupported_language(self) -> None:
        request = BabelDocRequest(
            source_lang="es",
            target_lang="de",
            document_b64=encode(b"%PDF-1.4\n%%EOF\n"),
        )

        response = asyncio.run(translate(request))
        payload = response_payload(response)

        self.assertEqual(response.status_code, 422)
        self.assertEqual(payload["error"]["code"], "UNSUPPORTED_LANGUAGE")
        self.assertFalse(payload["error"]["retryable"])

    def test_runtime_invalid_options_return_400(self) -> None:
        with patch(
            "app.main.run_babeldoc_translation",
            new=AsyncMock(side_effect=BabelDocInvalidInputError("options.qps is invalid")),
        ):
            response = asyncio.run(translate(self._request()))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response_payload(response)["error"]["code"], "INVALID_INPUT")

    def test_runtime_timeout_returns_retryable_504(self) -> None:
        with patch(
            "app.main.run_babeldoc_translation",
            new=AsyncMock(side_effect=BabelDocTimeoutError("processing exceeded 120s")),
        ):
            response = asyncio.run(translate(self._request()))

        payload = response_payload(response)
        self.assertEqual(response.status_code, 504)
        self.assertEqual(payload["error"]["code"], "TIMEOUT")
        self.assertTrue(payload["error"]["retryable"])

    def test_missing_runtime_config_returns_generic_503(self) -> None:
        with patch(
            "app.main.run_babeldoc_translation",
            new=AsyncMock(
                side_effect=BabelDocConfigError("missing BABELDOC_OPENAI_API_KEY=private-secret")
            ),
        ):
            response = asyncio.run(translate(self._request()))

        payload = response_payload(response)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(payload["error"]["code"], "SERVICE_UNAVAILABLE")
        self.assertNotIn("private-secret", json.dumps(payload))

    def test_runtime_failure_omits_process_output(self) -> None:
        with patch(
            "app.main.run_babeldoc_translation",
            new=AsyncMock(side_effect=BabelDocRuntimeError("source document text from stderr")),
        ):
            response = asyncio.run(translate(self._request()))

        payload = response_payload(response)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(payload["error"]["code"], "TRANSLATION_FAILED")
        self.assertNotIn("source document text", json.dumps(payload))


class GlossaryContractTests(unittest.TestCase):
    """Verify optional glossary CSV validation."""

    def test_valid_glossary_csv_decodes_rows(self) -> None:
        rows = validate_glossary_csv(
            encode(
                "term_en,term_de,term_fr\n"
                "notarized copy,beglaubigte Kopie,copie certifiée conforme\n"
            )
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["term_en"], "notarized copy")

    def test_missing_glossary_column_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "term_fr"):
            validate_glossary_csv(encode("term_en,term_de\nnotarized copy,beglaubigte Kopie\n"))

    def test_empty_glossary_rows_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least one term row"):
            validate_glossary_csv(encode("term_en,term_de,term_fr\n"))

    def test_partial_glossary_row_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "row 1"):
            validate_glossary_csv(encode("term_en,term_de,term_fr\nnotarized copy,,\n"))


class AuthContractTests(unittest.TestCase):
    """Verify BABELDOC_AUTH_TOKEN enforcement on POST /translate."""

    def setUp(self) -> None:
        self._original_token = os.environ.pop("BABELDOC_AUTH_TOKEN", None)

    def tearDown(self) -> None:
        if self._original_token is None:
            os.environ.pop("BABELDOC_AUTH_TOKEN", None)
        else:
            os.environ["BABELDOC_AUTH_TOKEN"] = self._original_token

    def test_no_token_configured_allows_any_request(self) -> None:
        self.assertIsNone(require_bearer_auth(None))
        self.assertIsNone(require_bearer_auth("Bearer anything"))

    def test_missing_header_is_rejected_when_token_configured(self) -> None:
        os.environ["BABELDOC_AUTH_TOKEN"] = "secret-token"
        self.assertEqual(require_bearer_auth(None), "UNAUTHORIZED")

    def test_wrong_token_is_rejected(self) -> None:
        os.environ["BABELDOC_AUTH_TOKEN"] = "secret-token"
        self.assertEqual(require_bearer_auth("Bearer wrong-token"), "UNAUTHORIZED")

    def test_malformed_header_is_rejected(self) -> None:
        os.environ["BABELDOC_AUTH_TOKEN"] = "secret-token"
        self.assertEqual(require_bearer_auth("secret-token"), "UNAUTHORIZED")

    def test_correct_token_is_accepted(self) -> None:
        os.environ["BABELDOC_AUTH_TOKEN"] = "secret-token"
        self.assertIsNone(require_bearer_auth("Bearer secret-token"))

    def test_translate_endpoint_rejects_unauthorized_request(self) -> None:
        os.environ["BABELDOC_AUTH_TOKEN"] = "secret-token"
        request = BabelDocRequest(
            source_lang="en",
            target_lang="de",
            document_b64=encode(b"%PDF-1.4\n%%EOF\n"),
        )
        response = asyncio.run(translate(request, authorization=None))
        payload = response_payload(response)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(payload["error"]["code"], "UNAUTHORIZED")


class ReadyEndpointTests(unittest.TestCase):
    """Verify /ready distinguishes real readiness from process liveness."""

    def test_ready_reports_unready_when_unconfigured(self) -> None:
        with patch(
            "app.main.get_runtime_config",
            side_effect=BabelDocConfigError("BabelDOC runtime is not configured"),
        ):
            response = asyncio.run(ready())

        payload = response_payload(response)
        self.assertEqual(response.status_code, 503)
        self.assertFalse(payload["ready"])
        self.assertFalse(payload["checks"]["configuration"])

    def test_ready_reports_ready_when_configured_and_executable_present(self) -> None:
        from app.runtime import BabelDocRuntimeConfig

        mock_config = BabelDocRuntimeConfig(
            openai_base_url="https://api.cloudflare.com/client/v4/accounts/test/ai/v1",
            openai_api_key="test-key",
            openai_model="@cf/meta/llama-3.3-70b-instruct-fp8-fast",
        )
        mock_response = MagicMock(status_code=200)
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.head = MagicMock(return_value=mock_response)

        with (
            patch("app.main.get_runtime_config", return_value=mock_config),
            patch("shutil.which", return_value="/usr/local/bin/babeldoc"),
            patch("httpx.Client", return_value=mock_client),
        ):
            response = asyncio.run(ready())

        payload = response_payload(response)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["ready"])
        self.assertTrue(payload["checks"]["configuration"])
        self.assertTrue(payload["checks"]["babeldoc_executable"])
        self.assertTrue(payload["checks"]["llm_endpoint_reachable"])


if __name__ == "__main__":
    unittest.main()

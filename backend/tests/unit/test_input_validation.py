# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for input validation (GDPR Domain 7 — target_lang + document_id)."""

import pytest

from app.api.v1.endpoints.translate import TranslationRequest


class TestTargetLangValidation:
    def test_valid_en(self):
        req = TranslationRequest(
            document_id="550e8400-e29b-41d4-a716-446655440000", target_language="en"
        )
        assert req.target_language == "en"

    def test_valid_de(self):
        req = TranslationRequest(
            document_id="550e8400-e29b-41d4-a716-446655440000", target_language="de"
        )
        assert req.target_language == "de"

    def test_valid_fr(self):
        req = TranslationRequest(
            document_id="550e8400-e29b-41d4-a716-446655440000", target_language="fr"
        )
        assert req.target_language == "fr"

    def test_invalid_lang_es_rejected(self):
        with pytest.raises(ValueError, match="target_language"):
            TranslationRequest(
                document_id="550e8400-e29b-41d4-a716-446655440000", target_language="es"
            )

    def test_invalid_lang_uppercase_rejected(self):
        with pytest.raises(ValueError, match="target_language"):
            TranslationRequest(
                document_id="550e8400-e29b-41d4-a716-446655440000", target_language="EN"
            )

    def test_invalid_lang_empty_rejected(self):
        with pytest.raises(ValueError, match="target_language"):
            TranslationRequest(
                document_id="550e8400-e29b-41d4-a716-446655440000", target_language=""
            )

    def test_invalid_lang_random_string_rejected(self):
        with pytest.raises(ValueError, match="target_language"):
            TranslationRequest(
                document_id="550e8400-e29b-41d4-a716-446655440000", target_language="javascript"
            )


class TestDocumentIdValidation:
    def test_valid_uuid4(self):
        req = TranslationRequest(
            document_id="550e8400-e29b-41d4-a716-446655440000", target_language="en"
        )
        assert req.document_id == "550e8400-e29b-41d4-a716-446655440000"

    def test_invalid_uuid_non_hex(self):
        with pytest.raises(ValueError, match="UUID4"):
            TranslationRequest(document_id="not-a-uuid", target_language="en")

    def test_invalid_uuid_wrong_version(self):
        with pytest.raises(ValueError, match="UUID4"):
            TranslationRequest(
                document_id="550e8400-e29b-11d4-a716-446655440000", target_language="en"
            )

    def test_invalid_uuid_wrong_variant(self):
        with pytest.raises(ValueError, match="UUID4"):
            TranslationRequest(
                document_id="550e8400-e29b-41d4-c716-446655440000", target_language="en"
            )

    def test_invalid_uuid_empty(self):
        with pytest.raises(ValueError, match="UUID4"):
            TranslationRequest(document_id="", target_language="en")

    def test_invalid_uuid_truncated(self):
        with pytest.raises(ValueError, match="UUID4"):
            TranslationRequest(document_id="550e8400-e29b-41d4", target_language="en")

    def test_sql_injection_attempt_rejected(self):
        with pytest.raises(ValueError, match="UUID4"):
            TranslationRequest(document_id="'; DROP TABLE audit_log; --", target_language="en")

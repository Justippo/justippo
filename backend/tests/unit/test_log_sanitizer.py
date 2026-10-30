# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for PII log sanitizer (GDPR Domain 1 — data minimisation)."""

from app.core.middleware import redact_query_string, sanitize_request_url_for_logging


class TestRedactQueryString:
    def test_redacts_single_param_value(self):
        assert redact_query_string("q=John+Doe") == "q=[REDACTED]"

    def test_redacts_multiple_param_values(self):
        result = redact_query_string("q=John&lang=en&page=1")
        assert result == "q=[REDACTED]&lang=[REDACTED]&page=[REDACTED]"

    def test_preserves_param_names(self):
        result = redact_query_string("name=Alice&email=alice@example.com")
        assert "name=" in result
        assert "email=" in result
        assert "Alice" not in result
        assert "alice@example.com" not in result

    def test_empty_string_returns_empty(self):
        assert redact_query_string("") == ""

    def test_no_equals_sign_unchanged(self):
        assert redact_query_string("flag") == "flag"

    def test_empty_value_redacted(self):
        assert redact_query_string("q=") == "q=[REDACTED]"

    def test_special_characters_in_value(self):
        result = redact_query_string("q=O'Brien&name=Müller")
        assert "O'Brien" not in result
        assert "Müller" not in result
        assert "q=[REDACTED]" in result
        assert "name=[REDACTED]" in result

    def test_none_input(self):
        assert redact_query_string(None) == ""

    def test_parameter_no_name(self):
        assert redact_query_string("=value") == "=[REDACTED]"

    def test_value_with_equal_signs(self):
        assert redact_query_string("q=a=b=c") == "q=[REDACTED]"

    def test_multiple_ampersands(self):
        assert redact_query_string("q=1&&lang=en") == "q=[REDACTED]&&lang=[REDACTED]"

    def test_url_encoded_values(self):
        assert redact_query_string("q=%20value%3D123") == "q=[REDACTED]"


class TestSanitizeRequestUrlForLogging:
    def test_redacts_query_string_in_full_url(self):
        url = "https://api.example.com/search?q=secret+query&lang=en"
        result = sanitize_request_url_for_logging(url)
        assert "secret+query" not in result
        assert "q=[REDACTED]" in result
        assert "lang=[REDACTED]" in result
        assert result.startswith("https://api.example.com/search?")

    def test_url_without_query_string_unchanged(self):
        url = "https://api.example.com/health"
        assert sanitize_request_url_for_logging(url) == url

    def test_url_with_empty_query_string(self):
        url = "https://api.example.com/search?"
        result = sanitize_request_url_for_logging(url)
        assert "search?" in result

    def test_preserves_url_structure(self):
        url = "http://localhost:8000/api/v1/documents/?target_lang=de"
        result = sanitize_request_url_for_logging(url)
        assert result.startswith("http://localhost:8000/api/v1/documents/?")
        assert "target_lang=[REDACTED]" in result

    def test_url_with_multiple_question_marks(self):
        url = "https://api.example.com/search?q=1?2"
        result = sanitize_request_url_for_logging(url)
        assert result == "https://api.example.com/search?q=[REDACTED]"

    def test_url_with_fragment(self):
        url = "https://api.example.com/search?q=1#frag"
        result = sanitize_request_url_for_logging(url)
        assert result == "https://api.example.com/search?q=[REDACTED]"

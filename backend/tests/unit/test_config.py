"""
Unit Tests — Core Configuration

Tests that the Settings model loads correctly from environment variables
and that computed properties return the expected values.
"""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_loads_with_required_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings must load when APP_SECRET_KEY is provided."""
    monkeypatch.setenv("APP_SECRET_KEY", "test-secret-key")
    settings = Settings()
    assert settings.APP_SECRET_KEY == "test-secret-key"


def test_feature_flags_default_to_false(monkeypatch: pytest.MonkeyPatch) -> None:
    """All Phase 2 and Sprint 3 feature flags must default to False."""
    monkeypatch.setenv("APP_SECRET_KEY", "test-secret-key")
    settings = Settings()
    assert settings.ENABLE_MATRIX_EXCHANGE is False
    assert settings.ENABLE_HEALTHCARE_PHASE2 is False
    assert settings.ENABLE_FHIR_PARSING is False


def test_hindsight_recall_profile_uses_documented_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_SECRET_KEY", "test-secret-key")
    monkeypatch.delenv("HINDSIGHT_RECALL_BUDGET", raising=False)
    monkeypatch.delenv("HINDSIGHT_RECALL_MAX_TOKENS", raising=False)

    settings = Settings(_env_file=None)

    assert settings.HINDSIGHT_RECALL_BUDGET == "mid"
    assert settings.HINDSIGHT_RECALL_MAX_TOKENS == 4096


def test_hindsight_recall_profile_accepts_valid_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("HINDSIGHT_RECALL_BUDGET", "low")
    monkeypatch.setenv("HINDSIGHT_RECALL_MAX_TOKENS", "2048")

    settings = Settings(_env_file=None)

    assert settings.HINDSIGHT_RECALL_BUDGET == "low"
    assert settings.HINDSIGHT_RECALL_MAX_TOKENS == 2048


def test_hindsight_recall_profile_rejects_unknown_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("HINDSIGHT_RECALL_BUDGET", "unbounded")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_cloudflare_ai_gateway_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cloudflare AI Gateway URL must be constructed from account ID and gateway ID."""
    monkeypatch.setenv("APP_SECRET_KEY", "test-secret")
    monkeypatch.setenv("CF_ACCOUNT_ID", "abc123")
    monkeypatch.setenv("CF_AI_GATEWAY_ID", "my-gateway")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "")
    monkeypatch.setenv("CLOUDFLARE_GATEWAY_ID", "")
    settings = Settings()
    assert "abc123" in settings.cloudflare_ai_gateway_url
    assert "my-gateway" in settings.cloudflare_ai_gateway_url


def test_cloudflare_ai_gateway_url_preferred(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cloudflare AI Gateway URL must prefer CLOUDFLARE_ prefixed env vars."""
    monkeypatch.setenv("APP_SECRET_KEY", "test-secret")
    monkeypatch.setenv("CF_ACCOUNT_ID", "legacy-account")
    monkeypatch.setenv("CF_AI_GATEWAY_ID", "legacy-gateway")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "new-account")
    monkeypatch.setenv("CLOUDFLARE_GATEWAY_ID", "new-gateway")
    settings = Settings()
    assert "new-account" in settings.cloudflare_ai_gateway_url
    assert "new-gateway" in settings.cloudflare_ai_gateway_url


def test_is_production_false_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_SECRET_KEY", "test-secret")
    settings = Settings()
    assert settings.is_production is False


def test_is_production_true_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_SECRET_KEY", "test-secret")
    monkeypatch.setenv("APP_ENV", "production")
    settings = Settings()
    assert settings.is_production is True

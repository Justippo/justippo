from __future__ import annotations

import hashlib

from app.core.network_policy import NetworkPolicy, get_policy, network_policy, record_egress

# ── Decorator ──────────────────────────────────────────────────────────────


def test_network_policy_attaches_default_policy() -> None:
    @network_policy()
    def my_tool() -> str:
        return "done"

    policy: NetworkPolicy | None = getattr(my_tool, "_network_policy", None)
    assert policy is not None
    assert policy.tool_name == "my_tool"
    assert policy.allow_egress is False
    assert policy.audit_egress is True
    assert policy.allowed_domains == []
    assert policy.disallowed_domains == []


def test_network_policy_with_custom_settings() -> None:
    @network_policy(
        allow_egress=True,
        audit_egress=False,
        allowed_domains=["gateway.ai.cloudflare.com"],
        disallowed_domains=["localhost"],
    )
    def search_tool() -> str:
        return "result"

    policy = getattr(search_tool, "_network_policy", None)
    assert policy is not None
    assert policy.tool_name == "search_tool"
    assert policy.allow_egress is True
    assert policy.audit_egress is False
    assert policy.allowed_domains == ["gateway.ai.cloudflare.com"]
    assert policy.disallowed_domains == ["localhost"]


def test_network_policy_preserves_function_behavior() -> None:
    @network_policy(allow_egress=True)
    def add(a: int, b: int) -> int:
        return a + b

    assert add(2, 3) == 5


# ── get_policy ─────────────────────────────────────────────────────────────


def test_get_policy_returns_policy() -> None:
    @network_policy(allow_egress=True)
    def tool() -> None:
        pass

    policy = get_policy(tool)
    assert policy is not None
    assert policy.allow_egress is True


def test_get_policy_returns_none_when_no_policy() -> None:
    def plain_func() -> None:
        pass

    assert get_policy(plain_func) is None


# ── record_egress ──────────────────────────────────────────────────────────


def test_record_egress_no_policy_allows_by_default() -> None:
    def no_policy() -> None:
        pass

    result = record_egress(no_policy, "https://example.com/api")
    assert result is None  # None when no policy (allowed by default)


def test_record_egress_blocked_when_not_allowed() -> None:
    @network_policy(allow_egress=False)
    def blocked_tool() -> None:
        pass

    result = record_egress(blocked_tool, "https://example.com/api")
    assert result is None  # blocked


def test_record_egress_blocked_by_disallowed_domain() -> None:
    @network_policy(allow_egress=True, disallowed_domains=["malicious.example.com"])
    def safe_tool() -> None:
        pass

    result = record_egress(safe_tool, "https://malicious.example.com/steal")
    assert result is None


def test_record_egress_allowed_when_domain_not_in_disallowed() -> None:
    @network_policy(allow_egress=True, disallowed_domains=["evil.com"])
    def safe_tool() -> None:
        pass

    result = record_egress(safe_tool, "https://good.example.com/api")
    assert result is not None
    expected = hashlib.sha256(b"https://good.example.com/api").hexdigest()[:16]
    assert result == expected


def test_record_egress_blocked_when_not_in_allowed_list() -> None:
    @network_policy(
        allow_egress=True,
        allowed_domains=["gateway.ai.cloudflare.com"],
    )
    def restricted_tool() -> None:
        pass

    result = record_egress(restricted_tool, "https://evil.com/hack")
    assert result is None


def test_record_egress_allowed_when_in_allowed_list() -> None:
    @network_policy(
        allow_egress=True,
        allowed_domains=["gateway.ai.cloudflare.com"],
    )
    def gateway_tool() -> None:
        pass

    result = record_egress(gateway_tool, "https://gateway.ai.cloudflare.com/v1/chat")
    assert result is not None


def test_record_egress_empty_allowed_list_does_not_block() -> None:
    @network_policy(allow_egress=True, allowed_domains=[])
    def unrestricted() -> None:
        pass

    result = record_egress(unrestricted, "https://anywhere.com/api")
    assert result is not None


def test_record_egress_appends_url_hash_to_policy() -> None:
    @network_policy(allow_egress=True, audit_egress=True)
    def audited_tool() -> None:
        pass

    url = "https://api.example.com/data"
    result = record_egress(audited_tool, url)

    assert result is not None
    expected_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
    assert result == expected_hash

    policy = audited_tool._network_policy
    assert result in policy.egress_urls


def test_record_egress_does_not_append_when_audit_disabled() -> None:
    @network_policy(allow_egress=True, audit_egress=False)
    def silent_tool() -> None:
        pass

    result = record_egress(silent_tool, "https://api.example.com/data")

    assert result is not None
    policy = silent_tool._network_policy
    assert len(policy.egress_urls) == 0


def test_record_egress_hash_is_consistent() -> None:
    @network_policy(allow_egress=True)
    def stable() -> None:
        pass

    r1 = record_egress(stable, "https://example.com/endpoint")
    r2 = record_egress(stable, "https://example.com/endpoint")
    assert r1 == r2


def test_record_egress_hashes_are_distinct_for_different_urls() -> None:
    @network_policy(allow_egress=True, audit_egress=True)
    def distinct() -> None:
        pass

    r1 = record_egress(distinct, "https://example.com/a")
    r2 = record_egress(distinct, "https://example.com/b")
    assert r1 != r2


# ── Edge cases ─────────────────────────────────────────────────────────────


def test_network_policy_called_on_non_async_function() -> None:
    @network_policy(allow_egress=True)
    def sync_func(x: int) -> int:
        return x * 2

    assert sync_func(21) == 42
    policy = sync_func._network_policy
    assert policy.allow_egress is True


def test_network_policy_called_on_async_function() -> None:
    @network_policy(allow_egress=True)
    async def async_func(x: int) -> int:
        return x * 2

    # Can't await here in sync test, just verify metadata
    policy = async_func._network_policy
    assert policy.tool_name == "async_func"
    assert policy.allow_egress is True


def test_record_egress_no_policy_no_error() -> None:
    """record_egress should not raise when function has no policy."""

    def raw_func() -> None:
        pass

    # Should not raise
    result = record_egress(raw_func, "https://example.com")
    assert result is None

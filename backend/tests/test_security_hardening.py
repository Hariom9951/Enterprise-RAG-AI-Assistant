"""
Enterprise RAG AI Assistant — Security Hardening Tests (Phase 5.5.1)
====================================================================
Validates targeted security fixes:
  - SEC-02: Production SECRET_KEY validation and safe exception handling.
  - SEC-04: Safe reverse-proxy IP handling (direct clients, trusted proxies, spoofing prevention).
  - SEC-05: Query-string logging sanitization and log record secret redaction.
"""

from __future__ import annotations

import io
import os
import pytest
from loguru import logger
from pydantic import ValidationError
from starlette.datastructures import QueryParams
from starlette.requests import Request
from starlette.types import Scope

from app.config.settings import Settings
from app.middleware.logging_middleware import (
    REDACTED_VALUE,
    RequestLoggingMiddleware,
    sanitize_query_params,
)
from app.middleware.rate_limit import (
    RateLimitingMiddleware,
    get_client_ip,
    is_ip_in_trusted_proxies,
)


def make_request(
    client_host: str | None = "192.168.1.50",
    headers: dict[str, str] | None = None,
    query_string: str = "",
    path: str = "/api/v1/memories",
    method: str = "GET",
) -> Request:
    """Construct an ASGI Request instance for testing middleware helpers."""
    raw_headers = []
    if headers:
        for k, v in headers.items():
            raw_headers.append((k.lower().encode("latin-1"), v.encode("latin-1")))

    scope: Scope = {
        "type": "http",
        "method": method,
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": query_string.encode("utf-8"),
        "headers": raw_headers,
        "client": (client_host, 54321) if client_host is not None else None,
        "app": None,
    }
    return Request(scope)


# =============================================================================
# SEC-02: Production SECRET_KEY validation
# =============================================================================


class TestProductionSecretKeyValidation:
    """Test suite for SEC-02: SECRET_KEY production validation."""

    def test_production_fails_when_secret_key_empty(self) -> None:
        """Startup in production must fail if SECRET_KEY is empty or whitespace."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                environment="production",
                secret_key="",
            )
        err_msg = str(exc_info.value)
        assert "SECRET_KEY must be set in production" in err_msg

        with pytest.raises(ValidationError) as exc_info:
            Settings(
                environment="production",
                secret_key="    ",
            )
        err_msg = str(exc_info.value)
        assert "SECRET_KEY must be set in production" in err_msg

    @pytest.mark.parametrize(
        "placeholder",
        [
            "change-me-in-production",
            "changeme",
            "placeholder-key-for-now",
            "secret",
            "default",
            "testsecret",
            "123456",
            "admin",
            "password",
            "secretkey",
            "insecure",
        ],
    )
    def test_production_fails_on_insecure_defaults(self, placeholder: str) -> None:
        """Startup in production must fail if SECRET_KEY is any known placeholder or insecure default."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                environment="production",
                secret_key=placeholder,
            )
        # Check the actual raised exception messages (excluding Pydantic's internal input_value echo)
        error_messages = [e["msg"] for e in exc_info.value.errors()]
        assert any(
            "SECRET_KEY cannot be a default or placeholder value in production" in msg
            for msg in error_messages
        )
        # Critical security check: Never include the key/placeholder in any error message
        for msg in error_messages:
            assert placeholder not in msg or placeholder in {"secret", "default"}

    def test_production_fails_when_secret_key_too_short(self) -> None:
        """Startup in production must fail if SECRET_KEY is shorter than 32 characters."""
        short_key = "short-custom-key-12345"
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                environment="production",
                secret_key=short_key,
            )
        error_messages = [e["msg"] for e in exc_info.value.errors()]
        assert any(
            "SECRET_KEY must be at least 32 characters long in production" in msg
            for msg in error_messages
        )
        # Key must never be included in any exception message
        for msg in error_messages:
            assert short_key not in msg

    def test_production_succeeds_with_valid_key(self) -> None:
        """Startup in production succeeds when a valid 32+ character key is provided."""
        valid_key = "b4f8d9a2c1e67890abcdef1234567890"
        cfg = Settings(
            environment="production",
            secret_key=valid_key,
            allowed_origins=["https://rag.company.com"],
        )
        assert cfg.environment == "production"
        assert cfg.is_production is True
        assert cfg.secret_key == valid_key

    def test_development_preserves_convenient_defaults(self) -> None:
        """Development and test environments preserve convenient defaults without raising."""
        with pytest.warns(UserWarning, match="SECRET_KEY is set to an insecure placeholder value"):
            cfg = Settings(
                environment="development",
                secret_key="change-me-in-production",
            )
        assert cfg.environment == "development"
        assert cfg.is_development is True

        # Custom dev keys do not warn or raise
        dev_cfg = Settings(
            environment="development",
            secret_key="dev-key",
        )
        assert dev_cfg.secret_key == "dev-key"

    def test_uses_validated_model_environment_not_os_environ(self) -> None:
        """Validation must use the validated model setting, not an unrelated OS environment variable."""
        original_env = os.environ.get("ENVIRONMENT")
        try:
            # Set OS environment to development
            os.environ["ENVIRONMENT"] = "development"

            # Pass production directly to Settings — it must enforce production validation regardless of OS env
            with pytest.raises(ValidationError, match="SECRET_KEY cannot be a default or placeholder"):
                Settings(
                    environment="production",
                    secret_key="change-me-in-production",
                )
        finally:
            if original_env is not None:
                os.environ["ENVIRONMENT"] = original_env
            else:
                os.environ.pop("ENVIRONMENT", None)


# =============================================================================
# SEC-04: Safe reverse-proxy IP handling
# =============================================================================


class TestSafeReverseProxyIpHandling:
    """Test suite for SEC-04: Safe reverse-proxy client IP extraction."""

    def test_is_ip_in_trusted_proxies(self) -> None:
        """Verify IP matching against exact addresses and CIDR networks."""
        trusted = ["127.0.0.1", "10.0.0.0/8", "172.16.0.1", "192.168.1.0/24"]

        assert is_ip_in_trusted_proxies("127.0.0.1", trusted) is True
        assert is_ip_in_trusted_proxies("10.1.2.3", trusted) is True
        assert is_ip_in_trusted_proxies("172.16.0.1", trusted) is True
        assert is_ip_in_trusted_proxies("192.168.1.100", trusted) is True

        assert is_ip_in_trusted_proxies("203.0.113.195", trusted) is False
        assert is_ip_in_trusted_proxies("172.17.0.1", trusted) is False
        assert is_ip_in_trusted_proxies("", trusted) is False
        assert is_ip_in_trusted_proxies("invalid-ip", trusted) is False

    def test_direct_client_no_trusted_proxies(self) -> None:
        """When no trusted proxies are configured, forwarded headers are ignored."""
        req = make_request(
            client_host="203.0.113.5",
            headers={"X-Forwarded-For": "1.2.3.4, 5.6.7.8"},
        )
        assert get_client_ip(req, trusted_proxies=[]) == "203.0.113.5"
        assert get_client_ip(req, trusted_proxies=None) == "203.0.113.5"

    def test_direct_client_spoofed_forwarded_header(self) -> None:
        """Direct connection from an untrusted client ignores spoofed X-Forwarded-For."""
        req = make_request(
            client_host="198.51.100.22",
            headers={"X-Forwarded-For": "10.0.0.1"},
        )
        trusted = ["10.0.0.1"]
        # Client IP is the direct socket peer, not the spoofed proxy IP
        assert get_client_ip(req, trusted_proxies=trusted) == "198.51.100.22"

    def test_trusted_proxy_single_hop(self) -> None:
        """When peer is a trusted proxy, real client IP is extracted from X-Forwarded-For."""
        req = make_request(
            client_host="10.0.0.1",
            headers={"X-Forwarded-For": "203.0.113.88"},
        )
        trusted = ["10.0.0.1"]
        assert get_client_ip(req, trusted_proxies=trusted) == "203.0.113.88"

    def test_trusted_proxy_multi_hop_chain(self) -> None:
        """Traverses multiple trusted proxies from right to left to find the first untrusted client IP."""
        req = make_request(
            client_host="10.0.0.1",
            headers={"X-Forwarded-For": "203.0.113.88, 10.0.0.2"},
        )
        trusted = ["10.0.0.1", "10.0.0.2"]
        assert get_client_ip(req, trusted_proxies=trusted) == "203.0.113.88"

    def test_spoofed_prepended_ip_through_trusted_proxy(self) -> None:
        """When an attacker injects a spoofed IP before a trusted proxy, the real client IP is selected."""
        # Attacker 198.51.100.99 sends X-Forwarded-For: 8.8.8.8 to trusted proxy 10.0.0.1.
        # Proxy appends attacker's IP: X-Forwarded-For: 8.8.8.8, 198.51.100.99
        req = make_request(
            client_host="10.0.0.1",
            headers={"X-Forwarded-For": "8.8.8.8, 198.51.100.99"},
        )
        trusted = ["10.0.0.1"]
        # Nearest untrusted upstream IP is 198.51.100.99, NOT the spoofed 8.8.8.8
        assert get_client_ip(req, trusted_proxies=trusted) == "198.51.100.99"

    def test_malformed_forwarded_headers_fallback_safely(self) -> None:
        """Malformed or injection attempts in X-Forwarded-For fall back safely to peer IP."""
        req = make_request(
            client_host="10.0.0.1",
            headers={"X-Forwarded-For": "malicious;payload, <script>alert(1)</script>"},
        )
        trusted = ["10.0.0.1"]
        assert get_client_ip(req, trusted_proxies=trusted) == "10.0.0.1"

    def test_missing_client_returns_unknown(self) -> None:
        """Requests with missing socket client return 'unknown'."""
        req = make_request(client_host=None)
        assert get_client_ip(req, trusted_proxies=["10.0.0.1"]) == "unknown"


# =============================================================================
# SEC-05: Query-string logging sanitization
# =============================================================================


class TestQueryStringLoggingSanitization:
    """Test suite for SEC-05: Query-string logging sanitization."""

    @pytest.mark.parametrize(
        "param_name",
        [
            "code",
            "state",
            "token",
            "access_token",
            "refresh_token",
            "secret",
            "client_secret",
            "api_key",
            "apikey",
            "password",
            "q",
            "query",
            # Case variations
            "CODE",
            "State",
            "Token",
            "Q",
            "Query",
            # Suffix variations
            "user_token",
            "auth_secret",
            "encryption_key",
        ],
    )
    def test_sanitizes_all_sensitive_keys(self, param_name: str) -> None:
        """All mandatory sensitive query parameters are redacted."""
        secret_val = "sensitive_value_12345"
        query_str = f"{param_name}={secret_val}&page=1"
        sanitized = sanitize_query_params(query_str)

        assert sanitized is not None
        assert f"{param_name}={REDACTED_VALUE}" in sanitized or f"{param_name.lower()}={REDACTED_VALUE}" in sanitized.lower()
        assert secret_val not in sanitized
        assert "page=1" in sanitized

    def test_preserves_non_sensitive_metadata(self) -> None:
        """Non-sensitive query parameters and pagination metadata are fully preserved."""
        query_str = "category=finance&page=2&limit=50&sort=desc"
        sanitized = sanitize_query_params(query_str)
        assert sanitized == "category=finance&page=2&limit=50&sort=desc"

    def test_handles_repeated_parameters(self) -> None:
        """Handles repeated query parameters safely without dropping them."""
        query_str = "q=first_query&q=second_query&filter=active"
        sanitized = sanitize_query_params(query_str)
        assert sanitized is not None
        assert "q=[REDACTED]&q=[REDACTED]" in sanitized
        assert "first_query" not in sanitized
        assert "second_query" not in sanitized
        assert "filter=active" in sanitized

    def test_empty_and_blank_query_handling(self) -> None:
        """Empty or whitespace query strings return None."""
        assert sanitize_query_params("") is None
        assert sanitize_query_params("   ") is None
        assert sanitize_query_params("?") is None
        assert sanitize_query_params(QueryParams()) is None

    @pytest.mark.asyncio
    async def test_request_logging_middleware_captured_logs_contain_no_secrets(self) -> None:
        """Verify that sensitive values never appear in captured Loguru access logs."""
        captured_logs: list[dict] = []

        def log_sink(message) -> None:
            record = message.record
            captured_logs.append(
                {
                    "message": record["message"],
                    "extra": record["extra"],
                }
            )

        handler_id = logger.add(log_sink, level="INFO")
        try:
            raw_secret_query = "top_secret_corporate_strategy"
            raw_token = "jwt_bearer_token_xyz987"
            raw_code = "oauth2_code_12345"

            req = make_request(
                client_host="192.168.1.10",
                query_string=f"q={raw_secret_query}&token={raw_token}&code={raw_code}&page=3",
            )

            async def dummy_call_next(request: Request):
                from fastapi.responses import Response
                return Response(status_code=200)

            from starlette.types import ASGIApp

            dummy_app: ASGIApp = lambda scope, receive, send: None
            middleware = RequestLoggingMiddleware(dummy_app)

            await middleware.dispatch(req, dummy_call_next)

            # Assert log records were created
            assert len(captured_logs) >= 2

            incoming_log = captured_logs[0]
            extra_dict = incoming_log["extra"].get("extra", incoming_log["extra"])
            extra_query = extra_dict.get("query")

            assert extra_query is not None
            # Sensitive raw values MUST NEVER appear in captured logs
            assert raw_secret_query not in extra_query
            assert raw_token not in extra_query
            assert raw_code not in extra_query

            # Redacted placeholders MUST be present
            assert f"q={REDACTED_VALUE}" in extra_query
            assert f"token={REDACTED_VALUE}" in extra_query
            assert f"code={REDACTED_VALUE}" in extra_query

            # Non-sensitive parameter is preserved
            assert "page=3" in extra_query

            # Check full log string representations across all captured records
            full_log_text = " ".join(str(log) for log in captured_logs)
            assert raw_secret_query not in full_log_text
            assert raw_token not in full_log_text
            assert raw_code not in full_log_text

        finally:
            logger.remove(handler_id)

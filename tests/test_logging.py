"""
Tests for Step 1.3: Structured Logging and Request Correlation.

These tests verify that:
1. The logger can be created with a module name
2. Log output is valid JSON (structured format)
3. Request ID context variable works correctly
4. The request correlation middleware sets a request ID header
5. Log entries include the request ID when one is set
6. Each request gets a unique ID

How these tests work:
- We capture log output using a StringIO handler
- We test the middleware by making HTTP requests through the test client
- We use contextvars directly to verify request ID propagation
"""

import json
import logging
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from sentinel.app import create_app
from sentinel.common.logging import (
    get_logger,
    setup_logging,
    request_id_ctx,
    get_request_id,
    set_request_id,
)


# ── Test 1: Logger creation ─────────────────────────────────────────────

class TestGetLogger:
    """Verify logger factory works correctly."""

    def test_get_logger_returns_logger(self):
        """get_logger() must return a standard Python Logger instance."""
        logger = get_logger("test_module")
        assert isinstance(logger, logging.Logger)

    def test_get_logger_uses_sentinel_namespace(self):
        """Logger name should be prefixed with 'sentinel.' for namespacing."""
        logger = get_logger("my_module")
        assert logger.name == "sentinel.my_module"

    def test_get_logger_different_modules_different_loggers(self):
        """Different module names should produce different logger instances."""
        logger_a = get_logger("module_a")
        logger_b = get_logger("module_b")
        assert logger_a is not logger_b
        assert logger_a.name != logger_b.name


# ── Test 2: Request ID context variable ──────────────────────────────────

class TestRequestIdContext:
    """Verify request ID context propagation."""

    def test_default_request_id_is_none(self):
        """Before any request, the context variable should return None."""
        # Reset context to ensure clean state
        token = request_id_ctx.set(None)
        try:
            assert get_request_id() is None
        finally:
            request_id_ctx.reset(token)

    def test_set_request_id(self):
        """set_request_id() should store the ID in the context variable."""
        test_id = "test-request-123"
        token = set_request_id(test_id)
        try:
            assert get_request_id() == test_id
        finally:
            request_id_ctx.reset(token)

    def test_request_id_is_isolated(self):
        """Setting a request ID should not affect the default context."""
        token = set_request_id("isolated-id")
        assert get_request_id() == "isolated-id"
        request_id_ctx.reset(token)
        # After reset, should be back to whatever it was before


# ── Test 3: JSON log formatter ───────────────────────────────────────────

class TestJsonFormatter:
    """Verify logs are output as valid JSON."""

    def test_log_output_is_valid_json(self):
        """Each log line must be parseable as JSON."""
        import io
        from sentinel.common.logging import JsonFormatter

        # Create a logger with our JSON formatter writing to a string buffer
        buffer = io.StringIO()
        handler = logging.StreamHandler(buffer)
        handler.setFormatter(JsonFormatter())

        test_logger = logging.getLogger("test.json_format")
        test_logger.addHandler(handler)
        test_logger.setLevel(logging.DEBUG)

        test_logger.info("Test message")

        output = buffer.getvalue().strip()
        parsed = json.loads(output)
        assert parsed["message"] == "Test message"
        assert parsed["level"] == "INFO"
        assert "timestamp" in parsed

        # Cleanup
        test_logger.removeHandler(handler)

    def test_log_includes_request_id_when_set(self):
        """When a request ID is in context, it should appear in the log JSON."""
        import io
        from sentinel.common.logging import JsonFormatter

        buffer = io.StringIO()
        handler = logging.StreamHandler(buffer)
        handler.setFormatter(JsonFormatter())

        test_logger = logging.getLogger("test.request_id_in_log")
        test_logger.addHandler(handler)
        test_logger.setLevel(logging.DEBUG)

        # Set a request ID in context
        token = set_request_id("req-abc-123")
        try:
            test_logger.info("Message with request ID")
            output = buffer.getvalue().strip()
            parsed = json.loads(output)
            assert parsed["request_id"] == "req-abc-123"
        finally:
            request_id_ctx.reset(token)
            test_logger.removeHandler(handler)

    def test_log_request_id_is_null_when_not_set(self):
        """When no request ID is set, the field should be null."""
        import io
        from sentinel.common.logging import JsonFormatter

        buffer = io.StringIO()
        handler = logging.StreamHandler(buffer)
        handler.setFormatter(JsonFormatter())

        test_logger = logging.getLogger("test.no_request_id")
        test_logger.addHandler(handler)
        test_logger.setLevel(logging.DEBUG)

        token = request_id_ctx.set(None)
        try:
            test_logger.info("No request ID here")
            output = buffer.getvalue().strip()
            parsed = json.loads(output)
            assert parsed["request_id"] is None
        finally:
            request_id_ctx.reset(token)
            test_logger.removeHandler(handler)


# ── Test 4: Request correlation middleware ────────────────────────────────

class TestRequestCorrelationMiddleware:
    """Verify the middleware adds request IDs to responses."""

    @pytest.fixture
    def app(self):
        return create_app()

    @pytest.fixture
    async def client(self, app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac

    @pytest.mark.anyio
    async def test_response_has_request_id_header(self, client):
        """Every response must include an X-Request-ID header."""
        response = await client.get("/api/does-not-exist")
        assert "x-request-id" in response.headers

    @pytest.mark.anyio
    async def test_request_id_is_valid_uuid(self, client):
        """The request ID should be a valid UUID string."""
        response = await client.get("/api/does-not-exist")
        request_id = response.headers["x-request-id"]
        # Should not raise if it's a valid UUID
        parsed = uuid.UUID(request_id)
        assert str(parsed) == request_id

    @pytest.mark.anyio
    async def test_each_request_gets_unique_id(self, client):
        """Two requests should get different IDs."""
        r1 = await client.get("/api/does-not-exist")
        r2 = await client.get("/api/does-not-exist")
        id1 = r1.headers["x-request-id"]
        id2 = r2.headers["x-request-id"]
        assert id1 != id2

    @pytest.mark.anyio
    async def test_client_provided_request_id_is_used(self, client):
        """If the client sends X-Request-ID, the server should use it."""
        custom_id = str(uuid.uuid4())
        response = await client.get(
            "/api/does-not-exist",
            headers={"X-Request-ID": custom_id},
        )
        assert response.headers["x-request-id"] == custom_id

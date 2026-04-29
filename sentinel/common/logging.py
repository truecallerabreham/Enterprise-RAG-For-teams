"""
Sentinel Structured Logging and Request Correlation.

This module provides three things:

1. A JSON log formatter that outputs structured log entries (not plain text).
2. A request ID context variable that propagates through async code.
3. A FastAPI middleware that assigns a unique ID to every request.

WHY STRUCTURED LOGGING?

Plain text logs like:
    INFO: User asked a question about HR policy

...are hard to search and filter programmatically. Structured JSON logs like:
    {"timestamp": "...", "level": "INFO", "request_id": "abc-123",
     "module": "portal", "message": "User asked a question about HR policy"}

...can be parsed by log aggregation tools (ELK, Datadog, CloudWatch) to answer
questions like "show me all errors for request abc-123" or "how many INFO logs
did the retrieval module emit in the last hour?"

WHY REQUEST CORRELATION?

A single user question triggers many operations: auth check, retrieval,
answer generation, audit recording. Without a shared request ID, these log
entries are impossible to connect. With correlation, every log entry from
the same request shares one ID, so you can trace the full lifecycle.

HOW CONTEXT VARIABLES WORK (contextvars):

Python's `contextvars` module provides variables that are automatically
scoped to the current execution context (similar to thread-local storage
but works with async code). When the middleware sets a request ID:
    set_request_id("abc-123")
...any code running within that same request (even deeply nested async
functions) can retrieve it with get_request_id() without needing the
value passed through every function signature.
"""

import json
import logging
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Request ID Context Variable
# ─────────────────────────────────────────────────────────────────────────────

# This ContextVar stores the current request's unique ID.
# It is set by the middleware at the start of each request and available
# anywhere in the code via get_request_id().
request_id_ctx: ContextVar[Optional[str]] = ContextVar(
    "request_id", default=None
)


def get_request_id() -> Optional[str]:
    """
    Retrieve the current request ID from context.

    Returns None if called outside of a request (e.g., during startup
    or in a background worker that hasn't set an ID).
    """
    return request_id_ctx.get()


def set_request_id(request_id: str):
    """
    Set the request ID in the current context.

    Returns a token that can be used to reset the context variable
    back to its previous value (useful in tests).
    """
    return request_id_ctx.set(request_id)


# ─────────────────────────────────────────────────────────────────────────────
# JSON Log Formatter
# ─────────────────────────────────────────────────────────────────────────────


class JsonFormatter(logging.Formatter):
    """
    Formats log records as single-line JSON objects.

    Each log entry includes:
    - timestamp: ISO 8601 UTC time
    - level: log level name (INFO, WARNING, ERROR, etc.)
    - module: which Python module emitted the log
    - message: the actual log message
    - request_id: the current request's correlation ID (null if none)

    WHY single-line JSON?
    Log aggregation systems expect one log entry per line. Multi-line
    logs (like stack traces with print()) break parsing. JSON on one
    line keeps each entry atomic and machine-readable.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.name,
            "message": record.getMessage(),
            "request_id": get_request_id(),
        }

        # Include exception info if present (e.g., logger.exception())
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry)


# ─────────────────────────────────────────────────────────────────────────────
# Logger Factory
# ─────────────────────────────────────────────────────────────────────────────


def get_logger(name: str) -> logging.Logger:
    """
    Create a namespaced logger for a Sentinel module.

    Usage:
        logger = get_logger("retrieval")
        logger.info("Searching for evidence")
        # Output: {"module": "sentinel.retrieval", "message": "Searching..."}

    WHY namespace with 'sentinel.'?
    Third-party libraries (FastAPI, uvicorn, httpx) also use Python's
    logging module. Prefixing with 'sentinel.' ensures our logs are
    distinguishable from library logs and can be filtered independently.
    """
    return logging.getLogger(f"sentinel.{name}")


def setup_logging(level: str = "INFO") -> None:
    """
    Configure the root 'sentinel' logger with JSON formatting.

    This should be called once during application startup. It:
    1. Gets the root 'sentinel' logger
    2. Sets the log level
    3. Attaches a StreamHandler with our JsonFormatter
    4. Prevents duplicate handlers if called multiple times

    The level parameter accepts standard logging level names:
    DEBUG, INFO, WARNING, ERROR, CRITICAL
    """
    logger = logging.getLogger("sentinel")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Prevent adding duplicate handlers on repeated calls
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)


# ─────────────────────────────────────────────────────────────────────────────
# Request Correlation Middleware
# ─────────────────────────────────────────────────────────────────────────────


class RequestCorrelationMiddleware:
    """
    ASGI middleware that assigns a unique ID to every HTTP request.

    For each incoming request:
    1. Check if the client sent an 'X-Request-ID' header
       - If yes: reuse that ID (useful for tracing across services)
       - If no: generate a new UUID4
    2. Store the ID in the context variable (available to all code)
    3. Add the ID to the response headers (client can see it)

    WHY ASGI middleware instead of FastAPI dependency?
    ASGI middleware wraps the entire request lifecycle, including
    error handling. A dependency only runs after routing succeeds.
    We want the request ID to be available even for 404 and 500
    responses.

    HOW ASGI WORKS (simplified):
    An ASGI app is a callable that receives three arguments:
    - scope: dict with request metadata (type, path, headers)
    - receive: async function to read the request body
    - send: async function to write the response

    This middleware intercepts 'send' to inject the X-Request-ID
    header into the response before it's sent to the client.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        # Only process HTTP requests (not websockets or lifespan events)
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Extract or generate the request ID
        headers = dict(scope.get("headers", []))
        client_request_id = headers.get(b"x-request-id", b"").decode() or None
        request_id = client_request_id or str(uuid.uuid4())

        # Store in context for this request's lifetime
        token = set_request_id(request_id)

        async def send_with_request_id(message):
            """Intercept the response to add the X-Request-ID header."""
            if message["type"] == "http.response.start":
                # Add our header to the existing response headers
                existing_headers = list(message.get("headers", []))
                existing_headers.append(
                    (b"x-request-id", request_id.encode())
                )
                message["headers"] = existing_headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            # Reset the context variable after the request completes
            request_id_ctx.reset(token)

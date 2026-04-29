"""
Sentinel Application Factory.

Creates and configures the FastAPI application instance. All module routers
are registered here to establish the modular monolith structure.

How it works:
- create_app() is a factory function that builds a fresh FastAPI instance.
- Each module's router is imported and included with its own URL prefix and tag.
- This centralizes route registration so the main entrypoint stays clean.
- Middleware (CORS, request ID, etc.) will be added in later steps.
"""

from fastapi import FastAPI

from sentinel.auth.router import router as auth_router
from sentinel.portal.router import router as portal_router
from sentinel.admin.router import router as admin_router
from sentinel.ingestion.router import router as ingestion_router
from sentinel.retrieval.router import router as retrieval_router
from sentinel.audits.router import router as audits_router
from sentinel.common.logging import RequestCorrelationMiddleware, setup_logging
from sentinel.common.health import router as health_router


def create_app() -> FastAPI:
    """
    Build and return the configured FastAPI application.

    This factory pattern allows:
    - Multiple app instances for testing (each test gets a fresh app)
    - Clear separation between app configuration and server startup
    - Easy addition of lifecycle hooks, middleware, and event handlers
    """
    app = FastAPI(
        title="Project Sentinel",
        description=(
            "Internal intelligence system that unifies company documents, "
            "GitHub repositories, and Slack discussions into one secure "
            "RAG-powered answer surface with department-level access control."
        ),
        version="0.1.0",
    )

    # ── Initialize structured logging ────────────────────────────────────
    setup_logging()

    # ── Add middleware (outermost first) ──────────────────────────────────
    # Request correlation middleware assigns a unique ID to every request.
    # It wraps the entire request lifecycle so even error responses get an ID.
    app.add_middleware(RequestCorrelationMiddleware)

    # ── Register module routers ──────────────────────────────────────────
    # Each router defines its own prefix (e.g., /api/auth, /api/portal)
    # and tag for OpenAPI documentation grouping.
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(portal_router)
    app.include_router(admin_router)
    app.include_router(ingestion_router)
    app.include_router(retrieval_router)
    app.include_router(audits_router)

    return app

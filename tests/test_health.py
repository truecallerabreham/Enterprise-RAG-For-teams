"""
Tests for Step 1.4: Health and Readiness Endpoints.

These tests verify that:
1. The liveness endpoint (/health/live) returns 200 when the app is running
2. The readiness endpoint (/health/ready) checks dependency status
3. Response bodies include structured status information
4. The health router is properly registered in the app

How these tests work:
- Liveness is simple: if the app can respond, it's alive
- Readiness is more nuanced: it checks dependencies (database, etc.)
  For now, we use a pluggable checker system that defaults to "healthy"
  and will be extended when we add real dependencies in Track 2
"""

import pytest
from httpx import ASGITransport, AsyncClient

from sentinel.app import create_app


@pytest.fixture
def app():
    """Create a fresh FastAPI app instance for each test."""
    return create_app()


@pytest.fixture
async def client(app):
    """Create an async HTTP client bound to the test app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── Test 1: Liveness endpoint ────────────────────────────────────────────

class TestLivenessEndpoint:
    """Verify the /health/live endpoint."""

    @pytest.mark.anyio
    async def test_liveness_returns_200(self, client):
        """If the app can respond at all, it's alive → 200."""
        response = await client.get("/health/live")
        assert response.status_code == 200

    @pytest.mark.anyio
    async def test_liveness_returns_status_ok(self, client):
        """Response body must include a status field set to 'ok'."""
        response = await client.get("/health/live")
        data = response.json()
        assert data["status"] == "ok"

    @pytest.mark.anyio
    async def test_liveness_response_has_correct_structure(self, client):
        """Response must have 'status' and 'service' fields."""
        response = await client.get("/health/live")
        data = response.json()
        assert "status" in data
        assert "service" in data
        assert data["service"] == "sentinel"


# ── Test 2: Readiness endpoint ───────────────────────────────────────────

class TestReadinessEndpoint:
    """Verify the /health/ready endpoint."""

    @pytest.mark.anyio
    async def test_readiness_returns_200_when_healthy(self, client):
        """When all dependencies are healthy, readiness returns 200."""
        response = await client.get("/health/ready")
        assert response.status_code == 200

    @pytest.mark.anyio
    async def test_readiness_returns_status_ok(self, client):
        """Response body must include status 'ok' when all checks pass."""
        response = await client.get("/health/ready")
        data = response.json()
        assert data["status"] == "ok"

    @pytest.mark.anyio
    async def test_readiness_includes_checks_section(self, client):
        """Response must include a 'checks' dict showing dependency statuses."""
        response = await client.get("/health/ready")
        data = response.json()
        assert "checks" in data
        assert isinstance(data["checks"], dict)

    @pytest.mark.anyio
    async def test_readiness_includes_database_check(self, client):
        """The checks section must include a 'database' entry."""
        response = await client.get("/health/ready")
        data = response.json()
        assert "database" in data["checks"]


# ── Test 3: Readiness with failing dependency ────────────────────────────

class TestReadinessWithFailure:
    """Verify readiness correctly reports unhealthy dependencies."""

    @pytest.mark.anyio
    async def test_readiness_returns_503_when_dependency_fails(self):
        """When a dependency check fails, readiness must return 503."""
        from sentinel.common.health import register_check, clear_checks

        app = create_app()

        # Register a check that always fails
        async def failing_db_check():
            return False

        register_check("database", failing_db_check)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health/ready")
            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "degraded"
            assert data["checks"]["database"] == "unhealthy"

        # Cleanup
        clear_checks()

    @pytest.mark.anyio
    async def test_readiness_shows_mixed_status(self):
        """When some deps are healthy and some not, show both."""
        from sentinel.common.health import register_check, clear_checks

        app = create_app()

        async def healthy_check():
            return True

        async def unhealthy_check():
            return False

        register_check("cache", healthy_check)
        register_check("database", unhealthy_check)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health/ready")
            data = response.json()
            assert data["checks"]["cache"] == "healthy"
            assert data["checks"]["database"] == "unhealthy"
            assert data["status"] == "degraded"

        clear_checks()


# ── Test 4: Health router is registered ──────────────────────────────────

class TestHealthRouterRegistration:
    """Verify the health router appears in the app's OpenAPI schema."""

    def test_openapi_includes_health_tag(self, app):
        """The OpenAPI schema should include the 'health' tag group."""
        schema = app.openapi()
        paths = schema.get("paths", {})
        health_paths = [p for p in paths if p.startswith("/health")]
        assert len(health_paths) >= 2  # /health/live and /health/ready

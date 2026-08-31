"""API checks requiring PostgreSQL are intended for the Docker service.

Run: docker compose up -d; pytest tests
"""
def test_required_routes_are_declared():
    from backend.app.main import app
    paths = {route.path for route in app.routes}
    for path in ["/personas", "/personas/{persona_id}/chat", "/sources/{source_id}", "/memories/{memory_id}"]:
        assert path in paths

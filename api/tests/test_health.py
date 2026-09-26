from pathlib import Path


def test_health_reports_database(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["db"] is True


def test_cors_configuration(client):
    # Origin localhost:5190 should be allowed, credentials False
    r = client.options(
        "/api/health",
        headers={
            "Origin": "http://localhost:5190",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5190"
    assert r.headers.get("access-control-allow-credentials") is None or r.headers.get("access-control-allow-credentials") == "false"

    # Other origins should not be allowed
    r_bad = client.options(
        "/api/health",
        headers={
            "Origin": "http://evil.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r_bad.headers.get("access-control-allow-origin") != "http://evil.com"


def test_settings_host_port_data_dir(monkeypatch):
    from api.settings import Settings
    monkeypatch.delenv("FIXER_DATA_DIR", raising=False)
    monkeypatch.delenv("FIXER_API_HOST", raising=False)
    monkeypatch.delenv("FIXER_API_PORT", raising=False)
    # Built-in defaults only: skip any untracked .env in the working directory
    s = Settings(_env_file=None)
    assert s.api_host == "127.0.0.1"
    assert s.api_port == 8190
    repo_root = Path(__file__).resolve().parents[2]
    assert s.data_dir.is_absolute()
    assert s.data_dir == repo_root / "data"


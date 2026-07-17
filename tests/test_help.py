"""Help page: Markdown docs render into the page, including the iOS section."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_help_page_renders_features(client: TestClient) -> None:
    resp = client.get("/help")
    assert resp.status_code == 200
    body = resp.text
    # Markdown was converted to HTML (headings), not shown as raw source.
    assert "<h1" in body
    assert "# Help" not in body
    # Core features are documented.
    for needle in ("Transactions", "Budgets", "Snapshots", "Tag-only rules"):
        assert needle in body


def test_help_page_includes_ios_section(client: TestClient) -> None:
    resp = client.get("/help")
    assert resp.status_code == 200
    body = resp.text
    assert 'id="ios-app"' in body
    assert "companion" in body.lower()
    assert "Export delta snapshot" in body
    assert "Import snapshot" in body


def test_help_in_nav(client: TestClient) -> None:
    resp = client.get("/help")
    assert resp.status_code == 200
    assert 'href="/help"' in resp.text

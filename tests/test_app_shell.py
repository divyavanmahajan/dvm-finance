"""App factory / UI shell tests."""

from __future__ import annotations

from abn_combined.app import NAV_TABS


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_root_serves_shell(client):
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.text
    assert "abn-combined" in body
    # All nav tabs are present in the rendered shell.
    for _path, label in NAV_TABS:
        assert label in body


def test_all_nav_pages_render(client):
    for path, _label in NAV_TABS:
        resp = client.get(path)
        assert resp.status_code == 200, path


def test_static_assets_served(client):
    for asset in ("htmx.min.js", "alpine.min.js", "pico.min.css"):
        resp = client.get(f"/static/vendor/{asset}")
        assert resp.status_code == 200, asset
    assert client.get("/static/app.css").status_code == 200


def test_default_host_is_localhost():
    from abn_combined.settings import Settings

    assert Settings.create(data_dir="/tmp/whatever").host == "127.0.0.1"

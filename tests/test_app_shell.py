"""App factory / UI shell tests."""

from __future__ import annotations

import re

from abn_combined.app import NAV_MENU, NAV_TABS


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_root_serves_shell(client):
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.text
    assert "Your Finance" in body
    # All nav tabs are present in the rendered shell.
    for _path, label in NAV_TABS:
        assert label in body


def test_all_nav_pages_render(client):
    for path, _label in NAV_TABS + NAV_MENU:
        resp = client.get(path)
        assert resp.status_code == 200, path


def test_top_bar_order_and_qr_icon(client):
    body = client.get("/").text
    bar = body[body.index('id="navbarNav"'):body.index('id="utilityDropdown"')]
    labels = ["Transactions", "Trends", "Budgets", "Cash Flow", "Import", "Cash", "Help"]
    positions = [bar.index(f"{label}\n") for label in labels]
    assert positions == sorted(positions)
    qr = bar.index('aria-label="Share to phone"')
    assert positions[labels.index("Cash")] < qr < positions[labels.index("Help")]
    assert 'href="/export?share=1"' in bar
    assert 'title="Share to phone"' in bar
    for gone in ("Rules", "Tags", "Download", "Upload", "Snapshots"):
        assert f"{gone}\n" not in bar


def test_menu_holds_export_rules_tags_duplicates(client):
    body = client.get("/").text
    menu = body[body.index('aria-labelledby="utilityDropdown"'):]
    menu = menu[: menu.index("</ul>")]
    assert re.findall(r'href="(/[a-z-]*)"', menu) == ["/export", "/rules", "/tags", "/merge"]


def test_menu_marks_the_active_item(client):
    body = client.get("/rules").text
    assert re.search(r'dropdown-toggle active', body)
    assert re.search(r'class="dropdown-item active" href="/rules"', body)
    assert not re.search(r'dropdown-toggle active', client.get("/trends").text)


def test_static_assets_served(client):
    for asset in ("htmx.min.js", "alpine.min.js", "pico.min.css"):
        resp = client.get(f"/static/vendor/{asset}")
        assert resp.status_code == 200, asset
    assert client.get("/static/app.css").status_code == 200


def test_default_host_is_localhost():
    from abn_combined.settings import Settings

    assert Settings.create(data_dir="/tmp/whatever").host == "127.0.0.1"

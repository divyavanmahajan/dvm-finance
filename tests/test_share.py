"""Tests for the one-shot LAN snapshot share server and its routes."""

from __future__ import annotations

import urllib.error
import urllib.request
from pathlib import Path

import pytest

from abn_combined.core import share as share_mod


@pytest.fixture(autouse=True)
def _clean_share():
    yield
    share_mod.stop_share()


def _local_url(share: share_mod.SnapshotShare) -> str:
    """Rewrite the share URL to loopback so tests don't depend on the LAN."""
    return f"http://127.0.0.1:{share.url.rsplit(':', 1)[1]}"


def _make_snapshot(tmp_path: Path) -> Path:
    p = tmp_path / "snapshot-test.json.gz"
    p.write_bytes(b"\x1f\x8b-fake-gzip-payload")
    return p


def test_share_serves_file_exactly_once(tmp_path) -> None:
    path = _make_snapshot(tmp_path)
    share = share_mod.start_share(path)

    with urllib.request.urlopen(_local_url(share), timeout=5) as resp:
        assert resp.status == 200
        assert resp.headers["Content-Type"] == "application/gzip"
        assert path.name in resp.headers["Content-Disposition"]
        assert resp.read() == path.read_bytes()

    assert share.downloaded
    assert not share.is_active()
    assert share_mod.get_active_share() is None


def test_share_rejects_wrong_token(tmp_path) -> None:
    path = _make_snapshot(tmp_path)
    share = share_mod.start_share(path)
    port = share.url.rsplit(":", 1)[1].split("/")[0]

    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/wrong-token", timeout=5)
    assert exc.value.code == 404
    # A bad guess must not consume the share.
    assert share.is_active()


def test_new_share_replaces_previous(tmp_path) -> None:
    first = share_mod.start_share(_make_snapshot(tmp_path))
    second = share_mod.start_share(_make_snapshot(tmp_path))
    assert first.token != second.token
    assert share_mod.get_active_share() is second


def test_stop_share_deactivates(tmp_path) -> None:
    share = share_mod.start_share(_make_snapshot(tmp_path))
    share_mod.stop_share()
    assert not share.is_active()
    assert share_mod.get_active_share() is None


def test_share_url_contains_token_and_port(tmp_path) -> None:
    share = share_mod.start_share(_make_snapshot(tmp_path))
    assert share.url.startswith("http://")
    assert share.url.endswith(f"/{share.token}")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def test_share_route_returns_qr_partial(client) -> None:
    resp = client.post("/snapshots/share")
    assert resp.status_code == 200
    html = resp.text
    assert "data:image/svg+xml" in html
    assert "Stop sharing" in html
    active = share_mod.get_active_share()
    assert active is not None
    assert active.url in html


def test_share_stop_route(client) -> None:
    client.post("/snapshots/share")
    assert share_mod.get_active_share() is not None
    resp = client.post("/snapshots/share/stop")
    assert resp.status_code == 200
    assert resp.text == ""
    assert share_mod.get_active_share() is None


def test_snapshots_page_has_share_button(client) -> None:
    resp = client.get("/snapshots")
    assert resp.status_code == 200
    assert "Share to phone" in resp.text
    assert 'id="share-qr"' in resp.text

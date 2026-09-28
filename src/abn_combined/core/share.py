"""One-shot LAN share server for snapshots.

`start_share(path)` exports nothing itself — it takes an already-written
snapshot file and serves it on the machine's LAN address at a random port
under a single-use random token path. The server accepts exactly one
successful download (or expires after `SHARE_TIMEOUT_SECONDS`) and then
shuts down, so nothing stays reachable on the network. The main app keeps
listening on 127.0.0.1 only.

The QR code on the Snapshots page encodes the returned URL; the iOS app
scans it, downloads the file, and runs its normal snapshot import.
"""

from __future__ import annotations

import http.server
import secrets
import socket
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from ..logging_config import get_logger

logger = get_logger(__name__)

SHARE_TIMEOUT_SECONDS = 600  # 10 minutes


def lan_ip() -> str:
    """This machine's LAN IP address (best effort; 127.0.0.1 fallback).

    A UDP connect never sends packets — it only makes the OS pick the
    outbound interface, whose address is what the phone must dial.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 80))  # TEST-NET-1, never routed
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


@dataclass
class SnapshotShare:
    """A live (or finished) one-shot share."""

    url: str
    token: str
    path: Path
    expires_at: datetime
    downloaded: bool = False
    _server: http.server.ThreadingHTTPServer | None = field(default=None, repr=False)

    def is_active(self) -> bool:
        return (
            self._server is not None
            and not self.downloaded
            and datetime.now() < self.expires_at
        )

    def stop(self) -> None:
        server, self._server = self._server, None
        if server is not None:
            # shutdown() blocks until serve_forever exits; do it off-thread
            # so a request handler (or route) can trigger it safely.
            threading.Thread(target=server.shutdown, daemon=True).start()


_lock = threading.Lock()
_active: SnapshotShare | None = None


def get_active_share() -> SnapshotShare | None:
    with _lock:
        return _active if _active is not None and _active.is_active() else None


def stop_share() -> None:
    global _active
    with _lock:
        if _active is not None:
            _active.stop()
            _active = None


def start_share(path: Path, timeout_seconds: int = SHARE_TIMEOUT_SECONDS) -> SnapshotShare:
    """Serve *path* once at ``http://<lan-ip>:<random-port>/<token>``.

    Replaces any previous share. The server shuts down after the first
    completed download or after *timeout_seconds*.
    """
    global _active

    token = secrets.token_urlsafe(16)

    class _Handler(http.server.BaseHTTPRequestHandler):
        # One route: GET /<token>. Everything else is 404 without detail.
        def do_GET(self) -> None:  # noqa: N802 (http.server API)
            share = _active
            if share is None or self.path != f"/{token}" or not share.is_active():
                self.send_error(404)
                return
            data = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/gzip")
            self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            share.downloaded = True
            logger.info("snapshot_share_downloaded", file=path.name)
            share.stop()

        def log_message(self, fmt: str, *args) -> None:  # noqa: D102
            logger.info("snapshot_share_request", detail=fmt % args)

    with _lock:
        if _active is not None:
            _active.stop()

        server = http.server.ThreadingHTTPServer(("0.0.0.0", 0), _Handler)
        port = server.server_address[1]
        share = SnapshotShare(
            url=f"http://{lan_ip()}:{port}/{token}",
            token=token,
            path=path,
            expires_at=datetime.now() + timedelta(seconds=timeout_seconds),
            _server=server,
        )
        _active = share

    threading.Thread(target=server.serve_forever, daemon=True, name="snapshot-share").start()

    def _expire() -> None:
        if not share.downloaded:
            logger.info("snapshot_share_expired", file=path.name)
        share.stop()

    timer = threading.Timer(timeout_seconds, _expire)
    timer.daemon = True
    timer.start()

    logger.info("snapshot_share_started", url=share.url, file=path.name)
    return share

"""The open of the browser when the command starts the server."""

from __future__ import annotations

from abn_combined.settings import NO_BROWSER_ENV, Settings


def test_the_address_replaces_the_host_that_means_each_interface(tmp_path) -> None:
    settings = Settings.create(data_dir=tmp_path, host="0.0.0.0", port=8000)  # noqa: S104
    assert settings.browser_url == "http://127.0.0.1:8000"


def test_the_address_keeps_the_loopback_host(tmp_path) -> None:
    settings = Settings.create(data_dir=tmp_path, host="127.0.0.1", port=8123)
    assert settings.browser_url == "http://127.0.0.1:8123"


def test_the_address_keeps_a_named_host(tmp_path) -> None:
    settings = Settings.create(data_dir=tmp_path, host="192.168.1.10", port=9000)
    assert settings.browser_url == "http://192.168.1.10:9000"


def test_the_parser_accepts_the_option() -> None:
    from abn_combined.cli import build_parser

    assert build_parser().parse_args(["--no-browser"]).no_browser is True
    assert build_parser().parse_args([]).no_browser is False


def test_the_option_stops_the_open(monkeypatch) -> None:
    from abn_combined.cli import _browser_is_wanted

    monkeypatch.delenv(NO_BROWSER_ENV, raising=False)
    assert _browser_is_wanted(no_browser_flag=False) is True
    assert _browser_is_wanted(no_browser_flag=True) is False


def test_the_variable_stops_the_open(monkeypatch) -> None:
    from abn_combined.cli import _browser_is_wanted

    monkeypatch.setenv(NO_BROWSER_ENV, "1")
    assert _browser_is_wanted(no_browser_flag=False) is False


def test_an_empty_variable_does_not_stop_the_open(monkeypatch) -> None:
    """An empty value is not a choice. The command therefore opens a browser."""
    from abn_combined.cli import _browser_is_wanted

    monkeypatch.setenv(NO_BROWSER_ENV, "")
    assert _browser_is_wanted(no_browser_flag=False) is True


# ---------------------------------------------------------------------------
# The wait for the server, and the open of the browser
# ---------------------------------------------------------------------------


def _health_server(data_dir, status: str = "ok", path: str = "/health"):
    """Serve one health answer, and return the server with its port.

    The caller closes the server. A test that serves another answer, or another
    path, stands for a program that is not this application.
    """
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    body = json.dumps({"status": status, "data_dir": str(data_dir)}).encode("utf-8")

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - the name comes from the base class
            if self.path != path:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # keep the test output clean
            return

    server = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_port


def test_the_browser_opens_after_the_server_accepts_a_connection(tmp_path) -> None:
    from abn_combined.cli import _open_browser_when_ready

    server, port = _health_server(tmp_path)
    try:
        settings = Settings.create(data_dir=tmp_path, host="127.0.0.1", port=port)
        opened: list[str] = []
        result = _open_browser_when_ready(
            settings, timeout_s=5.0, opener=lambda url: opened.append(url) or True
        )
        assert result is True
        assert opened == [f"http://127.0.0.1:{port}"]
    finally:
        server.shutdown()
        server.server_close()


def test_the_command_gives_up_when_the_server_never_answers(tmp_path) -> None:
    """No port accepts a connection, so the command opens no browser."""
    from abn_combined.cli import _open_browser_when_ready

    server, port = _health_server(tmp_path)
    server.shutdown()
    server.server_close()  # nothing answers at this port now

    settings = Settings.create(data_dir=tmp_path, host="127.0.0.1", port=port)
    opened: list[str] = []
    result = _open_browser_when_ready(
        settings, timeout_s=0.6, pause_s=0.1, opener=lambda url: opened.append(url) or True
    )
    assert result is False
    assert opened == []


def test_a_browser_that_does_not_start_writes_the_address(tmp_path, capsys) -> None:
    from abn_combined.cli import _open_browser_when_ready

    server, port = _health_server(tmp_path)
    try:
        settings = Settings.create(data_dir=tmp_path, host="127.0.0.1", port=port)
        assert _open_browser_when_ready(settings, timeout_s=5.0, opener=lambda url: False) is False
        assert f"http://127.0.0.1:{port}" in capsys.readouterr().err
    finally:
        server.shutdown()
        server.server_close()


def test_a_browser_that_raises_does_not_stop_the_server(tmp_path, capsys) -> None:
    from abn_combined.cli import _open_browser_when_ready

    def _raise(url: str) -> bool:
        raise RuntimeError("no display")

    server, port = _health_server(tmp_path)
    try:
        settings = Settings.create(data_dir=tmp_path, host="127.0.0.1", port=port)
        assert _open_browser_when_ready(settings, timeout_s=5.0, opener=_raise) is False
        err = capsys.readouterr().err
        assert "no display" in err
        assert f"http://127.0.0.1:{port}" in err
    finally:
        server.shutdown()
        server.server_close()


def test_the_server_starts_the_open_in_a_daemon_thread(tmp_path, monkeypatch) -> None:
    """The thread must be a daemon, so it does not hold the process open."""
    import threading

    from abn_combined import cli

    started: list[threading.Thread] = []
    real_thread = threading.Thread

    def _record(*args, **kwargs):
        thread = real_thread(*args, **kwargs)
        started.append(thread)
        return thread

    monkeypatch.setattr(threading, "Thread", _record)
    monkeypatch.setattr(cli, "_open_browser_when_ready", lambda *a, **k: True)
    monkeypatch.setattr("uvicorn.run", lambda *a, **k: None)

    settings = Settings.create(data_dir=tmp_path, port=8099)
    cli._run_server(settings, open_browser=True)

    assert len(started) == 1
    assert started[0].daemon is True
    assert started[0].name == "open-browser"


def test_the_server_starts_no_thread_when_the_browser_is_not_wanted(
    tmp_path, monkeypatch
) -> None:
    import threading

    from abn_combined import cli

    started = []
    real_thread = threading.Thread
    monkeypatch.setattr(
        threading, "Thread", lambda *a, **k: (started.append(1), real_thread(*a, **k))[1]
    )
    monkeypatch.setattr("uvicorn.run", lambda *a, **k: None)

    settings = Settings.create(data_dir=tmp_path, port=8099)
    cli._run_server(settings, open_browser=False)

    assert started == []


# ---------------------------------------------------------------------------
# The runs that open no browser
# ---------------------------------------------------------------------------


def _no_browser_guard(monkeypatch) -> list:
    """Record each call that would open a browser."""
    from abn_combined import cli

    opened: list = []
    monkeypatch.setattr(cli, "_open_browser_when_ready", lambda *a, **k: opened.append(1))
    return opened


def test_the_legacy_migration_opens_no_browser(tmp_path, monkeypatch) -> None:
    from abn_combined import cli

    opened = _no_browser_guard(monkeypatch)
    monkeypatch.setattr(cli, "_run_migrate_legacy", lambda *a, **k: 0)

    assert cli.main(["migrate-legacy", str(tmp_path / "legacy.db"),
                     "--data-dir", str(tmp_path)]) == 0
    assert opened == []


def test_an_occupied_port_opens_no_browser(tmp_path, monkeypatch, capsys) -> None:
    """The message and the non-zero exit status stay as they are.

    The command starts its wait before `uvicorn.run` binds the port, because
    only the bind can tell that another program holds it. The wait then asks
    the health endpoint, this application never answers, and no browser opens.
    """
    import webbrowser

    import pytest as _pytest

    from abn_combined import cli

    opened: list[str] = []
    monkeypatch.setattr(webbrowser, "open", lambda url: opened.append(url) or True)
    # Another program holds the port, so this application never answers.
    monkeypatch.setattr(cli, "_server_answers", lambda settings: False)

    def _in_use(*args, **kwargs):
        raise OSError(48, "address already in use")

    monkeypatch.setattr("uvicorn.run", _in_use)

    with _pytest.raises(SystemExit) as exc:
        cli.main(["--data-dir", str(tmp_path), "--port", "8099"])
    assert exc.value.code == 1
    assert "already in use" in capsys.readouterr().err
    assert opened == []


def test_an_unwritable_data_directory_opens_no_browser(tmp_path, monkeypatch, capsys) -> None:
    from abn_combined import cli
    from abn_combined.settings import Settings as _Settings

    opened = _no_browser_guard(monkeypatch)

    def _fail(self) -> None:
        raise RuntimeError("the data directory is not writable")

    monkeypatch.setattr(_Settings, "ensure_data_dir", _fail)

    assert cli.main(["--data-dir", str(tmp_path)]) == 1
    assert "not writable" in capsys.readouterr().err
    assert opened == []


def test_the_option_and_the_variable_each_stop_the_open(tmp_path, monkeypatch) -> None:
    from abn_combined import cli

    calls: list[bool] = []
    monkeypatch.setattr(cli, "_run_server",
                        lambda settings, open_browser=True: calls.append(open_browser))

    monkeypatch.delenv(NO_BROWSER_ENV, raising=False)
    cli.main(["--data-dir", str(tmp_path)])
    cli.main(["--data-dir", str(tmp_path), "--no-browser"])
    monkeypatch.setenv(NO_BROWSER_ENV, "1")
    cli.main(["--data-dir", str(tmp_path)])

    assert calls == [True, False, False]



def test_another_program_on_the_port_does_not_get_a_browser(tmp_path) -> None:
    """The probe must identify this application, not any open port.

    Another program holds the port and answers each request. A probe that only
    opens a socket would accept that program, and the browser would then open
    a page of the other program.
    """
    from abn_combined.cli import _open_browser_when_ready

    # The other program answers, but it does not serve the health endpoint.
    server, port = _health_server(tmp_path, path="/something-else")
    try:
        settings = Settings.create(data_dir=tmp_path, host="127.0.0.1", port=port)
        opened: list[str] = []
        result = _open_browser_when_ready(
            settings, timeout_s=0.8, pause_s=0.1,
            opener=lambda url: opened.append(url) or True,
        )
        assert result is False
        assert opened == []
    finally:
        server.shutdown()
        server.server_close()


def test_another_instance_with_another_data_directory_does_not_get_a_browser(
    tmp_path,
) -> None:
    """A second instance of this app on the port serves another data directory."""
    from abn_combined.cli import _open_browser_when_ready

    other_dir = tmp_path / "other"
    other_dir.mkdir()
    server, port = _health_server(other_dir)
    try:
        settings = Settings.create(data_dir=tmp_path, host="127.0.0.1", port=port)
        opened: list[str] = []
        result = _open_browser_when_ready(
            settings, timeout_s=0.8, pause_s=0.1,
            opener=lambda url: opened.append(url) or True,
        )
        assert result is False
        assert opened == []
    finally:
        server.shutdown()
        server.server_close()

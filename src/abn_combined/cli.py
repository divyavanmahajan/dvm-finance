"""Command-line entry point for dvm-finance."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable, Sequence

from .settings import DATA_DIR_ENV, NO_BROWSER_ENV, Settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dvm-finance",
        description="Integrated personal-finance app (download, parse, categorize, review).",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")
    parser.add_argument(
        "--data-dir",
        default=None,
        help=f"Data directory (overrides ${DATA_DIR_ENV} and the platform default).",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help=f"Do not open the browser at the address of the app "
        f"(same as setting ${NO_BROWSER_ENV}).",
    )

    subparsers = parser.add_subparsers(dest="command")

    migrate = subparsers.add_parser(
        "migrate-legacy",
        help="One-time import of transactions, rules, conditions and budgets "
        "from a legacy abn_analyst.db (idempotent; re-runs skip existing rows).",
    )
    migrate.add_argument("legacy_db", help="Path to the legacy abn_analyst.db file.")
    # Also accepted after the subcommand (argparse only sees top-level options
    # before it); SUPPRESS keeps this from clobbering a value given up front.
    migrate.add_argument("--data-dir", default=argparse.SUPPRESS, dest="data_dir",
                         help="Data directory (same as the global --data-dir).")

    return parser


def _server_answers(settings: Settings) -> bool:
    """Tell whether this application answers at the address.

    A socket that accepts a connection is not enough. Another program can hold
    the port, and the browser then opens that program. The health endpoint of
    this application names its data directory, so the answer identifies the
    server.
    """
    import json
    import urllib.request

    try:
        with urllib.request.urlopen(f"{settings.browser_url}/health", timeout=0.5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:  # noqa: BLE001 - any failure means the server is not ready
        return False
    return (
        payload.get("status") == "ok"
        and payload.get("data_dir") == str(settings.data_dir)
    )


def _open_browser_when_ready(
    settings: Settings,
    timeout_s: float = 10.0,
    pause_s: float = 0.2,
    opener: Callable[[str], bool] | None = None,
) -> bool:
    """Wait for the server, then open the browser. Return True after an open.

    The function asks the health endpoint until this application answers. The
    browser therefore never reaches a closed port, and it never reaches another
    program that holds the port. The function gives up after *timeout_s*, and it
    then opens no browser.
    """
    import time
    import webbrowser

    open_url = opener or webbrowser.open
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if _server_answers(settings):
            break
        time.sleep(pause_s)
    else:
        return False

    url = settings.browser_url
    try:
        opened = open_url(url)
    except Exception as exc:  # noqa: BLE001 - a browser must not stop the server
        print(f"Could not open a browser ({exc}). Open {url} by hand.", file=sys.stderr)
        return False
    if not opened:
        print(f"Could not open a browser. Open {url} by hand.", file=sys.stderr)
        return False
    return True


def _browser_is_wanted(no_browser_flag: bool) -> bool:
    """Tell whether the command opens a browser.

    The option `--no-browser` and the environment variable stop the open. An
    empty value of the variable does not stop it.
    """
    if no_browser_flag:
        return False
    return not os.getenv(NO_BROWSER_ENV)


def _run_migrate_legacy(legacy_db: str, settings: Settings) -> int:
    from .core.legacy_migration import LegacyMigrationError, migrate_legacy

    try:
        summary = migrate_legacy(legacy_db, settings)
    except LegacyMigrationError as exc:
        print(f"migrate-legacy failed: {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:  # e.g. unwritable data dir
        print(str(exc), file=sys.stderr)
        return 1
    print(summary.format())
    print(f"Destination database: {settings.db_path}")
    return 0


def _run_server(settings: Settings, open_browser: bool = True) -> None:
    import uvicorn

    from .app import create_app

    settings.ensure_data_dir()
    app = create_app(settings)
    url = settings.browser_url
    print(f"dvm-finance serving at {url}  (data dir: {settings.data_dir})")
    if open_browser:
        # `uvicorn.run` blocks, so another thread waits for the server and then
        # opens the browser. The thread is a daemon, so it does not hold the
        # process open after the server stops.
        import threading

        threading.Thread(
            target=_open_browser_when_ready,
            args=(settings,),
            name="open-browser",
            daemon=True,
        ).start()
    try:
        uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")
    except OSError as exc:
        if getattr(exc, "errno", None) in (48, 98) or "address already in use" in str(exc).lower():
            print(
                f"Port {settings.port} is already in use. Pass --port to choose another.",
                file=sys.stderr,
            )
            raise SystemExit(1) from exc
        raise


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    settings = Settings.create(data_dir=args.data_dir, host=args.host, port=args.port)

    if args.command == "migrate-legacy":
        return _run_migrate_legacy(args.legacy_db, settings)

    try:
        settings.ensure_data_dir()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    _run_server(settings, open_browser=_browser_is_wanted(args.no_browser))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

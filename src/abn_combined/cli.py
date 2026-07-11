"""Command-line entry point for abn-combined."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from .settings import DATA_DIR_ENV, Settings


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


def _run_server(settings: Settings) -> None:
    import uvicorn

    from .app import create_app

    settings.ensure_data_dir()
    app = create_app(settings)
    url = f"http://{settings.host}:{settings.port}"
    print(f"dvm-finance serving at {url}  (data dir: {settings.data_dir})")
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

    _run_server(settings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

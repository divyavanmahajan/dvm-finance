"""Shared real-Chrome/CDP plumbing for the downloaders.

Both the PayPal and ABN AMRO flows attach to an already-running Google
Chrome instance over CDP (``--remote-debugging-port``) instead of launching
a Playwright-managed browser. This avoids anti-bot detection, keeps bank
session cookies in a persistent profile, and means the app never needs
``playwright install`` — only the ``playwright`` pip package.
"""

from __future__ import annotations

DEFAULT_CDP_URL = "http://127.0.0.1:9226"

# Real path to the Google Chrome binary this is launched/connected to —
# macOS-specific, matching the rest of this package's scope. Used both to
# build the human-facing launch-command string (still shown as a fallback
# for manual launch, e.g. after a `launch_chrome_debug` failure) and as
# `argv[0]` for `launch_chrome_debug`'s `subprocess.Popen`.
CHROME_APP_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CHROME_USER_DATA_DIR = "~/.chrome/debugdir"


def cdp_port(cdp_url: str) -> int:
    """The debug port a CDP URL points at (default port when unparseable)."""
    from urllib.parse import urlparse

    try:
        port = urlparse(cdp_url).port
    except ValueError:
        port = None
    return port or urlparse(DEFAULT_CDP_URL).port


def chrome_launch_command(start_url: str = "", cdp_url: str = DEFAULT_CDP_URL) -> str:
    """The exact Chrome launch command shown to the user when CDP connection
    fails, on the port *cdp_url* points at, opening *start_url* if given."""
    command = (
        f"{CHROME_APP_PATH.replace(' ', '\\ ')} "
        f"--remote-debugging-port={cdp_port(cdp_url)} "
        f"--user-data-dir={CHROME_USER_DATA_DIR}"
    )
    return f"{command} {start_url}" if start_url else command


def no_contexts_message(cdp_url: str) -> str:
    """Failure message for a CDP browser that exposes no contexts."""
    return (
        "Connected Chrome has no open contexts. Ensure Chrome was started "
        f"with --remote-debugging-port={cdp_port(cdp_url)}."
    )


def launch_chrome_debug(cdp_url: str, start_url: str = "") -> None:
    """Launch real Chrome with remote debugging enabled, detached from this
    process — the button-driven equivalent of manually running
    `chrome_launch_command(start_url)` in a terminal.

    Parses the port from `cdp_url` so a non-default CDP URL (e.g. the
    "port already in use" fallback suggested by `connect_failure_message`)
    launches Chrome on the matching port. Raises `FileNotFoundError` if
    Chrome isn't installed at `CHROME_APP_PATH` — the caller (the
    launch-chrome route) turns that into a user-facing message pointing at
    `chrome_launch_command` as a manual fallback.
    """
    import os
    import subprocess

    if not os.path.exists(CHROME_APP_PATH):
        raise FileNotFoundError(
            f"Chrome not found at {CHROME_APP_PATH!r}. Run this in your terminal:\n"
            f"{chrome_launch_command(start_url, cdp_url)}"
        )

    port = cdp_port(cdp_url)
    user_data_dir = os.path.expanduser(CHROME_USER_DATA_DIR)
    argv = [
        CHROME_APP_PATH,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={user_data_dir}",
    ]
    if start_url:
        argv.append(start_url)
    subprocess.Popen(
        argv,
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def identify_cdp_endpoint(cdp_url: str, timeout: float = 3.0) -> str | None:
    """Return the ``Browser`` string from ``<cdp_url>/json/version``, or None."""
    import json as _json
    import urllib.request

    try:
        with urllib.request.urlopen(f"{cdp_url.rstrip('/')}/json/version", timeout=timeout) as resp:
            return _json.loads(resp.read().decode("utf-8")).get("Browser")
    except Exception:  # noqa: BLE001
        return None


def connect_failure_message(cdp_url: str, exc: Exception, start_url: str) -> str:
    """A targeted, actionable message for CDP connect failures."""
    browser = identify_cdp_endpoint(cdp_url)
    if "Browser context management is not supported" in str(exc):
        who = f"reports itself as {browser!r}" if browser else "did not identify itself"
        alt_url = f"http://127.0.0.1:{cdp_port(cdp_url) + 1}"
        return (
            f"Something is listening on {cdp_url} but it is not a full Chrome browser "
            f"(it {who}). Most likely another application is already using that port, "
            "so the Chrome you launched could not bind it. Either quit that application, "
            "or launch Chrome on a different port and put the matching URL in the "
            "'CDP URL' field, e.g.:\n"
            + chrome_launch_command(start_url, alt_url)
            + f"\nthen use {alt_url}"
        )
    return (
        f"Could not connect to Chrome at {cdp_url}. Please start Chrome with:\n"
        f"{chrome_launch_command(start_url, cdp_url)}\n\nError: {exc}"
    )

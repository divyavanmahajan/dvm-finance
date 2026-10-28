# Proposal

## Why

The user starts the app with `dvm-finance`, and the command prints a URL. The
user must then read the URL and open it by hand, each time. The app is a local
web application with one user, so the browser is always the next step.

## What Changes

- The command opens the default browser at the address of the app, after the
  server accepts a connection.
- The command opens the browser one time for each run, and only for the run of
  the server. The `migrate-legacy` subcommand opens no browser.
- The command opens no browser when the server does not start, for example when
  another program holds the port.
- A new option `--no-browser` stops the command from opening a browser. The
  environment variable `ABN_COMBINED_NO_BROWSER` has the same effect, for a
  service that starts the app without a command line.
- The command opens the address `127.0.0.1` when the bind host is `0.0.0.0`,
  because `0.0.0.0` is not an address that a browser can open.
- A browser that does not start writes a message. The server continues to run.

## Capabilities

### New Capabilities

None. The behavior belongs to the existing runtime capability.

### Modified Capabilities

- `app-runtime`: The capability holds the requirements for the start of the
  application, the data directory, and the message for an occupied port. It
  gains the requirement that the command opens the browser, and the rules for
  each case in which it does not.

## Impact

- `src/abn_combined/cli.py`: the parser gains `--no-browser`, and `_run_server`
  starts the browser after the server accepts a connection.
- `src/abn_combined/settings.py`: holds the address that a browser can open, if
  the host rewrite belongs there rather than in the command.
- No new dependency. The standard library module `webbrowser` does the work.
- The tests of the browser suite start the server with `uvicorn.run` directly,
  so they do not use `_run_server`. This change therefore does not open a
  browser during a test run.
- Documentation: `docs/developer.md` and `docs/product.md` name the new option.

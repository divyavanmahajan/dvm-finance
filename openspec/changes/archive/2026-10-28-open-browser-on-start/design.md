# Design

## Context

See `proposal.md` - Why. Three facts of the current code shape this design.

`cli.py:_run_server` prints the address and then calls `uvicorn.run`. That call
blocks until the server stops, so the command has no line after it that runs
while the server serves.

`cli.py:main` calls `_run_server` only for the run of the server. The subcommand
`migrate-legacy` returns before it. A failure of the data directory also returns
before it. The guard for the subcommand therefore already exists.

The browser suite starts the server with its own runner, which calls
`uvicorn.run(create_app(settings))` directly. It does not call `_run_server`.
See `tests/e2e/conftest.py`. A browser that opens from `_run_server` therefore
cannot disturb a test run.

## Goals / Non-Goals

**Goals:**

- Open the browser only when the server answers.
- Keep each failure of the browser away from the exit status of the server.
- Add no dependency.

**Non-Goals:**

- A choice of browser. The standard library already reads the variable
  `BROWSER`, and that is enough.
- A new window for each reload of the application.
- An automatic open for the iOS companion.

## Decisions

### A thread that waits for the port, not a sleep

`uvicorn.run` blocks, so the open must happen from another thread. The simple
form is a thread that sleeps one second and then opens the browser. That form is
wrong on a slow start: the browser then shows a connection error, and the user
believes the application is broken.

The thread instead asks the health endpoint of the application in a loop, with
a short pause between two tries and a limit of about ten seconds. It opens the
browser after this application answers. It writes a message and stops after the
limit.

The first form of this decision opened a socket to the host and the port, and
it opened the browser after the connection succeeded. That form is wrong when
another program already holds the port: the socket then connects to the other
program, and the browser opens a page of that program. The requirement for an
occupied port says that the command opens no browser. The health endpoint
answers with the data directory of the server, so the answer identifies this
application and not another program on the same port.

**Decision**: one daemon thread, started immediately before `uvicorn.run`, that
waits for a connection and then opens the browser. A daemon thread does not hold
the process open if the server stops first.

Alternative: the `startup` event of the application. It runs inside the server,
so it fires at the correct moment with no polling. It was rejected because the
tests and any other embedding use `create_app` directly, and such a start must
not open a browser.

### The loopback address replaces `0.0.0.0`

A bind host of `0.0.0.0` means each interface. It is not an address that a
browser can open. The command therefore opens `127.0.0.1` in that one case.

The project binds to `127.0.0.1` by default and states that it never widens the
bind address in silence, so this case is rare. It still needs the rule, because
`--host 0.0.0.0` is accepted today.

### The option and the variable both stop the open

`--no-browser` serves the command line. `ABN_COMBINED_NO_BROWSER` serves a start
with no command line, for example from a service file or a container. The
variable uses the prefix of the existing data-directory variable
`ABN_COMBINED_DATA_DIR`, so the two read as one family. The command and the
package carry the name `dvm-finance`, but no environment variable does, and a
second prefix would make the set harder to learn.

**Decision**: the command opens no browser when the option is present, or when
the variable holds a value that is not empty.

### Each failure of the browser is a message only

`webbrowser.open` returns `False` on a machine with no browser, and it can also
raise. The command catches each case, writes the address, and continues. The
server is the product; the browser is a convenience.

## Risks / Trade-offs

- **The browser opens before the first request can succeed** -> The thread waits
  for a real connection to the port, not for a fixed time.
- **A test or a service opens a window that nobody wants** -> The open lives in
  `_run_server`, which only the command line reaches. The browser suite uses its
  own runner, and a service can set the variable.
- **The thread holds the process open after the server stops** -> The thread is
  a daemon, and it also stops at its own time limit.
- **A second start opens a second window** -> Accepted. The command opens one
  browser for each run of the server, and the user starts the application one
  time for each session.

## Open Questions

- Whether the message for a browser that does not start should name the option
  `--no-browser`, so that the user can silence it. The requirement needs no
  change either way.

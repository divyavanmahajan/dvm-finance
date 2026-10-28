# Tasks

## 1. The address and the option

- [x] 1.1 Add the function that returns the address for the browser. It replaces
  the host `0.0.0.0` with `127.0.0.1`, and it keeps each other host. Verify with
  unit tests for `0.0.0.0`, for `127.0.0.1`, and for a named host.
- [x] 1.2 Add the option `--no-browser` to the parser, and read the environment
  variable `ABN_COMBINED_NO_BROWSER`. Verify with unit tests that the parser
  accepts the option, and that an empty variable does not stop the open.

## 2. The open of the browser

- [x] 2.1 Add the function that waits for a connection to the host and the port,
  with a short pause between two tries and a limit of ten seconds, and then
  opens the browser. Verify with unit tests that use a socket of the test and a
  false browser: one test for the open after the connection, and one test for
  the limit with no connection.
- [x] 2.2 Catch each failure of the browser. Write the address, and let the
  server continue. Verify with a unit test in which the false browser returns
  `False`, and with one in which it raises.
- [x] 2.3 Start the wait in a daemon thread from `_run_server`, immediately
  before `uvicorn.run`. Verify with a unit test that patches `uvicorn.run` and
  asserts that the thread starts and that it is a daemon.

## 3. The cases with no browser

- [x] 3.1 Verify with a unit test that the subcommand `migrate-legacy` opens no
  browser.
- [x] 3.2 Verify with a unit test that an occupied port keeps its message and
  its non-zero exit status, and opens no browser.
- [x] 3.3 Verify with a unit test that an unwritable data directory opens no
  browser.
- [x] 3.4 Verify with a unit test that the option and the variable each stop the
  open.

## 4. Documentation

- [x] 4.1 Name the new behavior and the option `--no-browser` in
  `docs/developer.md`, beside the commands. Verify that the documented command
  runs as written.
- [x] 4.2 Name the behavior in `docs/product.md`, where it describes the start
  of the application. Verify that the text matches the behavior of the command.

## 5. Integration

- [x] 5.1 Start the application by hand with no option, and verify that the
  browser opens at the application and that the page answers.
- [x] 5.2 Start the application by hand with `--no-browser`, and verify that no
  browser opens and that the application still serves.
- [x] 5.3 Run `pytest` and `ruff check .`, and verify that the coverage gate of
  80 percent still passes. Verify also that `pytest -m e2e` opens no browser
  window.

# Tasks

Start this change after `open-browser-on-start` reaches the main branch,
because that change adds the third variable.

## 1. The helper that reads a pair of names

- [x] 1.1 Add the helper in `src/abn_combined/settings.py` that reads the new
  name, falls back to the old name, and writes one warning to the standard error
  stream after a fall back. Verify with unit tests for the new name alone, the
  old name alone, both names, and neither name.
- [x] 1.2 Add the table that holds each pair of names beside the helper. Verify
  with a unit test that the table names each of the three variables, and that
  each new name starts with `DVM_FINANCE_`.

## 2. The three variables

- [x] 2.1 Rename `DATA_DIR_ENV` to `DVM_FINANCE_DATA_DIR`, and read it through
  the helper in `resolve_data_dir`. Verify with unit tests that the new name
  resolves the directory, that the old name still resolves it, and that the
  option still wins over both.
- [x] 2.2 Rename `NO_BROWSER_ENV` to `DVM_FINANCE_NO_BROWSER`, and read it
  through the helper. Verify with unit tests that each name stops the browser,
  and that an empty value stops nothing.
- [x] 2.3 Add the constant for the logging variable in
  `src/abn_combined/logging_config.py`, name it `DVM_FINANCE_LOG_ENV`, and read
  it through the helper. Verify with unit tests that each name selects the
  production form, and that the default stays `development`.

## 3. The warning

- [x] 3.1 Verify with a unit test that the application writes one warning for
  each old name it reads, and that the warning names both names.
- [x] 3.2 Verify with a unit test that the application writes no warning when
  the environment holds the new name only, and none when it holds neither.
- [x] 3.3 Verify with a unit test that the new name wins when both names hold a
  different value, and that the warning still appears.

## 4. Documentation

- [x] 4.1 Name the new variables in `docs/developer.md`, in the list of the
  variables and the flags, with one line for the old names and their removal.
  Verify that each documented command runs as written.
- [x] 4.2 Name the new variable in `docs/product.md`, where it describes the
  browser at the start. Verify that the text matches the behavior of the
  command.
- [x] 4.3 Replace the old names in `docs/phase/init/spec.md` and
  `docs/phase/init/01-project-setup/task.md`. Verify that no other word of those
  records changes.

## 5. Integration

- [x] 5.1 Search the repository for `ABN_COMBINED_` and verify that each
  remaining hit is the pair table, a test of the fall back, or the note about
  the removal. The sweep also found the artifacts of `open-browser-on-start`,
  which named the old variable. That change was complete, so it is archived
  first, and this change now modifies its requirement for the new name.
- [x] 5.2 Start the application with each new variable, and verify the behavior
  of each one: the data directory, the logging form, and the browser.
- [x] 5.3 Start the application with an old variable, and verify that it still
  works and that the warning names both names.
- [x] 5.4 Run `pytest` and `ruff check .`, and verify that the coverage gate of
  80 percent still passes.

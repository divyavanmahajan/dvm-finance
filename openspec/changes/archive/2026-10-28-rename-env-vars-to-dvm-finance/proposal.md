# Proposal

## Why

The project carries the name `dvm-finance`. The published package, the command
and the repository each use that name. The environment variables still use the
prefix `ABN_COMBINED_`, which the rename of the project left behind. A user who
looks for the variables of `dvm-finance` therefore finds a name that matches no
other part of the product.

## What Changes

- Each environment variable takes the prefix `DVM_FINANCE_`.

  | Old name | New name |
  |---|---|
  | `ABN_COMBINED_DATA_DIR` | `DVM_FINANCE_DATA_DIR` |
  | `ABN_COMBINED_LOG_ENV` | `DVM_FINANCE_LOG_ENV` |
  | `ABN_COMBINED_NO_BROWSER` | `DVM_FINANCE_NO_BROWSER` |

- The application reads the old name as well, for a time. The new name wins when
  both names hold a value.
- The application writes a deprecation warning when it reads a value from an old
  name. The warning names the new name.
- **BREAKING** in a later major version: the application will stop reading the
  old names. This change does not remove them.
- The variable for the logging environment gets a named constant, as the other
  two variables already have. The code holds that name one time only.
- Each document names the new variable. The documents are `docs/developer.md`,
  `docs/product.md`, and the two records under `docs/phase/init/`.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `app-runtime`: The capability holds the resolution of the data directory and
  the start of the application. It gains the names of the environment variables,
  the rule that the new name wins, and the warning for an old name.

## Impact

- `src/abn_combined/settings.py`: holds `DATA_DIR_ENV` and `NO_BROWSER_ENV`, and
  the resolution of the data directory. It gains the old names and the warning.
- `src/abn_combined/logging_config.py`: reads `ABN_COMBINED_LOG_ENV` as a string
  in the code. It gains a constant and the same two-name rule.
- `src/abn_combined/cli.py`: reads the variable for the browser through
  `NO_BROWSER_ENV`, so it needs no change of its own.
- The Python package keeps the name `abn_combined`. A rename of the package
  changes each import and the layout of the wheel, and it belongs in its own
  change.
- The iOS companion reads no environment variable, so it needs no change.
- The change `open-browser-on-start` adds `ABN_COMBINED_NO_BROWSER`. This change
  renames that variable, so it must follow that change into the main branch.

# Design

## Context

See `proposal.md` - Why. Three facts of the current code shape this design.

`settings.py` holds `DATA_DIR_ENV` and `NO_BROWSER_ENV` as constants, and
`resolve_data_dir` reads the first one. `cli.py` reads the second one through
the constant. A rename of a constant therefore reaches each reader.

`logging_config.py` reads `"ABN_COMBINED_LOG_ENV"` as a string inside the
function. It has no constant, so this change adds one.

The data directory holds the database, the statements and the snapshots. A
change that makes the application read another directory does not lose a file,
but the application then shows no transaction. A user reads that as the loss of
their data.

## Goals / Non-Goals

**Goals:**

- One prefix for each environment variable.
- No silent change of the data directory for a user who set the old name.
- One place in the code that holds the pair of names.

**Non-Goals:**

- The rename of the Python package `abn_combined`. That rename changes each
  import, the wheel and the module path of every test. It belongs in its own
  change.
- The removal of the old names. A later major version does that.
- A configuration file. The variables and the options stay as they are.

## Decisions

### One helper reads a pair of names

Each variable needs the same three steps: read the new name, fall back to the
old name, and warn after a fall back. Three copies of those steps drift, as the
duplicated clauses of the transfer exclusion already show in this project.

**Decision**: `settings.py` holds one helper, for example
`read_env(new_name, old_name)`. It returns the value and it writes the warning.
Each reader calls it. The pairs live in one table beside the helper, so a later
change that removes the old names edits one place.

### The warning goes to the standard error stream

The application writes the warning with `warnings.warn` or to `sys.stderr`
rather than through the logger. The reason is the order of the start: the
command resolves the data directory before it configures the logging, so a
warning through the logger can reach no handler.

**Decision**: write to `sys.stderr`, with the same form as the other messages of
the command. One warning for each old name, and not one for each read.

### The new name wins

A user who sets both names is in the middle of the migration. The new name is
the one they just added, so it is the one they mean. The application therefore
prefers it, and it still warns, because the old name is still in their profile
and the next major version will ignore it.

### The documents under `docs/phase/` change as well

Those two files record a past phase of the project. They are not living
documents. They still name a variable that will stop working, and a reader who
copies from them sets a dead variable.

**Decision**: update them, and keep each other word of those records as it is.

## Risks / Trade-offs

- **A user keeps the old name and never reads the warning** -> The warning names
  both names on each start. The old name keeps working until the next major
  version, so nothing breaks in the meantime.
- **The warning appears in a test and makes the output noisy** -> The tests set
  the new name. A test of the fall back asserts the warning, so the noise is the
  subject of that test.
- **A pair is forgotten** -> One table holds each pair, and a test asserts that
  the table covers each variable the code reads.
- **The change lands before `open-browser-on-start`** -> The variable
  `ABN_COMBINED_NO_BROWSER` does not yet exist on the main branch. This change
  therefore follows that change, and the tasks name the dependency.

## Open Questions

- Which major version removes the old names. The removal needs its own change,
  and a note in the release text of this one is enough for now.

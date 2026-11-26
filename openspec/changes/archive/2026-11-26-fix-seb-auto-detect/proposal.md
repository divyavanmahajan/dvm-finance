# Proposal

## Why

The format `auto` selects the parser from the file extension only. An SEB
export has the extension `.csv`, so `auto` gives it to the generic CSV parser.
That parser refuses the file, and the import stores no transaction. On
2026-11-26, the user uploaded an SEB file three times with `auto`. Each upload
failed, and three SEB transactions did not get into the database.

## What Changes

- With the format `auto`, the system SHALL give a `.csv` file with the SEB
  header row to the SEB parser.
- The upload form and the help page tell the user that `auto` finds an SEB file.
- An explicit format stays as it is.

## Capabilities

### Modified Capabilities

- `statement-upload`: The requirement "Format selection" adds the detection of
  the SEB header row.

## Impact

- `parsers/seb.py` gets the function `is_seb_file`.
- `parsers/__init__.py` `parse_statement_file` calls the SEB parser for an SEB
  `.csv` file.
- The upload form and `web/help/features.md` get new text.
- The iOS app is not part of this change.

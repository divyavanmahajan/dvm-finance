# Tasks

## 1. Detection of the SEB header row

- [x] 1.1 In `parsers/seb.py`, add `is_seb_file`. The function reads the first line of the file and compares it with the SEB columns. Add tests for an SEB file and for another CSV file. Verify with `pytest tests -k seb`.
- [x] 1.2 In `parsers/__init__.py` `parse_statement_file`, give a `.csv` file with the SEB header row to the SEB parser. Add a test that imports the SEB fixture with the format `auto`. Verify with `pytest tests/test_upload.py`.

## 2. User text

- [x] 2.1 Update the hint of the upload form and the Upload section of `web/help/features.md`. Verify that the text uses ASD-STE100.

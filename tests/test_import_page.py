"""Tests for the combined Import page and the redirects from the old paths."""

from __future__ import annotations

import pytest


def test_import_page_holds_downloads_upload_and_sample_data(client):
    resp = client.get("/import")
    assert resp.status_code == 200
    text = resp.text
    assert "<h1 class=\"h2\">Import</h1>" in text
    assert 'id="abn-status"' in text or "ABN AMRO" in text
    assert 'id="upload-form"' in text
    assert 'id="sample-data"' in text
    # The download sources come first, then the upload form.
    assert text.index('id="download"') < text.index('id="upload"') < text.index('id="sample-data"')


@pytest.mark.parametrize("old", ["/download", "/upload"])
def test_old_paths_redirect_to_import(client, old):
    resp = client.get(old, follow_redirects=False)
    assert resp.status_code == 307
    assert resp.headers["location"] == "/import"


def test_redirect_keeps_the_query_string(client):
    resp = client.get("/download?source=abn", follow_redirects=False)
    assert resp.headers["location"] == "/import?source=abn"

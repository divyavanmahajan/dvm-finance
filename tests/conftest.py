"""Shared test fixtures."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from abn_combined.app import create_app
from abn_combined.settings import Settings


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings.create(data_dir=tmp_path / "data")


@pytest.fixture
def app(settings):
    application = create_app(settings)
    # create_app runs migrations via the startup event, which only fires under
    # TestClient. Run them eagerly so tests using the app without a client (e.g.
    # direct import_file calls) also have the schema in place. Idempotent.
    from abn_combined.migrations import upgrade_to_head

    upgrade_to_head(settings)
    return application


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c

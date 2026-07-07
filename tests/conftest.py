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
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c

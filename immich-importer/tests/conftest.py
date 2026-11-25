from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "fixtures"))

from takeout2immich.config.models import (  # noqa: E402
    AppConfig,
    LocalSourceConfig,
    LogNotifierConfig,
    RuntimeConfig,
    StagingConfig,
    ValidationConfig,
)


@pytest.fixture(autouse=True)
def _data_home(tmp_path, monkeypatch):
    monkeypatch.setenv("TAKEOUT2IMMICH_HOME", str(tmp_path / "data"))
    monkeypatch.delenv("TAKEOUT2IMMICH_CONFIG", raising=False)


@pytest.fixture
def config(tmp_path) -> AppConfig:
    return AppConfig(
        source=LocalSourceConfig(path=tmp_path / "incoming", auto_confirm=False),
        staging=StagingConfig(path=tmp_path / "staging", min_free_gb=0),
        validation=ValidationConfig(report_dir=tmp_path / "reports"),
        notifications=[LogNotifierConfig(status_file=tmp_path / "state" / "status")],
        runtime=RuntimeConfig(
            state_db=tmp_path / "state" / "state.db",
            heartbeat_file=tmp_path / "state" / "heartbeat",
            max_attempts=2,
        ),
    )

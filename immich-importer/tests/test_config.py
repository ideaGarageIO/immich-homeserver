import stat

import pytest
from pydantic import ValidationError

from takeout2immich.config import AppConfig, load_config, read_secret, save_config, write_secret
from takeout2immich.config.models import DriveSourceConfig, LocalSourceConfig
from takeout2immich.config.store import ConfigNotFoundError


def test_defaults_are_drive_and_log(tmp_path):
    cfg = AppConfig()
    assert isinstance(cfg.source, DriveSourceConfig)
    assert [n.type for n in cfg.notifications] == ["log"]
    assert str(cfg.immich.api_key_file).startswith(str(tmp_path / "data"))


def test_round_trip(tmp_path, config):
    path = tmp_path / "cfg" / "config.yaml"
    save_config(config, path)
    loaded = load_config(path)
    assert loaded == config
    assert isinstance(loaded.source, LocalSourceConfig)


def test_missing_config(tmp_path):
    with pytest.raises(ConfigNotFoundError):
        load_config(tmp_path / "nope.yaml")


def test_source_discriminator_requires_fields():
    with pytest.raises(ValidationError):
        AppConfig.model_validate({"source": {"type": "local"}})  # path missing
    with pytest.raises(ValidationError):
        AppConfig.model_validate({"source": {"type": "ftp"}})


def test_unknown_keys_rejected():
    with pytest.raises(ValidationError):
        AppConfig.model_validate({"immich": {"url": "x", "apikey": "inline-secret"}})


def test_secret_files_are_private(tmp_path):
    p = tmp_path / "secrets" / "key"
    write_secret(p, "  s3cret \n")
    assert read_secret(p) == "s3cret"
    assert stat.S_IMODE(p.stat().st_mode) == 0o600
    assert stat.S_IMODE(p.parent.stat().st_mode) == 0o700


def test_config_never_contains_secret_values(tmp_path, config):
    path = tmp_path / "config.yaml"
    save_config(config, path)
    text = path.read_text()
    assert "api_key_file" in text and "api_key:" not in text

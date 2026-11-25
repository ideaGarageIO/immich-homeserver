"""Load/save config.yaml and secret files."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import yaml

from takeout2immich.config.models import AppConfig, data_dir


class ConfigNotFoundError(FileNotFoundError):
    pass


def default_config_path() -> Path:
    env = os.environ.get("TAKEOUT2IMMICH_CONFIG")
    return Path(env) if env else data_dir() / "config.yaml"


def load_config(path: Path | None = None) -> AppConfig:
    path = path or default_config_path()
    if not path.exists():
        raise ConfigNotFoundError(
            f"No config at {path}. Run `takeout2immich config` to create one."
        )
    raw = yaml.safe_load(path.read_text()) or {}
    return AppConfig.model_validate(raw)


def _atomic_write(path: Path, data: str, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(data)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def save_config(config: AppConfig, path: Path | None = None) -> Path:
    path = path or default_config_path()
    data = config.model_dump(mode="json")
    text = "# takeout2immich configuration. Edit with `takeout2immich config`.\n"
    text += yaml.safe_dump(data, sort_keys=False)
    _atomic_write(path, text, 0o644)
    return path


def write_secret(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    _atomic_write(path, value.strip() + "\n", 0o600)


def read_secret(path: Path) -> str:
    try:
        return path.read_text().strip()
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Secret file missing: {path}") from exc

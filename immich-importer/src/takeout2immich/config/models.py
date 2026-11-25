"""Configuration model (config.yaml).

Secrets are never stored inline: every credential is a path to a file that holds it.
Default paths live under the data directory (``$TAKEOUT2IMMICH_HOME``, default ``/data/importer``
inside the container).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field


def data_dir() -> Path:
    return Path(os.environ.get("TAKEOUT2IMMICH_HOME", "/data/importer"))


def _in_data(*parts: str):
    return lambda: data_dir().joinpath(*parts)


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid")


EVENT_TYPES = (
    "EXPORT_DETECTED",
    "DOWNLOAD_COMPLETE",
    "IMPORT_COMPLETE",
    "VALIDATION_PASSED",
    "VALIDATION_FAILED",
    "CLEANUP_DONE",
    "ERROR",
    "ACTION_REQUIRED",
)
EventName = Literal[
    "EXPORT_DETECTED",
    "DOWNLOAD_COMPLETE",
    "IMPORT_COMPLETE",
    "VALIDATION_PASSED",
    "VALIDATION_FAILED",
    "CLEANUP_DONE",
    "ERROR",
    "ACTION_REQUIRED",
]


class ImmichConfig(_Section):
    url: str = "http://immich-server:2283"
    api_key_file: Path = Field(default_factory=_in_data("secrets", "immich_api_key"))


class DriveSourceConfig(_Section):
    type: Literal["drive"] = "drive"
    rclone_binary: str = "rclone"
    rclone_remote: str = "gdrive"
    folder: str = "Takeout"
    rclone_config_file: Path = Field(default_factory=_in_data("secrets", "rclone.conf"))
    use_trash: bool = False
    verify_md5_locally: bool = True
    auto_confirm: bool = False


class LocalSourceConfig(_Section):
    type: Literal["local"] = "local"
    path: Path
    delete_originals: bool = False
    auto_confirm: bool = True


class DirectSourceConfig(_Section):
    type: Literal["direct"] = "direct"
    auto_confirm: bool = False


SourceConfig = Annotated[
    Union[DriveSourceConfig, LocalSourceConfig, DirectSourceConfig],
    Field(discriminator="type"),
]


class StagingConfig(_Section):
    path: Path = Path("/data/staging")
    min_free_gb: int = 20


class ImporterConfig(_Section):
    immich_go_binary: str = "immich-go"
    concurrent_tasks: int = Field(default=8, ge=1, le=20)
    manage_burst: Literal["NoStack", "Stack", "StackKeepRaw", "StackKeepJPEG"] = "Stack"
    manage_raw_jpeg: Literal["NoStack", "KeepRaw", "KeepJPG", "StackCoverRaw", "StackCoverJPG"] = (
        "StackCoverRaw"
    )
    manage_heic_jpeg: Literal["NoStack", "KeepHeic", "KeepJPG", "StackCoverHeic", "StackCoverJPG"] = (
        "StackCoverHeic"
    )
    include_unmatched: bool = True
    include_archived: bool = True
    include_partner: bool = True
    include_trashed: bool = False
    sync_albums: bool = True
    people_tag: bool = True
    takeout_tag: bool = True
    pause_immich_jobs: bool = True
    on_errors: str = "continue"
    extra_flags: list[str] = Field(default_factory=list)


class ValidationConfig(_Section):
    enabled: bool = True
    fail_on_missing: bool = True
    report_dir: Path = Field(default_factory=_in_data("reports"))
    batch_size: int = Field(default=1000, ge=1, le=5000)
    # fnmatch patterns (against the entry name) that are never counted as missing,
    # e.g. "*-edited.*" if you don't care about Google's edited copies.
    ignore_patterns: list[str] = Field(default_factory=list)


class CleanupConfig(_Section):
    delete_local_after_validation: bool = True
    delete_remote_after_validation: bool = True


class HomeAssistantNotifierConfig(_Section):
    type: Literal["homeassistant"] = "homeassistant"
    url: str
    token_file: Path = Field(default_factory=_in_data("secrets", "homeassistant_token"))
    service: str  # e.g. "mobile_app_pixel" -> POST /api/services/notify/mobile_app_pixel
    events: list[EventName] | None = None  # None = all events


class LogNotifierConfig(_Section):
    type: Literal["log"] = "log"
    status_file: Path = Field(default_factory=_in_data("state", "status"))
    events: list[EventName] | None = None


NotifierConfig = Annotated[
    Union[HomeAssistantNotifierConfig, LogNotifierConfig],
    Field(discriminator="type"),
]


class RuntimeConfig(_Section):
    poll_interval_s: int = Field(default=300, ge=10)
    state_db: Path = Field(default_factory=_in_data("state", "state.db"))
    heartbeat_file: Path = Field(default_factory=_in_data("state", "heartbeat"))
    max_attempts: int = Field(default=5, ge=1)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"


class AppConfig(_Section):
    immich: ImmichConfig = Field(default_factory=ImmichConfig)
    source: SourceConfig = Field(default_factory=DriveSourceConfig)
    staging: StagingConfig = Field(default_factory=StagingConfig)
    importer: ImporterConfig = Field(default_factory=ImporterConfig)
    validation: ValidationConfig = Field(default_factory=ValidationConfig)
    cleanup: CleanupConfig = Field(default_factory=CleanupConfig)
    notifications: list[NotifierConfig] = Field(default_factory=lambda: [LogNotifierConfig()])
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)

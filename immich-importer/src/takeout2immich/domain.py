"""Domain model: export sets, parts, stages, results and events."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


def now() -> datetime:
    return datetime.now(UTC)


class Stage(StrEnum):
    DISCOVERED = "DISCOVERED"
    DOWNLOADING = "DOWNLOADING"
    CONFIRMED = "CONFIRMED"  # user said the export is complete; final sweep pending
    DOWNLOADED = "DOWNLOADED"  # all parts present and verified
    IMPORTING = "IMPORTING"
    IMPORTED = "IMPORTED"
    VALIDATING = "VALIDATING"
    VALIDATED = "VALIDATED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    CLEANED = "CLEANED"
    DONE = "DONE"
    FAILED = "FAILED"


# Stages in which new parts may still appear and downloads continue.
DOWNLOAD_STAGES = {Stage.DISCOVERED, Stage.DOWNLOADING, Stage.CONFIRMED}
TERMINAL_STAGES = {Stage.DONE}


class PartState(StrEnum):
    PENDING = "PENDING"
    DOWNLOADING = "DOWNLOADING"  # transfer in progress (only one part at a time)
    DOWNLOADED = "DOWNLOADED"  # present locally and verified
    FAILED = "FAILED"


class ExportPart(BaseModel):
    name: str
    size: int
    md5: str | None = None
    remote_ref: str  # source-specific locator (rclone path, local path, ...)
    state: PartState = PartState.PENDING
    local_path: str | None = None
    attempts: int = 0
    error: str | None = None


class ImportResult(BaseModel):
    exit_code: int
    uploaded: int | None = None
    duplicates: int | None = None
    errors: int | None = None
    log_path: str | None = None
    output_tail: str = ""


class MissingItem(BaseModel):
    zip: str
    entry: str
    sha1: str
    reason: str = "not in Immich"


class ValidationReport(BaseModel):
    export_id: str
    created_at: datetime = Field(default_factory=now)
    expected: int = 0
    present: int = 0
    excluded: int = 0
    ignored: int = 0
    missing: list[MissingItem] = Field(default_factory=list)
    flagged: list[MissingItem] = Field(default_factory=list)  # trashed in Immich / unsupported
    report_path: str | None = None

    @property
    def passed(self) -> bool:
        return not self.missing

    def summary(self) -> str:
        return (
            f"expected {self.expected}, present {self.present}, missing {len(self.missing)}, "
            f"flagged {len(self.flagged)}, excluded {self.excluded}, ignored {self.ignored}"
        )


class ExportSet(BaseModel):
    id: str
    source_type: str
    stage: Stage = Stage.DISCOVERED
    parts: dict[str, ExportPart] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)
    confirmed_at: datetime | None = None
    import_result: ImportResult | None = None
    validation_summary: str | None = None
    validation_passed: bool | None = None
    report_path: str | None = None
    attempts: int = 0
    error: str | None = None
    failed_stage: Stage | None = None
    notified: list[str] = Field(default_factory=list)  # one-shot notification keys already sent

    def sorted_parts(self) -> list[ExportPart]:
        return [self.parts[k] for k in sorted(self.parts)]

    @property
    def total_size(self) -> int:
        return sum(p.size for p in self.parts.values())

    @property
    def downloaded_count(self) -> int:
        return sum(1 for p in self.parts.values() if p.state == PartState.DOWNLOADED)

    @property
    def all_downloaded(self) -> bool:
        return bool(self.parts) and self.downloaded_count == len(self.parts)

    def local_paths(self) -> list[str]:
        return [p.local_path for p in self.sorted_parts() if p.local_path]


_EXPORT_RE = re.compile(r"^(?P<id>takeout-\d{8}T\d{6}Z)(?:-\d+)*\.(?:zip|tgz)$", re.IGNORECASE)


def export_id_for(filename: str) -> str | None:
    """Group key for a Takeout archive name, e.g. takeout-20261125T153000Z-3-001.zip."""
    m = _EXPORT_RE.match(filename)
    return m.group("id") if m else None


class EventType(StrEnum):
    EXPORT_DETECTED = "EXPORT_DETECTED"
    DOWNLOAD_COMPLETE = "DOWNLOAD_COMPLETE"
    IMPORT_COMPLETE = "IMPORT_COMPLETE"
    VALIDATION_PASSED = "VALIDATION_PASSED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    CLEANUP_DONE = "CLEANUP_DONE"
    ERROR = "ERROR"
    ACTION_REQUIRED = "ACTION_REQUIRED"


class Event(BaseModel):
    type: EventType
    message: str
    export_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    at: datetime = Field(default_factory=now)

"""Source interface and registry.

A Source knows where Takeout archives come from. It lists them, fetches one part into the
staging directory, verifies it, and deletes the remote copy after a successful validation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from takeout2immich.domain import ExportPart, ExportSet


@runtime_checkable
class Source(Protocol):
    type: str

    def discover(self) -> list[ExportSet]:
        """Return the export sets currently visible, with their parts (state PENDING)."""

    def fetch(self, part: ExportPart, dest_dir: Path) -> Path:
        """Make the part available locally and return its path."""

    def verify(self, part: ExportPart, path: Path) -> bool:
        """True if the local copy matches the remote (size/checksum)."""

    def delete_remote(self, export_set: ExportSet) -> int:
        """Delete the source copy of every part (only after validation passed). Returns count deleted."""

    def check(self) -> tuple[bool, str]:
        """Health check used by `doctor` and the TUI Test button."""


def build_source(config) -> Source:
    from takeout2immich.config.models import (
        DirectSourceConfig,
        DriveSourceConfig,
        LocalSourceConfig,
    )

    if isinstance(config, DriveSourceConfig):
        from takeout2immich.sources.drive import DriveSource

        return DriveSource(config)
    if isinstance(config, LocalSourceConfig):
        from takeout2immich.sources.local import LocalSource

        return LocalSource(config)
    if isinstance(config, DirectSourceConfig):
        from takeout2immich.sources.direct import DirectSource

        return DirectSource(config)
    raise ValueError(f"Unknown source config: {config!r}")


def group_parts(source_type: str, parts: list[tuple[str, ExportPart]]) -> list[ExportSet]:
    """Group (export_id, part) pairs into ExportSets."""
    sets: dict[str, ExportSet] = {}
    for export_id, part in parts:
        es = sets.setdefault(export_id, ExportSet(id=export_id, source_type=source_type))
        es.parts[part.name] = part
    return [sets[k] for k in sorted(sets)]

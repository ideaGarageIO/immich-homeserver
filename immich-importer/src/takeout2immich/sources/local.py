"""Local source: Takeout archives that are already on disk (manual download, tests, dev)."""

from __future__ import annotations

from pathlib import Path

from takeout2immich.config.models import LocalSourceConfig
from takeout2immich.domain import ExportPart, ExportSet, export_id_for
from takeout2immich.sources.base import group_parts


class LocalSource:
    type = "local"

    def __init__(self, config: LocalSourceConfig):
        self.config = config

    def discover(self) -> list[ExportSet]:
        root = self.config.path
        if not root.is_dir():
            return []
        parts = []
        for f in sorted(root.iterdir()):
            export_id = export_id_for(f.name)
            if export_id and f.is_file():
                parts.append(
                    (export_id, ExportPart(name=f.name, size=f.stat().st_size, remote_ref=str(f)))
                )
        return group_parts(self.type, parts)

    def fetch(self, part: ExportPart, dest_dir: Path) -> Path:
        # No copy: the archive is already local. Cleanup never deletes files outside staging,
        # so the originals are only removed by delete_remote() when delete_originals is set.
        return Path(part.remote_ref)

    def verify(self, part: ExportPart, path: Path) -> bool:
        return path.exists() and path.stat().st_size == part.size

    def delete_remote(self, export_set: ExportSet) -> int:
        if not self.config.delete_originals:
            return 0
        for part in export_set.sorted_parts():
            Path(part.remote_ref).unlink(missing_ok=True)
        return len(export_set.parts)

    def check(self) -> tuple[bool, str]:
        if not self.config.path.is_dir():
            return False, f"{self.config.path} is not a directory"
        return True, f"{len(self.discover())} export set(s) in {self.config.path}"

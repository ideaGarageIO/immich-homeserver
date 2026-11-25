"""Google Drive source: Takeout delivered with "Add to Drive", pulled with rclone (OAuth)."""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

from takeout2immich.config.models import DriveSourceConfig
from takeout2immich.domain import ExportPart, ExportSet, export_id_for
from takeout2immich.sources.base import group_parts
from takeout2immich.util import hash_file

log = logging.getLogger(__name__)


class RcloneError(RuntimeError):
    pass


class DriveSource:
    type = "drive"

    def __init__(self, config: DriveSourceConfig, runner=subprocess.run):
        self.config = config
        self._run_proc = runner

    # helpers -------------------------------------------------------------
    @property
    def _root(self) -> str:
        folder = self.config.folder.strip("/")
        return f"{self.config.rclone_remote}:{folder}" if folder else f"{self.config.rclone_remote}:"

    def _rclone(self, *args: str, timeout: int | None = None) -> str:
        cmd = [
            self.config.rclone_binary,
            "--config",
            str(self.config.rclone_config_file),
            *args,
        ]
        log.debug("rclone: %s", " ".join(cmd))
        proc = self._run_proc(cmd, capture_output=True, text=True, timeout=timeout)
        if proc.returncode != 0:
            raise RcloneError(f"rclone {args[0]} failed ({proc.returncode}): {proc.stderr.strip()[-2000:]}")
        return proc.stdout

    # Source --------------------------------------------------------------
    def discover(self) -> list[ExportSet]:
        out = self._rclone("lsjson", "--files-only", "--hash", "--hash-type", "md5", self._root, timeout=300)
        items = json.loads(out or "[]")
        parts: list[tuple[str, ExportPart]] = []
        for item in items:
            name = item["Name"]
            export_id = export_id_for(name)
            if not export_id:
                continue
            md5 = (item.get("Hashes") or {}).get("md5") or (item.get("Hashes") or {}).get("MD5")
            parts.append(
                (
                    export_id,
                    ExportPart(name=name, size=int(item["Size"]), md5=md5, remote_ref=item["Path"]),
                )
            )
        return group_parts(self.type, parts)

    def fetch(self, part: ExportPart, dest_dir: Path) -> Path:
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / part.name
        if dest.exists() and dest.stat().st_size == part.size and self.verify(part, dest):
            return dest
        # rclone verifies the MD5 after transfer itself; --partial-suffix keeps half-written
        # files out of the way so a crashed download never looks complete.
        self._rclone(
            "copyto",
            f"{self._root}/{part.remote_ref}",
            str(dest),
            "--retries",
            "5",
            "--low-level-retries",
            "20",
            "--partial-suffix",
            ".partial",
        )
        return dest

    def verify(self, part: ExportPart, path: Path) -> bool:
        if not path.exists() or path.stat().st_size != part.size:
            return False
        if self.config.verify_md5_locally and part.md5:
            return hash_file(path, "md5") == part.md5.lower()
        return True

    def delete_remote(self, export_set: ExportSet) -> int:
        flag = "--drive-use-trash=true" if self.config.use_trash else "--drive-use-trash=false"
        for part in export_set.sorted_parts():
            self._rclone("deletefile", flag, f"{self._root}/{part.remote_ref}")
        return len(export_set.parts)

    def check(self) -> tuple[bool, str]:
        if not self.config.rclone_config_file.exists():
            return False, f"rclone config not found at {self.config.rclone_config_file}"
        try:
            self._rclone("lsjson", "--max-depth", "1", f"{self.config.rclone_remote}:", timeout=60)
        except (RcloneError, OSError, subprocess.TimeoutExpired) as exc:
            return False, str(exc)
        try:
            count = len(self.discover())
        except (RcloneError, json.JSONDecodeError) as exc:
            if "directory not found" in str(exc):
                return True, f"Drive reachable; folder '{self.config.folder}' does not exist yet"
            return False, str(exc)
        return True, f"Drive reachable; {count} export set(s) in '{self.config.folder}'"

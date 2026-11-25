"""Run `immich-go upload from-google-photos` for a whole export set.

All parts of a set go into ONE invocation: a JSON sidecar can live in a different zip than its
photo, and immich-go only matches them when it sees every part.

The counts parsed from immich-go's output are best-effort (its summary format is not a stable
interface). Completeness is decided by the validation step, not by these numbers.
"""

from __future__ import annotations

import logging
import re
import subprocess
from collections import deque
from datetime import UTC, datetime
from pathlib import Path

from takeout2immich.config.models import ImporterConfig
from takeout2immich.domain import ImportResult

log = logging.getLogger(__name__)


def _bool_flag(name: str, value: bool) -> str:
    return f"--{name}={'true' if value else 'false'}"


def build_args(
    cfg: ImporterConfig, server: str, api_key: str, paths: list[str], log_file: Path
) -> list[str]:
    return [
        cfg.immich_go_binary,
        "upload",
        "from-google-photos",
        f"--server={server}",
        f"--api-key={api_key}",
        "--no-ui",
        "--log-type=JSON",
        f"--log-file={log_file}",
        f"--concurrent-tasks={cfg.concurrent_tasks}",
        f"--manage-burst={cfg.manage_burst}",
        f"--manage-raw-jpeg={cfg.manage_raw_jpeg}",
        f"--manage-heic-jpeg={cfg.manage_heic_jpeg}",
        _bool_flag("include-unmatched", cfg.include_unmatched),
        _bool_flag("include-archived", cfg.include_archived),
        _bool_flag("include-partner", cfg.include_partner),
        _bool_flag("include-trashed", cfg.include_trashed),
        _bool_flag("sync-albums", cfg.sync_albums),
        _bool_flag("people-tag", cfg.people_tag),
        _bool_flag("takeout-tag", cfg.takeout_tag),
        _bool_flag("pause-immich-jobs", cfg.pause_immich_jobs),
        f"--on-errors={cfg.on_errors}",
        *cfg.extra_flags,
        *paths,
    ]


def redact(args: list[str]) -> list[str]:
    return ["--api-key=***" if a.startswith("--api-key=") else a for a in args]


_COUNT_PATTERNS = {
    "uploaded": re.compile(r"\buploaded\b[^0-9\n]{0,40}?(\d[\d,]*)", re.I),
    "duplicates": re.compile(r"(?:server has (?:the )?same|duplicate)[^0-9\n]{0,40}?(\d[\d,]*)", re.I),
    "errors": re.compile(r"\berrors?\b[^0-9\n]{0,40}?(\d[\d,]*)", re.I),
}


def parse_counts(text: str) -> dict[str, int | None]:
    """Best-effort: last number following each label in the output tail."""
    out: dict[str, int | None] = {}
    for key, pat in _COUNT_PATTERNS.items():
        matches = pat.findall(text)
        out[key] = int(matches[-1].replace(",", "")) if matches else None
    return out


class ImmichGoImporter:
    def __init__(self, cfg: ImporterConfig, server: str, api_key: str, log_dir: Path, popen=subprocess.Popen):
        self.cfg = cfg
        self.server = server
        self.api_key = api_key
        self.log_dir = log_dir
        self._popen = popen

    def run(self, export_id: str, paths: list[str]) -> ImportResult:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        log_file = self.log_dir / f"immich-go-{export_id}-{ts}.log"
        args = build_args(self.cfg, self.server, self.api_key, paths, log_file)
        log.info("Running: %s", " ".join(redact(args)))
        tail: deque[str] = deque(maxlen=200)
        with self._popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) as proc:
            assert proc.stdout is not None
            for line in proc.stdout:
                tail.append(line.rstrip("\n"))
                log.debug("immich-go: %s", line.rstrip())
            code = proc.wait()
        text = "\n".join(tail)
        counts = parse_counts(text)
        return ImportResult(exit_code=code, log_path=str(log_file), output_tail=text[-4000:], **counts)

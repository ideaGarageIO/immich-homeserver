"""Always-on notifier: logs every event and keeps a one-line status file."""

from __future__ import annotations

import logging

from takeout2immich.config.models import LogNotifierConfig
from takeout2immich.domain import Event

log = logging.getLogger("takeout2immich.events")


class LogNotifier:
    name = "log"

    def __init__(self, cfg: LogNotifierConfig):
        self.cfg = cfg

    def send(self, event: Event) -> None:
        prefix = f"[{event.export_id}] " if event.export_id else ""
        line = f"{event.at.isoformat(timespec='seconds')} {event.type.value} {prefix}{event.message}"
        log.info("%s", line)
        self.cfg.status_file.parent.mkdir(parents=True, exist_ok=True)
        self.cfg.status_file.write_text(line + "\n")

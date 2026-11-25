"""Home Assistant notifier: POST /api/services/notify/<service> with a long-lived access token."""

from __future__ import annotations

import httpx

from takeout2immich.config.models import HomeAssistantNotifierConfig
from takeout2immich.config.store import read_secret
from takeout2immich.domain import Event

TITLES = {
    "EXPORT_DETECTED": "Takeout export detected",
    "DOWNLOAD_COMPLETE": "Takeout download complete",
    "IMPORT_COMPLETE": "Immich import complete",
    "VALIDATION_PASSED": "Validation passed",
    "VALIDATION_FAILED": "Validation FAILED",
    "CLEANUP_DONE": "Cleanup done",
    "ERROR": "takeout2immich error",
    "ACTION_REQUIRED": "Action required",
}


class HomeAssistantNotifier:
    name = "homeassistant"

    def __init__(self, cfg: HomeAssistantNotifierConfig, transport=None):
        self.cfg = cfg
        self._transport = transport

    def _endpoint(self) -> str:
        service = self.cfg.service.removeprefix("notify.")
        return f"{self.cfg.url.rstrip('/')}/api/services/notify/{service}"

    def send(self, event: Event) -> None:
        token = read_secret(self.cfg.token_file)
        message = event.message if not event.export_id else f"[{event.export_id}] {event.message}"
        with httpx.Client(timeout=15, transport=self._transport) as c:
            r = c.post(
                self._endpoint(),
                headers={"Authorization": f"Bearer {token}"},
                json={"title": TITLES.get(event.type.value, event.type.value), "message": message},
            )
            r.raise_for_status()

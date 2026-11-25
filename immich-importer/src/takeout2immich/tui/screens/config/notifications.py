from __future__ import annotations

from takeout2immich.config.models import EVENT_TYPES, data_dir
from takeout2immich.doctor import check_notifications
from takeout2immich.tui.screens.config.base import ConfigSectionScreen, Field

# The form edits one Home Assistant notifier stored as notifications[*] with type=homeassistant.
# These pseudo keys live under "_ha" only while the form is being read.
FIELDS = [
    Field("_ha.enabled", "Send notifications to Home Assistant", kind="bool"),
    Field("_ha.url", "Home Assistant URL", help="e.g. http://homeassistant.local:8123"),
    Field("_ha.service", "Notify service", help="e.g. mobile_app_pixel (from notify.mobile_app_pixel)"),
    Field("_ha.token", "Long-lived access token", kind="secret", secret_path_key="_ha.token_file",
          help="HA: Profile → Security → Long-lived access tokens."),
    Field("_ha.token_file", "Token file"),
    Field("_ha.events", "Events (comma-separated, empty = all)", kind="list",
          help=", ".join(EVENT_TYPES)),
]


def _ha(data: dict) -> dict | None:
    return next((n for n in data.get("notifications", []) if n.get("type") == "homeassistant"), None)


class NotificationsScreen(ConfigSectionScreen):
    MODE = "notifications"
    TITLE_TEXT = "Notifications"
    INTRO = "Events are always logged and written to the status file. Optionally also send them to Home Assistant."
    HAS_TEST = True

    def fields(self, data):
        ha = _ha(data)
        data["_ha"] = {
            "enabled": ha is not None,
            "url": (ha or {}).get("url", ""),
            "service": (ha or {}).get("service", ""),
            "token_file": (ha or {}).get("token_file", str(data_dir() / "secrets" / "homeassistant_token")),
            "events": (ha or {}).get("events") or [],
        }
        return FIELDS

    def collect(self, data):
        keep = [n for n in data.get("notifications", []) if n.get("type") != "homeassistant"]
        if not any(n.get("type") == "log" for n in keep):
            keep.insert(0, {"type": "log"})
        values = {f.key.split(".", 1)[1]: self.read_value(f) for f in FIELDS if f.kind != "secret"}
        if values["enabled"]:
            if not values["url"] or not values["service"]:
                raise ValueError("Home Assistant URL and notify service are required when enabled")
            keep.append(
                {
                    "type": "homeassistant",
                    "url": values["url"],
                    "service": values["service"],
                    "token_file": values["token_file"],
                    "events": values["events"] or None,
                }
            )
        data["notifications"] = keep
        data.pop("_ha", None)
        return data

    def build(self):
        cfg, _ = super().build()
        secrets = {}
        token = self.read_value(next(f for f in FIELDS if f.kind == "secret"))
        if token:
            from pathlib import Path

            secrets[Path(self.read_value(next(f for f in FIELDS if f.key == "_ha.token_file")))] = token
        return cfg, secrets

    def checks(self, config):
        return check_notifications(config, send_test=True)

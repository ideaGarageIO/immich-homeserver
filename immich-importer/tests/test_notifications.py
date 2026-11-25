import json

import httpx
import respx

from takeout2immich.config.models import HomeAssistantNotifierConfig, LogNotifierConfig
from takeout2immich.config.store import write_secret
from takeout2immich.domain import Event, EventType
from takeout2immich.notifications import build_dispatcher
from takeout2immich.notifications.base import Dispatcher
from takeout2immich.notifications.homeassistant import HomeAssistantNotifier


def _ha_cfg(tmp_path, **kw):
    write_secret(tmp_path / "ha_token", "TOKEN123")
    return HomeAssistantNotifierConfig(url="http://ha.test:8123/", service="notify.mobile_app_x",
                                       token_file=tmp_path / "ha_token", **kw)


@respx.mock
def test_home_assistant_payload(tmp_path):
    route = respx.post("http://ha.test:8123/api/services/notify/mobile_app_x").mock(return_value=httpx.Response(200))
    HomeAssistantNotifier(_ha_cfg(tmp_path)).send(
        Event(type=EventType.VALIDATION_FAILED, message="2 missing", export_id="takeout-1")
    )
    req = route.calls.last.request
    assert req.headers["Authorization"] == "Bearer TOKEN123"
    body = json.loads(req.content)
    assert body == {"title": "Validation FAILED", "message": "[takeout-1] 2 missing"}


@respx.mock
def test_dispatcher_filters_events_and_survives_failures(tmp_path):
    route = respx.post("http://ha.test:8123/api/services/notify/mobile_app_x").mock(return_value=httpx.Response(500))
    status = tmp_path / "status"
    d = build_dispatcher([
        LogNotifierConfig(status_file=status),
        _ha_cfg(tmp_path, events=["ERROR"]),
    ])
    d.send(Event(type=EventType.IMPORT_COMPLETE, message="ok"))
    assert route.call_count == 0  # filtered out
    d.send(Event(type=EventType.ERROR, message="boom"))  # HA returns 500 -> logged, not raised
    assert route.call_count == 1
    assert "ERROR boom" in status.read_text()


def test_dispatcher_with_no_filter_sends_everything():
    got = []

    class N:
        name = "n"

        def send(self, e):
            got.append(e.type)

    d = Dispatcher([(N(), None)])
    for t in EventType:
        d.send(Event(type=t, message="x"))
    assert got == list(EventType)

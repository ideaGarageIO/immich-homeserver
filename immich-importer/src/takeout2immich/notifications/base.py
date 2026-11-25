"""Notifier interface and a dispatcher that applies per-notifier event filters."""

from __future__ import annotations

import logging
from typing import Protocol

from takeout2immich.domain import Event

log = logging.getLogger(__name__)


class Notifier(Protocol):
    name: str

    def send(self, event: Event) -> None: ...


class Dispatcher:
    def __init__(self, entries: list[tuple[Notifier, set[str] | None]]):
        self.entries = entries

    def send(self, event: Event) -> None:
        for notifier, events in self.entries:
            if events is not None and event.type.value not in events:
                continue
            try:
                notifier.send(event)
            except Exception as exc:  # a broken notifier must never stop the pipeline
                log.warning("Notifier %s failed: %s", notifier.name, exc)


def build_notifier(cfg) -> Notifier:
    from takeout2immich.config.models import HomeAssistantNotifierConfig, LogNotifierConfig

    if isinstance(cfg, HomeAssistantNotifierConfig):
        from takeout2immich.notifications.homeassistant import HomeAssistantNotifier

        return HomeAssistantNotifier(cfg)
    if isinstance(cfg, LogNotifierConfig):
        from takeout2immich.notifications.log import LogNotifier

        return LogNotifier(cfg)
    raise ValueError(f"Unknown notifier config: {cfg!r}")


def build_dispatcher(configs) -> Dispatcher:
    return Dispatcher(
        [(build_notifier(c), set(c.events) if c.events is not None else None) for c in configs]
    )

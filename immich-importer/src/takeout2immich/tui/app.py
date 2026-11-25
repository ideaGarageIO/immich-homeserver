"""Textual app: a sidebar with Status plus one screen per config section."""

from __future__ import annotations

from pathlib import Path

from textual.app import App

from takeout2immich.config.models import AppConfig
from takeout2immich.config.store import load_config, save_config
from takeout2immich.tui.screens.config.cleanup import CleanupScreen
from takeout2immich.tui.screens.config.immich import ImmichScreen
from takeout2immich.tui.screens.config.importer import ImporterScreen
from takeout2immich.tui.screens.config.notifications import NotificationsScreen
from takeout2immich.tui.screens.config.source import SourceScreen
from takeout2immich.tui.screens.config.staging import StagingScreen
from takeout2immich.tui.screens.config.validation import ValidationScreen
from takeout2immich.tui.screens.status import StatusScreen

# (mode name, sidebar label, screen class) - order is the sidebar order.
NAV = [
    ("status", "Status", StatusScreen),
    ("immich", "Immich", ImmichScreen),
    ("source", "Source", SourceScreen),
    ("staging", "Staging", StagingScreen),
    ("importer", "Importer", ImporterScreen),
    ("validation", "Validation", ValidationScreen),
    ("cleanup", "Cleanup", CleanupScreen),
    ("notifications", "Notifications", NotificationsScreen),
]


class ImporterApp(App):
    TITLE = "takeout2immich"
    CSS = """
    #nav { width: 22; border-right: solid $primary-darken-2; }
    #body { padding: 1 2; }
    .field-label { margin-top: 1; color: $text-muted; }
    .help { color: $text-muted; text-style: italic; }
    .row { height: auto; margin-top: 1; }
    .row Button { margin-right: 2; }
    #message { margin-top: 1; height: auto; }
    .ok { color: $success; }
    .fail { color: $error; }
    #actions Button { margin: 0 1 1 0; }
    """
    BINDINGS = [("q", "quit", "Quit")]
    MODES = {name: cls for name, _, cls in NAV}

    def __init__(self, config_path: Path):
        super().__init__()
        self.config_path = config_path
        self.config_exists = config_path.exists()
        self.config: AppConfig = load_config(config_path) if self.config_exists else AppConfig()
        self.sub_title = str(config_path)

    def on_mount(self) -> None:
        self.switch_mode("status" if self.config_exists else "immich")

    def save(self, config: AppConfig) -> None:
        save_config(config, self.config_path)
        self.config = config
        self.config_exists = True

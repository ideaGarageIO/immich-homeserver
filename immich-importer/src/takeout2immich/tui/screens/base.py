"""Base screen: header, sidebar navigation, body, footer."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, ListItem, ListView, Label


class BaseScreen(Screen):
    MODE: str = ""

    def compose(self) -> ComposeResult:
        from takeout2immich.tui.app import NAV

        yield Header()
        with Horizontal():
            items = [ListItem(Label(label), id=f"nav-{name}") for name, label, _ in NAV]
            index = next((i for i, (n, _, _) in enumerate(NAV) if n == self.MODE), 0)
            yield ListView(*items, id="nav", initial_index=index)
            with VerticalScroll(id="body"):
                yield from self.compose_body()
        yield Footer()

    def compose_body(self) -> ComposeResult:  # pragma: no cover - overridden
        yield from ()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.id != "nav" or event.item.id is None:
            return
        mode = event.item.id.removeprefix("nav-")
        if mode != self.MODE:
            self.app.switch_mode(mode)

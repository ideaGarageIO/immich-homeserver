"""Validation report viewer (opened from the Status screen)."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Footer, Static


class ReportScreen(ModalScreen):
    BINDINGS = [("escape", "dismiss", "Close"), ("q", "dismiss", "Close")]

    def __init__(self, report_json_path: str):
        super().__init__()
        self.path = Path(report_json_path)

    def compose(self) -> ComposeResult:
        txt = self.path.with_suffix(".txt")
        try:
            body = txt.read_text() if txt.exists() else self.path.read_text()
        except OSError as exc:
            body = f"Could not read report: {exc}"
        with VerticalScroll():
            yield Static(f"[b]{self.path.name}[/b]\n")
            yield Static(body, markup=False)
        yield Footer()

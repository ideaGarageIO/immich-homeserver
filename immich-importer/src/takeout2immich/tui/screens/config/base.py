"""Shared form machinery for config section screens.

A section screen declares FIELDS; the base renders them, loads values from the current config,
validates the edited config with pydantic on Save, writes secrets to their files (0600), and
runs the section's checks on Test.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, Input, Label, Select, Static, Switch

from takeout2immich.config.models import AppConfig
from takeout2immich.config.store import write_secret
from takeout2immich.tui.screens.base import BaseScreen


@dataclass
class Field:
    key: str  # dotted path into the config dict, e.g. "immich.url"
    label: str
    kind: str = "text"  # text | int | bool | select | secret | list
    options: list[str] = field(default_factory=list)
    help: str = ""
    secret_path_key: str | None = None  # for kind=secret: config key holding the file path

    @property
    def wid(self) -> str:
        return "f-" + self.key.replace(".", "__")


def get_path(d: dict, key: str) -> Any:
    for part in key.split("."):
        if not isinstance(d, dict) or part not in d:
            return None
        d = d[part]
    return d


def set_path(d: dict, key: str, value: Any) -> None:
    parts = key.split(".")
    for part in parts[:-1]:
        d = d.setdefault(part, {})
    d[parts[-1]] = value


class ConfigSectionScreen(BaseScreen):
    TITLE_TEXT = ""
    INTRO = ""
    FIELDS: list[Field] = []
    HAS_TEST = False

    # ---------------------------------------------------------------- compose
    def compose_body(self) -> ComposeResult:
        yield Static(f"[b]{self.TITLE_TEXT}[/b]")
        if self.INTRO:
            yield Static(self.INTRO, classes="help")
        # Buttons and messages sit above the fields so they stay reachable on long forms.
        with Horizontal(classes="row"):
            yield Button("Save", id="save", variant="primary")
            if self.HAS_TEST:
                yield Button("Test", id="test")
        yield Static("", id="message")
        data = self.app.config.model_dump(mode="json")
        for f in self.fields(data):
            yield Label(f.label, classes="field-label")
            yield self._widget(f, data)
            if f.help:
                yield Static(f.help, classes="help")

    def fields(self, data: dict) -> list[Field]:
        return self.FIELDS

    def _widget(self, f: Field, data: dict):
        value = get_path(data, f.key)
        if f.kind == "bool":
            return Switch(value=bool(value), id=f.wid)
        if f.kind == "select":
            return Select([(o, o) for o in f.options], value=value if value in f.options else f.options[0],
                          allow_blank=False, id=f.wid)
        if f.kind == "secret":
            path = Path(get_path(data, f.secret_path_key)) if f.secret_path_key else None
            placeholder = "(saved - leave empty to keep)" if path and path.exists() else "(not set)"
            return Input(password=True, placeholder=placeholder, id=f.wid)
        if f.kind == "list":
            return Input(value=", ".join(value or []), id=f.wid)
        if f.kind == "int":
            return Input(value="" if value is None else str(value), type="integer", id=f.wid)
        return Input(value="" if value is None else str(value), id=f.wid)

    # ---------------------------------------------------------------- collect / save
    def read_value(self, f: Field) -> Any:
        w = self.query_one(f"#{f.wid}")
        if f.kind == "bool":
            return w.value
        if f.kind == "select":
            return w.value
        if f.kind == "list":
            return [x.strip() for x in w.value.split(",") if x.strip()]
        if f.kind == "int":
            return int(w.value) if w.value.strip() else None
        return w.value.strip()

    def collect(self, data: dict) -> dict:
        """Apply form values onto a copy of the config dict. Override for structural sections."""
        for f in self.fields(data):
            if f.kind != "secret":
                set_path(data, f.key, self.read_value(f))
        return data

    def build(self) -> tuple[AppConfig, dict[Path, str]]:
        data = self.collect(copy.deepcopy(self.app.config.model_dump(mode="json")))
        cfg = AppConfig.model_validate(data)
        secrets: dict[Path, str] = {}
        cfg_data = cfg.model_dump(mode="json")
        for f in self.fields(cfg_data):
            if f.kind == "secret" and f.secret_path_key:
                v = self.read_value(f)
                if v:
                    secrets[Path(get_path(cfg_data, f.secret_path_key))] = v
        return cfg, secrets

    def message(self, text: str, ok: bool | None = None) -> None:
        cls = "" if ok is None else ("ok" if ok else "fail")
        msg = self.query_one("#message", Static)
        msg.set_classes(cls)
        msg.update(text)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save":
            self.do_save()
        elif event.button.id == "test":
            self.do_test()

    def do_save(self) -> bool:
        try:
            cfg, secrets = self.build()
        except ValidationError as exc:
            errs = "\n".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
            self.message(f"Not saved - fix these:\n{errs}", ok=False)
            return False
        except ValueError as exc:
            self.message(f"Not saved: {exc}", ok=False)
            return False
        for path, value in secrets.items():
            write_secret(path, value)
        self.app.save(cfg)
        for f in self.fields(cfg.model_dump(mode="json")):
            if f.kind == "secret":
                self.query_one(f"#{f.wid}", Input).value = ""
        self.message(f"Saved to {self.app.config_path}", ok=True)
        return True

    # ---------------------------------------------------------------- test
    def checks(self, config: AppConfig) -> list:
        return []

    def do_test(self) -> None:
        if not self.do_save():
            return
        self.message("Testing...")
        self._run_checks(self.app.config)

    @work(thread=True, exclusive=True)
    def _run_checks(self, config: AppConfig) -> None:
        results = self.checks(config)
        lines = [f"{'OK  ' if c.ok else 'FAIL'} {c.name}: {c.detail}" for c in results]
        ok = all(c.ok for c in results)
        self.app.call_from_thread(self.message, "\n".join(lines) or "No checks.", ok)

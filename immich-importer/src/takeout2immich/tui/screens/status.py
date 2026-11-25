"""Status: export sets, per-part progress, last validation result, recommended actions."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, DataTable, Static

from takeout2immich.actions import recommend
from takeout2immich.domain import ExportSet, Stage
from takeout2immich.state import StateStore
from takeout2immich.tui.screens.base import BaseScreen
from takeout2immich.util import human_size

# Action keys that translate into a request for the worker.
REQUESTS = {
    "confirm": ("confirm", {}),
    "revalidate": ("revalidate", {}),
    "reimport": ("reimport", {}),
    "cleanup": ("cleanup", {}),
    "force_cleanup": ("cleanup", {"force": True}),
    "retry": ("retry", {}),
}


class StatusScreen(BaseScreen):
    MODE = "status"

    def compose_body(self) -> ComposeResult:
        yield Static("[b]Status[/b]")
        yield DataTable(id="sets", cursor_type="row", zebra_stripes=True)
        yield Static("", id="detail")
        yield Static("[b]Recommended[/b]", classes="field-label")
        yield Horizontal(id="actions", classes="row")
        yield Static("", id="message")

    def on_mount(self) -> None:
        table = self.query_one("#sets", DataTable)
        table.add_columns("Export", "Stage", "Parts", "Size", "Updated")
        self._selected: str | None = None
        self._action_sig: tuple = ()
        self.refresh_data()
        self.set_interval(3, self.refresh_data)

    def _store(self) -> StateStore | None:
        if not self.app.config_exists:
            return None
        return StateStore(self.app.config.runtime.state_db)

    def refresh_data(self) -> None:
        store = self._store()
        table = self.query_one("#sets", DataTable)
        detail = self.query_one("#detail", Static)
        if store is None:
            detail.update("Not configured yet. Fill in Immich, Source and Staging (sidebar), then Save.")
            self._set_actions([])
            return
        sets = store.list()
        table.clear()
        for es in sets:
            table.add_row(
                es.id,
                es.stage.value,
                f"{es.downloaded_count}/{len(es.parts)}",
                human_size(es.total_size),
                es.updated_at.strftime("%Y-%m-%d %H:%M"),
                key=es.id,
            )
        if self._selected not in {s.id for s in sets}:
            active = [s for s in sets if s.stage != Stage.DONE]
            self._selected = (active or sets)[-1].id if sets else None
        es = next((s for s in sets if s.id == self._selected), None)
        detail.update(self._detail(es))
        self._set_actions(recommend(es, self.app.config.source.type), es)

    def _detail(self, es: ExportSet | None) -> str:
        if es is None:
            return "No export sets yet."
        lines = [f"[b]{es.id}[/b] - {es.stage.value}"]
        for p in es.sorted_parts():
            err = f"  ({p.error})" if p.error else ""
            lines.append(f"  {p.name}  {human_size(p.size)}  {p.state.value}{err}")
        if es.import_result:
            r = es.import_result
            lines.append(f"Import: exit {r.exit_code}, uploaded {r.uploaded}, duplicates {r.duplicates}, errors {r.errors}")
        if es.validation_summary:
            lines.append(f"Validation: {es.validation_summary}")
        if es.error:
            lines.append(f"[red]Error: {es.error}[/red]")
        return "\n".join(lines)

    def _set_actions(self, actions, es: ExportSet | None = None) -> None:
        sig = tuple(a.key for a in actions) + ((es.id,) if es else ())
        if sig == self._action_sig:
            return
        self._action_sig = sig
        box = self.query_one("#actions", Horizontal)
        box.remove_children()
        for a in actions:
            if a.key in REQUESTS or (a.key == "view_report" and es and es.report_path):
                box.mount(Button(a.label, id=f"act-{a.key}", variant="primary" if a.key == "confirm" else "default"))
            else:
                box.mount(Static(f"• {a.label}" + (f"  ({a.command})" if a.command else "")))

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self._selected = event.row_key.value
        self.refresh_data()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        key = (event.button.id or "").removeprefix("act-")
        store = self._store()
        if not store or not self._selected:
            return
        if key == "view_report":
            from takeout2immich.tui.screens.report import ReportScreen

            es = store.get(self._selected)
            if es and es.report_path:
                self.app.push_screen(ReportScreen(es.report_path))
            return
        if key in REQUESTS:
            action, payload = REQUESTS[key]
            store.add_request(action, self._selected, **payload)
            self.query_one("#message", Static).update(
                f"Queued '{action}' for {self._selected}; the worker applies it within a few seconds."
            )

# Architecture

## Package layout

```
src/takeout2immich/
├── cli.py                 Typer CLI (takeout2immich / t2i)
├── config/
│   ├── models.py          pydantic AppConfig; source is a union discriminated on `type`
│   └── store.py           load/save config.yaml; secret files (0600)
├── domain.py              ExportSet, ExportPart, Stage, ImportResult, ValidationReport, Event
├── state.py               SQLite: export sets + request queue; worker file lock
├── pipeline.py            the stage machine
├── actions.py             stage → recommended next action (CLI status, TUI, notifications)
├── runtime.py             builds a Pipeline from a config
├── doctor.py              health checks (CLI `doctor`, TUI Test buttons)
├── immich.py              minimal Immich REST client
├── sources/               Source protocol + drive / local / direct(placeholder)
├── importer/immich_go.py  runs immich-go for a whole export set
├── validation/            zip inventory (SHA-1, trashed flags) + Immich audit
├── cleanup.py             deletes staged zips + remote copy, only when VALIDATED
├── notifications/         Notifier protocol, dispatcher with event filters, homeassistant, log
└── tui/
    ├── app.py             Textual app, sidebar navigation (modes)
    └── screens/
        ├── base.py        shared layout
        ├── status.py      export sets, part progress, action buttons
        ├── report.py      validation report viewer
        └── config/        one screen per config section (+ base.py form machinery)
```

## Stage machine

```
DISCOVERED → DOWNLOADING ──(confirm)──→ CONFIRMED → DOWNLOADED → IMPORTING → IMPORTED
   → VALIDATING → VALIDATED → CLEANED → DONE
                ↘ VALIDATION_FAILED   (stops; nothing deleted)
any stage ↘ FAILED after runtime.max_attempts consecutive errors (`t2i retry`)
```

- Parts are downloaded as soon as the source shows them; the import waits for `CONFIRMED`
  because a JSON sidecar may sit in a different part than its photo.
- Every stage is idempotent. After a crash the worker simply continues: `IMPORTING` re-runs the
  import (immich-go skips what Immich already has), `VALIDATING` re-runs validation.
- The retry counter only resets when a stage actually changes.
- Cleanup refuses to run unless the export is `VALIDATED` (or `--force`), and never deletes
  files outside `staging.path`.

## Concurrency

Exactly one worker runs at a time (an `flock` next to the state DB). Front-ends — `t2i confirm`,
`t2i retry`, the TUI's action buttons — never modify an export set directly; they enqueue a
**request** in SQLite. The worker applies requests at the start of each pass, and the `watch`
loop polls the queue every 5 s so it reacts quickly.

## Interfaces

```python
class Source(Protocol):
    type: str
    def discover(self) -> list[ExportSet]: ...
    def fetch(self, part: ExportPart, dest_dir: Path) -> Path: ...
    def verify(self, part: ExportPart, path: Path) -> bool: ...
    def delete_remote(self, export_set: ExportSet) -> int: ...
    def check(self) -> tuple[bool, str]: ...

class Notifier(Protocol):
    name: str
    def send(self, event: Event) -> None: ...
```

Adding a source: implement `Source`, add a config model to the `SourceConfig` union in
`config/models.py`, register it in `sources/base.py:build_source`, and add a TUI field list in
`tui/screens/config/source.py`.

## Testing

`pytest` covers config, sources (rclone is faked), validation (Immich is mocked with respx),
the pipeline (resume from every stage, retries, failure paths), cleanup safety, notifications,
the CLI and the TUI (Textual's pilot). `tests/fixtures/make_takeout.py` builds realistic Takeout
zips with real JPEGs, which `compose.dev.yml` also uses for an end-to-end run against a real
Immich.

"""Command-line interface (installed as `takeout2immich` and `t2i`)."""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path
from typing import Annotated, Optional

import typer

from takeout2immich import __version__
from takeout2immich.actions import recommend
from takeout2immich.config import ConfigNotFoundError, default_config_path, load_config
from takeout2immich.domain import Stage, now
from takeout2immich.state import StateStore, WorkerBusyError
from takeout2immich.util import human_size

app = typer.Typer(
    help="Move a Google Photos Takeout export into Immich: download, verify, import, validate, clean up.",
    no_args_is_help=True,
    add_completion=False,
)
log = logging.getLogger("takeout2immich")

ConfigOpt = Annotated[
    Optional[Path],
    typer.Option("--config", "-c", help="Path to config.yaml (default: $TAKEOUT2IMMICH_CONFIG or /data/importer/config.yaml)"),
]


def _load(config_path: Path | None):
    from takeout2immich.runtime import setup_logging

    try:
        cfg = load_config(config_path)
    except ConfigNotFoundError as exc:
        typer.secho(str(exc), fg="red", err=True)
        raise typer.Exit(2) from exc
    setup_logging(cfg.runtime.log_level)
    return cfg


def _pipeline(config_path: Path | None):
    from takeout2immich.runtime import build_pipeline

    return build_pipeline(_load(config_path))


@app.command()
def version() -> None:
    """Print the version."""
    typer.echo(__version__)


@app.command()
def config(config_path: ConfigOpt = None) -> None:
    """Open the TUI: edit configuration and watch progress."""
    from takeout2immich.tui.app import ImporterApp

    ImporterApp(config_path or default_config_path()).run()


@app.command()
def doctor(
    config_path: ConfigOpt = None,
    send_test: Annotated[bool, typer.Option("--send-test", help="Also send a test notification")] = False,
) -> None:
    """Check configuration, Immich, the source, tools and notifications."""
    from takeout2immich.doctor import run_all

    cfg = _load(config_path)
    checks = run_all(cfg, send_test=send_test)
    for c in checks:
        mark = typer.style("OK  ", fg="green") if c.ok else typer.style("FAIL", fg="red")
        typer.echo(f"{mark} {c.name}: {c.detail}")
    raise typer.Exit(0 if all(c.ok for c in checks) else 1)


@app.command()
def run(
    config_path: ConfigOpt = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Only list what the source sees")] = False,
) -> None:
    """Run one pass of the pipeline."""
    p = _pipeline(config_path)
    if dry_run:
        for es in p.source.discover():
            typer.echo(f"{es.id}: {len(es.parts)} part(s), {human_size(es.total_size)}")
            for part in es.sorted_parts():
                typer.echo(f"  {part.name}  {human_size(part.size)}  md5={part.md5 or '-'}")
        return
    try:
        with p.store.worker_lock():
            p.tick()
    except WorkerBusyError as exc:
        typer.secho(str(exc), fg="yellow", err=True)
        raise typer.Exit(3) from exc
    _print_status(p.store, p.config.source.type)


@app.command()
def watch(config_path: ConfigOpt = None) -> None:
    """Run the pipeline forever (the container's default command)."""
    from takeout2immich.runtime import build_pipeline, setup_logging

    from takeout2immich.config.models import data_dir

    path = config_path or default_config_path()
    setup_logging()
    hb_ref = [data_dir() / "state" / "heartbeat"]
    _start_heartbeat(hb_ref)
    while True:
        try:
            cfg = load_config(path)
        except ConfigNotFoundError:
            log.warning("Not configured yet (%s). Run `takeout2immich config`. Waiting...", path)
            time.sleep(30)
            continue
        except Exception as exc:
            log.error("Config error: %s. Fix it with `takeout2immich config`. Waiting...", exc)
            time.sleep(30)
            continue
        logging.getLogger().setLevel(cfg.runtime.log_level)
        hb_ref[0] = cfg.runtime.heartbeat_file
        p = build_pipeline(cfg)
        try:
            with p.store.worker_lock():
                p.tick()
        except WorkerBusyError as exc:
            log.warning("%s", exc)
        except Exception:
            log.exception("Tick failed")
        # Wake early if someone queued a request (e.g. confirm from the TUI).
        deadline = time.monotonic() + cfg.runtime.poll_interval_s
        while time.monotonic() < deadline:
            time.sleep(5)
            if p.store.pending_requests():
                break


@app.command()
def health(config_path: ConfigOpt = None, max_age: int = 180) -> None:
    """Container healthcheck: exits 0 if the watch process is alive (heartbeat is fresh)."""
    try:
        hb = load_config(config_path).runtime.heartbeat_file
    except Exception:
        from takeout2immich.config.models import data_dir

        hb = data_dir() / "state" / "heartbeat"
    if not hb.exists():
        raise typer.Exit(0)  # just started
    raise typer.Exit(0 if time.time() - hb.stat().st_mtime < max_age else 1)


def _start_heartbeat(path_ref: list) -> None:
    """Touch the heartbeat file every 30 s from a daemon thread, so long imports stay healthy."""
    import threading

    def beat():
        while True:
            hb = path_ref[0]
            try:
                hb.parent.mkdir(parents=True, exist_ok=True)
                hb.write_text(now().isoformat())
            except OSError:
                pass
            time.sleep(30)

    threading.Thread(target=beat, daemon=True, name="heartbeat").start()


def _print_status(store: StateStore, source_type: str, as_json: bool = False) -> None:
    sets = store.list()
    if as_json:
        typer.echo(json.dumps([json.loads(s.model_dump_json()) for s in sets], indent=2))
        return
    if not sets:
        typer.echo("No export sets yet.")
    for es in sets:
        typer.echo(
            f"{es.id}  {es.stage.value:<18} parts {es.downloaded_count}/{len(es.parts)}  "
            f"{human_size(es.total_size)}"
        )
        if es.error:
            typer.secho(f"  error: {es.error}", fg="red")
        if es.validation_summary:
            typer.echo(f"  validation: {es.validation_summary}")
        if es.report_path:
            typer.echo(f"  report: {es.report_path}")
    active = [s for s in sets if s.stage != Stage.DONE]
    target = active[-1] if active else (sets[-1] if sets else None)
    typer.echo("\nNext:")
    for a in recommend(target, source_type):
        typer.echo(f"  - {a.label}" + (f"\n      $ {a.command}" if a.command else ""))


@app.command()
def status(
    config_path: ConfigOpt = None,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Show export sets, their stage and the recommended next action."""
    cfg = _load(config_path)
    _print_status(StateStore(cfg.runtime.state_db), cfg.source.type, as_json)


@app.command()
def confirm(export_id: Annotated[Optional[str], typer.Argument()] = None, config_path: ConfigOpt = None) -> None:
    """Tell the worker the export is complete (after Google's 'export ready' email)."""
    p = _pipeline(config_path)
    try:
        eid = p.request_confirm(export_id)
    except LookupError as exc:
        typer.secho(str(exc), fg="red", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"Confirmed {eid}. The worker will finish downloading, then import.")


def _with_set(config_path, export_id, fn):
    p = _pipeline(config_path)
    try:
        with p.store.worker_lock():
            es = p.store.get(export_id)
            if not es:
                typer.secho(f"No export set {export_id!r}", fg="red", err=True)
                raise typer.Exit(1)
            fn(p, es)
    except WorkerBusyError:
        return None, p
    return es, p


@app.command()
def validate(export_id: str, config_path: ConfigOpt = None) -> None:
    """Re-run validation for an export set (does not clean up)."""

    def go(p, es):
        if es.stage not in (Stage.IMPORTED, Stage.VALIDATED, Stage.VALIDATION_FAILED, Stage.VALIDATING):
            typer.secho(f"{es.id} is {es.stage.value}; nothing imported to validate yet.", fg="red", err=True)
            raise typer.Exit(1)
        p.validate(es)
        typer.echo(f"{es.stage.value}: {es.validation_summary}\nreport: {es.report_path}")

    es, p = _with_set(config_path, export_id, go)
    if es is None:  # daemon running: queue it instead
        p.store.add_request("revalidate", export_id)
        typer.echo("Worker is running; validation queued.")


@app.command()
def cleanup(
    export_id: str,
    config_path: ConfigOpt = None,
    force: Annotated[bool, typer.Option("--force", help="Clean up even though validation did not pass")] = False,
) -> None:
    """Delete local and remote archives of a validated export set."""
    from takeout2immich.cleanup import CleanupRefused

    def go(p, es):
        try:
            for line in p.run_cleanup(es, force=force):
                typer.echo(line)
        except CleanupRefused as exc:
            typer.secho(str(exc), fg="red", err=True)
            raise typer.Exit(1) from exc

    es, p = _with_set(config_path, export_id, go)
    if es is None:
        p.store.add_request("cleanup", export_id, force=force)
        typer.echo("Worker is running; cleanup queued.")


@app.command()
def reimport(export_id: str, config_path: ConfigOpt = None) -> None:
    """Re-run the import for an export whose archives are still on disk, then validate again."""
    cfg = _load(config_path)
    StateStore(cfg.runtime.state_db).add_request("reimport", export_id)
    typer.echo("Re-import queued; the worker picks it up on its next pass (or run `takeout2immich run`).")


@app.command()
def retry(export_id: str, config_path: ConfigOpt = None) -> None:
    """Retry a FAILED export set from the stage that failed."""
    cfg = _load(config_path)
    StateStore(cfg.runtime.state_db).add_request("retry", export_id)
    typer.echo("Retry queued; the worker picks it up on its next pass (or run `takeout2immich run`).")


def main() -> None:  # pragma: no cover
    app()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

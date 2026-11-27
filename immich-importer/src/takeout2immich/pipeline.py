"""The stage machine.

DISCOVERED → DOWNLOADING ─(confirm)→ CONFIRMED → DOWNLOADED → IMPORTING → IMPORTED
  → VALIDATING → VALIDATED → CLEANED → DONE
                ↘ VALIDATION_FAILED (stops; nothing deleted)
any stage ↘ FAILED after runtime.max_attempts consecutive errors (retry with `retry`)

Every step is idempotent, so a crash at any point is recovered by simply running again:
IMPORTING resumes as a fresh import (immich-go skips what the server already has) and
VALIDATING re-runs validation.
"""

from __future__ import annotations

import logging
import shutil
from collections.abc import Callable
from pathlib import Path

from takeout2immich import cleanup as cleanup_mod
from takeout2immich.config.models import AppConfig
from takeout2immich.domain import (
    DOWNLOAD_STAGES,
    TERMINAL_STAGES,
    Event,
    EventType,
    ExportSet,
    PartState,
    Stage,
    now,
)
from takeout2immich.state import StateStore

log = logging.getLogger(__name__)

# When a stage fails we resume from the stage that starts that work again.
_RESUME_FROM = {
    Stage.DISCOVERED: Stage.DOWNLOADING,
    Stage.DOWNLOADING: Stage.DOWNLOADING,
    Stage.CONFIRMED: Stage.CONFIRMED,
    Stage.DOWNLOADED: Stage.DOWNLOADED,
    Stage.IMPORTING: Stage.DOWNLOADED,
    Stage.IMPORTED: Stage.IMPORTED,
    Stage.VALIDATING: Stage.IMPORTED,
    Stage.VALIDATED: Stage.VALIDATED,
    Stage.CLEANED: Stage.CLEANED,
}


class StageError(RuntimeError):
    pass


class Pipeline:
    def __init__(
        self,
        config: AppConfig,
        store: StateStore,
        source,
        notifier,
        importer_factory: Callable[[], object],
        validator_factory: Callable[[], object],
    ):
        self.config = config
        self.store = store
        self.source = source
        self.notifier = notifier
        self._importer_factory = importer_factory
        self._validator_factory = validator_factory
        self._last_discover_error: str | None = None

    # ------------------------------------------------------------------ helpers
    def _notify(self, type_: EventType, message: str, es: ExportSet | None = None, **data) -> None:
        self.notifier.send(Event(type=type_, message=message, export_id=es.id if es else None, data=data))

    def _notify_once(self, es: ExportSet, key: str, type_: EventType, message: str) -> None:
        if key in es.notified:
            return
        es.notified.append(key)
        self._notify(type_, message, es)

    def _set_stage(self, es: ExportSet, stage: Stage) -> None:
        if es.stage != stage:
            log.info("%s: %s → %s", es.id, es.stage.value, stage.value)
            es.stage = stage
            # Only a real stage change resets the retry counter; re-entering the same stage
            # (e.g. IMPORTING after a crash) keeps counting toward max_attempts.
            es.attempts = 0
            es.error = None
        self.store.save(es)

    def _resolve(self, export_id: str | None, stages: set[Stage] | None = None) -> ExportSet:
        if export_id:
            es = self.store.get(export_id)
            if not es:
                raise LookupError(f"No export set {export_id!r}")
            return es
        candidates = [e for e in self.store.list() if stages is None or e.stage in stages]
        if len(candidates) != 1:
            ids = ", ".join(e.id for e in candidates) or "none"
            raise LookupError(f"Specify an export id (candidates: {ids})")
        return candidates[0]

    # ------------------------------------------------------------------ requests
    def request_confirm(self, export_id: str | None = None) -> str:
        es = self._resolve(export_id, {Stage.DISCOVERED, Stage.DOWNLOADING})
        self.store.add_request("confirm", es.id)
        return es.id

    def apply_requests(self) -> None:
        for req in self.store.pop_requests():
            es = self.store.get(req.export_id) if req.export_id else None
            if not es:
                log.warning("Ignoring %s request for unknown export %s", req.action, req.export_id)
                continue
            if req.action == "confirm" and es.stage in (Stage.DISCOVERED, Stage.DOWNLOADING):
                es.confirmed_at = now()
                self._set_stage(es, Stage.CONFIRMED)
            elif req.action == "revalidate" and es.stage in (
                Stage.IMPORTED,
                Stage.VALIDATED,
                Stage.VALIDATION_FAILED,
            ):
                self._set_stage(es, Stage.IMPORTED)
            elif req.action == "reimport" and es.stage in (
                Stage.IMPORTED,
                Stage.VALIDATED,
                Stage.VALIDATION_FAILED,
            ):
                if not all(Path(p).exists() for p in es.local_paths()):
                    log.warning("%s: cannot re-import, archives are no longer on disk", es.id)
                else:
                    self._set_stage(es, Stage.DOWNLOADED)
            elif req.action == "retry" and es.stage == Stage.FAILED:
                for part in es.parts.values():
                    if part.state != PartState.DOWNLOADED:
                        part.attempts, part.state, part.error = 0, PartState.PENDING, None
                self._set_stage(es, es.failed_stage or Stage.DOWNLOADING)
            elif req.action == "cleanup":
                self.run_cleanup(es, force=bool(req.payload.get("force")))
            else:
                log.warning("Request %s not applicable to %s in %s", req.action, es.id, es.stage.value)

    # ------------------------------------------------------------------ discovery
    def discover(self) -> list[ExportSet]:
        try:
            found = self.source.discover()
        except Exception as exc:
            msg = f"Could not list exports from {self.source.type}: {exc}"
            log.error(msg)
            if msg != self._last_discover_error:
                self._notify(EventType.ERROR, msg)
            self._last_discover_error = msg
            return []
        self._last_discover_error = None

        auto_confirm = getattr(self.config.source, "auto_confirm", False)
        for f in found:
            es = self.store.get(f.id)
            if es is None:
                es = f
                self.store.save(es)
                self._notify(
                    EventType.EXPORT_DETECTED,
                    f"{len(es.parts)} part(s) found so far; downloading as they appear.",
                    es,
                )
                if auto_confirm:
                    es.confirmed_at = now()
                    self._set_stage(es, Stage.CONFIRMED)
                else:
                    self._notify_once(
                        es,
                        "confirm",
                        EventType.ACTION_REQUIRED,
                        "When Google's 'export ready' email arrives, confirm the export is complete "
                        f"(takeout2immich confirm {es.id}).",
                    )
                    self.store.save(es)
            elif es.stage in DOWNLOAD_STAGES:
                new = [n for n in f.parts if n not in es.parts]
                for n in new:
                    es.parts[n] = f.parts[n]
                if new:
                    log.info("%s: %d new part(s)", es.id, len(new))
                    self.store.save(es)
        return found

    # ------------------------------------------------------------------ stages
    def _download(self, es: ExportSet) -> None:
        staging = self.config.staging.path
        min_free = self.config.staging.min_free_gb * 1024**3
        max_attempts = self.config.runtime.max_attempts
        # A part still marked DOWNLOADING was interrupted (container stopped mid-transfer);
        # only one worker runs at a time, so it is just pending again.
        for part in es.parts.values():
            if part.state == PartState.DOWNLOADING:
                part.state = PartState.PENDING
        for part in es.sorted_parts():
            if part.state == PartState.DOWNLOADED or part.attempts >= max_attempts:
                continue
            if self.source.type != "local":
                staging.mkdir(parents=True, exist_ok=True)
                free = shutil.disk_usage(staging).free
                if free - part.size < min_free:
                    raise StageError(
                        f"Not enough space in {staging} for {part.name}: "
                        f"{free / 1024**3:.1f} GB free, keeping {self.config.staging.min_free_gb} GB reserve"
                    )
            if es.stage == Stage.DISCOVERED:
                self._set_stage(es, Stage.DOWNLOADING)
            part.state = PartState.DOWNLOADING
            self.store.save(es)  # so `status` and the TUI show which part is in flight
            try:
                path = self.source.fetch(part, staging / es.id)
                ok = self.source.verify(part, path)
            except Exception as exc:
                part.attempts += 1
                part.state = PartState.FAILED
                part.error = str(exc)[-1000:]
                self.store.save(es)
                log.error("%s: download of %s failed: %s", es.id, part.name, exc)
                continue
            if ok:
                part.state, part.local_path, part.error = PartState.DOWNLOADED, str(path), None
                log.info("%s: %s verified (%d/%d)", es.id, part.name, es.downloaded_count, len(es.parts))
            else:
                part.attempts += 1
                part.state = PartState.FAILED
                part.error = "checksum/size mismatch"
                if self.source.type != "local":
                    Path(path).unlink(missing_ok=True)
            self.store.save(es)

        exhausted = [p.name for p in es.parts.values() if p.state != PartState.DOWNLOADED and p.attempts >= max_attempts]
        if exhausted:
            raise StageError(f"Giving up on {', '.join(exhausted)} after {max_attempts} attempts")
        if es.stage == Stage.CONFIRMED and es.all_downloaded:
            self._set_stage(es, Stage.DOWNLOADED)
            self._notify(
                EventType.DOWNLOAD_COMPLETE,
                f"All {len(es.parts)} part(s) downloaded and verified; starting import.",
                es,
            )

    def _import(self, es: ExportSet) -> None:
        self._set_stage(es, Stage.IMPORTING)
        result = self._importer_factory().run(es.id, es.local_paths())
        es.import_result = result
        self.store.save(es)
        if result.exit_code != 0:
            raise StageError(f"immich-go exited with {result.exit_code}; see {result.log_path}")
        self._set_stage(es, Stage.IMPORTED)
        counts = ", ".join(
            f"{k} {v}" for k, v in (("uploaded", result.uploaded), ("duplicates", result.duplicates), ("errors", result.errors)) if v is not None
        )
        self._notify(EventType.IMPORT_COMPLETE, f"Import finished ({counts or 'see log'}); validating.", es)

    def validate(self, es: ExportSet) -> None:
        if not self.config.validation.enabled:
            es.validation_summary = "skipped (validation disabled in config)"
            es.validation_passed = None
            self._set_stage(es, Stage.VALIDATED)
            return
        self._set_stage(es, Stage.VALIDATING)
        report = self._validator_factory().validate(es)
        es.validation_summary = report.summary()
        es.validation_passed = report.passed
        es.report_path = report.report_path
        if report.passed or not self.config.validation.fail_on_missing:
            self._set_stage(es, Stage.VALIDATED)
            self._notify(EventType.VALIDATION_PASSED, report.summary(), es)
        else:
            self._set_stage(es, Stage.VALIDATION_FAILED)
            self._notify(EventType.VALIDATION_FAILED, f"{report.summary()}. Nothing was deleted.", es)
            self._notify(
                EventType.ACTION_REQUIRED,
                f"Review the validation report ({report.report_path}).",
                es,
            )

    def run_cleanup(self, es: ExportSet, *, force: bool = False) -> list[str]:
        if force and es.stage != Stage.VALIDATED:
            log.warning("%s: forced cleanup from %s", es.id, es.stage.value)
        actions = cleanup_mod.cleanup(es, self.config, self.source, force=force)
        self._set_stage(es, Stage.CLEANED)
        self._notify(EventType.CLEANUP_DONE, "; ".join(actions) or "nothing to delete", es)
        self._finish(es)
        return actions

    def _finish(self, es: ExportSet) -> None:
        self._set_stage(es, Stage.DONE)
        if self.source.type == "drive":
            self._notify_once(
                es,
                "downgrade",
                EventType.ACTION_REQUIRED,
                "Migration of this export is complete. You can downgrade your Google One storage plan.",
            )
            self.store.save(es)

    def advance(self, es: ExportSet) -> None:
        """Move one export set as far as it can go right now."""
        while True:
            before = es.stage
            try:
                if es.stage in DOWNLOAD_STAGES:
                    self._download(es)
                elif es.stage in (Stage.DOWNLOADED, Stage.IMPORTING):
                    self._import(es)
                elif es.stage in (Stage.IMPORTED, Stage.VALIDATING):
                    self.validate(es)
                elif es.stage == Stage.VALIDATED:
                    c = self.config.cleanup
                    if c.delete_local_after_validation or c.delete_remote_after_validation:
                        self.run_cleanup(es)
                    else:
                        self._finish(es)
                elif es.stage == Stage.CLEANED:
                    self._finish(es)
            except Exception as exc:
                self._fail(es, exc)
                return
            if es.stage == before or es.stage in TERMINAL_STAGES:
                return

    def _fail(self, es: ExportSet, exc: Exception) -> None:
        es.attempts += 1
        es.error = str(exc)[-2000:]
        log.error("%s: %s failed (attempt %d): %s", es.id, es.stage.value, es.attempts, exc)
        if es.attempts >= self.config.runtime.max_attempts:
            es.failed_stage = _RESUME_FROM.get(es.stage, es.stage)
            es.stage = Stage.FAILED
            self.store.save(es)
            self._notify(EventType.ERROR, f"Stopped after {es.attempts} attempts: {es.error}", es)
        else:
            self.store.save(es)

    # ------------------------------------------------------------------ entry points
    def tick(self) -> None:
        self.apply_requests()
        self.discover()
        for es in self.store.list():
            if es.stage not in TERMINAL_STAGES and es.stage not in (Stage.FAILED, Stage.VALIDATION_FAILED):
                self.advance(es)

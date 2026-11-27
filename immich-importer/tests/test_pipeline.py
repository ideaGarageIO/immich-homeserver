from pathlib import Path

import pytest

from make_takeout import EXPORT_ID, build_takeout, sample_items
from takeout2immich.config.models import DriveSourceConfig
from takeout2immich.domain import EventType, ImportResult, PartState, Stage, ValidationReport
from takeout2immich.pipeline import Pipeline
from takeout2immich.sources import build_source
from takeout2immich.state import StateStore, WorkerBusyError


class Recorder:
    def __init__(self):
        self.events = []

    def send(self, event):
        self.events.append(event)

    def types(self):
        return [e.type for e in self.events]


class FakeImporter:
    def __init__(self, fail_times=0, exit_code=0):
        self.calls = 0
        self.fail_times = fail_times
        self.exit_code = exit_code

    def run(self, export_id, paths):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("immich unreachable")
        assert len(paths) == 2, "all parts must be imported together"
        return ImportResult(exit_code=self.exit_code, uploaded=4, duplicates=0, errors=0)


class FakeValidator:
    def __init__(self, missing=0):
        self.missing = missing
        self.calls = 0

    def validate(self, es):
        from takeout2immich.domain import MissingItem

        self.calls += 1
        miss = [MissingItem(zip="z", entry=f"e{i}", sha1="s") for i in range(self.missing)]
        return ValidationReport(export_id=es.id, expected=4, present=4 - self.missing, missing=miss, report_path="/r.json")


def make(config, tmp_path, importer=None, validator=None):
    build_takeout(Path(config.source.path), sample_items())
    rec = Recorder()
    imp = importer or FakeImporter()
    val = validator or FakeValidator()
    p = Pipeline(
        config, StateStore(config.runtime.state_db), build_source(config.source), rec, lambda: imp, lambda: val
    )
    return p, rec, imp, val


def test_no_import_before_confirm(config, tmp_path):
    p, rec, imp, _ = make(config, tmp_path)
    p.tick()
    p.tick()
    es = p.store.get(EXPORT_ID)
    assert es.stage == Stage.DOWNLOADING and es.all_downloaded
    assert imp.calls == 0
    assert EventType.EXPORT_DETECTED in rec.types()
    assert rec.types().count(EventType.ACTION_REQUIRED) == 1  # confirm reminder sent once


def test_full_flow_after_confirm(config, tmp_path):
    p, rec, imp, val = make(config, tmp_path)
    p.tick()
    p.request_confirm()
    p.tick()
    es = p.store.get(EXPORT_ID)
    assert es.stage == Stage.DONE
    assert imp.calls == 1 and val.calls == 1
    assert es.validation_passed is True
    t = rec.types()
    for ev in (EventType.DOWNLOAD_COMPLETE, EventType.IMPORT_COMPLETE, EventType.VALIDATION_PASSED, EventType.CLEANUP_DONE):
        assert ev in t
    # local source: originals outside staging are never deleted by cleanup
    assert len(list(Path(config.source.path).glob("*.zip"))) == 2


def test_auto_confirm_runs_straight_through(config, tmp_path):
    config.source.auto_confirm = True
    p, _, imp, _ = make(config, tmp_path)
    p.tick()
    assert p.store.get(EXPORT_ID).stage == Stage.DONE and imp.calls == 1


def test_validation_failure_stops_before_cleanup(config, tmp_path):
    config.source.auto_confirm = True
    config.source.delete_originals = True
    p, rec, _, _ = make(config, tmp_path, validator=FakeValidator(missing=1))
    p.tick()
    p.tick()
    es = p.store.get(EXPORT_ID)
    assert es.stage == Stage.VALIDATION_FAILED
    assert EventType.VALIDATION_FAILED in rec.types() and EventType.CLEANUP_DONE not in rec.types()
    assert len(list(Path(config.source.path).glob("*.zip"))) == 2  # nothing deleted


def test_forced_cleanup_after_failed_validation(config, tmp_path):
    config.source.auto_confirm = True
    config.source.delete_originals = True
    p, _, _, _ = make(config, tmp_path, validator=FakeValidator(missing=1))
    p.tick()
    p.store.add_request("cleanup", EXPORT_ID, force=True)
    p.tick()
    assert p.store.get(EXPORT_ID).stage == Stage.DONE
    assert list(Path(config.source.path).glob("*.zip")) == []


def test_transient_failure_retries_then_fails_then_retry_request_resumes(config, tmp_path):
    config.source.auto_confirm = True
    imp = FakeImporter(fail_times=2)  # max_attempts=2 in the fixture config
    p, rec, _, _ = make(config, tmp_path, importer=imp)
    p.tick()
    assert p.store.get(EXPORT_ID).stage == Stage.IMPORTING and p.store.get(EXPORT_ID).attempts == 1
    p.tick()
    es = p.store.get(EXPORT_ID)
    assert es.stage == Stage.FAILED and es.failed_stage == Stage.DOWNLOADED
    assert EventType.ERROR in rec.types()
    p.tick()
    assert p.store.get(EXPORT_ID).stage == Stage.FAILED  # stays failed without a retry request
    p.store.add_request("retry", EXPORT_ID)
    p.tick()
    assert p.store.get(EXPORT_ID).stage == Stage.DONE


def test_nonzero_exit_code_is_a_failure(config, tmp_path):
    config.source.auto_confirm = True
    p, _, _, _ = make(config, tmp_path, importer=FakeImporter(exit_code=1))
    p.tick()
    es = p.store.get(EXPORT_ID)
    assert es.stage == Stage.IMPORTING and "exited with 1" in es.error


@pytest.mark.parametrize("crash_stage", [Stage.IMPORTING, Stage.VALIDATING, Stage.VALIDATED, Stage.CLEANED])
def test_resume_after_crash_in_any_stage(config, tmp_path, crash_stage):
    config.source.auto_confirm = True
    p, _, _, _ = make(config, tmp_path)
    p.discover()
    es = p.store.get(EXPORT_ID)
    for part in es.parts.values():  # simulate: downloads were done before the crash
        part.state, part.local_path = PartState.DOWNLOADED, part.remote_ref
    es.stage = crash_stage
    p.store.save(es)
    p.tick()
    assert p.store.get(EXPORT_ID).stage == Stage.DONE


def test_new_parts_are_merged_while_downloading(config, tmp_path):
    p, _, _, _ = make(config, tmp_path)
    z2 = Path(config.source.path) / f"{EXPORT_ID}-002.zip"
    hidden = z2.with_suffix(".hidden")
    z2.rename(hidden)
    p.tick()
    assert len(p.store.get(EXPORT_ID).parts) == 1
    hidden.rename(z2)
    p.tick()
    assert len(p.store.get(EXPORT_ID).parts) == 2


def test_part_shows_downloading_while_in_flight(config, tmp_path):
    p, _, _, _ = make(config, tmp_path)
    real_fetch = p.source.fetch
    seen = []

    def spy(part, dest):
        # Read back what a front-end (TUI / `status`) would see mid-transfer.
        stored = p.store.get(EXPORT_ID)
        seen.append({n: x.state for n, x in stored.parts.items()})
        return real_fetch(part, dest)

    p.source.fetch = spy
    p.tick()
    assert len(seen) == 2
    first, second = sorted(p.store.get(EXPORT_ID).parts)
    assert seen[0] == {first: PartState.DOWNLOADING, second: PartState.PENDING}
    assert seen[1] == {first: PartState.DOWNLOADED, second: PartState.DOWNLOADING}
    assert all(x.state == PartState.DOWNLOADED for x in p.store.get(EXPORT_ID).parts.values())


def test_interrupted_download_state_is_reset(config, tmp_path):
    p, _, _, _ = make(config, tmp_path)
    p.discover()
    es = p.store.get(EXPORT_ID)
    for part in es.parts.values():  # simulate: worker killed mid-transfer
        part.state = PartState.DOWNLOADING
    p.store.save(es)
    p.source.fetch = lambda part, dest: (_ for _ in ()).throw(RuntimeError("network down"))
    p.tick()
    states = {x.state for x in p.store.get(EXPORT_ID).parts.values()}
    assert states == {PartState.FAILED}  # retried (not skipped) and no stale DOWNLOADING left


def test_disk_space_reserve_blocks_download(config, tmp_path):
    from takeout2immich.sources.drive import DriveSource
    from test_sources import FakeRclone

    config.source = DriveSourceConfig(rclone_config_file=tmp_path / "rclone.conf")
    config.staging.min_free_gb = 10**9  # impossible reserve
    fake = FakeRclone({f"{EXPORT_ID}-001.zip": b"a" * 10})
    p = Pipeline(config, StateStore(config.runtime.state_db), DriveSource(config.source, runner=fake),
                 Recorder(), FakeImporter, FakeValidator)
    p.tick()
    es = p.store.get(EXPORT_ID)
    assert "Not enough space" in es.error and es.downloaded_count == 0


def test_drive_done_sends_downgrade_reminder(config, tmp_path):
    from takeout2immich.sources.drive import DriveSource
    from test_sources import FakeRclone

    config.source = DriveSourceConfig(rclone_config_file=tmp_path / "rclone.conf", auto_confirm=True)
    build_takeout(tmp_path / "remote", sample_items())
    files = {z.name: z.read_bytes() for z in (tmp_path / "remote").glob("*.zip")}
    fake = FakeRclone(files)
    rec = Recorder()
    p = Pipeline(config, StateStore(config.runtime.state_db), DriveSource(config.source, runner=fake),
                 rec, FakeImporter, FakeValidator)
    p.tick()
    assert p.store.get(EXPORT_ID).stage == Stage.DONE
    assert files == {}  # remote copy deleted
    assert list((config.staging.path / EXPORT_ID).glob("*.zip")) == []  # local copy deleted
    assert any("downgrade" in e.message for e in rec.events if e.type == EventType.ACTION_REQUIRED)


def test_worker_lock_is_exclusive(config):
    store = StateStore(config.runtime.state_db)
    with store.worker_lock():
        with pytest.raises(WorkerBusyError):
            with StateStore(config.runtime.state_db).worker_lock():
                pass


def test_reimport_after_failed_validation(config, tmp_path):
    config.source.auto_confirm = True
    val = FakeValidator(missing=1)
    p, _, imp, _ = make(config, tmp_path, validator=val)
    p.tick()
    assert p.store.get(EXPORT_ID).stage == Stage.VALIDATION_FAILED and imp.calls == 1
    val.missing = 0
    p.store.add_request("reimport", EXPORT_ID)
    p.tick()
    assert p.store.get(EXPORT_ID).stage == Stage.DONE and imp.calls == 2

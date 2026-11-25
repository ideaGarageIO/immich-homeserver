import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from make_takeout import EXPORT_ID, build_takeout, sample_items
from takeout2immich.config.models import DirectSourceConfig, DriveSourceConfig, LocalSourceConfig
from takeout2immich.domain import ExportPart, export_id_for
from takeout2immich.sources import build_source
from takeout2immich.sources.drive import DriveSource, RcloneError


@pytest.mark.parametrize(
    "name,expected",
    [
        ("takeout-20261125T153000Z-001.zip", "takeout-20261125T153000Z"),
        ("takeout-20261125T153000Z-3-012.zip", "takeout-20261125T153000Z"),
        ("takeout-20261125T153000Z-001.tgz", "takeout-20261125T153000Z"),
        ("random.zip", None),
        ("takeout-20261125T153000Z-001.zip.partial", None),
    ],
)
def test_export_id_for(name, expected):
    assert export_id_for(name) == expected


def test_local_source_groups_parts(tmp_path):
    build_takeout(tmp_path / "in", sample_items())
    src = build_source(LocalSourceConfig(path=tmp_path / "in"))
    sets = src.discover()
    assert [s.id for s in sets] == [EXPORT_ID]
    assert sorted(sets[0].parts) == [f"{EXPORT_ID}-001.zip", f"{EXPORT_ID}-002.zip"]
    part = sets[0].parts[f"{EXPORT_ID}-001.zip"]
    path = src.fetch(part, tmp_path / "staging")
    assert path == tmp_path / "in" / part.name  # no copy
    assert src.verify(part, path)


def test_local_source_delete_originals_only_when_enabled(tmp_path):
    build_takeout(tmp_path / "in", sample_items())
    keep = build_source(LocalSourceConfig(path=tmp_path / "in"))
    es = keep.discover()[0]
    keep.delete_remote(es)
    assert len(list((tmp_path / "in").glob("*.zip"))) == 2
    build_source(LocalSourceConfig(path=tmp_path / "in", delete_originals=True)).delete_remote(es)
    assert list((tmp_path / "in").glob("*.zip")) == []


def test_direct_source_is_a_clear_placeholder():
    src = build_source(DirectSourceConfig())
    ok, msg = src.check()
    assert not ok and "not implemented" in msg
    with pytest.raises(NotImplementedError, match="docs/sources.md"):
        src.discover()


class FakeRclone:
    """Emulates the rclone subcommands DriveSource uses, backed by a dict of remote files."""

    def __init__(self, files: dict[str, bytes]):
        self.files = files
        self.calls: list[list[str]] = []

    def __call__(self, cmd, capture_output, text, timeout=None):
        self.calls.append(cmd)
        args = cmd[3:]  # strip binary --config file
        sub = args[0]
        if sub == "lsjson":
            listing = [
                {"Path": n, "Name": n, "Size": len(b), "Hashes": {"md5": hashlib.md5(b).hexdigest()}}
                for n, b in self.files.items()
            ]
            return subprocess.CompletedProcess(cmd, 0, json.dumps(listing), "")
        if sub == "copyto":
            name = args[1].rsplit("/", 1)[1]
            Path(args[2]).write_bytes(self.files[name])
            return subprocess.CompletedProcess(cmd, 0, "", "")
        if sub == "deletefile":
            name = args[2].rsplit("/", 1)[1]
            del self.files[name]
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return subprocess.CompletedProcess(cmd, 1, "", "unsupported")


def _drive(tmp_path, files, **kw):
    cfg = DriveSourceConfig(rclone_config_file=tmp_path / "rclone.conf", **kw)
    fake = FakeRclone(files)
    return DriveSource(cfg, runner=fake), fake


def test_drive_discover_fetch_verify_delete(tmp_path):
    files = {f"{EXPORT_ID}-001.zip": b"a" * 100, f"{EXPORT_ID}-002.zip": b"b" * 50, "notes.txt": b"x"}
    src, fake = _drive(tmp_path, files)
    [es] = src.discover()
    assert len(es.parts) == 2 and es.parts[f"{EXPORT_ID}-001.zip"].md5
    part = es.parts[f"{EXPORT_ID}-001.zip"]
    path = src.fetch(part, tmp_path / "staging")
    assert path.read_bytes() == b"a" * 100
    assert src.verify(part, path)
    # A second fetch of a verified file does not call rclone again.
    n = len(fake.calls)
    src.fetch(part, tmp_path / "staging")
    assert len(fake.calls) == n
    src.delete_remote(es)
    assert list(files) == ["notes.txt"]
    assert all("--drive-use-trash=false" in c for c in fake.calls if "deletefile" in c)


def test_drive_verify_detects_corruption(tmp_path):
    files = {f"{EXPORT_ID}-001.zip": b"a" * 100}
    src, _ = _drive(tmp_path, files)
    [es] = src.discover()
    part = es.parts[f"{EXPORT_ID}-001.zip"]
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"c" * 100)  # same size, wrong content
    assert not src.verify(part, bad)


def test_drive_rclone_error_is_raised(tmp_path):
    cfg = DriveSourceConfig(rclone_config_file=tmp_path / "rclone.conf")

    def failing(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 3, "", "directory not found")

    with pytest.raises(RcloneError, match="directory not found"):
        DriveSource(cfg, runner=failing).discover()


def test_drive_check_without_config(tmp_path):
    src, _ = _drive(tmp_path, {})
    ok, msg = src.check()
    assert not ok and "rclone config not found" in msg


def test_export_part_defaults():
    p = ExportPart(name="x", size=1, remote_ref="x")
    assert p.state == "PENDING" and p.attempts == 0

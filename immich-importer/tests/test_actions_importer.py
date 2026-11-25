from pathlib import Path

import pytest

from takeout2immich.actions import recommend
from takeout2immich.config.models import ImporterConfig
from takeout2immich.domain import ExportSet, Stage
from takeout2immich.importer.immich_go import ImmichGoImporter, build_args, parse_counts, redact


@pytest.mark.parametrize(
    "stage,keys",
    [
        (Stage.DISCOVERED, ["confirm"]),
        (Stage.DOWNLOADING, ["confirm"]),
        (Stage.CONFIRMED, ["wait"]),
        (Stage.IMPORTING, ["wait"]),
        (Stage.VALIDATION_FAILED, ["view_report", "reimport", "revalidate", "force_cleanup"]),
        (Stage.VALIDATED, ["cleanup"]),
        (Stage.DONE, ["view_report", "downgrade"]),
        (Stage.FAILED, ["view_logs", "retry"]),
    ],
)
def test_recommend(stage, keys):
    es = ExportSet(id="takeout-x", source_type="drive", stage=stage)
    assert [a.key for a in recommend(es, "drive")] == keys


def test_recommend_without_exports():
    assert recommend(None, "drive")[0].key == "request_export"
    assert recommend(None, "local")[0].key == "add_files"
    es = ExportSet(id="t", source_type="local", stage=Stage.DONE)
    assert "downgrade" not in [a.key for a in recommend(es, "local")]


def test_build_args_defaults():
    args = build_args(ImporterConfig(), "http://immich-server:2283", "KEY", ["/s/a.zip", "/s/b.zip"], Path("/r/l.log"))
    assert args[:3] == ["immich-go", "upload", "from-google-photos"]
    for flag in (
        "--server=http://immich-server:2283",
        "--no-ui",
        "--manage-burst=Stack",
        "--manage-raw-jpeg=StackCoverRaw",
        "--manage-heic-jpeg=StackCoverHeic",
        "--include-unmatched=true",
        "--include-trashed=false",
        "--sync-albums=true",
        "--on-errors=continue",
    ):
        assert flag in args
    assert args[-2:] == ["/s/a.zip", "/s/b.zip"]
    assert "KEY" not in " ".join(redact(args))


def test_parse_counts_best_effort():
    text = "Upload summary\nuploaded: 1,234\nserver has same: 56\nerrors: 0\n"
    assert parse_counts(text) == {"uploaded": 1234, "duplicates": 56, "errors": 0}
    assert parse_counts("nothing useful") == {"uploaded": None, "duplicates": None, "errors": None}


def test_importer_runs_process_and_captures_output(tmp_path):
    seen = {}

    class FakePopen:
        def __init__(self, args, **kw):
            seen["args"] = args
            self.stdout = iter(["starting\n", "uploaded: 3\n", "errors: 0\n"])

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def wait(self):
            return 0

    imp = ImmichGoImporter(ImporterConfig(), "http://s", "KEY", tmp_path, popen=FakePopen)
    r = imp.run("takeout-x", ["/a.zip"])
    assert r.exit_code == 0 and r.uploaded == 3 and r.errors == 0
    assert r.log_path.startswith(str(tmp_path)) and "takeout-x" in r.log_path


# Captured from a real immich-go 0.32.0 re-run against Immich v3.4.2 (dev stack).
REAL_RERUN_OUTPUT = """
Immich read 100%, Assets found: 5, Upload errors: 0, Uploaded 0
Asset Tracking Report:
=====================
Total Assets:          5  (3.2 KB)
  Processed:           4  (2.6 KB)
  Discarded:           1  (661 B)
  Errors:              0  (0 B)
Asset Lifecycle (DISCARDED):
  server has duplicate               :       4  (2.6 KB)
  discarded filtered                 :       1  (661 B)
"""


def test_parse_counts_real_immich_go_output():
    assert parse_counts(REAL_RERUN_OUTPUT) == {"uploaded": 0, "duplicates": 4, "errors": 0}

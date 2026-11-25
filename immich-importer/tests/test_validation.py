import json

import httpx
import respx

from make_takeout import EXPORT_ID, Item, build_takeout, sample_items
from takeout2immich.domain import ExportPart, ExportSet, PartState
from takeout2immich.immich import ImmichClient
from takeout2immich.validation import Validator, inventory

URL = "http://immich.test"


def _export_set(folder):
    es = ExportSet(id=EXPORT_ID, source_type="local")
    for z in sorted(folder.glob("*.zip")):
        es.parts[z.name] = ExportPart(
            name=z.name, size=z.stat().st_size, remote_ref=str(z), state=PartState.DOWNLOADED, local_path=str(z)
        )
    return es


def test_inventory_hashes_media_and_finds_trashed_across_zips(tmp_path):
    hashes = build_takeout(tmp_path, sample_items())
    entries = list(inventory([str(p) for p in sorted(tmp_path.glob("*.zip"))]))
    assert len(entries) == 5  # sidecars and html are not media
    by_name = {e.entry.split("Google Photos/")[1]: e for e in entries}
    for key, sha in hashes.items():
        assert by_name[key].sha1 == sha
    assert [k for k, e in by_name.items() if e.trashed] == ["Photos from 2023/IMG_0005.jpg"]


def _mock_check(present: set[str], trashed: set[str] = frozenset(), unsupported: set[str] = frozenset()):
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append(len(body["assets"]))
        results = []
        for a in body["assets"]:
            c = a["checksum"]
            if c in unsupported:
                results.append({"id": a["id"], "action": "reject", "reason": "unsupported-format"})
            elif c in present:
                results.append(
                    {"id": a["id"], "action": "reject", "reason": "duplicate", "assetId": "x", "isTrashed": c in trashed}
                )
            else:
                results.append({"id": a["id"], "action": "accept"})
        return httpx.Response(200, json={"results": results})

    return handler, calls


@respx.mock
def test_validation_passes_when_everything_is_present(tmp_path, config):
    hashes = build_takeout(tmp_path / "in", sample_items())
    handler, calls = _mock_check(set(hashes.values()))
    respx.post(f"{URL}/api/assets/bulk-upload-check").mock(side_effect=handler)
    config.validation.batch_size = 2
    report = Validator(config, ImmichClient(URL, "k")).validate(_export_set(tmp_path / "in"))
    assert report.passed
    assert (report.expected, report.present, report.excluded) == (4, 4, 1)  # trashed one excluded
    assert calls == [2, 2]  # batched
    assert (config.validation.report_dir).glob("validation-*.txt")


@respx.mock
def test_validation_reports_missing_and_flagged(tmp_path, config):
    items = sample_items() + [Item("Photos from 2024", "IMG_0006-edited.jpg")]
    hashes = build_takeout(tmp_path / "in", items)
    missing_sha = hashes["Photos from 2021/IMG_0002.jpg"]
    trashed_sha = hashes["Photos from 2022/IMG_0004.jpg"]
    present = set(hashes.values()) - {missing_sha}
    handler, _ = _mock_check(present, trashed={trashed_sha})
    respx.post(f"{URL}/api/assets/bulk-upload-check").mock(side_effect=handler)
    config.validation.ignore_patterns = ["*-edited.*"]
    report = Validator(config, ImmichClient(URL, "k")).validate(_export_set(tmp_path / "in"))
    assert not report.passed
    assert [m.entry.rsplit("/", 1)[1] for m in report.missing] == ["IMG_0002.jpg"]
    assert [(m.entry.rsplit("/", 1)[1], m.reason) for m in report.flagged] == [("IMG_0004.jpg", "in Immich trash")]
    assert report.ignored == 1
    txt = next(config.validation.report_dir.glob("validation-*.txt")).read_text()
    assert "FAILED" in txt and "IMG_0002.jpg" in txt


@respx.mock
def test_trashed_items_count_when_importer_includes_them(tmp_path, config):
    hashes = build_takeout(tmp_path / "in", sample_items())
    trashed_sha = hashes["Photos from 2023/IMG_0005.jpg"]
    handler, _ = _mock_check(set(hashes.values()) - {trashed_sha})
    respx.post(f"{URL}/api/assets/bulk-upload-check").mock(side_effect=handler)
    config.importer.include_trashed = True
    report = Validator(config, ImmichClient(URL, "k")).validate(_export_set(tmp_path / "in"))
    assert report.excluded == 0 and len(report.missing) == 1

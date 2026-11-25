import pytest

from takeout2immich.cleanup import CleanupRefused, cleanup
from takeout2immich.domain import ExportPart, ExportSet, Stage


class FakeSource:
    type = "fake"

    def __init__(self):
        self.deleted = []

    def delete_remote(self, es):
        self.deleted.append(es.id)
        return len(es.parts)


def _set(stage, paths):
    es = ExportSet(id="takeout-x", source_type="fake", stage=stage)
    for p in paths:
        es.parts[p.name] = ExportPart(name=p.name, size=1, remote_ref=p.name, local_path=str(p))
    return es


@pytest.mark.parametrize("stage", [s for s in Stage if s != Stage.VALIDATED])
def test_refuses_unless_validated(config, tmp_path, stage):
    src = FakeSource()
    with pytest.raises(CleanupRefused):
        cleanup(_set(stage, []), config, src)
    assert src.deleted == []


def test_deletes_only_inside_staging(config, tmp_path):
    staging = config.staging.path
    staging.mkdir(parents=True)
    inside = staging / "a.zip"
    outside = tmp_path / "b.zip"
    inside.write_bytes(b"1")
    outside.write_bytes(b"2")
    src = FakeSource()
    cleanup(_set(Stage.VALIDATED, [inside, outside]), config, src)
    assert not inside.exists() and outside.exists()
    assert src.deleted == ["takeout-x"]


def test_respects_flags(config, tmp_path):
    config.cleanup.delete_local_after_validation = False
    config.cleanup.delete_remote_after_validation = False
    config.staging.path.mkdir(parents=True)
    f = config.staging.path / "a.zip"
    f.write_bytes(b"1")
    src = FakeSource()
    cleanup(_set(Stage.VALIDATED, [f]), config, src)
    assert f.exists() and src.deleted == []

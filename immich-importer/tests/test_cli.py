from typer.testing import CliRunner

from make_takeout import EXPORT_ID, build_takeout, sample_items
from takeout2immich.cli import app
from takeout2immich.config import save_config
from takeout2immich.state import StateStore

runner = CliRunner()


def test_status_without_config(tmp_path):
    r = runner.invoke(app, ["status", "-c", str(tmp_path / "missing.yaml")])
    assert r.exit_code == 2 and "No config" in r.output


def test_run_dry_run_and_confirm_flow(tmp_path, config):
    cfg_path = tmp_path / "config.yaml"
    save_config(config, cfg_path)
    build_takeout(config.source.path, sample_items())

    r = runner.invoke(app, ["run", "--dry-run", "-c", str(cfg_path)])
    assert r.exit_code == 0 and EXPORT_ID in r.output and "-002.zip" in r.output
    assert StateStore(config.runtime.state_db).list() == []  # dry run writes nothing

    # one pass: discovered + downloaded, waiting for confirmation
    r = runner.invoke(app, ["status", "-c", str(cfg_path)])
    assert "No export sets yet" in r.output

    from takeout2immich.runtime import build_pipeline

    build_pipeline(config).tick()
    r = runner.invoke(app, ["status", "-c", str(cfg_path)])
    assert "DOWNLOADING" in r.output and "takeout2immich confirm" in r.output

    r = runner.invoke(app, ["confirm", "-c", str(cfg_path)])
    assert r.exit_code == 0 and f"Confirmed {EXPORT_ID}" in r.output
    assert [q.action for q in StateStore(config.runtime.state_db).pending_requests()] == ["confirm"]


def test_cleanup_refuses_unvalidated(tmp_path, config):
    cfg_path = tmp_path / "config.yaml"
    save_config(config, cfg_path)
    build_takeout(config.source.path, sample_items())
    from takeout2immich.runtime import build_pipeline

    build_pipeline(config).tick()
    r = runner.invoke(app, ["cleanup", EXPORT_ID, "-c", str(cfg_path)])
    assert r.exit_code == 1 and "only runs after validation passed" in r.output


def test_health_exits_zero_when_unconfigured(tmp_path):
    r = runner.invoke(app, ["health", "-c", str(tmp_path / "missing.yaml")])
    assert r.exit_code == 0


def test_both_entry_points_declared():
    import tomllib
    from pathlib import Path

    scripts = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text())["project"]["scripts"]
    assert scripts == {"takeout2immich": "takeout2immich.cli:app", "t2i": "takeout2immich.cli:app"}

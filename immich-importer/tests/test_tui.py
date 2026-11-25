import stat

from textual.widgets import Button, Input, Select

from make_takeout import EXPORT_ID, build_takeout, sample_items
from takeout2immich.config import load_config, save_config
from takeout2immich.state import StateStore
from takeout2immich.tui.app import ImporterApp


async def test_first_run_opens_immich_and_saves_config_and_secret(tmp_path):
    cfg_path = tmp_path / "config.yaml"
    app = ImporterApp(cfg_path)
    async with app.run_test(size=(120, 50)) as pilot:
        assert app.screen.MODE == "immich"
        app.screen.query_one("#f-immich__url", Input).value = "http://immich.test:2283"
        app.screen.query_one("#f-immich__api_key", Input).value = "SECRETKEY"
        await pilot.click("#save")
        await pilot.pause()
    cfg = load_config(cfg_path)
    assert cfg.immich.url == "http://immich.test:2283"
    assert cfg.immich.api_key_file.read_text().strip() == "SECRETKEY"
    assert stat.S_IMODE(cfg.immich.api_key_file.stat().st_mode) == 0o600
    assert "SECRETKEY" not in cfg_path.read_text()


async def test_invalid_value_is_not_saved(tmp_path, config):
    cfg_path = tmp_path / "config.yaml"
    save_config(config, cfg_path)
    app = ImporterApp(cfg_path)
    async with app.run_test(size=(120, 60)) as pilot:
        app.switch_mode("importer")
        await pilot.pause()
        app.screen.query_one("#f-importer__concurrent_tasks", Input).value = "99"
        await pilot.click("#save")
        await pilot.pause()
        assert "Not saved" in str(app.screen.query_one("#message").render())
    assert load_config(cfg_path).importer.concurrent_tasks == 8


async def test_switching_source_type_to_drive(tmp_path, config):
    cfg_path = tmp_path / "config.yaml"
    save_config(config, cfg_path)
    app = ImporterApp(cfg_path)
    async with app.run_test(size=(120, 60)) as pilot:
        app.switch_mode("source")
        await pilot.pause()
        app.screen.query_one("#f-source__type", Select).value = "drive"
        await pilot.click("#save")
        await pilot.pause()
        assert app.screen.query("#f-source__rclone_remote")  # drive fields now shown
    assert load_config(cfg_path).source.type == "drive"


async def test_notifications_screen_adds_home_assistant(tmp_path, config):
    cfg_path = tmp_path / "config.yaml"
    save_config(config, cfg_path)
    app = ImporterApp(cfg_path)
    async with app.run_test(size=(120, 70)) as pilot:
        app.switch_mode("notifications")
        await pilot.pause()
        s = app.screen
        s.query_one("#f-_ha__enabled").value = True
        s.query_one("#f-_ha__url", Input).value = "http://ha:8123"
        s.query_one("#f-_ha__service", Input).value = "mobile_app_x"
        s.query_one("#f-_ha__token", Input).value = "HATOKEN"
        s.query_one("#f-_ha__events", Input).value = "ERROR, VALIDATION_FAILED"
        await pilot.click("#save")
        await pilot.pause()
    cfg = load_config(cfg_path)
    types = [n.type for n in cfg.notifications]
    assert types == ["log", "homeassistant"]
    ha = cfg.notifications[1]
    assert ha.events == ["ERROR", "VALIDATION_FAILED"] and ha.token_file.read_text().strip() == "HATOKEN"


async def test_status_shows_progress_and_confirm_queues_request(tmp_path, config):
    cfg_path = tmp_path / "config.yaml"
    save_config(config, cfg_path)
    build_takeout(config.source.path, sample_items())
    from takeout2immich.runtime import build_pipeline

    build_pipeline(config).tick()
    app = ImporterApp(cfg_path)
    async with app.run_test(size=(140, 50)) as pilot:
        assert app.screen.MODE == "status"
        await pilot.pause()
        assert "DOWNLOADING" in str(app.screen.query_one("#detail").render())
        btn = app.screen.query_one("#act-confirm", Button)
        await pilot.click("#act-confirm")
        await pilot.pause()
        assert btn is not None
    reqs = StateStore(config.runtime.state_db).pending_requests()
    assert [(r.action, r.export_id) for r in reqs] == [("confirm", EXPORT_ID)]

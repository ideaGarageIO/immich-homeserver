from __future__ import annotations

from textual.widgets import Select

from takeout2immich.doctor import check_source
from takeout2immich.tui.screens.config.base import ConfigSectionScreen, Field

TYPE_FIELD = Field(
    "source.type",
    "Source type",
    kind="select",
    options=["drive", "local", "direct"],
    help="drive: Takeout delivered to Google Drive (recommended). local: zips already on disk. "
    "direct: planned, not implemented yet. Save after changing the type to see its fields.",
)

DRIVE_FIELDS = [
    Field("source.rclone_remote", "rclone remote name", help="The remote you created with `rclone config`."),
    Field("source.folder", "Drive folder", help="Takeout writes into 'Takeout' in My Drive."),
    Field("source.rclone_config_file", "rclone config file"),
    Field("source.use_trash", "Move deleted exports to Drive trash", kind="bool",
          help="Off = delete permanently (trash still counts against your quota)."),
    Field("source.verify_md5_locally", "Re-check MD5 after download", kind="bool"),
    Field("source.auto_confirm", "Import without waiting for confirmation", kind="bool",
          help="Leave off: confirm once Google's 'export ready' email arrives."),
]

LOCAL_FIELDS = [
    Field("source.path", "Folder with takeout-*.zip files"),
    Field("source.delete_originals", "Delete the original zips after validation", kind="bool"),
    Field("source.auto_confirm", "Import as soon as files are found", kind="bool"),
]

KEYS_BY_TYPE = {
    "drive": [f.key for f in DRIVE_FIELDS],
    "local": [f.key for f in LOCAL_FIELDS],
    "direct": [],
}


class SourceScreen(ConfigSectionScreen):
    MODE = "source"
    TITLE_TEXT = "Source"
    INTRO = "Where Takeout archives come from. See docs/google-drive-setup.md for the rclone setup."
    HAS_TEST = True

    def fields(self, data):
        t = (data.get("source") or {}).get("type", "drive")
        return [TYPE_FIELD] + {"drive": DRIVE_FIELDS, "local": LOCAL_FIELDS}.get(t, [])

    def collect(self, data):
        old = data.get("source") or {}
        new_type = self.query_one(f"#{TYPE_FIELD.wid}", Select).value
        if new_type != old.get("type"):
            # Switching type: start a fresh section; defaults fill the rest.
            data["source"] = {"type": new_type}
            if new_type == "local":
                data["source"]["path"] = "/data/takeout-local"
            return data
        section = {"type": new_type}
        for f in self.fields(data)[1:]:
            section[f.key.split(".", 1)[1]] = self.read_value(f)
        data["source"] = section
        return data

    def do_save(self) -> bool:
        before = self.app.config.source.type
        ok = super().do_save()
        if ok and self.app.config.source.type != before:
            self.refresh(recompose=True)
        return ok

    def checks(self, config):
        return [check_source(config)]

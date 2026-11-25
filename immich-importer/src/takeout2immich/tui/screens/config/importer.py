from __future__ import annotations

from takeout2immich.doctor import check_tools
from takeout2immich.tui.screens.config.base import ConfigSectionScreen, Field


class ImporterScreen(ConfigSectionScreen):
    MODE = "importer"
    TITLE_TEXT = "Importer (immich-go)"
    INTRO = "Options passed to `immich-go upload from-google-photos`. Defaults keep everything and stack pairs."
    HAS_TEST = True
    FIELDS = [
        Field("importer.concurrent_tasks", "Concurrent uploads (1-20)", kind="int"),
        Field("importer.manage_burst", "Burst photos", kind="select",
              options=["Stack", "NoStack", "StackKeepRaw", "StackKeepJPEG"]),
        Field("importer.manage_raw_jpeg", "RAW + JPEG pairs", kind="select",
              options=["StackCoverRaw", "StackCoverJPG", "NoStack", "KeepRaw", "KeepJPG"],
              help="Keep* modes drop one file of the pair; validation will then report it missing."),
        Field("importer.manage_heic_jpeg", "HEIC + JPEG pairs", kind="select",
              options=["StackCoverHeic", "StackCoverJPG", "NoStack", "KeepHeic", "KeepJPG"]),
        Field("importer.include_unmatched", "Import files without a JSON sidecar", kind="bool"),
        Field("importer.include_archived", "Import archived photos", kind="bool"),
        Field("importer.include_partner", "Import partner-shared photos", kind="bool"),
        Field("importer.include_trashed", "Import photos trashed in Google", kind="bool"),
        Field("importer.sync_albums", "Recreate albums", kind="bool"),
        Field("importer.people_tag", "Tag people (people/<name>)", kind="bool"),
        Field("importer.takeout_tag", "Tag with the takeout id", kind="bool"),
        Field("importer.pause_immich_jobs", "Pause Immich jobs while uploading", kind="bool"),
        Field("importer.on_errors", "On errors", help="stop, continue, or a number (max errors)"),
        Field("importer.extra_flags", "Extra flags (comma-separated)", kind="list"),
    ]

    def checks(self, config):
        return check_tools(config)

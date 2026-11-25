from __future__ import annotations

from takeout2immich.tui.screens.config.base import ConfigSectionScreen, Field


class CleanupScreen(ConfigSectionScreen):
    MODE = "cleanup"
    TITLE_TEXT = "Cleanup"
    INTRO = "What happens once validation has passed. Nothing is ever deleted from Google Photos itself."
    FIELDS = [
        Field("cleanup.delete_local_after_validation", "Delete downloaded zips from staging", kind="bool"),
        Field("cleanup.delete_remote_after_validation", "Delete the export from the source (Drive)", kind="bool"),
    ]

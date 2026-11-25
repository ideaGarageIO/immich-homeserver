from __future__ import annotations

from takeout2immich.tui.screens.config.base import ConfigSectionScreen, Field


class ValidationScreen(ConfigSectionScreen):
    MODE = "validation"
    TITLE_TEXT = "Validation"
    INTRO = (
        "After the import, every photo/video in the archives is checked against Immich by SHA-1. "
        "Nothing is deleted unless validation passes."
    )
    FIELDS = [
        Field("validation.enabled", "Validate after import", kind="bool"),
        Field("validation.fail_on_missing", "Stop if anything is missing", kind="bool",
              help="Off = report missing items but still continue to cleanup."),
        Field("validation.report_dir", "Report directory"),
        Field("validation.ignore_patterns", "Ignore file patterns (comma-separated)", kind="list",
              help="e.g. *-edited.* to not count Google's edited copies."),
        Field("validation.batch_size", "Checksums per API call", kind="int"),
    ]

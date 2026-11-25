from __future__ import annotations

from takeout2immich.doctor import check_staging
from takeout2immich.tui.screens.config.base import ConfigSectionScreen, Field


class StagingScreen(ConfigSectionScreen):
    MODE = "staging"
    TITLE_TEXT = "Staging"
    INTRO = (
        "Where downloaded archives are kept until they are imported and validated. "
        "Needs about the size of your whole export (e.g. ~370 GB) plus the reserve."
    )
    HAS_TEST = True
    FIELDS = [
        Field("staging.path", "Staging directory (inside the container)",
              help="Mapped from IMPORTER_STAGING_PATH in the server .env."),
        Field("staging.min_free_gb", "Free-space reserve (GB)", kind="int",
              help="Downloads pause rather than eat into this reserve."),
    ]

    def checks(self, config):
        return [check_staging(config)]

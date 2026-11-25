from __future__ import annotations

from takeout2immich.doctor import check_immich
from takeout2immich.tui.screens.config.base import ConfigSectionScreen, Field


class ImmichScreen(ConfigSectionScreen):
    MODE = "immich"
    TITLE_TEXT = "Immich"
    INTRO = (
        "Where Immich runs and the API key used for importing and validation. "
        "Create the key in Immich: Account Settings → API Keys (needs the asset.upload permission)."
    )
    HAS_TEST = True
    FIELDS = [
        Field("immich.url", "Server URL", help="Inside the compose project: http://immich-server:2283"),
        Field("immich.api_key", "API key", kind="secret", secret_path_key="immich.api_key_file"),
        Field("immich.api_key_file", "API key file", help="Where the key is stored (mode 0600)."),
    ]

    def checks(self, config):
        return check_immich(config)

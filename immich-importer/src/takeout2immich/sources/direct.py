"""Direct-download source (planned).

Downloading Takeout parts straight from Google's links needs a signed-in browser and has to get
through Google's hourly re-authentication. It is not implemented yet; see docs/sources.md.
"""

from __future__ import annotations

from takeout2immich.config.models import DirectSourceConfig

_MSG = (
    "source.type 'direct' is planned but not implemented yet. "
    "Use 'drive' (Takeout → Add to Drive) or 'local'. See docs/sources.md."
)


class DirectSource:
    type = "direct"

    def __init__(self, config: DirectSourceConfig):
        self.config = config

    def discover(self):
        raise NotImplementedError(_MSG)

    def fetch(self, part, dest_dir):
        raise NotImplementedError(_MSG)

    def verify(self, part, path):
        raise NotImplementedError(_MSG)

    def delete_remote(self, export_set):
        raise NotImplementedError(_MSG)

    def check(self) -> tuple[bool, str]:
        return False, _MSG

"""Delete local archives and the remote copy - only once validation has passed."""

from __future__ import annotations

import logging
from pathlib import Path

from takeout2immich.config.models import AppConfig
from takeout2immich.domain import ExportSet, Stage
from takeout2immich.util import is_within

log = logging.getLogger(__name__)


class CleanupRefused(RuntimeError):
    pass


def cleanup(export_set: ExportSet, config: AppConfig, source, *, force: bool = False) -> list[str]:
    """Returns a list of human-readable actions taken. Never deletes outside the staging dir."""
    if export_set.stage != Stage.VALIDATED and not force:
        raise CleanupRefused(
            f"{export_set.id} is {export_set.stage.value}; cleanup only runs after validation passed "
            "(use --force to override)."
        )
    done: list[str] = []
    if config.cleanup.delete_local_after_validation:
        staging = config.staging.path
        for part in export_set.sorted_parts():
            if not part.local_path:
                continue
            p = Path(part.local_path)
            if is_within(p, staging):
                p.unlink(missing_ok=True)
                done.append(f"deleted local {p.name}")
            else:
                log.info("Not deleting %s: outside staging dir", p)
    if config.cleanup.delete_remote_after_validation:
        n = source.delete_remote(export_set)
        done.append(f"deleted {n} source part(s) ({source.type})" if n else f"source copies kept ({source.type})")
    return done

"""Build the pipeline and its collaborators from a config."""

from __future__ import annotations

import logging

from takeout2immich.config.models import AppConfig
from takeout2immich.config.store import read_secret
from takeout2immich.immich import ImmichClient
from takeout2immich.importer import ImmichGoImporter
from takeout2immich.notifications import build_dispatcher
from takeout2immich.pipeline import Pipeline
from takeout2immich.sources import build_source
from takeout2immich.state import StateStore
from takeout2immich.validation import Validator


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)


def build_pipeline(config: AppConfig) -> Pipeline:
    store = StateStore(config.runtime.state_db)
    source = build_source(config.source)
    notifier = build_dispatcher(config.notifications)

    def importer_factory():
        return ImmichGoImporter(
            config.importer,
            server=config.immich.url,
            api_key=read_secret(config.immich.api_key_file),
            log_dir=config.validation.report_dir,
        )

    def validator_factory():
        client = ImmichClient(config.immich.url, read_secret(config.immich.api_key_file))
        return Validator(config, client)

    return Pipeline(config, store, source, notifier, importer_factory, validator_factory)

"""Check every media file of an export set against Immich by SHA-1.

Immich's POST /api/assets/bulk-upload-check answers, per checksum:
  reject/duplicate          -> already in Immich           => present
  accept                    -> Immich does not have it      => MISSING
  reject/unsupported-format -> Immich can't store it        => flagged
  isTrashed=true            -> present but in Immich trash  => flagged
Entries that the importer is configured to skip (Google-trashed while include_trashed=false) are
counted as excluded; entries matching validation.ignore_patterns are counted as ignored.
"""

from __future__ import annotations

import fnmatch
import json
import logging
import posixpath
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from takeout2immich.config.models import AppConfig
from takeout2immich.domain import ExportSet, MissingItem, ValidationReport
from takeout2immich.immich import ImmichClient
from takeout2immich.validation.inventory import MediaEntry, inventory

log = logging.getLogger(__name__)


class Validator:
    def __init__(self, config: AppConfig, client: ImmichClient):
        self.config = config
        self.client = client

    def _ignored(self, entry: MediaEntry) -> bool:
        name = posixpath.basename(entry.entry)
        return any(fnmatch.fnmatch(name, p) for p in self.config.validation.ignore_patterns)

    def validate(self, export_set: ExportSet) -> ValidationReport:
        vcfg = self.config.validation
        report = ValidationReport(export_id=export_set.id)
        by_sha: dict[str, list[MediaEntry]] = defaultdict(list)

        for entry in inventory(export_set.local_paths()):
            if self._ignored(entry):
                report.ignored += 1
                continue
            if entry.trashed and not self.config.importer.include_trashed:
                report.excluded += 1
                continue
            report.expected += 1
            by_sha[entry.sha1].append(entry)

        shas = list(by_sha)
        for i in range(0, len(shas), vcfg.batch_size):
            batch = shas[i : i + vcfg.batch_size]
            results = self.client.bulk_upload_check([(sha, sha) for sha in batch])
            for res in results:
                entries = by_sha[res.id]
                if res.action == "accept":
                    report.missing += [_item(e, "not in Immich") for e in entries]
                elif res.reason == "unsupported-format":
                    report.flagged += [_item(e, "unsupported format") for e in entries]
                elif res.is_trashed:
                    report.present += len(entries)
                    report.flagged += [_item(e, "in Immich trash") for e in entries]
                else:
                    report.present += len(entries)

        report.report_path = str(self._write(report))
        log.info("Validation %s: %s", export_set.id, report.summary())
        return report

    def _write(self, report: ValidationReport) -> Path:
        d = self.config.validation.report_dir
        d.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        base = d / f"validation-{report.export_id}-{ts}"
        json_path = base.with_suffix(".json")
        json_path.write_text(report.model_dump_json(indent=2))
        lines = [
            f"Validation report for {report.export_id}",
            f"Result: {'PASSED' if report.passed else 'FAILED'}",
            report.summary(),
            "",
        ]
        if report.missing:
            lines.append("Missing from Immich:")
            lines += [f"  {posixpath.basename(m.zip)}  {m.entry}" for m in report.missing]
            lines.append("")
        if report.flagged:
            lines.append("Flagged (review):")
            lines += [f"  [{m.reason}] {posixpath.basename(m.zip)}  {m.entry}" for m in report.flagged]
        base.with_suffix(".txt").write_text("\n".join(lines) + "\n")
        return json_path


def _item(e: MediaEntry, reason: str) -> MissingItem:
    return MissingItem(zip=e.zip, entry=e.entry, sha1=e.sha1, reason=reason)


def load_report(path: str | Path) -> ValidationReport:
    return ValidationReport.model_validate(json.loads(Path(path).read_text()))

"""Recommended next action for each stage - shared by `status`, the TUI and notifications."""

from __future__ import annotations

from dataclasses import dataclass

from takeout2immich.domain import ExportSet, Stage


@dataclass(frozen=True)
class Action:
    key: str  # machine id; the TUI maps it to a button
    label: str
    command: str | None = None  # CLI equivalent, if any


REQUEST_EXPORT = Action(
    "request_export",
    "Request a Google Takeout export: Google Photos only, .zip, 50 GB parts, delivery 'Add to Drive'",
)
WAIT = Action("wait", "Nothing to do - the worker is busy with this stage")


def recommend(export_set: ExportSet | None, source_type: str = "drive") -> list[Action]:
    if export_set is None:
        if source_type == "local":
            return [Action("add_files", "Put takeout-*.zip files into the configured local folder")]
        return [REQUEST_EXPORT]

    eid = export_set.id
    s = export_set.stage
    if s in (Stage.DISCOVERED, Stage.DOWNLOADING):
        return [
            Action(
                "confirm",
                "When Google's 'your export is ready' email arrives, confirm the export is complete",
                f"takeout2immich confirm {eid}",
            )
        ]
    if s in (Stage.CONFIRMED, Stage.DOWNLOADED, Stage.IMPORTING, Stage.IMPORTED, Stage.VALIDATING):
        return [WAIT]
    if s == Stage.VALIDATION_FAILED:
        return [
            Action("view_report", "Review the validation report", None),
            Action("reimport", "Re-run the import (e.g. after upload errors), then validate again",
                   f"takeout2immich reimport {eid}"),
            Action("revalidate", "Re-run validation (e.g. after changing ignore patterns)",
                   f"takeout2immich validate {eid}"),
            Action(
                "force_cleanup",
                "Accept the result and clean up anyway",
                f"takeout2immich cleanup {eid} --force",
            ),
        ]
    if s == Stage.VALIDATED:
        return [Action("cleanup", "Delete the local and remote archives", f"takeout2immich cleanup {eid}")]
    if s in (Stage.CLEANED, Stage.DONE):
        actions = [Action("view_report", "Review the validation report", None)]
        if source_type == "drive":
            actions.append(
                Action("downgrade", "Migration done: you can downgrade your Google One storage plan now")
            )
        return actions
    if s == Stage.FAILED:
        return [
            Action("view_logs", "Check the logs for the error", "deploy.sh logs"),
            Action("retry", "Retry from the failed stage", f"takeout2immich retry {eid}"),
        ]
    return []

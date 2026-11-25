# Validation

After the import, the importer proves that every photo and video from the export is in Immich
before anything is deleted. It does not trust immich-go's summary for this — it asks Immich
directly.

## How it works

1. Every zip of the export is read (streamed, nothing is unpacked). For each media file
   (images, RAW, video) it computes the **SHA-1** of the original bytes.
2. JSON sidecars are read to find items Google marks as **trashed** (sidecars may live in a
   different zip than the photo, so all parts are scanned).
3. The checksums are sent in batches to Immich's
   `POST /api/assets/bulk-upload-check` — the same endpoint Immich's own uploaders use to skip
   duplicates. Immich answers per checksum:

| Immich says | Meaning | Counted as |
|---|---|---|
| `reject` / `duplicate` | already in Immich | **present** |
| `reject` / `duplicate` + `isTrashed` | in Immich, but in its trash | present, **flagged** |
| `accept` | Immich doesn't have it | **missing** |
| `reject` / `unsupported-format` | Immich can't store this type | **flagged** |

Not counted at all:

- **excluded** — items trashed in Google while `importer.include_trashed` is `false`
  (the importer deliberately skips them);
- **ignored** — files matching `validation.ignore_patterns` (e.g. `*-edited.*`).

Validation **passes when nothing is missing**. Then (and only then) cleanup runs.

## Reading the report

Each run writes two files to `validation.report_dir`:

- `validation-<export>-<time>.txt` — the summary, every missing file (`zip  path/in/zip`) and
  every flagged file with its reason;
- `validation-<export>-<time>.json` — the same, machine-readable.

`t2i status` prints the path; the TUI's **View report** opens it.

## When validation fails

Nothing is deleted and the export stays in `VALIDATION_FAILED`. Typical causes and fixes:

| Cause | Fix |
|---|---|
| A `Keep*` RAW/HEIC option dropped one file of each pair | Expected; if you're happy, clean up with `--force` |
| immich-go hit errors (network, timeouts) | `t2i reimport <export-id>` (or **Re-run the import** in the TUI) — it imports again and re-validates |
| Google's `-edited` copies you don't want | Add `*-edited.*` to `ignore_patterns`, then `t2i validate <export>` |
| A file type Immich doesn't support | Shown as *flagged*, not missing |

Then either re-validate:

```bash
t2i validate <export-id>
```

or accept the result and clean up anyway:

```bash
t2i cleanup <export-id> --force
```

## Notes

- Hashing reads the whole export once more (hours for hundreds of GB). It runs after the import,
  so it doesn't slow the upload, but Immich's own background jobs will share the disk.
- Validation compares exact bytes. If Immich (or immich-go) ever stored a modified file, it would
  show as missing — validation errs on the side of not deleting.

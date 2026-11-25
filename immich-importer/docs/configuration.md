# Configuration

The importer reads `config.yaml` from `$TAKEOUT2IMMICH_CONFIG`, or `$TAKEOUT2IMMICH_HOME/config.yaml`
(`/data/importer/config.yaml` in the container). Edit it with `t2i config` (the TUI validates
every field) or by hand. Unknown keys are rejected, so typos fail loudly.

**Secrets are never stored in `config.yaml`.** Every credential is a file path; the TUI writes
those files with mode `0600` in a `0700` directory.

Default paths below assume `TAKEOUT2IMMICH_HOME=/data/importer`.

## `immich`

| Key | Default | Meaning |
|---|---|---|
| `url` | `http://immich-server:2283` | Immich base URL (the compose service name works inside the project) |
| `api_key_file` | `/data/importer/secrets/immich_api_key` | File holding the Immich API key |

## `source`

Exactly one source, chosen by `type`.

### `type: drive` (Takeout delivered to Google Drive)

| Key | Default | Meaning |
|---|---|---|
| `rclone_remote` | `gdrive` | Remote name in `rclone.conf` |
| `folder` | `Takeout` | Folder in My Drive that Takeout writes to |
| `rclone_config_file` | `/data/importer/secrets/rclone.conf` | rclone config with the OAuth token |
| `rclone_binary` | `rclone` | |
| `use_trash` | `false` | `false` = delete permanently after validation (trash counts against quota) |
| `verify_md5_locally` | `true` | Re-hash each part after download and compare with Drive's MD5 |
| `auto_confirm` | `false` | `true` = import as soon as parts are downloaded, without waiting for `confirm`. Risky: the export may not be finished |

### `type: local` (zips already on disk)

| Key | Default | Meaning |
|---|---|---|
| `path` | — (required) | Folder containing `takeout-*.zip` |
| `delete_originals` | `false` | Delete the zips in `path` after validation |
| `auto_confirm` | `true` | Import as soon as the files are found |

### `type: direct`

Reserved for a future source; see [sources.md](sources.md).

## `staging`

| Key | Default | Meaning |
|---|---|---|
| `path` | `/data/staging` | Where downloaded parts are kept until cleanup |
| `min_free_gb` | `20` | Downloads stop rather than leave less than this free |

## `importer` (immich-go)

Passed to `immich-go upload from-google-photos`. All parts of an export go into one run.

| Key | Default | immich-go flag |
|---|---|---|
| `immich_go_binary` | `immich-go` | |
| `concurrent_tasks` | `8` | `--concurrent-tasks` (1–20) |
| `manage_burst` | `Stack` | `--manage-burst` |
| `manage_raw_jpeg` | `StackCoverRaw` | `--manage-raw-jpeg` |
| `manage_heic_jpeg` | `StackCoverHeic` | `--manage-heic-jpeg` |
| `include_unmatched` | `true` | `--include-unmatched` (files without a JSON sidecar) |
| `include_archived` | `true` | `--include-archived` |
| `include_partner` | `true` | `--include-partner` |
| `include_trashed` | `false` | `--include-trashed` |
| `sync_albums` | `true` | `--sync-albums` |
| `people_tag` | `true` | `--people-tag` |
| `takeout_tag` | `true` | `--takeout-tag` |
| `pause_immich_jobs` | `true` | `--pause-immich-jobs` |
| `on_errors` | `continue` | `--on-errors` (validation is the real gate) |
| `extra_flags` | `[]` | Appended verbatim |

`Keep*` choices for RAW/HEIC pairs drop one file of each pair; validation will then (correctly)
report those files as missing.

## `validation`

| Key | Default | Meaning |
|---|---|---|
| `enabled` | `true` | Check every media file against Immich after the import |
| `fail_on_missing` | `true` | Stop (no cleanup) if anything is missing |
| `report_dir` | `/data/importer/reports` | Validation reports and immich-go logs |
| `batch_size` | `1000` | Checksums per API call |
| `ignore_patterns` | `[]` | Filename globs never counted as missing, e.g. `*-edited.*` |

## `cleanup`

| Key | Default | Meaning |
|---|---|---|
| `delete_local_after_validation` | `true` | Delete staged zips (only files inside `staging.path`) |
| `delete_remote_after_validation` | `true` | Delete the export from the source (Drive) |

## `notifications`

A list. A `log` notifier is always useful (it writes the status file); add Home Assistant:

```yaml
notifications:
  - type: log
    status_file: /data/importer/state/status
  - type: homeassistant
    url: http://homeassistant.local:8123
    service: mobile_app_my_phone          # notify.mobile_app_my_phone
    token_file: /data/importer/secrets/homeassistant_token
    events: [ERROR, VALIDATION_FAILED, VALIDATION_PASSED, ACTION_REQUIRED]   # omit for all
```

Events: `EXPORT_DETECTED`, `DOWNLOAD_COMPLETE`, `IMPORT_COMPLETE`, `VALIDATION_PASSED`,
`VALIDATION_FAILED`, `CLEANUP_DONE`, `ERROR`, `ACTION_REQUIRED`.

## `runtime`

| Key | Default | Meaning |
|---|---|---|
| `poll_interval_s` | `300` | Seconds between passes of the `watch` loop (requests wake it early) |
| `state_db` | `/data/importer/state/state.db` | SQLite state |
| `heartbeat_file` | `/data/importer/state/heartbeat` | Used by the container healthcheck |
| `max_attempts` | `5` | Consecutive failures before a stage is marked `FAILED` |
| `log_level` | `INFO` | |

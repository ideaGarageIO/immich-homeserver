# immich-importer (`takeout2immich`)

Move a Google Photos Takeout export into [Immich](https://immich.app):
**download → verify → import → validate → clean up**, with resumable state, a TUI, and
Home Assistant notifications.

```
t2i config     # TUI: configure, and watch progress
t2i doctor     # check Immich, the source, tools and notifications
t2i status     # where each export is, and what to do next
t2i confirm    # tell it the Takeout export is complete
```

- Runs as a container next to Immich (`watch` loop) — see [docs/deployment.md](docs/deployment.md).
- Pluggable sources: `drive` (Takeout → Google Drive, via rclone) and `local` (zips on disk).
  A `direct` source is planned — see [docs/sources.md](docs/sources.md).
- Nothing is deleted until every photo/video is confirmed in Immich by checksum —
  see [docs/validation.md](docs/validation.md).

Documentation: [quickstart](docs/quickstart.md) · [Google Drive setup](docs/google-drive-setup.md) ·
[configuration](docs/configuration.md) · [sources](docs/sources.md) · [validation](docs/validation.md) ·
[deployment](docs/deployment.md) · [architecture](docs/architecture.md)

Tested with Immich v3.4.2, immich-go 0.32.0 and rclone 1.76.0.

## Development

```bash
uv venv -p 3.12 .venv && uv pip install -p .venv -e '.[dev]'
.venv/bin/pytest
```

A throwaway Immich for end-to-end testing: see the header of [compose.dev.yml](compose.dev.yml).

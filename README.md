# immich-homeserver

A self-hosted [Immich](https://immich.app) setup plus **immich-importer**, a tool that moves a
Google Photos library into Immich through Google Takeout — unattended, checksum-verified, and
validated against Immich before anything is deleted.

| Folder | What it is |
|---|---|
| [`deployment/`](deployment/) | Docker Compose for Immich + the importer, and the scripts that deploy it from a laptop to a server |
| [`immich-importer/`](immich-importer/) | The importer (`takeout2immich`, CLI alias `t2i`): Python package, container image, tests and docs |

## How the migration works

1. You request a Google Takeout export of Google Photos, delivered to **Google Drive**.
2. The importer (running next to Immich) sees the parts appear in Drive and downloads them with
   rclone, checking each part's MD5.
3. When Google emails you that the export is ready, you **confirm** it (one command or one button).
4. The importer runs [immich-go](https://github.com/simulot/immich-go) over all parts at once,
   then **validates** that every photo and video is in Immich by SHA-1.
5. Only if validation passes, it deletes the downloaded archives and the copy in Drive.
6. Home Assistant (optional) tells you about every step.

Start with [immich-importer/docs/quickstart.md](immich-importer/docs/quickstart.md).

## Deploying

```bash
cp deployment/deploy.example.yaml deployment/deploy.yaml   # your server (gitignored)
deployment/deploy.sh deploy                               # sync, back up DB, build, start
deployment/deploy.sh config                               # configure the importer (TUI)
```

See [immich-importer/docs/deployment.md](immich-importer/docs/deployment.md).

## Keeping private details out of git

Host paths, hostnames and similar details stay in gitignored files (`.env`,
`deployment/deploy.yaml`, `deployment/docker-compose.override.yml`). List any strings that must
never be published in a gitignored `.private-patterns` file and install the hook:

```bash
ln -sf ../../deployment/check-public.sh .git/hooks/pre-commit
```

`deploy.sh deploy` runs the same check.

## License

MIT — see [LICENSE](LICENSE).

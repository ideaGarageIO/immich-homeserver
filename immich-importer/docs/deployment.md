# Deployment

The importer runs as the `immich-importer` service in the same Compose project as Immich. Its
default command is `takeout2immich watch`: a loop that applies queued requests (confirm, retry,
...), checks the source, and moves each export through its stages. Everything — the CLI, the
TUI, rclone and immich-go — runs inside the container; nothing is installed on the host.

## The service

```yaml
  immich-importer:
    container_name: immich_importer
    build: ./immich-importer
    image: immich-importer:local
    command: ['watch']
    user: '${IMPORTER_UID:-1000}:${IMPORTER_GID:-1000}'
    volumes:
      - ${IMPORTER_DATA_PATH:-./importer-data}:/data/importer
      - ${IMPORTER_STAGING_PATH:?Set IMPORTER_STAGING_PATH in .env}:/data/staging
    depends_on:
      - immich-server
    restart: unless-stopped
```

| Host path | Container | Holds |
|---|---|---|
| `IMPORTER_DATA_PATH` | `/data/importer` | `config.yaml`, `secrets/`, `state/`, `reports/` |
| `IMPORTER_STAGING_PATH` | `/data/staging` | Downloaded Takeout parts (size of your export) |

Both must be writable by `IMPORTER_UID:IMPORTER_GID`. The container's healthcheck runs
`takeout2immich health` (the `watch` loop touches a heartbeat file every 30 s).

## Deploying from a laptop (`deployment/deploy.sh`)

The repo is the source of truth; `deploy.sh` pushes it to the server over SSH.

```bash
cp deployment/deploy.example.yaml deployment/deploy.yaml   # host, user, remote_dir (gitignored)
deployment/deploy.sh deploy
```

`deploy` does, in order:

1. `check-public.sh` — refuses to continue if any tracked file contains a private string.
2. Preflight: `.env` exists and defines `IMPORTER_STAGING_PATH`; the data/staging dirs exist and
   are writable.
3. Backs up the server's `docker-compose.yml` (and override) as `*.bak-<timestamp>`.
4. rsyncs `docker-compose.yml`, `docker-compose.override.yml` (if present locally),
   `backup-db.sh` and `example.env` into `remote_dir`, and `immich-importer/` into
   `remote_dir/immich-importer/`. **Never touched:** `.env`, `postgres/`, `importer-data/`,
   `db-backups/`, or anything else already on the server.
5. `docker compose config -q`, then `backup-db.sh` (a `pg_dumpall`, last 10 kept in
   `db-backups/`), then `docker compose up -d --build`.
6. Waits until Immich answers and every service is healthy, then runs `takeout2immich doctor`.

Other subcommands:

| Command | Does |
|---|---|
| `deploy.sh config` | Opens the TUI on the server (`ssh -t` + `docker compose exec`) |
| `deploy.sh status` / `doctor` | Importer status / checks |
| `deploy.sh confirm [ID]` | Confirms the Takeout export is complete |
| `deploy.sh logs` | Follows the importer logs |
| `deploy.sh rollback` | Restores the newest compose backup and restarts |

## Host-specific mounts

Keep mounts that only make sense on your machine (e.g. existing photo folders used as External
Libraries) in `deployment/docker-compose.override.yml` — gitignored, merged automatically by
Compose, and synced by `deploy.sh`. See `docker-compose.override.example.yml`.

## Later: published images

Once the image is published to GHCR, replace `build:` with
`image: ghcr.io/ideagarageio/immich-importer:<version>` and `deploy` no longer needs to build on
the server.

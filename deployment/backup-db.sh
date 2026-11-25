#!/usr/bin/env bash
# Runs ON THE SERVER (next to docker-compose.yml): dump the Immich database before compose changes.
# Keeps the 10 most recent dumps in ./db-backups.
set -euo pipefail
cd "$(dirname "$0")"

container=${DB_CONTAINER:-immich_postgres}
db_user=$(sed -nE 's/^DB_USERNAME=(.*)$/\1/p' .env | tail -1)
db_user=${db_user:-postgres}

if ! docker ps --format '{{.Names}}' | grep -qx "$container"; then
  echo "backup-db: $container is not running; skipping (nothing to back up yet)." >&2
  exit 0
fi

mkdir -p db-backups
chmod 700 db-backups
out="db-backups/immich-db-$(date +%Y%m%d-%H%M%S).sql.gz"
docker exec "$container" pg_dumpall --clean --if-exists --username="$db_user" | gzip > "$out"
size=$(stat -c %s "$out")
if (( size < 1024 )); then
  echo "backup-db: dump looks too small ($size bytes): $out" >&2
  exit 1
fi
ls -1t db-backups/immich-db-*.sql.gz | tail -n +11 | xargs -r rm --
echo "backup-db: $out ($(du -h "$out" | cut -f1))"

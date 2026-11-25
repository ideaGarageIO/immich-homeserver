#!/usr/bin/env bash
# Laptop -> server deployment and remote shortcuts. Reads deployment/deploy.yaml (gitignored).
#
#   deploy.sh deploy           sync files, back up the DB, build + start, health check
#   deploy.sh config           open the importer TUI on the server
#   deploy.sh status|doctor    importer status / health checks
#   deploy.sh confirm [ID]     confirm the Takeout export is complete
#   deploy.sh logs             follow the importer logs
#   deploy.sh rollback         restore the previous docker-compose.yml(+override) and restart
#
# Server-only files are never touched: .env, postgres/, bin/, importer-data/, db-backups/.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(dirname "$HERE")
CONF="$HERE/deploy.yaml"
[[ -f "$CONF" ]] || { echo "Missing $CONF (copy deploy.example.yaml)" >&2; exit 2; }

yaml_get() { sed -nE "s/^$1:[[:space:]]*\"?([^\"#]*[^\"#[:space:]])\"?.*$/\1/p" "$CONF" | head -1; }
HOST=$(yaml_get host)
RUSER=$(yaml_get user)
RDIR=$(yaml_get remote_dir)
TARGET="$RUSER@$HOST"
SERVICE=immich-importer

ssh_b() { ssh -o BatchMode=yes "$TARGET" "$@"; }
ssh_t() { ssh -t "$TARGET" "$@"; }
in_dir() { printf 'cd %s && %s' "$RDIR" "$1"; }
log() { printf '\033[1m==> %s\033[0m\n' "$*"; }

preflight() {
  log "Preflight on $TARGET:$RDIR"
  ssh_b "$(in_dir 'test -f .env || { echo "no .env in $PWD" >&2; exit 1; }
    for v in IMPORTER_STAGING_PATH; do
      grep -q "^$v=" .env || { echo "Add $v=... to $PWD/.env (see example.env)" >&2; exit 1; }
    done
    stage=$(sed -nE "s/^IMPORTER_STAGING_PATH=(.*)$/\1/p" .env | tail -1)
    data=$(sed -nE "s/^IMPORTER_DATA_PATH=(.*)$/\1/p" .env | tail -1); data=${data:-./importer-data}
    mkdir -p "$stage" "$data" && test -w "$stage" && test -w "$data"')"
}

cmd_deploy() {
  "$HERE/check-public.sh"
  preflight
  local ts; ts=$(date +%Y%m%d-%H%M%S)
  log "Backing up current compose files (.bak-$ts)"
  ssh_b "$(in_dir "cp -p docker-compose.yml docker-compose.yml.bak-$ts
    if [ -f docker-compose.override.yml ]; then cp -p docker-compose.override.yml docker-compose.override.yml.bak-$ts; fi")"

  log "Syncing files"
  rsync -a "$HERE/docker-compose.yml" "$HERE/backup-db.sh" "$HERE/example.env" "$TARGET:$RDIR/"
  if [[ -f "$HERE/docker-compose.override.yml" ]]; then
    rsync -a "$HERE/docker-compose.override.yml" "$TARGET:$RDIR/"
  fi
  rsync -a --delete \
    --exclude .venv --exclude __pycache__ --exclude .pytest_cache --exclude '*.egg-info' --exclude .dev \
    "$ROOT/immich-importer/" "$TARGET:$RDIR/immich-importer/"

  log "Validating compose config"
  ssh_b "$(in_dir 'docker compose config -q')"
  log "Backing up the database"
  ssh_b "$(in_dir './backup-db.sh')"
  log "Building and starting"
  ssh_b "$(in_dir 'docker compose up -d --build')"
  health
}

health() {
  log "Waiting for services to be healthy"
  for _ in $(seq 1 60); do
    if ssh_b "$(in_dir 'curl -fsS localhost:2283/api/server/ping >/dev/null && ! docker compose ps --format "{{.Health}}" | grep -qE "starting|unhealthy"')"; then
      ssh_b "$(in_dir 'docker compose ps --format "table {{.Name}}\t{{.Status}}"')"
      log "Importer doctor"
      ssh_b "$(in_dir "docker compose exec -T $SERVICE takeout2immich doctor")" || \
        echo "(doctor reports problems - run 'deploy.sh config' to finish configuration)"
      return 0
    fi
    sleep 5
  done
  echo "Services did not become healthy in time:" >&2
  ssh_b "$(in_dir 'docker compose ps')" >&2
  return 1
}

cmd_rollback() {
  local bak
  bak=$(ssh_b "$(in_dir 'ls -1t docker-compose.yml.bak-* 2>/dev/null | head -1')")
  [[ -n "$bak" ]] || { echo "No compose backup found" >&2; exit 1; }
  local ts=${bak#docker-compose.yml.bak-}
  log "Restoring compose files from $ts"
  ssh_b "$(in_dir "cp -p $bak docker-compose.yml
    if [ -f docker-compose.override.yml.bak-$ts ]; then cp -p docker-compose.override.yml.bak-$ts docker-compose.override.yml;
    else rm -f docker-compose.override.yml; fi
    docker compose up -d --remove-orphans")"
  health
}

case "${1:-}" in
  deploy) cmd_deploy ;;
  config) ssh_t "$(in_dir "docker compose exec $SERVICE takeout2immich config")" ;;
  status) ssh_b "$(in_dir "docker compose exec -T $SERVICE takeout2immich status")" ;;
  doctor) ssh_b "$(in_dir "docker compose exec -T $SERVICE takeout2immich doctor ${2:-}")" ;;
  confirm) ssh_b "$(in_dir "docker compose exec -T $SERVICE takeout2immich confirm ${2:-}")" ;;
  logs) ssh_t "$(in_dir "docker compose logs -f --tail 100 $SERVICE")" ;;
  health) health ;;
  rollback) cmd_rollback ;;
  *) sed -n '2,12p' "$0"; exit 2 ;;
esac

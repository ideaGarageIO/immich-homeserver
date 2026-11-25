#!/usr/bin/env bash
# Prepare the dev stack (compose.dev.yml): create the Immich admin, an API key, and a
# config.yaml that uses the local source on ./.dev/incoming.
set -euo pipefail
cd "$(dirname "$0")/.."

URL=http://127.0.0.1:2284/api
EMAIL=admin@example.com
PASS=devpassword
DATA=.dev/importer-data

echo "Waiting for Immich..."
for _ in $(seq 1 90); do
  curl -fsS "$URL/server/ping" >/dev/null 2>&1 && break
  sleep 2
done
curl -fsS "$URL/server/ping" >/dev/null

curl -fsS -X POST "$URL/auth/admin-sign-up" -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\",\"name\":\"Dev Admin\"}" >/dev/null 2>&1 || true
TOKEN=$(curl -fsS -X POST "$URL/auth/login" -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["accessToken"])')
KEY=$(curl -fsS -X POST "$URL/api-keys" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"name":"takeout2immich-dev","permissions":["all"]}' | python3 -c 'import json,sys; print(json.load(sys.stdin)["secret"])')

mkdir -p "$DATA/secrets"
chmod 700 "$DATA/secrets"
umask 077
printf '%s\n' "$KEY" > "$DATA/secrets/immich_api_key"
umask 022
cat > "$DATA/config.yaml" <<YAML
immich:
  url: http://immich-server:2283
  api_key_file: /data/importer/secrets/immich_api_key
source:
  type: local
  path: /data/takeout-local
  auto_confirm: false
staging:
  path: /data/staging
  min_free_gb: 1
runtime:
  poll_interval_s: 10
YAML
echo "Dev config written to $DATA/config.yaml (Immich UI: http://127.0.0.1:2284, $EMAIL / $PASS)"

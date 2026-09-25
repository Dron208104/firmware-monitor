#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
mkdir -p backups
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
name="firmware-monitor-$stamp.db"
docker compose exec -T app python -m app.manage backup --output "/data/$name"
docker compose cp "app:/data/$name" "backups/$name" >/dev/null
docker compose exec -T app rm -f "/data/$name"
chmod 600 "backups/$name" 2>/dev/null || true
echo "Резервная копия: backups/$name"

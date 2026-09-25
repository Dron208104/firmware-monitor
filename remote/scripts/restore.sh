#!/usr/bin/env sh
set -eu
[ "$#" -eq 1 ] || { echo "Использование: $0 backups/firmware-monitor-ДАТА.db" >&2; exit 2; }
cd "$(dirname "$0")/.."
backup="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
[ -f "$backup" ] || { echo "Файл резервной копии не найден." >&2; exit 1; }
docker compose stop app
docker compose run --rm -v "$backup:/restore/input.db:ro" app python -m app.manage restore --input /restore/input.db
docker compose up -d
echo "Восстановление завершено. Проверьте: docker compose ps"

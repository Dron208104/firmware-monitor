#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
docker compose config --quiet
docker compose ps
container="$(docker compose ps -q app)"
[ -n "$container" ] || { echo "Контейнер app не запущен." >&2; exit 1; }
status="$(docker inspect --format='{{.State.Health.Status}}' "$container")"
[ "$status" = healthy ] || { echo "Healthcheck: $status" >&2; exit 1; }
docker compose exec -T app python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3).read().decode())"
echo "Проверка завершена успешно."

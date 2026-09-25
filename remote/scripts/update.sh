#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
version="${1:-}"
[ -n "$version" ] || { echo "Использование: $0 1.1.0" >&2; exit 2; }
case "$version" in *[!0-9.]*|'') echo "Некорректный номер версии." >&2; exit 2;; esac

"./scripts/backup.sh"
current="$(sed -n 's/^APP_VERSION=//p' .env | tail -n 1)"
cp .env ".env.before-update-${current:-unknown}"
sed "s/^APP_VERSION=.*/APP_VERSION=$version/" .env > .env.next && mv .env.next .env

image="$(sed -n 's/^FIRMWARE_MONITOR_IMAGE=//p' .env | tail -n 1)"
if [ -n "$image" ] && printf '%s' "$image" | grep -q '/'; then
  base="${image%:*}"
  sed "s|^FIRMWARE_MONITOR_IMAGE=.*|FIRMWARE_MONITOR_IMAGE=$base:$version|" .env > .env.next && mv .env.next .env
  docker compose pull app
  docker compose up -d --no-build app
else
  docker compose up -d --build app
fi

echo "Ожидание healthcheck..."
i=0
until [ "$(docker inspect --format='{{.State.Health.Status}}' "$(docker compose ps -q app)" 2>/dev/null || true)" = healthy ]; do
  i=$((i+1)); [ "$i" -lt 40 ] || { echo "Обновление не прошло healthcheck. Инструкция отката: docs/UPDATE.md" >&2; exit 1; }; sleep 3
done
echo "Firmware Monitor обновлён до версии $version."

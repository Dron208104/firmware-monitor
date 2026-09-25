#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")/.."

command -v docker >/dev/null 2>&1 || { echo "Ошибка: Docker не установлен." >&2; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "Ошибка: Docker Compose v2 недоступен." >&2; exit 1; }

if [ ! -f .env ]; then
  cp .env.example .env
  if command -v openssl >/dev/null 2>&1; then
    key="$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '\n')"
  else
    echo "Ошибка: для генерации ENCRYPTION_KEY требуется openssl." >&2
    exit 1
  fi
  escaped_key="$(printf '%s' "$key" | sed 's/[&|]/\\&/g')"
  sed "s|^ENCRYPTION_KEY=.*|ENCRYPTION_KEY=$escaped_key|" .env.example > .env
  chmod 600 .env 2>/dev/null || true
  echo "Создан файл .env с уникальным ключом шифрования. Сохраните его резервную копию."
else
  echo "Используется существующий .env."
fi

if grep -q '^ENCRYPTION_KEY=replace-with-generated-fernet-key$' .env; then
  echo "Ошибка: замените ENCRYPTION_KEY в .env." >&2
  exit 1
fi

docker compose up -d --build
echo "Ожидание готовности приложения..."
i=0
until docker compose exec -T app python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3)" >/dev/null 2>&1; do
  i=$((i+1)); [ "$i" -lt 30 ] || { docker compose logs --tail=100 app; exit 1; }; sleep 2
done

if docker compose exec -T app python -c "from app.db import SessionLocal; from app.models import User; from sqlalchemy import select; db=SessionLocal(); raise SystemExit(0 if db.scalar(select(User.id)) else 1)"; then
  echo "Администратор уже существует."
else
  echo "Создание первого администратора."
  printf "Логин администратора [admin]: "
  read -r admin_name
  admin_name="${admin_name:-admin}"
  docker compose exec app python -m app.manage create-admin --username "$admin_name"
fi

port="$(sed -n 's/^APP_PORT=//p' .env | tail -n 1)"; port="${port:-8080}"
echo "Firmware Monitor установлен: http://127.0.0.1:$port"

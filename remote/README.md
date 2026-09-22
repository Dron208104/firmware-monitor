# Firmware Monitor

Внутренний сервис мониторинга версий прошивок сетевого оборудования. Это канонический каталог приложения; историческая копия `staging` не используется для сборки.

## Запуск

Требуются Docker и Docker Compose. Создайте `.env` по `.env.example`, задайте уникальный `ENCRYPTION_KEY` и создайте администратора после запуска:

```bash
cp .env.example .env
docker compose up -d --build
docker compose exec app python -m app.manage create-admin --username admin
curl http://127.0.0.1:8080/health
```

SQLite хранится в Docker volume `firmware_data`. Не удаляйте volume при обновлении приложения. Для работы через публичную сеть используйте HTTPS и установите `SESSION_COOKIE_SECURE=true`.

## Тесты

```bash
python3.13 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
```

Статические файлы обслуживаются приложением напрямую; отдельного frontend-сборщика нет.

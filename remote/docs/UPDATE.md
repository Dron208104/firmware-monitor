# Обновление и откат

Перед продуктивным обновлением прочитайте `CHANGELOG.md` и проверьте новую версию на тестовой копии базы.

## Обновление

```bash
git pull --ff-only
./scripts/update.sh 1.1.0
./scripts/verify.sh
```

Скрипт создаёт резервную копию, сохраняет прежний `.env`, обновляет образ или локальную сборку и ожидает healthcheck.

## Откат

```bash
git checkout v1.0.0
docker compose up -d --build app
```

Если новая версия изменила данные несовместимым образом, восстановите резервную копию: `./scripts/restore.sh backups/firmware-monitor-ДАТА.db`.

Не используйте `docker compose down -v`: команда удалит рабочий volume.

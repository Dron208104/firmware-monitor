# Эксплуатация

## Состояние и журналы

```bash
docker compose ps
./scripts/verify.sh
docker compose logs --tail=200 app
```

## Управление

```bash
docker compose restart app
docker compose exec app python -m app.manage reset-password --username admin
docker compose exec app python -m app.manage create-admin --username operator
```

Docker-журнал ограничен тремя файлами по 10 МБ. Отдельно контролируйте объём volume и `backups`.

Не удаляйте volume, не меняйте `ENCRYPTION_KEY` в работающей установке и перед восстановлением сохраняйте текущую базу.

# Firmware Monitor

Firmware Monitor — self-hosted система учёта сетевого оборудования и контроля версий прошивок. Она получает установленную версию по SNMP, проверяет официальные источники производителей и уведомляет ответственных сотрудников по электронной почте.

Текущая версия: **1.0.0**.

## Возможности

- оборудование, каталоги, поиск, фильтрация и сортировка;
- получение версии по SNMPv1, SNMPv2c и SNMPv3;
- официальные источники QTECH, MikroTik, Eltex, D-Link и Zyxel;
- ручные и автоматические проверки;
- SMTP-уведомления и повторные напоминания;
- роли администратора и наблюдателя;
- ограничение наблюдателя выбранными каталогами;
- журнал событий и история проверок;
- резервное копирование, восстановление и контролируемое обновление.

## Быстрая установка

Требования: Linux-сервер, Docker Engine, Docker Compose v2 и OpenSSL.

```bash
git clone https://github.com/Dron208104/firmware-monitor.git
cd firmware-monitor/remote
chmod +x scripts/*.sh
./scripts/install.sh
```

По умолчанию интерфейс доступен только локально: `http://127.0.0.1:8080`. Для доступа из сети измените `APP_BIND_ADDRESS` в `.env` или настройте reverse proxy с HTTPS.

Полная инструкция: [docs/INSTALLATION.md](docs/INSTALLATION.md).

## Основные команды

```bash
./scripts/verify.sh                  # проверить состояние
./scripts/backup.sh                  # создать резервную копию
./scripts/update.sh 1.1.0            # обновить версию
./scripts/restore.sh backups/file.db # восстановить базу
docker compose logs -f app           # посмотреть журнал
```

## Разработка

```bash
python3.13 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
docker compose up -d --build
```

Правила разработки и выпуска версий описаны в [CONTRIBUTING.md](CONTRIBUTING.md). История релизов находится в [CHANGELOG.md](CHANGELOG.md).

## Документация

- [Установка](docs/INSTALLATION.md)
- [Обновление и откат](docs/UPDATE.md)
- [Резервное копирование](docs/BACKUP.md)
- [Эксплуатация](docs/OPERATIONS.md)
- [Безопасность](docs/SECURITY.md)

## Важные данные

Рабочая база хранится в Docker volume проекта `firmware-monitor`. Файл `.env`, ключ `ENCRYPTION_KEY` и резервные копии нельзя добавлять в Git. Потеря `ENCRYPTION_KEY` сделает сохранённые SMTP- и SNMP-секреты недоступными.

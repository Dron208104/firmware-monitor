# Установка в организации

## Требования

- Linux x86_64/arm64;
- Docker Engine 25+ и Docker Compose v2;
- OpenSSL;
- 2 CPU, 2 ГБ RAM и 5 ГБ свободного места;
- доступ к официальным сайтам производителей и SMTP-серверу;
- UDP-доступ от сервера к управляемым устройствам на SNMP-порт.

## Установка из репозитория

```bash
git clone https://github.com/Dron208104/firmware-monitor.git
cd firmware-monitor/remote
chmod +x scripts/*.sh
./scripts/install.sh
```

Установщик создаст `.env`, сгенерирует ключ шифрования, соберёт контейнер, дождётся healthcheck и предложит создать первого администратора.

## Сетевой доступ

Безопасное значение по умолчанию:

```dotenv
APP_BIND_ADDRESS=127.0.0.1
APP_PORT=8080
```

При публикации через корпоративный reverse proxy оставьте loopback-адрес. Для прямого доступа из доверенной VLAN можно указать IP сервера или `0.0.0.0`, ограничив порт межсетевым экраном.

## HTTPS

TLS должен завершаться на reverse proxy или балансировщике. После включения HTTPS установите `SESSION_COOKIE_SECURE=true` и выполните `docker compose up -d app`.

## Проверка

```bash
./scripts/verify.sh
docker compose logs --tail=100 app
```

После входа настройте SMTP, профили SNMP, источники прошивок, расписание и пользователей.

# Аудит безопасности Firmware Monitor

## Финальная повторная проверка — 25.09.2026

Повторно проверены актуальная ветка `main`, закреплённые зависимости, backend, шаблоны, браузерный JavaScript, Docker-конфигурация, разграничение прав и Git-дерево. Проверка не является гарантией отсутствия неизвестных уязвимостей; активное сканирование реального корпоративного узла, сетевого оборудования и SMTP не выполнялось.

Результат после безопасных исправлений:

- `pip-audit`: известных уязвимостей в закреплённых production-зависимостях не найдено;
- Bandit: 0 High, 0 Medium, 4 Low; оставшиеся B105 — названия полей и тексты ошибок, не пароли или ключи;
- `pytest`: 136 тестов успешно, включая новые проверки timing-safe входа, ограничения памяти throttling и security headers;
- Python `compileall`, `node --check` и `git diff --check`: успешно;
- сборка Docker локально не завершилась: Docker BuildKit завис без вывода и был остановлен; CI продолжает собирать образ при изменениях;
- удалены неиспользуемые `catalog.js`, `catalog.css` и недокументированный генератор демонстрационных устройств `seed.py`;
- production-зависимости не удалялись: каждая используется непосредственно приложением или runtime;
- устранено различие Argon2-проверки для существующего и отсутствующего логина;
- process-local хранилище неудачных входов ограничено 10 000 ключами; для нескольких реплик по-прежнему рекомендуется Redis/общая БД;
- SQL миграции переведены с формируемого `IN (...)` на расширяемые bind-параметры;
- добавлены COOP, CORP, X-Permitted-Cross-Domain-Policies и условный HSTS при `SESSION_COOKIE_SECURE=true`;
- ранняя установка темы вынесена из inline JavaScript во внешний файл и теперь соответствует действующей CSP.

Сохраняющиеся архитектурные риски: администратор может направлять SNMP/SSH на доступные контейнеру IPv4-адреса; корпоративный SMTP может находиться в private-сети; полная защита от DNS rebinding требует egress firewall или прокси с IP pinning; `AUTH_DISABLED=true` нельзя использовать в рабочем окружении; для нескольких экземпляров приложения нужен общий rate limiter. Перед внешней публикацией обязательны HTTPS, `SESSION_COOKIE_SECURE=true`, firewall и согласованные allowlist CIDR/SMTP relay.

Дата аудита: 23.09.2026  
Область: локальный репозиторий `remote`, его тестовая БД и сервис из `compose.yaml`. Внешние сайты производителей, сетевые устройства, SMTP-серверы и узлы локальной сети не сканировались. Реальные письма и SNMP/SSH-запросы не отправлялись.

## 1. Область проверки и ограничения

Проверены FastAPI backend, Jinja/JavaScript frontend, SQLAlchemy/SQLite, авторизация и RBAC, SNMP/SSH-профили, SMTP, провайдеры прошивок, Dockerfile/Compose, зависимости, история Git и правила исключения. Реальные данные, `.env`, volumes, пароли и ключи не изменялись. Commit и push не выполнялись.

До аудита рабочее дерево уже содержало пользовательские изменения в backend, шаблонах, стилях, JavaScript и тестах, а также новые модули контроля доступа. Они сохранены без отката.

## 2. Архитектура и поверхность атаки

Стек: Python 3.13, FastAPI/Starlette, SQLAlchemy, SQLite, Jinja2, vanilla JavaScript, APScheduler, httpx/urllib, pysnmp/netmiko, SMTP. Отдельного frontend-сборщика и nginx в текущем Compose нет.

Потоки данных:

1. Браузер → порт `8080` → Uvicorn/FastAPI → SQLite в volume `/data`.
2. Backend → устройство по SNMP/SSH при явной проверке подключения.
3. Backend → allowlist-домены производителей при проверке прошивок.
4. Backend → настраиваемый SMTP-сервер при тесте и отправке уведомлений.
5. APScheduler → проверка моделей → база → выбранные почтовые уведомления.

Секреты: Argon2id-хэши паролей пользователей; SHA-256 хэши session token; SNMP/SMTP-секреты, зашифрованные Fernet-ключом из окружения. Cookie содержит случайный session token, а не пароль. Администратор управляет устройствами, источниками, SMTP, профилями и пользователями. Наблюдатель имеет read-only доступ только к назначенным каталогам.

## 3. Executive summary

Проект имеет хорошую базу: Argon2id, серверный RBAC, CSRF, HttpOnly/SameSite cookies, отзыв сессий, шифрование SNMP/SMTP-секретов, ORM-запросы, allowlist источников, тайм-ауты и ограничения размера ответов, non-root контейнер, `cap_drop: ALL`, `no-new-privileges`, зафиксированные версии зависимостей. Известных CVE в `requirements.txt` не найдено.

До исправлений подтверждены 2 High, 4 Medium, 5 Low и 2 Info. Главные риски: неограниченный размер входящего HTTP-тела; SMTP как средство обращения backend к произвольному TCP-узлу; проверка redirect-цели некоторых firmware-запросов только после сетевого обращения.

Вердикт до исправлений: **ТОЛЬКО ПОСЛЕ ИСПРАВЛЕНИЙ**.

## 4. Таблица находок

| ID | Критичность | Приоритет | CWE | Находка | Статус |
|---|---|---|---|---|---|
| FM-SEC-001 | High | P1 | CWE-400 | Нет общего лимита тела HTTP-запроса | **исправлено** |
| FM-SEC-002 | High | P1 | CWE-918 | Произвольный SMTP-хост позволяет серверные TCP-подключения | частично усилено, требуется политика сети |
| FM-SEC-003 | Medium | P1 | CWE-918 | Redirect проверяется после обращения в legacy/части firmware providers | **исправлено** |
| FM-SEC-004 | Medium | P2 | CWE-307 | Rate limit входа хранится только в памяти процесса и только на пару IP+логин | подтверждено |
| FM-SEC-005 | Medium | P2 | CWE-693 / CWE-1021 | Нет централизованных security/cache headers | **исправлено** |
| FM-SEC-006 | Medium | P2 | CWE-918 | Администратор может назначить устройству любой IPv4 и порт управления | подтверждено, архитектурное решение |
| FM-SEC-007 | Low | P3 | CWE-200 | OpenAPI/Swagger доступны любому вошедшему наблюдателю | **исправлено** |
| FM-SEC-008 | Low | P3 | CWE-16 | Compose публикует приложение на всех интерфейсах без TLS/reverse proxy | подтверждено |
| FM-SEC-009 | Low | P3 | CWE-778 | Аудит административных действий неполный | подтверждено |
| FM-SEC-010 | Low | P3 | CWE-16 | `AUTH_DISABLED=true` полностью отключает аутентификацию | подтверждено, диагностическая настройка |
| FM-SEC-011 | Low | P3 | CWE-1104 | Пакеты закреплены по версиям, но без hash-checking | подтверждено |
| FM-SEC-012 | Info | P3 | CWE-16 | Root filesystem контейнера остаётся writable, resource limits не заданы | подтверждено |
| FM-SEC-013 | Info | P3 | CWE-312 | Локальные SSH-ключи лежат рядом с репозиторием, но корректно исключены из Git | подтверждено |

## 5. Подробные находки

### FM-SEC-001 — неограниченный размер запроса

- Компонент: HTTP middleware/backend; все POST/PATCH endpoints, включая `/login`.
- Файл: `app/main.py`, создание приложения и middleware.
- Права: не требуются для `/login`.
- Условия: доступ к порту 8080.
- Влияние: крупные или chunked-запросы могут занять память/CPU воркера и ухудшить доступность.
- Доказательство: в приложении и Compose отсутствуют `Content-Length`/stream limits и nginx `client_max_body_size`; Starlette разбирает тело до endpoint.
- Ожидаемо: ранний `413 Payload Too Large` до разбора формы/JSON.
- Исправление: ASGI middleware с подсчётом реально прочитанных байтов и лимитом около 1 MiB; регрессионный тест для обычного и chunked-потока.

### FM-SEC-002 — SMTP SSRF/внутреннее TCP-подключение

- Компонент: `app/mailer.py`, `/api/settings/smtp`, `/api/settings/smtp/test`.
- Права: администратор и валидный CSRF.
- Условия: возможность сохранить SMTP-конфигурацию и нажать тест.
- Влияние: backend соединяется с произвольным hostname/IP и портом; это может использоваться для разведки внутренних SMTP/TCP-сервисов.
- Доказательство: `normalize_smtp_config` проверяет только непустой host и диапазон порта; `_send_email` передаёт их в `smtplib.SMTP/SMTP_SSL`.
- Ожидаемо: явная allowlist SMTP-хостов/сетей или отдельный relay; запрет loopback/link-local/metadata по умолчанию.
- Исправление: конфигурируемая allowlist. Автоматически не блокировать private IP без решения владельца: корпоративный SMTP часто внутренний.
- Регрессия: mock DNS для loopback/private/public и разрешённого внутреннего relay.

### FM-SEC-003 — проверка redirect после сетевого обращения

- Компонент: `app/vendors.py`, Eltex/Zyxel/D-Link providers.
- Endpoint: проверки отдельной модели/устройства и `/check-all`.
- Права: администратор; также фоновый планировщик использует сохранённые URL.
- Условия: разрешённый URL или сохранённая official URL отвечает redirect на private/link-local адрес либо DNS меняется между проверкой и соединением.
- Влияние: backend может выполнить GET к внутреннему HTTP-сервису.
- Доказательство: `follow_redirects=True` в legacy/Eltex/Zyxel; финальный URL валидируется после `get()`. D-Link `urlopen` также валидирует `geturl()` после запроса.
- Ожидаемо: redirects отключены; каждый `Location` валидируется до следующего запроса; число redirects ограничено. Для полной защиты нужна DNS/IP pinning на момент соединения.
- Исправление: общий безопасный fetch helper; минимум — ручной redirect loop с валидацией каждой цели.

### FM-SEC-004 — непостоянный и неполный login throttling

- Компонент: `app/auth.py`, `/login`.
- Права: не требуются.
- Влияние: перезапуск/несколько workers сбрасывают или разделяют лимит; перебор множества логинов с одного IP не ограничен глобально.
- Доказательство: `_attempts` — process-local `defaultdict`, ключ `IP:normalized_username`.
- Исправление: хранить попытки в БД/Redis, добавить отдельный лимит по IP и очистку; не менять текст ошибки.

### FM-SEC-005 — отсутствуют security headers

- Компонент: все HTML/API ответы.
- Влияние: clickjacking, более слабое ограничение XSS, возможное кеширование приватных страниц.
- Доказательство: нет CSP/frame-ancestors, X-Content-Type-Options, Referrer-Policy, Permissions-Policy и `Cache-Control: no-store` для приватных ответов.
- Исправление: централизованный middleware; HSTS не добавлять на HTTP-only стенде.

### FM-SEC-006 — произвольная цель управления устройством

- Компонент: `DeviceCreate.address`, `snmp_port`, legacy edit и connection test.
- Права: администратор.
- Влияние: приложение может использоваться как ограниченный сканер IPv4/портов внутри доступной контейнеру сети.
- Доказательство: принимается любой синтаксически корректный IPv4 и порт 1..65535; сетевой allowlist отсутствует.
- Исправление: настраиваемые CIDR `ALLOWED_DEVICE_NETWORKS` и допустимые management ports; миграция не нужна. Нельзя внедрять без определения рабочих подсетей.

### FM-SEC-007 — документация API доступна наблюдателю

- Компонент: `/docs`, `/redoc`, `/openapi.json`.
- Права: любой активный пользователь.
- Влияние: облегчает перечисление административных endpoint; прямого обхода RBAC не даёт.
- Исправление: отключить docs в production или ограничить их администратором.

### FM-SEC-008 — прямой HTTP на всех интерфейсах

- Компонент: `compose.yaml` (`8080:8080`).
- Влияние: при публикации за пределы доверенной сети cookie может идти без Secure; отсутствует TLS boundary.
- Исправление: bind `127.0.0.1:8080:8080` за reverse proxy либо явно ограничить firewall; HTTPS и `SESSION_COOKIE_SECURE=true`.

### FM-SEC-009 — пробелы аудита

- Компонент: административные изменения SMTP, источников, моделей, устройств, автоматизации.
- Влияние: расследование инцидента не показывает кто изменил критические сетевые настройки.
- Исправление: писать маскированные audit events без паролей/community.

### FM-SEC-010 — аварийное отключение auth

- Компонент: `AUTH_DISABLED` в middleware.
- Условия: ошибочная production-конфигурация.
- Влияние: все endpoint становятся анонимно доступны с правами фактического администратора.
- Исправление: разрешать только совместно с явным development mode и loopback bind либо убрать настройку из production.

### FM-SEC-011 — нет hash locking

- Компонент: `requirements.txt`.
- Влияние: компрометация index/артефакта сложнее обнаруживается, хотя версии закреплены.
- Исправление: генерировать lock с `--generate-hashes`, использовать доверенный index.

### FM-SEC-012 — hardening контейнера неполный

- Положительно: non-root user, все capabilities удалены, no-new-privileges, отдельный volume данных.
- Осталось: writable root filesystem, нет tmpfs и resource limits.
- Исправление: проверить `read_only: true`, `tmpfs: /tmp`, `pids_limit`, memory/cpu limits на тестовом стенде.

### FM-SEC-013 — локальные SSH-ключи около checkout

- Файлы не отслеживаются и попадают под `*_ed25519`; секретов в истории Git не обнаружено.
- Рекомендация: хранить ключи в `%USERPROFILE%\.ssh`, не рядом с проектом.

## 6. Исправленные уязвимости

- FM-SEC-001: добавлен ASGI middleware с реальным лимитом 1 MiB, проверкой `Content-Length` и подсчётом chunked body; превышение получает 413 до endpoint.
- FM-SEC-003: legacy, Eltex, Zyxel и D-Link теперь валидируют каждую redirect-цель до следующего соединения; redirects ограничены тремя; ответы читаются потоково с лимитом.
- FM-SEC-005: добавлены CSP, `frame-ancestors`, X-Frame-Options, nosniff, Referrer-Policy, Permissions-Policy и `Cache-Control: no-store` для динамических ответов. HSTS намеренно не добавлялся на HTTP-only стенде.
- FM-SEC-007: `/docs`, `/redoc` и `/openapi.json` включены в admin-only RBAC.
- FM-SEC-002 частично: SMTP до соединения блокирует localhost, loopback, link-local/cloud metadata, unspecified, multicast и reserved адреса. Private corporate SMTP сохранён для совместимости; полное закрытие требует allowlist.
- Docker: отключён заголовок Uvicorn `Server`.
- Добавлено 5 security regression tests в `tests/test_security_hardening.py`.

## 7. Неисправленные риски и причины

FM-SEC-002 и FM-SEC-006 требуют определения разрешённых SMTP relay и CIDR сетевых устройств. Автоматическое блокирование всех private ranges нарушит типовой сценарий внутреннего Firmware Monitor. DNS rebinding полностью устраняется только IP pinning/сетевой egress policy. FM-SEC-004 требует общего хранилища throttling для нескольких процессов. Инфраструктурные FM-SEC-008/012 требуют решения по reverse proxy и лимитам хоста.

## 8. SAST, dependency, secret и container scan

- `pip-audit`: известных уязвимостей в `requirements.txt` не найдено.
- Bandit после исправлений: 0 High, 2 Medium, 4 Low. B310 устранён. Оба B608 в миграции — false positive: значения берутся из статического tuple исходного кода, не из ввода. B105 — названия ключей/сообщения, не секреты.
- Secret scan: Gitleaks/TruffleHog отсутствуют. Локальный поиск рабочего дерева и всей Git-истории не выявил приватных ключей или реальных credentials. Найденные совпадения — `.env.example`, названия полей и тестовые фикстуры.
- Trivy отсутствует; container CVE scan не выполнен.
- Compose validation не выполнена: обязательный локальный `.env` отсутствует; он намеренно не создавался и не подменялся.

## 9. Динамические проверки

Использованы TestClient и отдельная временная SQLite БД; внешние подключения замокированы. Подтверждены: 401 без сессии, 403 viewer на административных API, серверная защита текущего/последнего администратора, CSRF, отзыв сессий после смены пароля, сокрытие SNMP/SMTP-секретов, валидация режимов SNMPv3, запрет локальных firmware URL, 413 для oversized body, блокировка loopback SMTP до соединения и проверка redirect до второго запроса.

Активный ZAP scan не выполнялся: ZAP не установлен. Реальный SMTP/SNMP/SSH и внешние firmware endpoints не вызывались.

## 10. Выполненные команды

`git status --short`, `git ls-files`, `git log`, `rg`, `git grep` по истории, `pip-audit -r requirements.txt`, `bandit -r app`, `docker compose config --quiet`, `pytest`, `compileall`, `node --check`, `git diff --check`. Команды с секретами не выполнялись и в отчёт не включены.

## 11. Результаты тестов и сборки

До security-исправлений функциональный набор: 115 passed. После исправлений: **120 passed**, Python compile, JavaScript syntax и `git diff --check` успешны. Отдельной frontend-сборки нет. Docker image не собран: локальный Docker Desktop daemon недоступен (`dockerDesktopLinuxEngine` не запущен). Чистая временная SQLite БД создаётся и мигрируется в полном тестовом прогоне.

## 12. Рекомендации перед production

1. Исправить FM-SEC-001 и FM-SEC-003.
2. Задать SMTP allowlist и CIDR устройств, затем закрыть FM-SEC-002/006.
3. Развернуть HTTPS reverse proxy, включить Secure cookie и ограничить bind/firewall.
4. Перенести login throttling в общее постоянное хранилище.
5. Добавить Trivy/Gitleaks и hash-locked requirements в CI.
6. Добавить централизованный audit trail критических настроек.

## 13. Чек-лист повторной проверки

- [ ] oversized и chunked body получают 413;
- [ ] redirect на loopback/private блокируется до соединения;
- [ ] SMTP разрешает только согласованный relay/сети;
- [ ] SNMP/SSH разрешены только в согласованных CIDR;
- [ ] viewer получает 403 на все admin API и docs;
- [ ] текущий и последний активный admin защищены backend;
- [ ] cookies Secure под HTTPS, HttpOnly и SameSite;
- [ ] CSP/frame/cache headers присутствуют;
- [ ] секреты не возвращаются API и не попадают в логи/diff;
- [ ] pip-audit, Bandit, Gitleaks и Trivy проходят в CI;
- [ ] тесты, чистая миграция и Docker healthcheck проходят.

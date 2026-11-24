# Автодеплой campus.flacoo.ru

GitHub Actions проверяет Ruff, ShellCheck, синтаксис JavaScript, оба production Compose,
собирает Docker-образ и запускает тесты приложения, Chromium и сценариев деплоя.
Дополнительный Docker-тест проверяет HTTP/ACME, HTTPS-проксирование, запрет приватного
API без Telegram-авторизации и автоматический reload nginx при замене сертификата.
Проверки работают на push и pull request. Автодеплой — только из main после всех проверок.
Артефакт содержит архив образа и `image.ref` с точным тегом сборки. При Re-run failed
jobs деплой использует этот тег, даже если номер попытки деплоя отличается от сборки.
Артефакт хранится один день; после его удаления используйте Re-run all jobs для новой сборки.
Android остаётся отдельным workflow и не блокирует деплой серверного приложения.

## Только три секрета GitHub

Settings → Secrets and variables → Actions:

| Secret | Значение |
| --- | --- |
| `SSH_HOST` | IPv4 или hostname VPS |
| `SSH_USER` | SSH-пользователь, например root |
| `SSH_PASSWORD` | Пароль этого пользователя |

SSH работает на порту 22. Для другого порта можно дополнительно задать SSH_PORT.
Публичный ключ, SSH_KNOWN_HOSTS и registry token не требуются. Используется
StrictHostKeyChecking=accept-new: первый ключ принимается автоматически, а остальные
соединения этого запуска проверяются по нему. Между запусками ключ не закрепляется;
независимой проверки подлинности первого соединения нет.

## Один раз: токен приложения

Локально подготовлены два игнорируемых Git файла:

- `.env` — UID/GID контейнера (1000:1000);
- `.private/.env` — BOT_TOKEN, OWNER_TELEGRAM_ID и настройки приложения.

В `.private/.env` уже задан MINI_APP_URL=https://campus.flacoo.ru. Заполните BOT_TOKEN
из BotFather и числовой OWNER_TELEGRAM_ID. Токен нельзя получить из SSH-пароля.
Не коммитьте заполненные файлы; workflow не загружает их из GitHub.

На сервере под выбранным SSH-пользователем:

```bash
umask 077
mkdir -p "$HOME/itmo-campus/.private"
nano "$HOME/itmo-campus/.private/.env"
```

Минимальное содержимое:

```dotenv
BOT_TOKEN=123456789:YOUR_BOT_TOKEN
OWNER_TELEGRAM_ID=123456789
MINI_APP_URL=https://campus.flacoo.ru
```

Можно вместо редактора загрузить подготовленный локальный `.private/.env` по SCP
в эту папку. Скрипт автоматически создаст остальные каталоги, `.env` с UID/GID и
выставит права для контейнера. Существующие настройки и данные сохраняются.
Если токен не заполнен, первый workflow создаст шаблон `.private/.env`, остановится
с понятным сообщением до запуска приложения и сертификата. Заполните файл и нажмите
Re-run all jobs. Это ошибка настройки deploy, а не падение тестов приложения.

Нужны Linux amd64, Docker Engine с Compose v2 (`up --wait`), bash, curl и util-linux
(flock). SSH-пользователь должен иметь доступ к Docker. Для Ubuntu при необходимости:

```bash
apt-get update
apt-get install -y curl util-linux
```

Образ содержит Chromium: оставьте место для архива и нескольких образов (несколько ГБ).
Старые образы автоматически не удаляются. Если старый бот работает на другом устройстве,
остановите его перед первым запуском на VPS: один Telegram-токен — один polling-процесс.
Старый cron с deploy/update.sh отключите.

## nginx и сертификат — тоже в Docker

Состав деплоя:

- проект `itmo-campus`, сервис `bot`, порт только 127.0.0.1:8787;
- проект `itmo-campus-gateway`, сервис `nginx`, host network, TCP/80 и TCP/443;
- сервис `certbot`, выпуск и продление Let's Encrypt через HTTP-01.

DNS campus.flacoo.ru должен вести на VPS; TCP/80 и TCP/443 должны быть свободны и
доступны извне. AAAA должна вести на рабочий IPv6 этого же сервера либо отсутствовать.
В предоставленном выводе ss эти порты были свободны. **Если вы уже добавили campus-блоки
в remnawave-nginx по предыдущей инструкции, удалите только эти campus-блоки и выполните
nginx -t / reload в том контейнере перед первым новым деплоем.** Иначе два nginx будут
конкурировать за 80/443. Существующие блоки neth и Unix-сокет оставьте.

При первом запуске workflow:

1. Загружает тот же образ, который прошёл тесты.
2. Поднимает nginx с HTTP-конфигурацией для ACME.
3. Выпускает сертификат campus.flacoo.ru через Certbot (принимает условия Let's Encrypt,
   регистрирует ACME-аккаунт без email, чтобы не требовать четвёртого секрета).
4. Проверяет и включает HTTPS; запускает постоянный контейнер продления.
5. Обновляет бота, ждёт healthcheck и проверяет HTTP и HTTPS приложения.

Certbot проверяет продление каждые 12 часов. nginx замечает замену сертификата в течение
60 секунд и выполняет nginx -t + reload. Сертификаты и ACME-данные хранятся в именованных
Docker volumes проекта gateway. Не удаляйте их через compose down -v / volume prune.
Ни Docker socket, ни секреты бота в nginx/Certbot не монтируются.

Настройка системного nginx, certbot.timer или ручной выпуск сертификата не нужны.
Remnawave, его Compose, сертификат neth и Unix-сокет скрипт не изменяет и не перезапускает.

## Проверка и перезапуск

После push/merge в main:

```bash
cd "$HOME/itmo-campus"
export CAMPUS_ROOT="$PWD"
export CAMPUS_IMAGE=$(cat current/image)
docker compose -p itmo-campus --env-file .env -f current/compose.production.yaml ps
docker compose -p itmo-campus-gateway --env-file .env -f current/compose.gateway.yaml ps
curl --fail https://campus.flacoo.ru/
```

После редактирования `.private/.env` достаточно перезапустить бота:

```bash
cd "$HOME/itmo-campus"
export CAMPUS_ROOT="$PWD"
export CAMPUS_IMAGE=$(cat current/image)
docker compose -p itmo-campus --env-file .env -f current/compose.production.yaml restart bot
```

Логи:

```bash
docker compose -p itmo-campus --env-file .env -f current/compose.production.yaml logs --tail=50 bot
docker compose -p itmo-campus-gateway --env-file .env -f current/compose.gateway.yaml logs --tail=50 nginx certbot
```

Скрипт сериализует деплои через flock; GitHub также выполняет deploy последовательно.
При ошибке HTTPS-шлюза ещё работающий бот не заменяется. При ошибке запуска нового бота
или итогового HTTP/HTTPS-запроса возвращается предыдущий образ/Compose бота; job остаётся
красным. Gateway управляется отдельно; его уже выпущенный сертификат сохраняется.
База при откате не откатывается: перед несовместимыми миграциями нужна резервная копия.
Пересоздание одного бота даёт короткий перерыв. Healthcheck не проверяет все внешние
сервисы ИТМО/почты; вход в них выполняет владелец аккаунта по основному README.

## Локальные проверки

```bash
python -m pip install -r requirements-dev.txt
ruff check .
shellcheck deploy/*.sh deploy/gateway/*.sh
docker build -t itmo-campus:ci-check .
docker run --rm --init --shm-size=1g -e TEST_ISU_BROWSER=1 \
  -v "$PWD/tests:/app/tests:ro" -v "$PWD/deploy:/app/deploy:ro" \
  itmo-campus:ci-check python -m unittest discover -s tests -v
python tests/gateway_smoke.py
```

Интеграционный тест использует временные самоподписанные сертификаты, временные Docker
контейнеры/volume, локальную БД и не обращается к Let's Encrypt или Telegram.
Реальный сертификат можно проверить только при деплое на VPS с доступным DNS/HTTP.

## Личный доступ и вход в ИТМО

Для автоматического развёртывания GitHub Actions использует секреты `CAMPUS_OWNER_ID` и `ADMIN_VERIFY_SHA256`. Первый содержит разрешённый числовой Telegram ID, второй — SHA-256 от случайного секрета команды `/verify`. Значения записываются в постоянный `.private/access.env` с правами 600. Сама команда хранится у владельца. При смене владельца существующей базы запуск требует устранить расхождение.

Кнопка входа открывает официальный сайт в виртуальном браузере через HTTPS в Mini App владельца. Окно закрывается при отключении устройства или через семь минут. Доступ к виртуальному экрану идёт через локальный Unix-сокет. Сессии Chromium, база и привязка будильника лежат в постоянном `$CAMPUS_ROOT/data`. Для переноса между разными серверами нужна согласованная копия данных и приватной конфигурации. Для входов, сделанных раньше на Mac, можно один раз авторизоваться на новом сервере. Администратор хоста имеет доступ к этим данным. Прекращение сессии самим ИТМО потребует нового входа.

Посторонние сообщения не создают ответов или записей в базе. В приватном чате владельца допускается три запуска и три попытки проверки за минуту. Шлюз nginx дополнительно ограничивает HTTP-запросы по клиентскому адресу и суммарно. Защиту канала сервера от объёмного сетевого трафика предоставляет хостинг.

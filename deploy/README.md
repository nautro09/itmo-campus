# Бот на Ubuntu 22.04

Понадобятся Git, Docker Engine с Compose v2 и пользователь с доступом к Docker. Команды выполняются под одним пользователем. [Установка Docker на Ubuntu](https://docs.docker.com/engine/install/ubuntu/)

## Первый запуск

```sh
git clone https://github.com/nautro09/itmo-campus.git ~/itmo-campus
cd ~/itmo-campus
umask 077
mkdir -p data .private
cp -n .env.example .private/.env
printf 'CAMPUS_UID=%s\nCAMPUS_GID=%s\n' "$(id -u)" "$(id -g)" > .env
nano .private/.env
```

В **.private/.env** заполни BOT_TOKEN и MINI_APP_URL (публичный HTTPS-адрес сервера), при необходимости добавь почтовые настройки. Настрой DNS и HTTPS. Например, в Caddy на хосте укажи свой домен и проксируй запросы:

```caddy
campus.example.org {
    reverse_proxy 127.0.0.1:8787
}
```

Перед переключением останови бота на Mac. Для переноса заданий, писем и привязки чата скопируй базу из остановленной папки data в data на сервере по SSH. У владельца контейнера должны быть права записи. Можно приватно перенести настройки Mac в .private/.env и заменить временный туннель постоянным адресом. Администратор хоста имеет доступ к этим файлам.

```sh
sh deploy/update.sh
docker compose ps
docker compose logs --tail=30 bot
```

Для первой привязки нового чата используй код из логов. В обычной работе графический экран не требуется. Для входа в ИТМО ID и ИСУ на сервере подключись с Mac по SSH с X11 forwarding (локально нужен работающий XQuartz, на сервере xauth и разрешённый X11Forwarding). Из этой SSH-сессии выполни:

```sh
cd ~/itmo-campus
docker compose stop bot
for source in itmo isu; do
  docker run --rm -it --init --network host --shm-size=1g \
    --user "$(id -u):$(id -g)" -e DISPLAY -e XAUTHORITY=/tmp/campus-xauth \
    -v "${XAUTHORITY:-$HOME/.Xauthority}:/tmp/campus-xauth:ro" \
    -v "$PWD/data:/app/data" itmo-campus:local python connect.py "$source" || break
done
docker compose up -d
```

Вход выполняет владелец учётной записи. Если ИТМО завершит сеанс, повтори вход для соответствующего источника.

## Обновления

Для ручного обновления выполни `sh deploy/update.sh` из папки проекта. Для автоматического запусти `crontab -e` под тем же пользователем и добавь:

```cron
*/5 * * * * /bin/sh "$HOME/itmo-campus/deploy/update.sh" >> "$HOME/itmo-campus/.private/update.log" 2>&1
```

Раз в пять минут сервер проверяет main. При новом коммите он собирает образ и пересоздаёт контейнер. Если сборка сорвётся, текущий контейнер продолжит работать, а cron повторит попытку. База, сеансы Chromium и секреты хранятся в каталогах на сервере и переживают пересоздание. Включи автозапуск службы Docker при загрузке Ubuntu. Политика unless-stopped поднимет бота после перезагрузки или падения процесса. Для проверки обновлений смотри .private/update.log и docker compose ps.

Если на сервере работает Hysteria, см. [варианты портов, конфигурацию Nginx и выпуск сертификата](nginx/README.md). Эти файлы подключаются вручную.

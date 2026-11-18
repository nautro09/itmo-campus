# Варианты HTTPS рядом с Hysteria

Это примеры для обсуждения с владельцем сервера. Compose не включает Nginx и не занимает публичные порты 80/443.

Сначала посмотри слушателей отдельно для TCP и UDP:

```sh
sudo ss -lntp '( sport = :80 or sport = :443 )'
sudo ss -lnup '( sport = :80 or sport = :443 )'
```

- Если Hysteria слушает только UDP/443, обычный HTTPS в Nginx может использовать TCP/443 на том же IP. Не включай HTTP/3 в этом блоке. Проверь также настройки TCP-маскировки Hysteria и её способ продления собственных сертификатов.
- Если TCP/80 и TCP/443 уже принимает Nginx или Caddy, добавь домен бота в существующий прокси. Примеры ниже предназначены для Nginx на хосте с ботом. У Caddy уже есть свой менеджер сертификатов.
- Если TCP/80 занят, DNS-01 позволяет подтвердить домен TXT-записью. Для автопродления настрой DNS-плагин Certbot для своего провайдера с минимальными правами. Это решает выпуск сертификата. Для входящего HTTPS всё ещё нужен доступный TCP-порт или существующий прокси.
- Если TCP/443 монопольно занят и его владелец не маршрутизирует HTTPS, можно использовать отдельный IP либо внешний HTTPS-туннель. Отдельный IP поможет, если слушатели привязаны к конкретным адресам. Для постоянного домена у туннеля должен быть устойчивый адрес. Останавливать Hysteria ради продления сертификата не требуется.

## Пример HTTP-01 для существующего или свободного Nginx

Направь DNS на сервер. Если есть AAAA, настрой также IPv6-listen и проверь маршрут. HTTP-01 требует публичного доступа к TCP/80. В обоих примерах замени campus.example.org реальным доменом. Сначала подключи только campus-http.conf через sites-enabled либо conf.d, в зависимости от установки. После установки nginx и certbot выполни:

```sh
sudo mkdir -p /var/www/letsencrypt/.well-known/acme-challenge
sudo nginx -t && sudo systemctl reload nginx
sudo certbot certonly --webroot -w /var/www/letsencrypt -d campus.example.org
```

Подключи campus-https.conf после выпуска. Оставь HTTP-блок для продлений, проверь конфигурацию и включи reload после успешного продления:

```sh
sudo nginx -t && sudo systemctl reload nginx
sudo install -d /etc/letsencrypt/renewal-hooks/deploy
printf '%s\n' '#!/bin/sh' 'nginx -t && systemctl reload nginx' | sudo tee /etc/letsencrypt/renewal-hooks/deploy/reload-campus-nginx >/dev/null
sudo chmod 755 /etc/letsencrypt/renewal-hooks/deploy/reload-campus-nginx
sudo systemctl enable --now certbot.timer
sudo certbot renew --dry-run
```

Укажи https://campus.example.org в MINI_APP_URL серверного .private/.env и перезапусти контейнер при переходе на домен. [Проверки Let's Encrypt](https://letsencrypt.org/docs/challenge-types/) · [Конфигурация Hysteria](https://v2.hysteria.network/docs/advanced/Full-Server-Config/)

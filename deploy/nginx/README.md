# nginx для campus.flacoo.ru

Актуальный вариант полностью работает в Docker:

- `../compose.gateway.yaml` — nginx + Certbot;
- `../gateway/http.conf` — HTTP и ACME;
- `../gateway/https.conf` — TLS и proxy_pass на 127.0.0.1:8787;
- `../setup-gateway.sh` — первый выпуск сертификата и включение HTTPS;
- `../gateway/nginx.sh` — reload при обновлении сертификата;
- `../gateway/renew.sh` — продление каждые 12 часов.

Вставлять campus-блоки в существующий remnawave-nginx больше не нужно. Новый nginx
использует свободные TCP/80 и TCP/443. Старый продолжает обслуживать neth через
Unix-сокет. Если campus-блоки из предыдущей инструкции уже добавлены в старый nginx,
удалите только их и выполните проверку/reload перед запуском нового gateway.

Полная подготовка, три секрета, заполнение .env и команды перезапуска:
[инструкция деплоя](../README.md).

Старые campus-http.conf и campus-https.conf в этом каталоге — общие примеры ручной
настройки, они не используются текущим CI/CD.

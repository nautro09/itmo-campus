#!/usr/bin/env bash
set -Eeuo pipefail
release=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
: "${CAMPUS_ROOT:?Set CAMPUS_ROOT}"
gateway() {
    docker compose --project-name itmo-campus-gateway --env-file "$CAMPUS_ROOT/.env" -f "$release/compose.gateway.yaml" "$@"
}
config_dir="$CAMPUS_ROOT/gateway/conf.d"
mkdir -p "$config_dir"
# nginx workers must be able to traverse the read-only configuration directory.
chmod 755 "$config_dir"
if [[ ! -f $config_dir/default.conf ]]; then
    install -m 644 "$release/gateway/http.conf" "$config_dir/default.conf"
fi
gateway config --quiet
gateway up -d --wait --wait-timeout 45 nginx
# Stop the renewal loop to avoid racing Certbot's certificate-directory lock.
gateway stop certbot
trap 'gateway up -d certbot || echo "Could not restart certificate renewal" >&2' EXIT
gateway run --rm --no-deps --entrypoint certbot certbot certonly \
    --webroot -w /var/www/acme --cert-name campus.flacoo.ru -d campus.flacoo.ru \
    --non-interactive --agree-tos --register-unsafely-without-email --keep-until-expiring

cp "$config_dir/default.conf" "$config_dir/previous.bak"
cat "$release/gateway/http.conf" "$release/gateway/https.conf" > "$config_dir/next.tmp"
chmod 644 "$config_dir/next.tmp"
mv -f "$config_dir/next.tmp" "$config_dir/default.conf"
if ! gateway exec -T nginx nginx -t || ! gateway exec -T nginx nginx -s reload; then
    mv -f "$config_dir/previous.bak" "$config_dir/default.conf"
    gateway exec -T nginx nginx -t && gateway exec -T nginx nginx -s reload
    exit 1
fi
gateway up -d certbot
trap - EXIT
curl --fail --silent --show-error --retry 5 --retry-all-errors --max-time 10 \
    --resolve campus.flacoo.ru:443:127.0.0.1 https://campus.flacoo.ru/healthz >/dev/null

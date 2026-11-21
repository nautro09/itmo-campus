#!/bin/sh
set -eu
certificate=/etc/letsencrypt/live/campus.flacoo.ru/fullchain.pem
watch_certificate() {
    previous=$(sha256sum "$certificate" 2>/dev/null || true)
    while sleep "${CERTIFICATE_CHECK_SECONDS:-60}"; do
        current=$(sha256sum "$certificate" 2>/dev/null || true)
        if [ -n "$current" ] && [ "$current" != "$previous" ]; then
            if nginx -t && nginx -s reload; then
                previous=$current
            fi
        fi
    done
}
watch_certificate &
exec nginx -g 'daemon off;'

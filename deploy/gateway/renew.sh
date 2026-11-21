#!/bin/sh
set -eu
trap 'exit 0' TERM INT
while :; do
    certbot renew --webroot -w /var/www/acme --non-interactive --quiet || echo 'Certificate renewal failed; will retry' >&2
    sleep 43200 &
    wait "$!"
done

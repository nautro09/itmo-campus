#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
exec 9>.private/update.lock
flock -n 9 || exit 0
git pull --ff-only origin main
revision=$(git rev-parse HEAD)
if [ "$(cat .private/deployed 2>/dev/null || true)" = "$revision" ]; then
    exit 0
fi
docker compose up -d --build --wait --wait-timeout 150
echo "$revision" > .private/deployed

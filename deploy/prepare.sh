#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
: "${CAMPUS_ROOT:?Set CAMPUS_ROOT}"
mkdir -p "$CAMPUS_ROOT/data" "$CAMPUS_ROOT/.private"
if [[ ! -f $CAMPUS_ROOT/.env ]]; then
    campus_uid=$(id -u)
    campus_gid=$(id -g)
    if [[ $campus_uid == 0 ]]; then campus_uid=1000; campus_gid=1000; fi
    printf 'CAMPUS_UID=%s\nCAMPUS_GID=%s\n' "$campus_uid" "$campus_gid" > "$CAMPUS_ROOT/.env"
    if [[ $(id -u) == 0 ]]; then
        chown "$campus_uid:$campus_gid" "$CAMPUS_ROOT/data" "$CAMPUS_ROOT/.private"
    fi
fi
if [[ ! -f $CAMPUS_ROOT/.private/.env ]]; then
    cp "$source_dir/app.env.example" "$CAMPUS_ROOT/.private/.env"
    echo "Created $CAMPUS_ROOT/.private/.env; fill BOT_TOKEN and OWNER_TELEGRAM_ID on the server."
fi
# Also handle a configuration uploaded by root before the first deployment.
if [[ $(id -u) == 0 ]]; then
    chown --reference="$CAMPUS_ROOT/.private" "$CAMPUS_ROOT/.private/.env"
fi
chmod 600 "$CAMPUS_ROOT/.private/.env"

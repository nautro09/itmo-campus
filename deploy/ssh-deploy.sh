#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

: "${SSH_HOST:?Set SSH_HOST secret}"
: "${SSH_USER:?Set SSH_USER secret}"
: "${SSH_PASSWORD:?Set SSH_PASSWORD secret}"
: "${GITHUB_SHA:?Missing GITHUB_SHA}"
: "${GITHUB_RUN_ID:?Missing GITHUB_RUN_ID}"
SSH_PORT=${SSH_PORT:-22}
[[ $SSH_HOST =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]*$ && $SSH_USER =~ ^[a-zA-Z_][a-zA-Z0-9_-]*$ ]] || {
    echo 'Use an IPv4 address / hostname and a plain SSH username' >&2; exit 1;
}
[[ $SSH_PORT =~ ^[0-9]{1,5}$ && $GITHUB_SHA =~ ^[0-9a-f]{40}$ && $GITHUB_RUN_ID =~ ^[0-9]+$ ]] || exit 1
[[ ${GITHUB_RUN_ATTEMPT:-1} =~ ^[0-9]+$ ]] || exit 1
export SSHPASS=$SSH_PASSWORD
unset SSH_PASSWORD
known_hosts=$(mktemp)
trap 'rm -f -- "$known_hosts"' EXIT
# Trust the first connection in this CI run; subsequent connections use that key.
options=(-o StrictHostKeyChecking=accept-new -o "UserKnownHostsFile=$known_hosts" -o ConnectTimeout=20
         -o ServerAliveInterval=15 -o ServerAliveCountMax=4 -o PubkeyAuthentication=no
         -o 'PreferredAuthentications=password,keyboard-interactive' -o NumberOfPasswordPrompts=1)
target="$SSH_USER@$SSH_HOST"
if [[ ${CHECK_LOGIN_ONLY:-0} == 1 ]]; then
    # Resolve the fixed Compose service on the SSH host.
    # shellcheck disable=SC2016
    sshpass -e ssh "${options[@]}" -p "$SSH_PORT" "$target" \
        'bot=$(docker ps -q --filter label=com.docker.compose.project=itmo-campus --filter label=com.docker.compose.service=bot); test -n "$bot" && docker exec -i "$bot" python -' < deploy/check-login.py
    exit
fi
remote="itmo-campus/releases/$GITHUB_SHA-$GITHUB_RUN_ID-${GITHUB_RUN_ATTEMPT:-1}"
sshpass -e ssh "${options[@]}" -p "$SSH_PORT" "$target" "umask 077; mkdir -p '$remote'"
sshpass -e scp "${options[@]}" -P "$SSH_PORT" \
    dist/image.tar.gz dist/image.ref deploy/compose.production.yaml deploy/compose.gateway.yaml \
    deploy/release.sh deploy/prepare.sh deploy/setup-gateway.sh deploy/app.env.example "$target:$remote/"
sshpass -e scp "${options[@]}" -P "$SSH_PORT" -r deploy/gateway "$target:$remote/"
if [[ -n ${CAMPUS_OWNER_ID:-} || -n ${ADMIN_VERIFY_SHA256:-} ]]; then
    [[ ${CAMPUS_OWNER_ID:-} =~ ^[1-9][0-9]{0,18}$ && ${ADMIN_VERIFY_SHA256:-} =~ ^[0-9a-f]{64}$ ]] || exit 1
    printf 'OWNER_TELEGRAM_ID=%s\nADMIN_VERIFY_SHA256=%s\n' "$CAMPUS_OWNER_ID" "$ADMIN_VERIFY_SHA256" |
        sshpass -e ssh "${options[@]}" -p "$SSH_PORT" "$target" "umask 077; cat > '$remote/access.env'"
fi
sshpass -e ssh "${options[@]}" -p "$SSH_PORT" "$target" "bash '$remote/release.sh' '$GITHUB_SHA'"

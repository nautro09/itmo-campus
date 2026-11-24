#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

revision=${1:?Usage: release.sh COMMIT_SHA}
[[ $revision =~ ^[0-9a-f]{40}$ ]] || { echo 'Invalid commit SHA' >&2; exit 1; }
release=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
export CAMPUS_ROOT
CAMPUS_ROOT=$(cd -- "$release/../.." && pwd)
release_id=${release##*/}
[[ $release_id =~ ^$revision(-[0-9]+-[0-9]+)?$ ]] || { echo 'Invalid release directory' >&2; exit 1; }
# A deploy-only rerun reuses an artifact built in an earlier run attempt.
# The release directory identifies this deployment, not the image build.
[[ -f $release/image.ref ]] || {
    echo 'Image metadata missing; run the full workflow from the updated commit' >&2
    exit 1
}
export CAMPUS_IMAGE
CAMPUS_IMAGE=$(cat "$release/image.ref")
[[ $CAMPUS_IMAGE =~ ^itmo-campus:$revision-[0-9]+-[0-9]+$ ]] || {
    echo 'Invalid image metadata or image belongs to another commit' >&2
    exit 1
}
cd "$CAMPUS_ROOT"

exec 9>"$CAMPUS_ROOT/deploy.lock"
flock -w 600 9 || { echo 'Another deployment is running' >&2; exit 1; }
bash "$release/prepare.sh"
[[ -s .private/.env && -d data && -f .env ]] || {
    echo 'Prepare data/, .env and .private/.env first; see deploy/README.md' >&2
    exit 1
}
grep -Eq '^BOT_TOKEN=.+:.+' .private/.env || {
    echo "Fill BOT_TOKEN in $CAMPUS_ROOT/.private/.env, then rerun the workflow" >&2
    exit 1
}
if [[ -f $release/access.env ]]; then
    install -m 600 "$release/access.env" .private/access.env.next
    if [[ $(id -u) == 0 ]]; then chown --reference=.private/.env .private/access.env.next; fi
    mv -f .private/access.env.next .private/access.env
    rm -- "$release/access.env"
fi
command -v curl >/dev/null
docker info >/dev/null
docker compose version

compose() {
    docker compose --project-name itmo-campus --env-file "$CAMPUS_ROOT/.env" -f "$1/compose.production.yaml" "${@:2}"
}
compose "$release" config --quiet
previous=''
if [[ -L current ]]; then
    previous=$(readlink -f current)
    [[ -f $previous/image ]] || { echo 'Previous release metadata missing' >&2; exit 1; }
fi

docker load --input "$release/image.tar.gz"
docker image inspect "$CAMPUS_IMAGE" >/dev/null
rm -- "$release/image.tar.gz"
printf '%s\n' "$CAMPUS_IMAGE" > "$release/image"

# Prepare HTTPS before replacing the running bot. Remnawave is a separate project.
bash "$release/setup-gateway.sh"

rollback() {
    trap - ERR HUP INT TERM
    echo 'Deployment failed; restoring previous release' >&2
    if [[ -n $previous ]]; then
        export CAMPUS_IMAGE
        CAMPUS_IMAGE=$(cat "$previous/image")
        if compose "$previous" up -d --no-build --pull never --wait --wait-timeout 180 bot; then
            echo 'Previous release restored' >&2
        else
            echo 'ROLLBACK FAILED: inspect docker compose status on the server' >&2
        fi
    else
        compose "$release" stop bot || true
        echo 'First deployment failed; no previous release exists' >&2
    fi
    exit 1
}
trap rollback ERR HUP INT TERM
compose "$release" up -d --no-build --pull never --wait --wait-timeout 180 bot
curl --fail --silent --show-error --retry 3 --retry-connrefused --max-time 10 http://127.0.0.1:8787/ >/dev/null
curl --fail --silent --show-error --retry 3 --retry-all-errors --max-time 10 \
    --resolve campus.flacoo.ru:443:127.0.0.1 https://campus.flacoo.ru/ >/dev/null

ln -sfn -- "$release" current.next
mv -Tf -- current.next current
trap - ERR HUP INT TERM
echo "Deployed $revision; container and HTTP checks passed"

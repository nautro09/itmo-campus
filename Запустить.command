#!/bin/sh
set -eu
cd "$(dirname "$0")"
umask 077
if [ ! -f .env ]; then
    cp .env.example .env
    chmod 600 .env
    echo 'Создан локальный .env. Заполни BOT_TOKEN и запусти снова.'
    exit 0
fi
if [ ! -x .venv/bin/python ]; then
    python3 -m venv .venv
fi
.venv/bin/python -m pip install --disable-pip-version-check -r requirements.txt
export PLAYWRIGHT_BROWSERS_PATH="$PWD/.browsers"
.venv/bin/python -m playwright install chromium
exec .venv/bin/python local_host.py

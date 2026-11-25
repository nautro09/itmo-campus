"""Check the deployed login browser with an empty, disposable profile."""
import asyncio
import os
import socket
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from playwright.async_api import Error, async_playwright

from inbox import ISU
from itmo import PORTAL, login_browser_error
from private_login import display


async def probe():
    os.umask(0o077)
    for folder in ("my-itmo-browser", "isu-browser"):
        profile = Path("/app/data") / folder
        writable = os.access(profile if profile.exists() else profile.parent, os.W_OK)
        lock = profile / "SingletonLock"
        foreign_lock = lock.is_symlink() and os.readlink(lock).rpartition("-")[0] != socket.gethostname()
        print(f"{folder}: writable={writable}, other-host lock={foreign_lock}", flush=True)
    with tempfile.TemporaryDirectory() as temp:
        async with display() as (env, _, __), async_playwright() as engine:
            try:
                context = await engine.chromium.launch_persistent_context(temp, env=env, headless=False)
            except Error as error:
                print(login_browser_error(error, "проверки", False))
                return False
            try:
                page = await context.new_page()
                passed = True
                for site in (PORTAL, ISU):
                    host = urlsplit(site).hostname
                    try:
                        response = await page.goto(site, wait_until="commit", timeout=20000)
                        print(f"{host}: HTTP {response.status if response else 'unknown'}", flush=True)
                        if not response or response.status >= 400:
                            passed = False
                    except Error as error:
                        print(login_browser_error(error, host, True), flush=True)
                        passed = False
                return passed
            finally:
                await context.close()


if __name__ == "__main__":
    raise SystemExit(0 if asyncio.run(probe()) else 1)

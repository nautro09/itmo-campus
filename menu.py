"""Register the Telegram chat menu for a fixed domain or a local Quick Tunnel."""
import asyncio
import os
import re
import shutil
import sys
from urllib.parse import urlsplit


async def register_menu(api, url, owner):
    menu = {"type": "web_app", "text": "Открыть Пару", "web_app": {"url": url}}
    await api.call("setChatMenuButton", menu_button=menu)
    if owner:
        await api.call("setChatMenuButton", chat_id=owner, menu_button=menu)


async def serve_menu(api, store):
    url = os.getenv("MINI_APP_URL", "").strip()
    if url:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Проверь публичный HTTPS-адрес в MINI_APP_URL.")
    tunnel = os.getenv("MINI_APP_TUNNEL", "").lower() == "cloudflare"
    if not (url or tunnel):
        print("Для кнопки «Открыть Пару» укажи MINI_APP_URL или MINI_APP_TUNNEL в .env.", flush=True)
        return
    binary = shutil.which("cloudflared") or "/opt/homebrew/bin/cloudflared"
    origin = "http://127.0.0.1:" + str(int(os.getenv("WEB_PORT") or 8787))
    while True:
        process = None
        try:
            target = url
            if not target:
                process = await asyncio.create_subprocess_exec(
                    binary, "tunnel", "--no-autoupdate", "--protocol", "http2", "--url", origin,
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
                target = await asyncio.wait_for(tunnel_url(process.stderr), 60)
            await register_menu(api, target, store.get("owner"))
            with store.db:
                store.set("wake_origin",target.rstrip("/"))
            print("Кнопка «Открыть Пару» установлена в Telegram.", flush=True)
            if not process:
                return
            # Drain diagnostics while cloudflared maintains and reconnects the tunnel.
            async for _ in process.stderr:
                pass
        except FileNotFoundError:
            print("Для MINI_APP_TUNNEL=cloudflare требуется cloudflared.", file=sys.stderr, flush=True)
            return
        except Exception as error:
            print("Кнопка Mini App пока недоступна:", type(error).__name__, file=sys.stderr, flush=True)
        finally:
            if process and process.returncode is None:
                try:
                    process.terminate()
                except ProcessLookupError:
                    pass
                try:
                    await asyncio.wait_for(process.wait(), 5)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
        await asyncio.sleep(10)


async def tunnel_url(stream):
    async for line in stream:
        match = re.search(rb'https://[a-z0-9-]+\.trycloudflare\.com(?=[\s|]|$)', line)
        if match:
            return match.group().decode("ascii")
    raise ConnectionError("Cloudflare не выдал адрес.")

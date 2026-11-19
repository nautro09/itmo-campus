"""Register the Telegram chat menu for a fixed domain or a local Quick Tunnel."""
import asyncio
from contextlib import asynccontextmanager
import os
from pathlib import Path
import re
import shutil
import sys
from urllib.parse import urlsplit


async def register_menu(api, url, owner):
    menu = {"type": "web_app", "text": "Открыть Пару", "web_app": {"url": url}}
    await api.call("setChatMenuButton", menu_button=menu)
    if owner:
        await api.call("setChatMenuButton", chat_id=owner, menu_button=menu)


async def publish(api, store, url):
    await register_menu(api, url, store.get("owner"))
    with store.db:
        old = store.get("wake_origin")
        if store.get("wake_device") and not store.get("wake_device_origin") and old:
            store.set("wake_device_origin", old)
        store.set("wake_origin", url.rstrip("/"))
    print("Кнопка «Открыть Пару» установлена в Telegram.", flush=True)


@asynccontextmanager
async def quick_tunnel(port):
    binary = shutil.which("cloudflared") or "/opt/homebrew/bin/cloudflared"
    process = await asyncio.create_subprocess_exec(
        binary, "tunnel", "--no-autoupdate", "--protocol", "http2", "--url", f"http://127.0.0.1:{port}",
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
    try:
        target = await asyncio.wait_for(tunnel_url(process.stderr), 60)
        yield target, process
    finally:
        if process.returncode is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(process.communicate(), 5)
            except asyncio.TimeoutError:
                process.kill()
                await process.communicate()


async def serve_menu(api, store):
    url = os.getenv("MINI_APP_URL", "").strip()
    address_file = os.getenv("PARA_MENU_FILE", "")
    if url:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Проверь публичный HTTPS-адрес в MINI_APP_URL.")
    if not (url or address_file or os.getenv("MINI_APP_TUNNEL", "").lower() == "cloudflare"):
        print("Для кнопки «Открыть Пару» укажи MINI_APP_URL или MINI_APP_TUNNEL в .env.", flush=True)
        return
    registered = ""
    while True:
        try:
            if url:
                await publish(api,store,url)
                return
            if address_file:
                path = Path(address_file)
                target = path.read_text(encoding="ascii").strip() if path.exists() else ""
                if target and registered != target and re.fullmatch(r"https://[a-z0-9-]+\.trycloudflare\.com",target):
                    await publish(api,store,target)
                    registered = target
                await asyncio.sleep(3)
                continue
            async with quick_tunnel(int(os.getenv("WEB_PORT") or 8787)) as (target, process):
                await publish(api,store,target)
                async for _ in process.stderr:
                    pass
        except FileNotFoundError:
            if not address_file:
                print("Для MINI_APP_TUNNEL=cloudflare требуется cloudflared.", file=sys.stderr, flush=True)
                return
        except Exception as error:
            print("Кнопка Mini App пока недоступна:", type(error).__name__, file=sys.stderr, flush=True)
        await asyncio.sleep(10)


async def tunnel_url(stream):
    while line := await stream.readline():
        match = re.search(rb'https://[a-z0-9-]+\.trycloudflare\.com(?=[\s|]|$)', line)
        if match:
            return match.group().decode("ascii")
    raise ConnectionError("Cloudflare не выдал адрес.")

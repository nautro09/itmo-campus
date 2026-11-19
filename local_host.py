"""Keep the Mac Quick Tunnel and its loopback listener while reloading the bot."""
import asyncio
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory

from dotenv import dotenv_values

from menu import quick_tunnel

ROOT = Path(__file__).resolve().parent


async def publish_url(path, port):
    while True:
        try:
            async with quick_tunnel(port) as (url, process):
                tmp = path.with_suffix(".new")
                tmp.write_text(url, encoding="ascii")
                os.replace(tmp, path)
                # Keep the pipe drained during long sessions.
                async for _ in process.stderr:
                    pass
        except (OSError, asyncio.TimeoutError) as error:
            print("Временный адрес пока недоступен ·", type(error).__name__, flush=True)
        finally:
            path.unlink(missing_ok=True)
        await asyncio.sleep(10)


def revision():
    try:
        head = subprocess.run(["git", "rev-parse", "--verify", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True, check=False)
    except OSError:
        return ""
    return head.stdout.strip() if head.returncode == 0 else ""


async def stop_process(process):
    if process.returncode is None:
        try:
            process.send_signal(signal.SIGINT)
            await asyncio.wait_for(process.wait(), 15)
        except asyncio.TimeoutError:
            process.kill()
        except ProcessLookupError:
            pass
    await process.wait()


async def serve(listener, address):
    loop = asyncio.get_running_loop()
    stopping, reload_bot = asyncio.Event(), asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        loop.add_signal_handler(sig, (reload_bot if sig == signal.SIGHUP else stopping).set)
    tunnel = asyncio.create_task(publish_url(address, listener.getsockname()[1]))
    stop = asyncio.create_task(stopping.wait())
    env = dict(os.environ, PARA_WEB_FD=str(listener.fileno()), PARA_MENU_FILE=str(address))
    try:
        while not stopping.is_set():
            head = revision()
            reload_bot.clear()
            process = await asyncio.create_subprocess_exec(sys.executable, str(ROOT/"bot.py"),
                cwd=ROOT, env=env, pass_fds=(listener.fileno(),))
            exited = asyncio.create_task(process.wait())
            changed = asyncio.create_task(reload_bot.wait())
            try:
                while True:
                    done, _ = await asyncio.wait((exited, changed, stop), timeout=30,
                                                 return_when=asyncio.FIRST_COMPLETED)
                    if stop in done:
                        return 0
                    if exited in done:
                        return process.returncode or 0
                    new_head = revision()
                    if changed in done or (head and new_head and head != new_head):
                        print("Обновляю бота на текущем HTTPS-адресе.", flush=True)
                        break
            finally:
                changed.cancel()
                await stop_process(process)
                await asyncio.gather(changed, exited, return_exceptions=True)
    finally:
        stop.cancel()
        tunnel.cancel()
        await asyncio.gather(stop, tunnel, return_exceptions=True)


def main():
    os.umask(0o077)
    settings = {**dotenv_values(ROOT/".env", interpolate=False), **os.environ}
    if (sys.platform != "darwin" or (settings.get("MINI_APP_URL") or "").strip()
            or (settings.get("MINI_APP_TUNNEL") or "").lower() != "cloudflare"
            or (settings.get("WEB_HOST") or "127.0.0.1") != "127.0.0.1"):
        os.execl(sys.executable, sys.executable, str(ROOT/"bot.py"))
    data = ROOT/"data"
    data.mkdir(mode=0o700, exist_ok=True)
    with TemporaryDirectory(prefix="local-menu-", dir=data) as tmp:
        try:
            listener = socket.create_server(("127.0.0.1", int(settings.get("WEB_PORT") or 8787)))
        except OSError as exc:
            raise SystemExit("Не удалось открыть порт Пары. Проверь, запущен ли бот в другом окне.") from exc
        with listener:
            raise SystemExit(asyncio.run(serve(listener, Path(tmp)/"address")))


if __name__ == "__main__":
    main()

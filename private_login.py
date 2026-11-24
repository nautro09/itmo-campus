"""An ephemeral owner-only viewer for a single ITMO sign-in."""
import asyncio
import base64
import hashlib
import hmac
import os
from pathlib import Path
import secrets
import shutil
import tempfile
import time
from contextlib import asynccontextmanager
from html.parser import HTMLParser

from aiohttp import web, WSMsgType

ASSETS = Path("/usr/share/novnc")


class InlineScripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inline = False
        self.hashes = []

    def handle_starttag(self, tag, attrs):
        self.inline = tag == "script" and "src" not in dict(attrs)

    def handle_endtag(self, tag):
        self.inline = False

    def handle_data(self, data):
        if self.inline and data.strip():
            digest = base64.b64encode(hashlib.sha256(data.encode()).digest()).decode()
            self.hashes.append("'sha256-" + digest + "'")


def viewer_policy():
    parser = InlineScripts()
    parser.feed((ASSETS / "vnc.html").read_text())
    return ("default-src 'self'; script-src 'self' " + " ".join(parser.hashes)
            + "; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; "
              "object-src 'none'; base-uri 'self'; form-action 'none'")


@asynccontextmanager
async def display():
    with tempfile.TemporaryDirectory(prefix="para-screen-") as directory:
        authority = Path(directory) / "auth"
        authority.touch(mode=0o600)
        sock = Path(directory) / "viewer.sock"
        number = 1000 + secrets.randbelow(30000)
        name = f":{number}"
        auth = await asyncio.create_subprocess_exec("xauth","-f",str(authority),"source","-",
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.DEVNULL)
        await auth.communicate(f"add {name} . {secrets.token_hex(16)}\n".encode())
        if auth.returncode:
            raise RuntimeError("xauth")
        proc = await asyncio.create_subprocess_exec("Xtigervnc",name,"-auth",str(authority),
            "-geometry","1000x780","-depth","24","-nolisten","tcp","-rfbport","-1",
            "-rfbunixpath",str(sock),"-rfbunixmode","0600","-SecurityTypes","None",
            "-AcceptCutText=0","-SendCutText=0",stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL)
        try:
            for _ in range(100):
                if proc.returncode is not None:
                    raise RuntimeError("virtual display")
                if sock.is_socket():
                    break
                await asyncio.sleep(.05)
            reader, writer = await asyncio.open_unix_connection(sock)
            try:
                env = {k:os.environ[k] for k in ("PATH","HOME","LANG","TZ","LD_LIBRARY_PATH") if k in os.environ}
                yield {**env, "DISPLAY":name, "XAUTHORITY":str(authority)}, reader, writer
            finally:
                writer.close()
                await writer.wait_closed()
        finally:
            if proc.returncode is None:
                proc.terminate()
            await proc.wait()


class PrivateLogin:
    def __init__(self, bot, authorize):
        self.bot, self.authorize = bot, authorize
        self.ticket = None
        self.active = False
        self.last = -100.
        self.available = (ASSETS / "vnc.html").is_file() and bool(shutil.which("Xtigervnc"))

    async def issue(self, request):
        if not self.authorize(request):
            raise web.HTTPForbidden()
        source = request.match_info["source"]
        if not self.available:
            raise web.HTTPServiceUnavailable(text="Приватный вход доступен в серверной версии Docker.")
        now = time.monotonic()
        if self.active or now-self.last < 3:
            raise web.HTTPTooManyRequests(text="Окно уже открыто или только что запрошено.")
        self.last = now
        key = secrets.token_urlsafe(32)
        self.ticket = (key, now+45, source)
        response = web.json_response({"viewer":"/login.html"})
        # Partition by the embedding site so Telegram Web works with third-party cookies blocked.
        response.headers.add("Set-Cookie", f"__Secure-para-login={key}; Max-Age=45; Path=/login/socket; "
                             "HttpOnly; Secure; SameSite=None; Partitioned")
        return response

    async def socket(self, request):
        origin = self.bot.s.get("wake_origin") or os.getenv("MINI_APP_URL","").rstrip("/")
        if not origin or request.headers.get("Origin") != origin or not self.ticket or self.active:
            raise web.HTTPForbidden()
        key, expires, source = self.ticket
        supplied = request.cookies.get("__Secure-para-login","")
        if expires <= time.monotonic() or not hmac.compare_digest(key.encode(),supplied.encode()):
            raise web.HTTPForbidden()
        ws=web.WebSocketResponse(protocols=("binary",),max_msg_size=256*1024,heartbeat=20,compress=False)
        if not ws.can_prepare(request).ok:
            raise web.HTTPBadRequest()
        self.ticket=None
        self.active=True
        try:
            await ws.prepare(request)
            await asyncio.wait_for(self.session(ws,source),timeout=420)
        except (ConnectionError,RuntimeError,asyncio.TimeoutError,OSError):
            pass
        finally:
            self.active=False
            await ws.close()
        return ws

    async def session(self, ws, source):
        async with display() as (env, reader, writer):
            async def output():
                while chunk := await reader.read(65536):
                    await ws.send_bytes(chunk)
            async def inputs():
                async for message in ws:
                    if message.type != WSMsgType.BINARY:
                        break
                    writer.write(message.data)
                    await writer.drain()
            login=self.bot.sign_into_inbox if source=="isu" else self.bot.sign_in
            tasks=[asyncio.create_task(f) for f in (output(),inputs(),login(env))]
            try:
                done,_=await asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks,return_exceptions=True)

    def register(self,app):
        app.router.add_post("/login/open/{source:itmo|isu}",self.issue)
        app.router.add_get("/login/socket",self.socket)
        if self.available:
            app.router.add_static("/viewer/",ASSETS,show_index=False)

"""Loopback-only Android instrumentation fixture using the production wake routes."""
import ssl
import sys
from datetime import datetime, timedelta
from pathlib import Path

from aiohttp import web

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import wake
from itmo import MSK
from store import Store

store = Store(":memory:")
now = datetime.now(MSK)
tomorrow = (now.date() + timedelta(days=1)).isoformat()
code = "abcdefghijklmnopqrstuvwx"
site = "https://127.0.0.1:18787"
with store.db:
    store.set("wake_on", True)
    store.set("wake_rules", "08:10=06:20, 09:50=08:30, 13:30=11:00")
    store.set("cache", {tomorrow: {"checked": now.isoformat(), "lessons": [
        {"time_start": "09:50", "format": "Очно - дистанционный", "building": "A"}]}})
    store.set("latest_dates", [tomorrow])
    store.set("wake_origin", site)
    store.set("wake_pair", {"hash": wake.digest(code), "until": now.timestamp()+600})

async def scenario(request):
    with store.db:
        step = request.match_info["step"]
        if step == "relink":
            store.set("wake_pair", {"hash": wake.digest(code), "until": datetime.now(MSK).timestamp()+120})
        elif step == "reschedule":
            store.set("wake_rules", "09:50=07:45")
        elif step == "revoke":
            wake.revoke(store)
        elif step == "verified" and (store.get("wake_ack") or {}).get("rank") != 3:
            raise web.HTTPConflict()
    return web.Response(text="ok")

app = web.Application()
wake.register(app, store)
app.router.add_post("/test/{step:relink|reschedule|revoke|verified}", scenario)
tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
tls.load_cert_chain(*sys.argv[1:3])
web.run_app(app, host="127.0.0.1", port=18787, ssl_context=tls, access_log=None)

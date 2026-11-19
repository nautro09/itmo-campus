"""Owner settings and a separate, alarm-only device API."""
import hashlib
import hmac
import json
import re
import secrets
import time
from datetime import datetime, timedelta

from aiohttp import web
from extras import onsite
from itmo import MSK

PAIR_LABEL = "Привязать будильник телефона к расписанию"
DEFAULTS = dict(wake_free_off=False, wake_on=False, wake_prep=40, wake_online=20,
                wake_rules="08:10=06:20, 09:50=08:30")
CLOCK = r"(?:[01]\d|2[0-3]):[0-5]\d"


def rules(text):
    if not isinstance(text, str) or len(text) > 500:
        raise ValueError("Слишком длинный список правил.")
    result = {}
    for entry in text.split(",") if text.strip() else []:
        match = re.fullmatch(rf"\s*({CLOCK})\s*=\s*({CLOCK})\s*", entry)
        if not match or match[2] >= match[1] or match[1] in result:
            raise ValueError("Пример: 08:10=06:20, 09:50=08:30. Подъём должен быть раньше пары.")
        result[match[1]] = match[2]
    return result


def plan(store, now=None):
    now = now or datetime.now(MSK)
    cache = store.get("cache", {})
    latest = store.get("latest_dates", [])
    custom = rules(store.get("wake_rules", DEFAULTS["wake_rules"]))
    days = []
    for offset in (0, 1):
        day = (now.date()+timedelta(days=offset)).isoformat()
        row = {"day":day, "action":"keep"}
        days.append(row)
        if not store.get("wake_on", False):
            row["action"] = "cancel"
            continue
        entry = cache.get(day)
        if not entry or day not in latest or store.get("source_error"):
            continue
        checked = datetime.fromisoformat(entry["checked"])
        if not timedelta(0) <= now-checked <= timedelta(hours=2):
            continue
        lessons = entry["lessons"]
        if not lessons:
            row["action"] = "cancel"
            continue
        start = min(x["time_start"] for x in lessons)
        first = [x for x in lessons if x["time_start"] == start]
        begins = datetime.fromisoformat(day+"T"+start).replace(tzinfo=MSK)
        leads = []
        for lesson in first:
            if not onsite(lesson):
                leads.append(store.get("wake_online",20))
            elif start in custom:
                wake = datetime.fromisoformat(day+"T"+custom[start]).replace(tzinfo=MSK)
                leads.append(int((begins-wake).total_seconds()//60))
            else:
                travel = store.get("campus_minutes",{}).get(lesson.get("building"),store.get("travel_minutes",35))
                leads.append(travel+store.get("wake_prep",40))
        at = begins-timedelta(minutes=max(leads))
        if at > now:
            row.update(action="set", at=int(at.timestamp()))
    return days


def proposal(store, now=None):
    days = plan(store, now)
    if not store.get("wake_on",False):
        return {"day":days[1]["day"],"action":"off"}
    row = days[0] if days[0]["action"]=="set" else days[1]
    if row["action"]=="cancel" and not store.get("wake_free_off",False):
        return dict(row,action="free")
    return row


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def status(store):
    info = store.get("wake_ack")
    if not store.get("wake_device"):
        return "Телефон не привязан."
    if not info:
        return "Телефон привязан. Ожидаю подтверждения будильника."
    last = store.get("wake_last_seen")
    status = "Последний ответ телефона · " + (datetime.fromisoformat(last).strftime("%d.%m %H:%M МСК") if last else info["time"]) + "\n" + info["text"]
    if last and datetime.now(MSK) - datetime.fromisoformat(last) > timedelta(minutes=45):
        status += "\nТелефон давно не выходил на связь. Проверь адрес сервера и фоновую работу APK."
    return status


def pair_text(store):
    origin = store.get("wake_origin")
    if not origin:
        raise ValueError("Для привязки нужен действующий HTTPS-адрес приложения.")
    code = secrets.token_urlsafe(18)
    store.set("wake_pair", {"hash":digest(code), "until":time.time()+300})
    return f"В приложении на телефоне введи адрес и одноразовый код. Код действует 5 минут. Новая привязка заменяет прежний телефон.\n\n{origin}\n{code}"


def revoke(store):
    for key in ("wake_pair","wake_device","wake_ack","wake_last_seen"):
        store.set(key,None)


def register(app, store):
    async def device(request):
        auth = request.headers.get("Authorization","")
        if not auth.startswith("Bearer ") or len(auth)>160:
            raise web.HTTPUnauthorized()
        hashed = digest(auth[7:])
        op = request.match_info["op"]
        if op == "pair":
            ticket = store.get("wake_pair") or {}
            if ticket.get("until",0)<time.time() or not hmac.compare_digest(ticket.get("hash",""),hashed):
                raise web.HTTPUnauthorized()
            secret = secrets.token_urlsafe(32)
            with store.db:
                revoke(store)
                store.set("wake_device",digest(secret))
            return web.json_response({"token":secret})
        key = store.get("wake_device") or ""
        nonce = request.headers.get("X-Wake-Nonce","")
        stamp = request.headers.get("X-Wake-Time","")
        ack = request.headers.get("X-Wake-Revision","")
        if (not key or not re.fullmatch(r"[0-9a-f]{32}",nonce) or not re.fullmatch(r"[0-9]{10}",stamp)
                or abs(time.time()-int(stamp))>120 or not re.fullmatch(r"[a-f0-9]{0,64}",ack)):
            raise web.HTTPUnauthorized()
        signed = f"{op}\n{stamp}\n{nonce}\n{ack}"
        expected = hmac.digest(key.encode(),signed.encode(),"sha256").hex()
        if not hmac.compare_digest(expected.encode(),auth[7:].encode()):
            raise web.HTTPUnauthorized()

        def reply(data):
            body = json.dumps(data,separators=(",",":")).encode()
            mac = hmac.digest(key.encode(),nonce.encode()+b"\n"+body,"sha256").hex()
            return web.Response(body=body,content_type="application/json",headers={"X-Wake-MAC":mac})
        stages = {"received":"Телефон получил расчёт", "opened":"Открыты штатные Часы", "confirmed":"Пользователь подтвердил изменение в Часах"}
        if op=="nativeplan" or op in stages:
            row = proposal(store)
            revision = digest(json.dumps(row,sort_keys=True))
            if op=="nativeplan":
                settings = {name: store.get(name, default) for name, default in DEFAULTS.items()}
                settings["travel_minutes"] = store.get("travel_minutes", 35)
                return reply({"proposal":row,"revision":revision,"settings":settings})
            if not hmac.compare_digest(revision,ack):
                raise web.HTTPConflict()
            if op!="received" and row["action"] not in ("set","cancel"):
                raise web.HTTPConflict()
            with store.db:
                store.set("wake_last_seen", datetime.now(MSK).isoformat())
            old = store.get("wake_ack") or {}
            rank = list(stages).index(op)
            if old.get("revision")!=revision or rank>old.get("rank",-1):
                label = datetime.fromtimestamp(row["at"],MSK).strftime("%H:%M МСК") if "at" in row else {"free":"свободный день","cancel":"выключить","off":"режим выключен","keep":"сохранить прежнее время"}[row["action"]]
                with store.db:
                    store.set("wake_ack",{"revision":revision,"rank":rank,"time":datetime.now(MSK).strftime("%d.%m %H:%M МСК"),
                                          "text":f"{stages[op]} · {row['day']} · {label}"})
            return reply({"ok":True})
        days = plan(store)
        revision = digest(str(days))
        if op=="plan":
            return reply({"days":days,"revision":revision})
        if not hmac.compare_digest(request.headers.get("X-Wake-Revision","")[:64].encode(),revision.encode()):
            raise web.HTTPConflict()
        messages = []
        for row in days:
            when = datetime.fromtimestamp(row["at"],MSK).strftime("%H:%M") if row["action"]=="set" else ""
            label = {"set":"подъём "+when,"cancel":"выключен","keep":"без изменений"}[row["action"]]
            messages.append(row["day"]+" · "+label)
        with store.db:
            old = store.get("wake_ack") or {}
            text = "\n".join(messages)
            store.set("wake_ack",{"time":datetime.now(MSK).strftime("%d.%m %H:%M МСК"),"text":text})
            if old.get("text")!=text and any(row["action"]=="set" for row in days):
                store.post(store.get("owner"),"⏰ Приложение версии 1 подтвердило свой будильник\n"+text,delivery="background")
        return reply({"ok":True})
    app.router.add_post("/device/{op:pair|plan|ack|nativeplan|received|opened|confirmed}",device)

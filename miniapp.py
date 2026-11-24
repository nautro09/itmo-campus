import hashlib
import hmac
import json
import os
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl

from aiohttp import web
import wake
from private_login import PrivateLogin, viewer_policy
from extras import campus_names, draft_task, weekly_report
from itmo import MSK
from planner import REMIND

WEB = Path(__file__).resolve().parent/"web"
DEFAULTS = dict(**wake.DEFAULTS,notify_isu=True,notify_imap=True,notify_bars=True,notify_schedule=True,notify_due=True,quiet_on=True,quiet_start="23:00",quiet_end="07:00",quiet_first=True,theme="paper",morning_on=True,morning_time="07:30",interval=1,travel_on=False,
                travel_minutes=35,campus_minutes={},weekly_on=True,mail_on=True)


def authorized(raw, token, owner, now=None):
    if not owner or not raw or len(raw)>12000:
        return False
    try:
        fields = parse_qsl(raw,strict_parsing=True,keep_blank_values=True,max_num_fields=32)
        data = dict(fields)
        signature = data.pop("hash")
        if len(fields)!=len(data)+1 or len(signature)!=64:
            return False
        payload = "\n".join(k+"="+data[k] for k in sorted(data))
        key = hmac.digest(b"WebAppData",token.encode(),"sha256")
        expected = hmac.new(key,payload.encode(),hashlib.sha256).hexdigest()
        age = (time.time() if now is None else now)-int(data["auth_date"])
        return (hmac.compare_digest(expected,signature) and -30<=age<=3600 and
                json.loads(data["user"])["id"]==owner)
    except (ValueError,KeyError,TypeError):
        return False


def services(bot):
    s = bot.s
    checked = s.get("last_check")
    available = bool(checked and not s.get("source_error"))
    statuses = {"itmo":{"ok":available,"detail":s.get("source_error") or
                ("Проверено "+datetime.fromisoformat(checked).strftime("%d.%m в %H:%M МСК") if checked else "Ожидает подключения")},
                "telegram":s.get("telegram_status",{"ok":False,"detail":"Ещё не проверено"})}
    statuses.update(bot.mail.statuses())
    return statuses


def state(bot):
    s = bot.s
    now = datetime.now(MSK)
    tasks = [dict(r,done=bool(r["done"]),steps=[]) for r in s.db.execute(
        "SELECT id,title,category,due,lead,done FROM tasks ORDER BY due,id")]
    by_id = {t["id"]:t for t in tasks}
    for row in s.db.execute("SELECT id,task_id,title,done FROM steps ORDER BY id"):
        by_id[row["task_id"]]["steps"].append(dict(row,done=bool(row["done"])))
    statuses = services(bot)
    cache = s.get("cache", {})
    stale = bool(s.get("source_error"))
    latest = set(s.get("latest_dates", []))
    pending = bot.check_job is not None and not bot.check_job.done()
    return dict(wake_preview=wake.proposal(s,now),wake_status=wake.status(s), campuses=campus_names(s,cache), bars=bot.grades.report(), check_pending=pending, today=now.date().isoformat(),now=now.isoformat(),profile=s.get("profile",{}),
                settings={k:s.get(k,v) for k,v in DEFAULTS.items()},services=statuses,
                days=[dict(date=d,lessons=item["lessons"],checked=item["checked"],stale=bool(stale or d not in latest or item["checked"][:10]!=now.date().isoformat())) for d,item in sorted(cache.items()) if d>=now.date().isoformat()],
                tasks=tasks,categories=[r[0] for r in s.db.execute("SELECT name FROM categories ORDER BY name")],
                mail=[dict(r) for r in s.db.execute("SELECT id,source,subject,sender,date,body FROM mail ORDER BY id DESC LIMIT 100")],
                warning=s.get("source_error") or "")


def field(value, limit):
    if not isinstance(value,str) or not 1<=len(value.strip())<=limit:
        raise ValueError(f"Введи текст длиной от 1 до {limit} символов.")
    return value.strip()


def integer(value, low, high):
    if type(value) is not int or not low<=value<=high:
        raise ValueError("Число вне допустимого диапазона.")
    return value


def boolean(value):
    if type(value) is not bool:
        raise ValueError("Проверь значение переключателя.")
    return value


def save_settings(store, values):
    if not values or not values.keys() <= DEFAULTS.keys():
        raise ValueError("Неизвестная настройка.")
    for k,v in values.items():
        if type(DEFAULTS[k]) is bool:
            boolean(v)
        elif k in ("morning_time","quiet_start","quiet_end"):
            v=datetime.strptime(field(v,5),"%H:%M").strftime("%H:%M")
        elif k=="theme" and v not in ("paper","night","mint"):
            raise ValueError("Выбери одну из трёх тем.")
        elif k=="interval" and integer(v,0,30) not in (0,1,5,15,30):
            raise ValueError("Недоступный интервал.")
        elif k=="campus_minutes":
            if not isinstance(v,dict) or len(v)>100:
                raise ValueError("Проверь список корпусов.")
            v={field(building,256):integer(minutes,1,240) for building,minutes in v.items()}
        elif k=="wake_rules":
            wake.rules(v)
        elif k in ("wake_prep","wake_online"):
            integer(v,0,240)
        elif k=="travel_minutes":
            integer(v,1,240)
        store.set(k,v)
    if store.get("quiet_start","23:00")==store.get("quiet_end","07:00"):
        raise ValueError("Начало и конец тихих часов должны различаться.")


def change_task(db,action,p):
    if action=="task_save":
        title, category = field(p["title"],160),field(p["category"],32)
        due = datetime.strptime(field(p["due"],16),"%Y-%m-%d %H:%M").strftime("%Y-%m-%d %H:%M")
        lead = integer(p["lead"],-1,1440)
        if lead not in REMIND.values():
            raise ValueError("Выбери время напоминания.")
        db.execute("INSERT OR IGNORE INTO categories VALUES (?)",(category,))
        if "id" not in p:
            steps = p.get("steps",[])
            if not isinstance(steps,list) or len(steps)>30:
                raise ValueError("Можно добавить до 30 шагов за раз.")
            task=db.execute("INSERT INTO tasks(title,category,due,lead) VALUES (?,?,?,?)",(title,category,due,lead)).lastrowid
            db.executemany("INSERT INTO steps(task_id,title) VALUES (?,?)",[(task,field(x,160)) for x in steps])
            return
    task = integer(p.get("task_id") if action.startswith("step_") else p.get("id"),1,2**63-1)
    if not db.execute("SELECT 1 FROM tasks WHERE id=?",(task,)).fetchone():
        raise ValueError("Задание уже удалено. Обнови список.")
    if action=="task_save":
        db.execute("UPDATE tasks SET reminded=CASE WHEN lead!=? OR due!=? THEN 0 ELSE reminded END, title=?,category=?,due=?,lead=? WHERE id=?",
                   (lead,due,title,category,due,lead,task))
    elif action=="task_done":
        db.execute("UPDATE tasks SET done=? WHERE id=?",(boolean(p["done"]),task))
    elif action=="task_delete":
        db.execute("DELETE FROM steps WHERE task_id=?",(task,))
        db.execute("DELETE FROM tasks WHERE id=?",(task,))
    elif action=="step_add":
        db.execute("INSERT INTO steps(task_id,title) VALUES (?,?)",(task,field(p["title"],160)))
    else:
        step=integer(p["id"],1,2**63-1)
        if action=="step_done":
            changed=db.execute("UPDATE steps SET done=? WHERE id=? AND task_id=?",(boolean(p["done"]),step,task))
        else:
            changed=db.execute("DELETE FROM steps WHERE id=? AND task_id=?",(step,task))
        if not changed.rowcount:
            raise ValueError("Подзадача уже удалена.")


async def action(bot, kind, data):
    s=bot.s
    notice=""
    if kind=="task_from_text":
        return {"draft":draft_task(field(data["text"],12000))}
    if kind in {"task_save","task_done","task_delete","step_add","step_done","step_delete"}:
        with s.db:
            change_task(s.db,kind,data)
    elif kind=="settings":
        with s.db:
            save_settings(s,data)
    elif kind in ("itmo_login","isu_login"):
        notice="Обнови Mini App и открой приватное окно входа."
    elif kind == "check_services":
        notice = bot.start_check()
    elif kind in ("mail_check","refresh"):
        if kind!="mail_check":
            if s.get("connected") and not bot.monitor.signing_in:
                await bot.monitor.fetch()
            else:
                notice="Для загрузки расписания войди в ИТМО ID."
        if kind!="refresh":
            await bot.mail.sync()
        if kind=="mail_check" and not (s.get("isu_connected") or bot.mail.imap.host):
            notice="Подключи входящие ИСУ или заполни настройки почты в .env."
    elif kind in ("wake_pair","wake_revoke"):
        with s.db:
            if kind=="wake_pair":
                return dict(state(bot), pairing=wake.pair_ticket(s))
            else:
                wake.revoke(s)
                notice="Доступ телефона отозван."
    elif kind=="bars_check":
        await bot.grades.sync()
        notice=bot.grades.report()
    elif kind=="week_report":
        notice=weekly_report(s,datetime.now(MSK).date())
    else:
        raise ValueError("Неизвестное действие.")
    return dict(state(bot),notice=notice)


def application(bot,token):
    @web.middleware
    async def headers(request, handler):
        response=await handler(request)
        response.headers.update({"Cache-Control":"no-store","X-Content-Type-Options":"nosniff","Referrer-Policy":"no-referrer",
                                 "Content-Security-Policy":"default-src 'self'; script-src 'self' https://telegram.org; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; base-uri 'self'; object-src 'none'; form-action 'none'"})
        if request.path.startswith("/viewer/") and policy:
            response.headers["Content-Security-Policy"]=policy
        return response
    app=web.Application(client_max_size=64*1024,middlewares=[headers])
    async def asset(request):
        filename = "pair.html" if request.path == "/pair" else request.match_info.get("asset","index.html")
        return web.FileResponse(WEB/filename)
    async def api(request):
        if not authorized(request.headers.get("X-Telegram-Init-Data",""),token,bot.s.get("owner")):
            return web.json_response({"error":"Открой приложение заново через меню своего Telegram-бота."},status=403)
        try:
            data=await request.json()
            if not isinstance(data,dict):
                raise ValueError()
            if request.path=="/api/services":
                result={"services":services(bot), "check_pending":bot.check_job is not None and not bot.check_job.done()}
            else:
                result=state(bot) if request.path=="/api/state" else await action(bot,data.pop("action"),data)
            return web.json_response(result)
        except (ValueError,KeyError,TypeError,OverflowError):
            return web.json_response({"error":"Проверь поля или обнови страницу и повтори действие."},status=400)
    login=PrivateLogin(bot,lambda r: authorized(r.headers.get("X-Telegram-Init-Data",""),token,bot.s.get("owner")))
    policy=viewer_policy() if login.available else ""
    login.register(app)
    wake.register(app,bot.s)
    app.router.add_get("/pair",asset)
    app.router.add_get("/",asset)
    app.router.add_get("/{asset:index\\.html|app\\.js|app\\.css|qr\\.js|pair\\.js}",asset)
    app.router.add_post("/api/services",api)
    app.router.add_post("/api/state",api)
    app.router.add_post("/api/action",api)
    return app


async def start_web(bot,token):
    runner=web.AppRunner(application(bot,token),access_log=None)
    await runner.setup()
    if "PARA_WEB_FD" in os.environ:
        import socket
        listener = socket.socket(fileno=int(os.environ["PARA_WEB_FD"]))
        await web.SockSite(runner,listener).start()
    else:
        await web.TCPSite(runner,os.getenv("WEB_HOST") or "127.0.0.1",int(os.getenv("WEB_PORT") or 8787)).start()
    return runner

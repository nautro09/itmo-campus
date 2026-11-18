import asyncio
import hmac
import json
import os
import secrets
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from itmo import MSK, Portal, SourceError
from grades import Grades
from monitor import Monitor
from planner import BACK, HOME, MAIN, SETTINGS, TODAY, TOMORROW, Planner, pairs
from store import Store
from dotenv import load_dotenv
from extras import campus_names, draft_task, weekly_report
from inbox import IsuInbox
from mailbox_sync import ENV, Mail
from miniapp import start_web, state
from menu import serve_menu
import wake
from miniapp import save_settings
from planner import FROM_TEXT, MAIL, WEEK

ROOT = Path(__file__).resolve().parent
LOGIN = "🔑 Войти в my.itmo"
CLOCK = "🕰 Время рассылки"
INTERVAL = "🔄 Частота проверки"
PAIR = "🔗 Привязать чат"


class TelegramError(Exception):
    def __init__(self, code, delay=3):
        super().__init__(f"Telegram HTTP {code}")
        self.code, self.delay = code, delay


class Telegram:
    def __init__(self, token):
        self.base = "https://api.telegram.org/bot" + token + "/"

    def _call(self, method, args):
        req = Request(self.base+method, data=json.dumps(args).encode(),
                      headers={"Content-Type":"application/json"})
        try:
            with urlopen(req, timeout=35) as response:
                result = json.load(response)
        except HTTPError as e:
            try:
                delay = json.load(e).get("parameters", {}).get("retry_after", 3)
            except (ValueError, OSError):
                delay = 3
            raise TelegramError(e.code, delay) from None
        except (URLError, OSError, ValueError):
            raise TelegramError(0) from None
        if not result.get("ok"):
            raise TelegramError(result.get("error_code", 0))
        return result["result"]

    async def call(self, method, **args):
        return await asyncio.to_thread(self._call, method, args)


class Bot:
    def __init__(self, store, portal):
        self.s = store
        self.plan = Planner(store)
        self.monitor = Monitor(store, portal)
        self.grades = Grades(store, portal)
        self.portal = portal
        self.isu = IsuInbox(ROOT/"data"/"isu-browser")
        self.mail = Mail(store,self.isu)
        self.isu_job = None
        self.check_job = None
        self.report_check = False
        self.api = None
        self.login_job = None
        self.pair_code = secrets.token_urlsafe(8)
        self.pair_attempts = {}

    def settings(self):
        st = self.s
        interval = st.get("interval",1)
        on = st.get("morning_on",True)
        connected = "подключено" if st.get("connected") else "ожидает входа"
        checked = st.get("last_check")
        last = datetime.fromisoformat(checked).strftime("%d.%m в %H:%M") if checked else "ещё не было"
        message = (f"⚙️ Настройки\n\nmy.itmo · {connected}\nПоследняя проверка · {last}\n"
                   f"Утренняя рассылка · {st.get('morning_time','07:30')+' МСК' if on else 'выключена'}\n"
                   f"Изменения на 7 дней · {str(interval)+' мин' if interval else 'проверка выключена'}")
        for key, label in (("isu","Входящие ИСУ"), ("mail","Учебный IMAP")):
            message += "\n" + label + " · " + self.mail.statuses()[key]["detail"]
        if st.get("source_error"):
            message += "\n\n" + st.get("source_error")
        toggle = "Выключить рассылку" if on else "Включить рассылку"
        return self.plan.screen("settings", message, [[LOGIN,"🔑 Войти в ИСУ"], [CLOCK, toggle], [INTERVAL],
                              ["🚶 Дорога", "🗓 Сводка по воскресеньям"],["🌙 Тихие часы","⏰ Будильник"],["🔎 Проверить связь"]])

    def begin_login(self, isu=False):
        if isu:
            if not self.isu_job or self.isu_job.done():
                self.mail.signing_in = True
                self.isu_job=asyncio.create_task(self.sign_into_inbox())
            return "В окне Chromium на компьютере с ботом войди в ИСУ и открой «Сообщения → Входящие»."
        if not self.login_job or self.login_job.done():
            self.login_job = asyncio.create_task(self.sign_in())
        return "На компьютере с ботом откроется окно ИТМО ID. Войди в аккаунт. После подключения придёт сообщение."

    async def sign_into_inbox(self):
        try:
            await self.isu.login()
            with self.s.db:
                self.s.set("isu_connected",True)
            message = "Вход сохранён. Входящие будут проверяться автоматически."
            self.mail.last = 0
            ok = True
        except Exception as e:
            ok = False
            message = str(e) if isinstance(e, SourceError) else "Не удалось сохранить вход в ИСУ. Проверь доступ к папке data и окно Chromium."
        finally:
            self.mail.signing_in = False
        with self.s.db:
            self.s.set("isu_status", {"ok": ok, "detail": message})
            self.s.post(self.s.get("owner"), "✉️ ИСУ · " + message)

    def start_check(self, report=False):
        self.report_check |= report
        if self.check_job is None or self.check_job.done():
            self.check_job = asyncio.create_task(self.check_services())
        return "Проверяю подключения. Результаты появятся в профиле" + (" и в этом чате." if report else ".")

    async def check_services(self):
        checks = [self.check_telegram(), self.mail.sync()]
        if self.s.get("connected") and not self.monitor.signing_in and not self.monitor.lock.locked():
            checks.append(self.monitor.fetch())
        try:
            await asyncio.gather(*checks)
            if self.report_check:
                statuses = state(self)["services"]
                labels = {"isu":"Входящие ИСУ","mail":"Почта","itmo":"my.itmo","telegram":"Telegram"}
                with self.s.db:
                    self.s.post(self.s.get("owner"), "\n".join(f"{labels[k]} · {v['detail']}" for k,v in statuses.items()))
        finally:
            self.report_check = False

    async def check_telegram(self):
        try:
            await asyncio.wait_for(self.api.call("getMe"), 8)
            result={"ok":True,"detail":"Telegram ответил в "+datetime.now(MSK).strftime("%H:%M МСК")}
        except (TelegramError,AttributeError,asyncio.TimeoutError):
            result={"ok":False,"detail":"Нет ответа Telegram."}
        with self.s.db:
            self.s.set("telegram_status",result)

    def draft(self,text):
        draft=draft_task(text)
        message=(f"Черновик задания\n{draft['title']}\nКатегория · {draft['category']}\n"
                 f"Срок · {draft['due'] or 'нужно выбрать'}\nПодзадач · {len(draft['steps'])}")
        return self.plan.screen("draft",message,[["Сохранить черновик","Изменить срок"],["Изменить название","Изменить категорию"],[BACK]],draft=draft)

    async def sign_in(self):
        self.monitor.signing_in = True
        try:
            await self.portal.login()
            with self.s.db:
                self.s.set("connected", True)
                self.s.set("last_attempt", 0)
                self.s.post(self.s.get("owner"), "✅ Личное расписание подключено. Загружаю ближайшие 7 дней.")
            await self.monitor.fetch()
        except SourceError as e:
            with self.s.db:
                self.s.post(self.s.get("owner"), str(e))
        except Exception as e:
            print("Ошибка подключения:", type(e).__name__, file=sys.stderr)
            with self.s.db:
                self.s.post(self.s.get("owner"), "Не удалось открыть окно входа. Проверь установку Chromium на компьютере с ботом.")
        finally:
            self.monitor.signing_in = False

    async def route(self, text):
        screen = self.s.get("screen", {"name":"home"})
        name = screen["name"]
        if text in (HOME, "/start"):
            return self.plan.home()
        if text == "📈 Баллы БаРС":
            await self.grades.sync()
            return self.plan.screen("grades", self.grades.report(), [["📈 Баллы БаРС"]])
        if text == FROM_TEXT:
            return self.plan.screen("from_text","Перешли сообщение преподавателя или отправь текст задания.",[[BACK]])
        if text==WEEK:
            if self.s.get("connected") and not self.monitor.signing_in:
                await self.monitor.fetch()
            return self.plan.screen("home",weekly_report(self.s,datetime.now(MSK).date()),MAIN)
        if text=="🔑 Войти в ИСУ":
            return self.begin_login(True),self.s.get("keyboard",MAIN)
        if text==MAIL or (text==BACK and name=="mail_item"):
            rows=self.s.db.execute("SELECT id,subject FROM mail ORDER BY id DESC LIMIT 10").fetchall()
            buttons=[[f"✉ {r['id']} · {r['subject'][:36]}"] for r in rows]
            switch="Выключить пересылку" if self.s.get("mail_on",True) else "Включить пересылку"
            return self.plan.screen("mail","Последние письма" if rows else "Здесь появятся письма после подключения входящих.",
                       buttons+[["🔑 Войти в ИСУ","Проверить почту"],[switch]])
        if name=="mail" and text in ("Включить пересылку","Выключить пересылку"):
            self.s.set("mail_on",text=="Включить пересылку")
            return await self.route(MAIL)
        if text=="Проверить почту" and name=="mail":
            await self.mail.sync()
            msg,rows=await self.route(MAIL)
            details=[label+" · "+self.mail.statuses()[key]["detail"] for label,key in (("ИСУ","isu"),("IMAP","mail"))]
            return msg+"\n"+("\n".join(filter(None,details)) or "Подключи ИСУ или заполни IMAP в .env."),rows
        if name=="mail" and text.startswith("✉ ") and text.split()[1].isdigit():
            item=self.s.db.execute("SELECT * FROM mail WHERE id=?",(int(text.split()[1]),)).fetchone()
            if item:
                return self.plan.screen("mail_item",f"{item['sender']} · {item['date']}\n{item['subject']}\n\n{item['body']}",
                                        [["Создать задание из письма"],[BACK]],mail_id=item["id"])
        if name=="mail_item" and text=="Создать задание из письма":
            row=self.s.db.execute("SELECT subject,body FROM mail WHERE id=?",(screen["mail_id"],)).fetchone()
            return self.draft(row["subject"]+"\n"+row["body"])
        if name=="from_text" and text!=BACK:
            return self.draft(text)
        if name=="draft":
            d=screen["draft"]
            data=dict(d,mode="new")
            if text=="Изменить название":
                return self.plan.screen("draft_title","Как назвать задание?",[[BACK]],draft=d)
            if text=="Изменить категорию":
                return self.plan.categories(data)
            if text=="Изменить срок" or (text=="Сохранить черновик" and not d["due"]):
                return self.plan.date_picker(data)
            if text=="Сохранить черновик":
                return self.plan.handle("За час",dict(name="lead",data=data))
        if name=="draft_title" and text!=BACK:
            d=screen["draft"]
            if not 1<=len(text)<=160:
                return "Введи название до 160 символов.",self.s.get("keyboard",MAIN)
            d["title"]=text
            return self.plan.screen("draft",f"{text}\n{d['due'] or 'Выбери срок'}",[["Сохранить черновик","Изменить срок"],[BACK]],draft=d)
        if text=="🚶 Дорога" and name=="settings":
            return self.plan.screen("travel","Сколько минут обычно занимает дорога до корпуса? Можно ввести число от 1 до 240.",[["20","35","50"],["По корпусам"],["Выключить напоминание"],[BACK]])
        if (name=="travel" and text=="По корпусам") or (name=="campus_time" and text==BACK):
            names = campus_names(self.s)
            return self.plan.screen("campuses", "Выбери корпус из расписания." if names else "Корпуса появятся после загрузки очных пар.",
                                    [[building] for building in names]+[[BACK]], buildings=names)
        if name=="campuses" and text in screen.get("buildings",[]):
            minutes = self.s.get("campus_minutes",{}).get(text,self.s.get("travel_minutes",35))
            return self.plan.screen("campus_time", f"{text} · сейчас {minutes} мин. Введи от 1 до 240 минут.",
                                    [["20","35","50"],["Общее время"],[BACK]],building=text)
        if name=="campus_time":
            values = self.s.get("campus_minutes",{})
            if text=="Общее время":
                values.pop(screen["building"],None)
            elif text.isdecimal() and 1<=int(text)<=240:
                values[screen["building"]] = int(text)
                self.s.set("travel_on",True)
            else:
                return "Введи число от 1 до 240.",self.s.get("keyboard",MAIN)
            self.s.set("campus_minutes",values)
            return self.settings()
        if name=="travel" and (text=="Выключить напоминание" or text.isdecimal() and 1<=int(text)<=240):
            self.s.set("travel_on",text!="Выключить напоминание")
            if text.isdecimal():
                self.s.set("travel_minutes",int(text))
            return self.settings()
        if text=="🗓 Сводка по воскресеньям" and name=="settings":
            on=self.s.get("weekly_on",True)
            return self.plan.screen("weekly","Воскресная сводка в 18:00 МСК · "+("включена" if on else "выключена"),
                                    [["Выключить сводку" if on else "Включить сводку"],[BACK]])
        if name=="weekly" and text in ("Включить сводку","Выключить сводку"):
            self.s.set("weekly_on",text=="Включить сводку")
            return self.settings()
        if text=="⏰ Будильник" or name in ("wake","wake_input") and text not in (BACK, HOME):
            notice = ""
            fields = {"Время сборов":"wake_prep","До онлайн-пары":"wake_online","Правила подъёма":"wake_rules"}
            try:
                if name=="wake_input" and text!="⏰ Будильник":
                    field = screen["field"]
                    value = ("" if text=="Сбросить правила" else text) if field=="wake_rules" else int(text)
                    save_settings(self.s,{field:value})
                elif text in fields:
                    message = "Введи правила через запятую, например 08:10=06:20, 09:50=08:30." if text=="Правила подъёма" else "Введи число минут от 0 до 240."
                    return self.plan.screen("wake_input",message,([["Сбросить правила"]] if text=="Правила подъёма" else [["20","40","60"]])+[[BACK]],field=fields[text])
                elif text=="Привязать Honor":
                    notice=wake.pair_text(self.s)
                elif text=="Отозвать доступ":
                    wake.revoke(self.s)
                elif text=="Переключить будильник":
                    self.s.set("wake_on",not self.s.get("wake_on",False))
            except ValueError as err:
                return str(err) if not str(err).startswith("invalid literal") else "Введи число минут.",self.s.get("keyboard",MAIN)
            mode="включён" if self.s.get("wake_on",False) else "выключен"
            details = (f"Будильник {mode}. Сборы: {self.s.get('wake_prep',40)} мин + дорога до корпуса. "
                       f"Онлайн: за {self.s.get('wake_online',20)} мин. Правила для очных пар: "
                       f"{self.s.get('wake_rules',wake.DEFAULTS['wake_rules']) or 'нет'}.")
            return self.plan.screen("wake",details+"\n"+wake.status(self.s)+"\n"+notice,
                [["Переключить будильник","Привязать Honor"],["Время сборов","До онлайн-пары"],["Правила подъёма","Отозвать доступ"],[BACK]])
        if text=="🌙 Тихие часы" or (name=="quiet" and text!=BACK):
            if name=="quiet" and text!="🌙 Тихие часы":
                if text=="Переключить режим":
                    self.s.set("quiet_on",not self.s.get("quiet_on",True))
                elif text=="Исключение первой пары":
                    self.s.set("quiet_first",not self.s.get("quiet_first",True))
                else:
                    try:
                        start,end = [datetime.strptime(v.strip(),"%H:%M").strftime("%H:%M") for v in text.replace("–","-").split("-")]
                        if start==end:
                            raise ValueError()
                    except ValueError:
                        return "Введи интервал, например 23:00-07:00.",self.s.get("keyboard",MAIN)
                    self.s.set("quiet_start",start)
                    self.s.set("quiet_end",end)
            mode = "включены" if self.s.get("quiet_on",True) else "выключены"
            exception = "сразу" if self.s.get("quiet_first",True) else "в сводке"
            return self.plan.screen("quiet",f"🌙 Тихие часы {mode} · {self.s.get('quiet_start','23:00')}–{self.s.get('quiet_end','07:00')} МСК. Изменения ближайшей первой пары — {exception}. Введи свой интервал или выбери ниже.",
                [["23:00-07:00","22:00-08:00"],["Переключить режим","Исключение первой пары"],[BACK]])
        if text=="🔎 Проверить связь":
            return self.start_check(report=True), self.s.get("keyboard",MAIN)
        if text == SETTINGS or (text == BACK and name in ("interval","clock","travel","weekly","campuses","quiet","wake","wake_input")):
            return self.settings()
        if text in (TODAY,TOMORROW):
            if not self.s.get("connected"):
                return self.plan.screen("settings", "Подключи личное расписание. Окно для входа откроется на компьютере, где запущен бот.", [[LOGIN]])
            if self.monitor.signing_in:
                return "Дождись окончания входа в окне ИТМО.", self.s.get("keyboard", MAIN)
            await self.monitor.fetch()
            day = datetime.now(MSK).date() + timedelta(days=int(text == TOMORROW))
            return self.plan.screen("home", self.monitor.show_day(day), MAIN)
        if name == "settings":
            if text == LOGIN:
                return self.begin_login(), self.s.get("keyboard",MAIN)
            if text == INTERVAL:
                return self.plan.screen("interval", "Как часто проверять изменения на ближайшие 7 дней?",
                                        pairs(["1 мин", "5 мин", "15 мин", "30 мин", "Выключить проверки"])+[[BACK]])
            if text == CLOCK:
                return self.plan.screen("clock", "Выбери время утренней рассылки или введи ЧЧ:ММ по Москве.",
                                        pairs(["06:30","07:00","07:30","08:00","08:30","09:00"])+[[BACK]])
            if text in ("Включить рассылку","Выключить рассылку"):
                self.s.set("morning_on", text == "Включить рассылку")
                return self.settings()
        if name == "interval" and text in ("1 мин","5 мин","15 мин","30 мин","Выключить проверки"):
            self.s.set("interval", int(text.split()[0]) if text.endswith("мин") else 0)
            self.s.set("last_attempt",0)
            return self.settings()
        if name == "clock":
            try:
                at = datetime.strptime(text,"%H:%M").strftime("%H:%M")
            except ValueError:
                return "Введи время в формате ЧЧ:ММ.", self.s.get("keyboard", MAIN)
            self.s.set("morning_time", at)
            self.s.set("morning_on", True)
            return self.settings()
        return self.plan.handle(text, screen)

    async def update(self, event):
        uid = event["update_id"]
        if uid == self.s.get("last_update"):
            return
        msg = event.get("message", {})
        chat = msg.get("chat", {})
        text = (msg.get("text") or msg.get("caption") or "").strip()
        chat_id = chat.get("id")
        if chat.get("type") == "private" and chat_id == msg.get("from",{}).get("id") and text:
            owner = self.s.get("owner")
            if not owner:
                now = time.monotonic()
                recent = [t for t in self.pair_attempts.get(chat_id,[]) if t > now-60]
                if text in ("/start", PAIR):
                    response = "Введи код привязки из терминала на компьютере с ботом.", [[PAIR]]
                elif len(recent) >= 5:
                    response = "Попробуй через минуту.", [[PAIR]]
                elif hmac.compare_digest(text.encode(), self.pair_code.encode()):
                    self.s.set("owner", chat_id)
                    response = self.plan.home()
                    response = ("Чат привязан. Открой «Настройки», чтобы подключить my.itmo.\n\n"+response[0], response[1])
                else:
                    self.pair_attempts[chat_id] = recent + [now]
                    response = "Код не подошёл. Проверь код в терминале.", [[PAIR]]
            elif owner == chat_id:
                response = self.draft(text) if msg.get("forward_origin") else await self.route(text)
            else:
                response = None
            if response:
                message, rows = response
                if self.s.get("owner") == chat_id:
                    self.s.set("keyboard",rows)
                self.s.post(chat_id,message,rows)
        self.s.set("last_update",uid)
        self.s.db.commit()


async def poll(api, bot):
    while True:
        try:
            last = bot.s.get("last_update")
            opts = dict(offset=last+1) if last is not None else {}
            updates = await api.call("getUpdates", timeout=20, allowed_updates=["message"], **opts)
            for update in updates:
                await bot.update(update)
        except TelegramError as e:
            if e.code in (401,404,409):
                raise
            await asyncio.sleep(e.delay)
        except Exception as e:
            bot.s.db.rollback()
            print("Ошибка обработки сообщения:", type(e).__name__, file=sys.stderr)
            await asyncio.sleep(3)


async def deliver(api, store):
    while True:
        item = store.next_delivery()
        if not item:
            await asyncio.sleep(1)
            continue
        args = {"chat_id":item["chat"], "text":item["text"], "link_preview_options":{"is_disabled":True}}
        if item["keyboard"]:
            args["reply_markup"] = {"keyboard":json.loads(item["keyboard"]), "resize_keyboard":True, "is_persistent":True}
        try:
            await api.call("sendMessage", **args)
        except TelegramError as e:
            if e.code == 401:
                raise
            if e.code not in (400,403):
                await asyncio.sleep(e.delay)
                continue
            print("Telegram отклонил сообщение, код", e.code, file=sys.stderr)
        with store.db:
            store.db.execute("DELETE FROM outbox WHERE id=?", (item["id"],))
        await asyncio.sleep(1.05)


async def clock(monitor):
    while True:
        try:
            await monitor.tick()
        except Exception as e:
            print("Проверка не завершена:", type(e).__name__, file=sys.stderr)
        await asyncio.sleep(3)


async def main():
    os.umask(0o077)
    data = ROOT / "data"
    data.mkdir(mode=0o700, exist_ok=True)
    # A second launcher must not deliver the same outbox or share the browser profile.
    process_lock = sqlite3.connect(data / "instance.lock", timeout=0)
    try:
        process_lock.execute("BEGIN EXCLUSIVE")
    except sqlite3.OperationalError:
        raise SystemExit("Бот уже запущен или его папка данных недоступна.")
    load_dotenv(ENV,interpolate=False)
    token = os.getenv("BOT_TOKEN","")
    if not token or ":" not in token or any(c.isspace() or c in "/?#" for c in token):
        raise SystemExit("Заполни BOT_TOKEN в локальном .env. Для перехода с v1 перенеси значение data/telegram-token в .env.")
    api = Telegram(token)
    me = await api.call("getMe")
    store = Store(data/"planner.sqlite3")
    portal = Portal(data/"my-itmo-browser")
    bot = Bot(store, portal)
    bot.api=api
    configured=os.getenv("OWNER_TELEGRAM_ID","").strip()
    if configured:
        if not configured.isdecimal() or int(configured)<=0 or store.get("owner") not in (None,int(configured)):
            raise SystemExit("Проверь OWNER_TELEGRAM_ID и владельца существующей базы.")
        with store.db:
            store.set("owner",int(configured))
    with store.db:
        store.set("telegram_status",{"ok":True,"detail":"Связь установлена при запуске."})
    runner=await start_web(bot,token)
    print(f"Бот запущен: https://t.me/{me['username']}", flush=True)
    if not store.get("owner"):
        print(f"Код привязки для первого входа: {bot.pair_code}", flush=True)
    try:
        await asyncio.gather(poll(api, bot), deliver(api,store), clock(bot.monitor),bot.mail.run(),bot.grades.run(),serve_menu(api,store))
    finally:
        if bot.login_job and not bot.login_job.done():
            bot.login_job.cancel()
            await asyncio.gather(bot.login_job, return_exceptions=True)
        if bot.isu_job and not bot.isu_job.done():
            bot.isu_job.cancel()
            await asyncio.gather(bot.isu_job,return_exceptions=True)
        if bot.check_job and not bot.check_job.done():
            bot.check_job.cancel()
            await asyncio.gather(bot.check_job,return_exceptions=True)
        await runner.cleanup()
        await bot.isu.close()
        await portal.close()
        process_lock.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except TelegramError as exc:
        msg = {401:"Telegram отклонил токен. Проверь BOT_TOKEN в .env.",
               404:"Telegram не узнал токен. Проверь BOT_TOKEN в .env.",
               409:"Telegram сообщил о конфликте. Проверь, что работает один экземпляр бота и для него выключен webhook."}
        raise SystemExit(msg.get(exc.code, f"Не удалось связаться с Telegram (код {exc.code})."))

import re
import asyncio
import hmac
import json
import os
import hashlib
from collections import deque
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import aiohttp

from bulletin import COVERS, article
from itmo import MSK, Portal, SourceError
from grades import Grades
from monitor import Monitor
from planner import BACK, HOME, MAIN, SETTINGS, TODAY, TOMORROW, Planner, pairs
from store import Store
from dotenv import load_dotenv
from extras import campus_names, draft_task, weekly_report
from inbox import IsuInbox
from mailbox_sync import ENV, Mail
from miniapp import start_web, services
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
    def __init__(self, token, session):
        self.base = "https://api.telegram.org/bot" + token + "/"
        self.session = session

    async def call(self, method, **args):
        try:
            async with self.session.post(self.base + method, json=args, allow_redirects=False) as response:
                try:
                    result = await response.json(content_type=None)
                except (ValueError, UnicodeError):
                    raise TelegramError(response.status if response.status >= 400 else 0) from None
                if response.status != 200 or not result.get("ok"):
                    raise TelegramError(result.get("error_code") or response.status,
                                        result.get("parameters", {}).get("retry_after", 3))
                return result["result"]
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
            raise TelegramError(0) from None


class Bot:
    def __init__(self, store, portal):
        self.s = store
        self.plan = Planner(store)
        self.monitor = Monitor(store, portal)
        self.grades = Grades(store, portal)
        self.portal = portal
        self.isu = IsuInbox(ROOT/"data"/"isu-browser")
        self.mail = Mail(store,self.isu)
        self.check_job = None
        self.mail_check_job = None
        self.report_check = False
        self.api = None
        self.owner = store.get("owner")
        self.starts = deque()
        self.verifications = deque()

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
        statuses = self.mail.statuses()
        for key, label in (("isu","Входящие ИСУ"), ("mail","Учебный IMAP")):
            message += "\n" + label + " · " + statuses[key]["detail"]
        if st.get("source_error"):
            message += "\n\n" + st.get("source_error")
        toggle = "Выключить рассылку" if on else "Включить рассылку"
        return self.plan.screen("settings", message, [[LOGIN,"🔑 Войти в ИСУ"], *([["Войти в Microsoft 365"]] if os.getenv("MS_CLIENT_ID") else []), [CLOCK, toggle], [INTERVAL],
                              ["🚶 Дорога", "🗓 Сводка по воскресеньям"],["🌙 Тихие часы","⏰ Будильник"],["🔔 Уведомления"],["🔎 Проверить связь"]])

    def login_button(self, isu=False):
        origin = self.s.get("wake_origin") or os.getenv("MINI_APP_URL","").rstrip("/")
        if not origin.startswith("https://"):
            return "Публичный адрес Mini App ещё не готов.", [[BACK]]
        source = "isu" if isu else "itmo"
        button = {"text":"Открыть приватный вход","web_app":{"url":origin+"/?login="+source}}
        return "Открой официальный сайт в приватном окне на этом устройстве. После входа сервер продолжит проверку круглосуточно.", [[button]]

    async def sign_into_inbox(self, env):
        self.mail.signing_in = True
        try:
            await self.isu.login(env)
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
                statuses = services(self)
                labels = {"isu":"Входящие ИСУ","mail":"Почта","itmo":"my.itmo","telegram":"Telegram"}
                with self.s.db:
                    self.s.post(self.s.get("owner"), "\n".join(f"{labels[k]} · {v['detail']}" for k,v in statuses.items()))
        finally:
            self.report_check = False

    async def report_mail_check(self):
        try:
            await self.mail.sync()
            statuses = self.mail.statuses()
            message = "\n".join(label + " · " + statuses[key]["detail"]
                                for label, key in (("ИСУ", "isu"), ("IMAP", "mail")))
        except Exception as exc:
            print("Ошибка проверки почты:", type(exc).__name__, file=sys.stderr)
            message = "Не удалось проверить почту. Попробуй ещё раз."
        with self.s.db:
            rows = None
            if self.s.get("screen", {}).get("name") == "mail":
                _, rows = await self.route(MAIL)
                self.s.set("keyboard", rows)
            self.s.post(self.s.get("owner"), message, rows)

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

    async def sign_in(self, env):
        self.monitor.signing_in = True
        try:
            await self.portal.login(env)
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
                self.s.post(self.s.get("owner"), "Не удалось открыть окно входа. Открой вход ещё раз из профиля Пары.")
        finally:
            self.monitor.signing_in = False

    async def route(self, text):
        screen = self.s.get("screen", {"name":"home"})
        name = screen["name"]
        if text=="/start clock" and self.s.get("owner"):
            try:
                return wake.pair_text(self.s), self.s.get("keyboard", MAIN)
            except ValueError as error:
                return str(error), self.s.get("keyboard", MAIN)
        if text in (HOME, "/start"):
            return self.plan.home()
        if text == "📈 Баллы БаРС":
            await self.grades.sync()
            return self.plan.screen("grades", self.grades.report(), [["📈 Баллы БаРС"]])
        if text == FROM_TEXT:
            return self.plan.screen("from_text","Перешли сообщение преподавателя или отправь текст задания.",[[BACK]])
        if text==WEEK:
            if self.s.get("connected") and not self.monitor.signing_in:
                await self.monitor.fetch(for_days=[datetime.now(MSK).date() + timedelta(days=i) for i in range(7)])
            return self.plan.screen("home",weekly_report(self.s,datetime.now(MSK).date()),MAIN)
        if text=="Войти в Microsoft 365":
            return await self.mail.link_outlook(),self.s.get("keyboard",MAIN)
        if text=="🔑 Войти в ИСУ":
            return self.login_button(True)
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
            if self.mail_check_job is None or self.mail_check_job.done():
                self.mail_check_job = asyncio.create_task(self.report_mail_check())
            return "Проверяю входящие. Пришлю результат в этот чат.", self.s.get("keyboard", MAIN)
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
        if text=="Правила подъёма" or name in ("wake_slots","wake_start","wake_time") and text not in (BACK,HOME):
            mapping=wake.rules(self.s.get("wake_rules",wake.DEFAULTS["wake_rules"]))
            if text=="＋ Добавить пару":
                return self.plan.screen("wake_start","Когда начинается пара? Введи ЧЧ:ММ.",[["11:30","13:30","15:20"],[BACK]])
            if name=="wake_start" or name=="wake_slots" and text.startswith("К "):
                start=text if name=="wake_start" else screen.get("choices",{}).get(text,"")
                if not re.fullmatch(wake.CLOCK,start):
                    return "Введи начало пары в формате ЧЧ:ММ.",self.s.get("keyboard",MAIN)
                return self.plan.screen("wake_time",f"Пара в {start}. Выбери или введи время подъёма.",[["06:20","08:30"],["Удалить правило"],[BACK]],start=start)
            if name=="wake_time":
                start=screen["start"]
                if text=="Удалить правило":
                    mapping.pop(start,None)
                elif re.fullmatch(wake.CLOCK,text) and text<start:
                    mapping[start]=text
                else:
                    return "Подъём должен быть раньше пары. Введи ЧЧ:ММ.",self.s.get("keyboard",MAIN)
                value=", ".join(k+"="+v for k,v in sorted(mapping.items()))
                try: save_settings(self.s,{"wake_rules":value})
                except ValueError as err: return str(err),self.s.get("keyboard",MAIN)
            choices={f"К {i}-й · {t} → {v}":t for i,(t,v) in enumerate(sorted(mapping.items()),1)}
            return self.plan.screen("wake_slots","Начало пары и время подъёма",[[k] for k in choices]+[["＋ Добавить пару"],[BACK]],choices=choices)
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
                elif text in (wake.PAIR_LABEL,"Привязать Honor"):
                    notice=wake.pair_text(self.s)
                elif text=="Отозвать доступ":
                    wake.revoke(self.s)
                elif text=="Выходной: менять режим":
                    self.s.set("wake_free_off",not self.s.get("wake_free_off",False))
                elif text=="Переключить будильник":
                    self.s.set("wake_on",not self.s.get("wake_on",False))
            except ValueError as err:
                return str(err) if not str(err).startswith("invalid literal") else "Введи число минут.",self.s.get("keyboard",MAIN)
            mode="включён" if self.s.get("wake_on",False) else "выключен"
            details = (f"Будильник {mode}. Сборы: {self.s.get('wake_prep',40)} мин + дорога до корпуса. "
                       f"Без правила для онлайн-пары · за {self.s.get('wake_online',20)} мин. Время по парам · "
                       f"{self.s.get('wake_rules',wake.DEFAULTS['wake_rules']) or 'нет'}.")
            details += "\nСвободный день · " + ("предложить выключение" if self.s.get("wake_free_off",False) else "оставить как есть")
            return self.plan.screen("wake",details+"\n"+wake.status(self.s)+"\n"+notice,
                [["Переключить будильник",wake.PAIR_LABEL],["Время сборов","До онлайн-пары"],["Правила подъёма","Выходной: менять режим"],["Отозвать доступ"],[BACK]])
        if text=="🔔 Уведомления" or name=="notice_types" and text!=BACK:
            options={"Письма ИСУ":"notify_isu","Письма IMAP":"notify_imap","Баллы БаРС":"notify_bars","Изменения пар":"notify_schedule","Дедлайны":"notify_due","Дорога":"travel_on","Утренняя рассылка":"morning_on","Недельная сводка":"weekly_on"}
            label=text.removeprefix("✓ ").removeprefix("○ ")
            if label in options:
                key=options[label]
                self.s.set(key,not self.s.get(key,key!="travel_on"))
            buttons=[("✓ " if self.s.get(key,key!="travel_on") else "○ ")+title for title,key in options.items()]
            return self.plan.screen("notice_types","Выбери уведомления для Telegram.",pairs(buttons)+[[BACK]])
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
        if text == SETTINGS or (text == BACK and name in ("interval","clock","travel","weekly","campuses","quiet","wake","wake_input","wake_slots","wake_start","wake_time","notice_types")):
            return self.settings()
        if text in (TODAY,TOMORROW):
            if not self.s.get("connected"):
                return self.plan.screen("settings", "Подключи личное расписание. Открой приватный вход на своём устройстве.", [[LOGIN]])
            if self.monitor.signing_in:
                return "Дождись окончания входа в окне ИТМО.", self.s.get("keyboard", MAIN)
            day = datetime.now(MSK).date() + timedelta(days=int(text == TOMORROW))
            await self.monitor.fetch(for_days=[day])
            return self.plan.screen("home", self.monitor.show_day(day), MAIN)
        if name == "settings":
            if text == LOGIN:
                return self.login_button()
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
        msg = event.get("message", {})
        chat = msg.get("chat", {})
        chat_id = chat.get("id")
        owner = self.owner
        if not owner or chat.get("type") != "private" or chat_id != owner or msg.get("from",{}).get("id") != owner:
            return
        if uid == self.s.get("last_update"):
            return
        text = (msg.get("text") or msg.get("caption") or "").strip()
        if text:
            command = text.split(maxsplit=1)[0].lower()
            if command in ("/start","/verify"):
                attempts = self.verifications if command == "/verify" else self.starts
                now = time.monotonic()
                while attempts and attempts[0] <= now-60:
                    attempts.popleft()
                if len(attempts)>=3:
                    return
                attempts.append(now)
            if command == "/verify":
                digest = os.getenv("ADMIN_VERIFY_SHA256","")
                value = text.partition(" ")[2].strip()
                if msg.get("forward_origin") or not digest or not hmac.compare_digest(hashlib.sha256(value.encode()).hexdigest(),digest):
                    return
                response = ("Доступ владельца подтверждён. " + self.settings()[0], self.s.get("keyboard", MAIN))
            else:
                response = self.draft(text) if msg.get("forward_origin") else await self.route(text)
            if response:
                message, rows = response
                if rows and not isinstance(rows[0][0],dict):
                    self.s.set("keyboard",rows)
                rubric = None
                if owner == chat_id:
                    view = self.s.get("screen", {}).get("name")
                    if text in (TODAY, TOMORROW) and view == "home" and not self.monitor.signing_in:
                        rubric = "day"
                    elif text == WEEK and view == "home":
                        rubric = "week"
                    elif view == "grades" and text == "📈 Баллы БаРС":
                        rubric = "grades"
                    elif view == "mail_item" and text.startswith("✉ "):
                        rubric = "mail"
                    elif view in ("list", "card"):
                        rubric = "tasks"
                self.s.post(chat_id, message, rows, rubric=rubric)
        self.s.set("last_update",uid)
        self.s.db.commit()


async def poll(api, bot):
    last = bot.s.get("last_update")
    while True:
        try:
            opts = dict(offset=last+1) if last is not None else {}
            updates = await api.call("getUpdates", timeout=20, allowed_updates=["message"], **opts)
            for update in updates:
                await bot.update(update)
                last = update["update_id"]
        except TelegramError as e:
            if e.code in (401,404,409):
                raise
            await asyncio.sleep(e.delay)
        except Exception as e:
            bot.s.db.rollback()
            print("Ошибка обработки сообщения:", type(e).__name__, file=sys.stderr)
            await asyncio.sleep(3)


async def send_outbox_item(api, item):
    common = {"chat_id": item["chat"]}
    if item["keyboard"]:
        rows = json.loads(item["keyboard"])
        common["reply_markup"] = ({"inline_keyboard":rows} if rows and rows[0] and isinstance(rows[0][0],dict) else
                                  {"keyboard":rows,"resize_keyboard":True,"is_persistent":True})
    kind, text = item["rubric"], item["text"]
    if kind:
        for cover in ((True, False) if kind in COVERS else (False,)):
            try:
                await api.call("sendRichMessage", rich_message=article(kind, text, cover=cover), **common)
                return
            except TelegramError as exc:
                if exc.code == 404:
                    break
                if exc.code != 400:
                    raise
    first = text.partition("\n")[0]
    if kind and first:
        common["entities"] = [{"type": "bold", "offset": 0, "length": len(first.encode("utf-16-le")) // 2}]
    await api.call("sendMessage", text=text, link_preview_options={"is_disabled": True}, **common)


async def deliver(api, store):
    signal = store.delivery_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    while True:
        signal.clear()
        item = store.next_delivery()
        if not item:
            try:
                # Recheck held notifications when the quiet-hours minute changes.
                await asyncio.wait_for(signal.wait(), 60 - time.time() % 60)
            except asyncio.TimeoutError:
                pass
            continue
        started = loop.time()
        try:
            await send_outbox_item(api, item)
        except TelegramError as e:
            if e.code == 401:
                raise
            if e.code not in (400,403):
                await asyncio.sleep(e.delay)
                continue
            print("Telegram отклонил сообщение, код", e.code, file=sys.stderr)
        with store.db:
            store.db.execute("DELETE FROM outbox WHERE id=?", (item["id"],))
        await asyncio.sleep(max(0, started + 1.05 - loop.time()))


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
    load_dotenv(ENV.with_name("access.env"),interpolate=False)
    load_dotenv(ENV,interpolate=False)
    token = os.getenv("BOT_TOKEN","")
    if not token or ":" not in token or any(c.isspace() or c in "/?#" for c in token):
        raise SystemExit("Заполни BOT_TOKEN в локальном .env. Для перехода с v1 перенеси значение data/telegram-token в .env.")
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=35), trust_env=True) as session:
            await run_bot(data, Telegram(token, session), token)
    finally:
        process_lock.close()


async def run_bot(data, api, token):
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
        bot.owner = int(configured)
    with store.db:
        store.set("telegram_status",{"ok":True,"detail":"Связь установлена при запуске."})
        store.set("wake_bot_username", me["username"])
    runner=await start_web(bot,token)
    print(f"Бот запущен: https://t.me/{me['username']}", flush=True)
    if not store.get("owner"):
        print("Доступ закрыт. Укажи OWNER_TELEGRAM_ID в приватном окружении.", flush=True)
    workers = [asyncio.create_task(job) for job in (poll(api, bot), deliver(api, store),
               clock(bot.monitor), bot.mail.run(), bot.grades.run(), serve_menu(api, store))]
    try:
        await asyncio.gather(*workers)
    finally:
        jobs = workers + [job for job in (bot.mail.oauth_job, bot.mail_check_job, bot.check_job) if job]
        for job in jobs:
            job.cancel()
        await asyncio.gather(*jobs, return_exceptions=True)
        await runner.cleanup()
        await bot.isu.close()
        await portal.close()
        store.db.close()


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

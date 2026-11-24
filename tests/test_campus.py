import hashlib
import hmac
import json
import sys
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock
from urllib.parse import urlencode

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from aiohttp.test_utils import TestClient, TestServer
from bot import Bot
from extras import departure, draft_task, weekly_report
from itmo import MSK
from mailbox_sync import Mail, allowed, parse_message
from miniapp import action, application, authorized
from store import Store


def signed(chat,token,ts):
    data={"user":json.dumps({"id":chat}),"auth_date":str(ts)}
    canonical="\n".join(k+"="+data[k] for k in sorted(data))
    data["hash"]=hmac.new(hmac.digest(b"WebAppData",token.encode(),"sha256"),canonical.encode(),hashlib.sha256).hexdigest()
    return urlencode(data)


class CampusTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.s=Store(":memory:")
        self.s.set("owner",123)
        self.b=Bot(self.s,None)

    def tearDown(self):
        self.s.db.close()

    def test_telegram_identity(self):
        now=int(time.time())
        self.assertTrue(authorized(signed(123,"test",now),"test",123))
        self.assertFalse(authorized(signed(123,"test",now-4000),"test",123))
        self.assertFalse(authorized(signed(999,"test",now),"test",123))
        self.assertFalse(authorized(signed(123,"another",now),"test",123))
        self.assertFalse(authorized("", "test",None))

    async def test_forwarded_message_and_undo(self):
        text="Сдать лабораторную до завтра 17:20\n- Нарисовать график\n- Оформить отчёт"
        event={"update_id":7,"message":{"chat":{"type":"private","id":123},"from":{"id":123},"text":text,"forward_origin":{"type":"hidden_user"}}}
        await self.b.update(event)
        self.assertEqual(self.s.db.execute("SELECT count(*) FROM tasks").fetchone()[0],0)
        self.assertEqual(self.s.get("screen")["draft"]["steps"],["Нарисовать график","Оформить отчёт"])
        await self.b.route("Сохранить черновик")
        await self.b.route("✅ Выполнить")
        await self.b.route("↩ Отменить выполнение")
        self.assertEqual(self.s.db.execute("SELECT done FROM tasks").fetchone()[0],0)
        self.assertEqual(self.s.db.execute("SELECT count(*) FROM steps").fetchone()[0],2)
        self.assertEqual(draft_task("Без даты")["due"],"")

    async def test_mail_baseline_retry_and_restart(self):
        source=AsyncMock()
        m=Mail(self.s,source)
        self.s.set("isu_connected",True)
        m.imap.host=""
        def mail(uid):
            return dict(key=str(uid),sender="Отправитель",subject="Задание",body="Текст "+str(uid),date="18 ноя.")
        source.read.return_value=[mail(1)]
        await m.sync()
        self.assertEqual(self.s.db.execute("SELECT count(*) FROM outbox").fetchone()[0],0)
        source.read.return_value=[mail(2),mail(1)]
        await m.sync()
        source.read.side_effect=OSError()
        await m.sync()
        self.assertFalse(self.s.get("isu_status")["ok"])
        source.read.side_effect=None
        m=Mail(self.s,source)
        m.imap.host=""
        await m.sync()
        self.assertEqual(self.s.db.execute("SELECT count(*) FROM outbox").fetchone()[0],1)
        self.assertEqual(self.s.db.execute("SELECT count(*) FROM mail").fetchone()[0],2)

    def test_readable_email(self):
        raw=b"From: Sender <sender@isu.ifmo.ru>\r\nSubject: Deadline\r\nContent-Type: text/html; charset=utf-8\r\n\r\n<p>Details</p><script>invisible</script>"
        message=parse_message(raw,"fixture")
        self.assertEqual(message["body"],"Details")
        self.assertTrue(allowed(message["sender"],["isu.ifmo.ru"]))
        self.assertFalse(allowed("somebody@example.com",["isu.ifmo.ru"]))

    def test_departure_and_week(self):
        now=datetime(2026,11,18,9,25,tzinfo=MSK)
        day=now.date().isoformat()
        self.s.set("travel_on",True)
        self.s.set("campus_minutes",{"Корпус А":40})
        self.s.set("latest_dates",[day])
        rows=[dict(subject="Семинар",format="онлайн",building="",time_start="08:00"),
              dict(subject="Физика",format="очно",building="Корпус А",time_start="10:00")]
        self.s.set("cache",{day:dict(lessons=rows,checked=now.isoformat())})
        departure(self.s,now)
        departure(self.s,now)
        sent=self.s.db.execute("SELECT text FROM outbox").fetchall()
        self.assertEqual(len(sent),1)
        self.assertIn("40 мин",sent[0][0])
        self.assertIn("пар — 2",weekly_report(self.s,now.date()))

    async def test_sunday_once(self):
        now=datetime(2026,11,22,18,1,tzinfo=MSK)
        self.b.monitor.now=lambda:now
        await self.b.monitor.tick()
        await self.b.monitor.tick()
        items=self.s.db.execute("SELECT text FROM outbox").fetchall()
        self.assertEqual(len(items),1)
        self.assertIn("23.11 по 29.11",items[0][0])

    async def test_task_crud_and_transaction(self):
        p={"title":"Доклад","due":"2027-01-01 14:00","category":"Физика","lead":60,"steps":["слайды"]}
        model=await action(self.b,"task_save",p)
        task=model["tasks"][0]
        self.assertEqual(task["steps"][0]["title"],"слайды")
        for done in (True,False):
            model=await action(self.b,"task_done",dict(id=task["id"],done=done))
            self.assertEqual(model["tasks"][0]["done"],done)
        with self.assertRaises(ValueError):
            await action(self.b,"task_save",dict(p,steps=[""]))
        self.assertEqual(self.s.db.execute("SELECT count(*) FROM tasks").fetchone()[0],1)
        model=await action(self.b,"task_delete",dict(id=task["id"]))
        self.assertFalse(model["tasks"])
        self.assertFalse(self.s.db.execute("SELECT * FROM steps").fetchall())

    async def test_http_private_api(self):
        testtoken="test-only"
        async with TestClient(TestServer(application(self.b,testtoken))) as client:
            res=await client.post("/api/state",json={})
            self.assertEqual(res.status,403)
            for path in ("/.env","/data/planner.sqlite3","/bot.py"):
                self.assertEqual((await client.get(path)).status,404)
            for path in ("/","/app.js","/app.css","/login.html","/login.css"):
                self.assertEqual((await client.get(path)).status,200)
            auth={"X-Telegram-Init-Data":signed(123,testtoken,int(time.time()))}
            res=await client.post("/api/action",headers=auth,json={"action":"settings","theme":"mint","campus_minutes":{"A":25}})
            self.assertEqual(res.status,200)
            self.assertEqual((await res.json())["settings"]["theme"],"mint")
            self.assertEqual(self.s.get("campus_minutes"),{"A":25})

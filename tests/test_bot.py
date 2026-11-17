import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bot import Bot, CLOCK, INTERVAL
from itmo import MSK, SourceError, changes, parse_week
from monitor import Monitor
from planner import BACK, NEW, SETTINGS, TASKS, TODAY
from store import Store


def day_entry(day, group, pair_id):
    return {"date":day.isoformat(), "lessons":[{"subject":"Алгебра", "group":group,
            "time_start":"08:20", "time_end":"09:50", "room":"101", "pair_id":pair_id}]}


def sample(day):
    return {"code":0, "data":[day_entry(day,"Поток А",34),day_entry(day+timedelta(days=1),"Поток Б",65)]}


class Source:
    def __init__(self, body):
        self.body = body
        self.calls = 0

    async def read(self, start):
        self.calls += 1
        if isinstance(self.body, Exception):
            raise self.body
        return parse_week(self.body,start)


class DiffTests(unittest.TestCase):
    d = date(2026,11,18)

    def test_groups_new_day_and_reorder(self):
        body = sample(self.d)
        body["data"][0]["lessons"].append(dict(body["data"][1]["lessons"][0]))
        before = parse_week(body,self.d)
        body["data"][0]["lessons"].reverse()
        after = parse_week(body,self.d)
        self.assertEqual(changes(before,after), [])
        shifted = parse_week(sample(self.d+timedelta(days=1)),self.d+timedelta(days=1))
        shifted.update({self.d.isoformat():after[self.d.isoformat()]})
        shifted[(self.d+timedelta(days=1)).isoformat()] = after[(self.d+timedelta(days=1)).isoformat()]
        self.assertEqual(changes(after,shifted), [])

    def test_time_room_and_move(self):
        body = sample(self.d)
        before = parse_week(body,self.d)
        lesson = body["data"][0]["lessons"].pop()
        lesson.update(time_start="10:00",room="302")
        body["data"][1]["lessons"].append(lesson)
        delta = changes(before,parse_week(body,self.d))
        self.assertEqual(len(delta),1)
        for fragment in ("Было", "18.11","19.11","08:20","10:00","101","302"):
            self.assertIn(fragment,delta[0])

    def test_add_remove_unknown_and_bad_data(self):
        body = sample(self.d)
        old = parse_week(body,self.d)
        body["data"][0]["lessons"] = []
        after = parse_week(body,self.d)
        self.assertIn("Убрали",changes(old,after)[0])
        self.assertIn("Добавили",changes(after,old)[0])
        self.assertEqual(changes(old,{}),[])
        for payload in ({"code":1,"data":[]},{"code":0,"data":[{"date":self.d.isoformat()}]}, "HTML"):
            with self.assertRaises(SourceError):
                parse_week(payload,self.d)


class MonitorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.s = Store(":memory:")
        self.s.set("owner",10)
        self.s.set("connected",True)
        self.now = datetime(2026,11,18,7,29,tzinfo=MSK)
        self.source = Source(sample(self.now.date()))
        self.m = Monitor(self.s,self.source,lambda:self.now)

    def messages(self):
        return [r[0] for r in self.s.db.execute("SELECT text FROM outbox")]

    async def test_fresh_morning_and_single_diff(self):
        await self.m.tick()
        self.assertEqual(self.messages(),[])
        self.now += timedelta(minutes=1)
        self.source.body["data"][0]["lessons"][0]["room"] = "404"
        await self.m.tick()
        self.assertEqual(self.source.calls,2)
        self.assertEqual(len(self.messages()),2)
        self.assertIn("Изменения",self.messages()[0])
        self.assertIn("404",self.messages()[1])
        self.now += timedelta(minutes=5)
        await self.m.tick()
        self.assertEqual(len(self.messages()),2)
        self.assertEqual(self.source.calls,3)

    async def test_offline_morning_recovery_with_checks_off(self):
        await self.m.fetch()
        self.s.set("interval",0)
        self.now += timedelta(minutes=2)
        self.source.body = SourceError("Нет сети.")
        await self.m.tick()
        self.assertTrue(any("Сохранённая копия" in m for m in self.messages()))
        self.assertFalse(any("Убрали" in m for m in self.messages()))
        self.source.body = sample(self.now.date())
        self.now += timedelta(minutes=5)
        await self.m.tick()
        self.assertIn("Доброе утро",self.messages()[-1])
        self.assertNotIn("Сохранённая копия",self.messages()[-1])
        self.assertEqual(self.s.get("morning_sent"),self.now.date().isoformat())

    async def test_missing_today_doesnt_repeat_morning(self):
        self.now += timedelta(minutes=2)
        self.source.body["data"] = self.source.body["data"][1:]
        await self.m.tick()
        self.now += timedelta(minutes=5)
        await self.m.tick()
        self.assertEqual(len(self.messages()),1)
        self.assertIn("не вернул данные",self.messages()[0])
        self.source.body = sample(self.now.date())
        self.now += timedelta(minutes=5)
        await self.m.tick()
        self.assertEqual(len(self.messages()),2)

    async def test_deadline_survives_restarts(self):
        for title,done in [("Отчёт",0),("Сдано",1)]:
            self.s.db.execute("INSERT INTO tasks(title,category,due,lead,done) VALUES (?,'Учёба',?,60,?)",
                              (title,"2026-11-18 08:20",done))
        await self.m.tick()
        await Monitor(self.s,self.source,lambda:self.now).tick()
        self.assertEqual(len(self.messages()),1)
        self.assertIn("Отчёт",self.messages()[0])


class MenuTests(unittest.IsolatedAsyncioTestCase):
    async def test_today_fetches_when_monitor_is_disabled(self):
        s = Store(":memory:")
        d = datetime.now(MSK).date()
        source = Source(sample(d))
        bot = Bot(s,source)
        for key, value in dict(owner=42, connected=True, interval=0, morning_on=False).items():
            s.set(key,value)
        first, _ = await bot.route(TODAY)
        self.assertIn("ауд. 101",first)
        source.body["data"][0]["lessons"][0]["room"] = "910"
        second, _ = await bot.route(TODAY)
        self.assertEqual(source.calls,2)
        self.assertIn("ауд. 910",second)
        self.assertNotIn("ауд. 101",second)

    async def test_keyboard_flow_and_persistence(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"bot.db"
            s = Store(path)
            bot = Bot(s,None)
            number = 0
            async def send(text, chat=42, kind="private"):
                nonlocal number
                number += 1
                event = {"update_id":number,"message":{"text":text,"from":{"id":chat},"chat":{"id":chat,"type":kind}}}
                await bot.update(event)
                await bot.update(event)
                return s.db.execute("SELECT text FROM outbox ORDER BY id DESC").fetchone()[0]
            await send("/start")
            await send(bot.pair_code,kind="group")
            self.assertIsNone(s.get("owner"))
            await send(bot.pair_code)
            await send(NEW)
            await send("Сдать лабораторную")
            await send("＋ Своя категория")
            await send("Физика")
            tomorrow = (datetime.now(MSK).date()+timedelta(days=1)).strftime("%d.%m.%Y")
            await send(tomorrow)
            await send("18:00")
            self.assertIn("Задание сохранено",await send("За час"))
            await send("＋ Подзадача")
            await send("Построить график\nНаписать вывод")
            await send(s.get("keyboard")[0][0])
            self.assertIn("1/2",await send(BACK))
            await send("Перенести срок")
            await send(tomorrow)
            self.assertIn("21:00",await send("21:00"))
            s.db.close()
            s = Store(path)
            bot = Bot(s,None)
            await send(TASKS)
            await send("По категории")
            self.assertIn("Сдать лабораторную", await send("📁 Физика"))
            await send(s.get("keyboard")[0][0])
            await send("✅ Выполнить")
            await send(TASKS)
            self.assertIn("Сдать лабораторную",await send("Выполненные"))
            count = s.db.execute("SELECT count(*) FROM outbox").fetchone()[0]
            await send(TASKS,chat=77)
            self.assertEqual(s.db.execute("SELECT count(*) FROM outbox").fetchone()[0],count)
            await send(SETTINGS)
            await send(INTERVAL)
            self.assertIn("1 мин",await send("1 мин"))
            await send(CLOCK)
            self.assertIn("08:10",await send("08:10"))
            self.assertEqual(s.db.execute("SELECT count(*) FROM tasks").fetchone()[0],1)
            s.db.close()

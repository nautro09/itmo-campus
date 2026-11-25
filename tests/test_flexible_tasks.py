from datetime import datetime
from unittest import IsolatedAsyncioTestCase

from bot import Bot
from extras import PESOCHNAYA, campus_names, campus_overrides, campus_travel
from itmo import MSK
from miniapp import change_task
from store import Store


class ReminderTests(IsolatedAsyncioTestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.addCleanup(self.store.db.close)
        self.store.set("owner", 42)
        self.bot = Bot(self.store, None)
        self.task = dict(title="Начать готовиться к КР", category="Учёба", due="2026-11-26 08:10", lead=60)

    async def tick(self, stamp):
        self.bot.monitor.now = lambda: datetime.fromisoformat(stamp).replace(tzinfo=MSK)
        await self.bot.monitor.tick()
        return [row[0] for row in self.store.db.execute("SELECT text FROM outbox ORDER BY id")]

    async def test_independent_deadline_and_reminder(self):
        payload = dict(self.task, remind_at="2026-11-25 18:00")
        change_task(self.store.db, "task_save", payload)
        self.assertEqual(await self.tick("2026-11-25 17:59"), [])
        messages = await self.tick("2026-11-25 18:00")
        self.assertEqual(len(messages), 1)
        self.assertIn("Сдать до 26.11.2026 в 08:10", messages[0])
        change_task(self.store.db, "task_save", dict(payload, id=1, due="2026-11-27 08:10"))
        self.assertEqual(await self.tick("2026-11-26 08:10"), messages)

    async def test_custom_minutes_updated_with_deadline(self):
        payload = dict(self.task, lead=137)
        change_task(self.store.db, "task_save", payload)
        change_task(self.store.db, "task_save", dict(payload, id=1, due="2026-11-26 10:10"))
        self.assertFalse(await self.tick("2026-11-26 07:52"))
        self.assertEqual(len(await self.tick("2026-11-26 07:53")), 1)

    def test_keyboard_date_without_year(self):
        planner = self.bot.plan
        screen = {"name":"lead_exact","data":dict(self.task, mode="new")}
        text, _ = planner.handle("25.11 18:00", screen)
        self.assertIn("25.11.2026 в 18:00", text)
        self.assertIn("26.11.2026 в 08:10", text)

    def test_campus_alias_shares_travel_time(self):
        address = "Санкт-Петербург, Песочная наб., д. 14"
        self.assertIn(PESOCHNAYA, campus_names(self.store))
        self.assertEqual(campus_overrides({address:45}), {PESOCHNAYA:45})
        self.assertEqual(campus_travel({PESOCHNAYA:45}, address, 35), 45)

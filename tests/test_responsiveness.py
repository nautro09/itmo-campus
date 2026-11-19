import asyncio
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

from bot import Bot, deliver
from planner import HOME, MAIL
from itmo import MSK
from monitor import Monitor
from store import Store


class ResponseTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.store.set("quiet_on", False)
        self.addCleanup(self.store.db.close)

    async def test_idle_sender_wakes_and_serves_buttons_in_order(self):
        sent = asyncio.Event()
        api = AsyncMock()
        api.call.side_effect = lambda *args, **kwargs: sent.set()
        worker = asyncio.create_task(deliver(api, self.store))
        try:
            await asyncio.sleep(0)
            with self.store.db:
                self.store.post(1, "Почта", delivery="background")
                self.store.post(1, "Изменения пары", delivery="first")
                self.store.post(1, "Настройки")
                self.store.post(1, "Домой")
            await asyncio.wait_for(sent.wait(), .5)
            self.assertEqual(api.call.await_args.kwargs["text"], "Настройки")
            for expected in ("Домой", "Изменения пары", "Почта"):
                item = self.store.next_delivery()
                self.assertEqual(item["text"], expected)
                self.store.db.execute("DELETE FROM outbox WHERE id=?", (item["id"],))
        finally:
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)

    async def test_schedule_reuse_requires_recent_success_for_requested_day(self):
        now = datetime(2026, 11, 19, 10, tzinfo=MSK)
        day = now.date()
        portal = AsyncMock()
        portal.identity = {}
        portal.read.return_value = {day.isoformat(): []}
        self.store.set("morning_on", False)
        monitor = Monitor(self.store, portal, lambda: now)
        await monitor.fetch(for_days=[day])
        await monitor.fetch(for_days=[day])
        self.assertEqual(portal.read.await_count, 1)
        await monitor.fetch(for_days=[day + timedelta(days=1)])
        self.assertEqual(portal.read.await_count, 2)
        now += timedelta(seconds=31)
        await monitor.fetch(for_days=[day])
        self.assertEqual(portal.read.await_count, 3)
        self.store.set("source_error", "Нет сети")
        await monitor.fetch(for_days=[day])
        self.assertEqual(portal.read.await_count, 4)

    async def test_overlapping_requests_share_one_read(self):
        started, release = asyncio.Event(), asyncio.Event()
        now = datetime(2026, 11, 19, 10, tzinfo=MSK)
        day = now.date()
        async def slow_read(start):
            started.set()
            await release.wait()
            return {day.isoformat(): []}
        portal = AsyncMock()
        portal.identity = {}
        portal.read.side_effect = slow_read
        self.store.set("morning_on", False)
        monitor = Monitor(self.store, portal, lambda: now)
        first = asyncio.create_task(monitor.fetch())
        await started.wait()
        other = asyncio.create_task(monitor.fetch(for_days=[day]))
        await asyncio.sleep(0)
        release.set()
        await asyncio.gather(first, other)
        portal.read.assert_awaited_once_with(day)

    async def test_mail_check_does_not_block_or_restore_an_old_keyboard(self):
        self.store.set("owner", 11)
        bot = Bot(self.store, None)
        release = asyncio.Event()
        bot.mail.sync = AsyncMock(side_effect=release.wait)
        await bot.route(MAIL)
        reply, _ = await bot.route("Проверить почту")
        self.assertIn("Проверяю", reply)
        await bot.route("Проверить почту")
        await bot.route(HOME)
        release.set()
        await bot.mail_check_job
        bot.mail.sync.assert_awaited_once()
        self.assertIsNone(self.store.next_delivery()["keyboard"])
        self.assertEqual(self.store.get("screen")["name"], "home")

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bot import Bot
from grades import Grades
from itmo import SourceError
from miniapp import state
from store import Store


class StudyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.addCleanup(self.store.db.close)
        self.store.set("owner", 100)
        self.store.set("connected", True)

    async def test_score_change_after_restart_and_network_failure(self):
        portal = AsyncMock()
        def points(mark):
            return ["1/3", [{"name":"Физика", "est_id":1, "current_score":mark}]]
        portal.record_book.side_effect = [points("10,0"), SourceError("Сбой"), points(10), points(9), points(9)]
        for _ in range(5):
            await Grades(self.store, portal).sync()
        messages = self.store.db.execute("SELECT text FROM outbox").fetchall()
        self.assertEqual(len(messages), 1)
        self.assertIn("10 → 9", messages[0][0])

    async def test_campus_keyboard_and_independent_mail_statuses(self):
        bot = Bot(self.store, None)
        self.store.set("cache", {"2030-01-01":{"checked":"2030-01-01", "lessons":[{"building":"А","format":"очно"},{"building":"Б","format":"online"}]}})
        self.store.set("isu_connected", True)
        self.store.set("isu_status", {"ok":True,"detail":"Проверено"})
        bot.mail.imap.host = ""
        model = state(bot)
        self.assertTrue(model["services"]["isu"]["ok"])
        self.assertIn("не настроен", model["services"]["mail"]["detail"])
        bot.settings()
        await bot.route("🚶 Дорога")
        _, rows = await bot.route("По корпусам")
        self.assertIn(["А"],rows)
        self.assertNotIn(["Б"],rows)
        await bot.route("А")
        await bot.route("45")
        self.assertEqual(self.store.get("campus_minutes"), {"А":45})

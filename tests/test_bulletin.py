import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock

from bot import TelegramError, send_outbox_item
from bulletin import article
from store import Store


class BulletinTests(unittest.IsolatedAsyncioTestCase):
    async def test_cover_and_fallback_keep_keyboard_and_literal_text(self):
        store = Store(":memory:")
        self.addCleanup(store.db.close)
        text = "Доброе утро!\n\n19.11.2026, четверг\n\n08:10–09:40  А & Б <img>\nауд. 101"
        store.post(5, text, [["Сегодня"]], rubric="morning")
        row = store.next_delivery()
        api = AsyncMock()
        api.call.side_effect = [TelegramError(400), TelegramError(400), {}]
        await send_outbox_item(api, row)
        first, second, third = api.call.await_args_list
        self.assertEqual([c.args[0] for c in (first, second, third)],
                         ["sendRichMessage", "sendRichMessage", "sendMessage"])
        markup = first.kwargs["rich_message"]["html"]
        self.assertTrue(markup.startswith("<img "))
        self.assertIn("<h3>08:10–09:40</h3>", markup)
        self.assertIn("А &amp; Б &lt;img&gt;", markup)
        self.assertNotIn("<img ", second.kwargs["rich_message"]["html"])
        self.assertEqual(third.kwargs["text"], text)
        self.assertEqual(first.kwargs["reply_markup"], third.kwargs["reply_markup"])

        api.reset_mock()
        api.call.side_effect = TelegramError(429)
        with self.assertRaises(TelegramError):
            await send_outbox_item(api, row)
        self.assertEqual(api.call.await_count, 1)

    def test_legacy_outbox_and_long_mail(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "old.sqlite"
            conn = sqlite3.connect(path)
            conn.execute("CREATE TABLE outbox (id INTEGER PRIMARY KEY, chat INTEGER, text TEXT, keyboard TEXT)")
            conn.execute("INSERT INTO outbox(chat,text) VALUES (5,'Сохранённое сообщение')")
            conn.commit()
            conn.close()
            store = Store(path)
            try:
                self.assertIsNone(store.next_delivery()["rubric"])
                store.post(5, "ИСУ · Автор\nТема\n\n" + "😀" * 4000, [["Назад"]], rubric="mail")
                parts = store.db.execute("SELECT * FROM outbox WHERE id>1 ORDER BY id").fetchall()
                self.assertEqual(parts[0]["rubric"], "mail")
                self.assertTrue(all(p["rubric"] is None for p in parts[1:]))
                self.assertTrue(parts[-1]["keyboard"])
                self.assertEqual(sum(p["text"].count("😀") for p in parts), 4000)
            finally:
                store.db.close()

    def test_change_and_quiet_digest_preserve_the_original(self):
        markup = article("changes", "Изменения в расписании\n\nИзменили пару\nБыло  19.11 · 101\nСтало  19.11 · 203")["html"]
        self.assertIn("<b>Было</b>", markup)
        self.assertIn("19.11 · 203", markup)
        store = Store(":memory:")
        self.addCleanup(store.db.close)
        store.post(5, "ИСУ\nТема\n\n<x>", delivery="background", rubric="mail", now=datetime(2026,11,18,23))
        row = store.next_delivery(datetime(2026,11,19,8))
        self.assertEqual(row["rubric"], "digest")
        self.assertIn("&lt;x&gt;", article(row["rubric"], row["text"])["html"])

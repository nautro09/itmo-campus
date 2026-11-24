import hashlib
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

from bot import Bot
from store import Store


class PrivateAccess(IsolatedAsyncioTestCase):
    def setUp(self):
        self.s=Store(":memory:")
        self.addCleanup(self.s.db.close)
        self.s.set("owner",42)
        self.bot=Bot(self.s,None)
        self.seq=0

    async def send(self, uid, text, kind="private"):
        self.seq+=1
        await self.bot.update({"update_id":self.seq,"message":{"chat":{"type":kind,"id":uid},"from":{"id":uid},"text":text}})

    async def test_foreign_updates_have_no_state_or_replies(self):
        changes=self.s.db.total_changes
        for uid in range(100,1100):
            await self.send(uid,"/start")
            await self.send(uid,"/verify example")
        self.assertEqual(self.s.db.total_changes,changes)
        for _ in range(10):
            await self.send(42,"/start")
        self.assertEqual(self.s.db.execute("select count(*) from outbox").fetchone()[0],3)

    async def test_private_verification(self):
        with patch.dict("os.environ",ADMIN_VERIFY_SHA256=hashlib.sha256(b"test-only").hexdigest()):
            await self.send(42,"/verify wrong")
            await self.send(42,"/verify test-only","group")
            await self.send(55,"/verify test-only")
            self.assertEqual(self.s.db.execute("select count(*) from outbox").fetchone()[0],0)
            await self.send(42,"/verify test-only")
            reply=self.s.db.execute("select text from outbox").fetchone()[0]
            self.assertIn("Доступ владельца подтверждён",reply)
            self.assertNotIn("test-only",reply)

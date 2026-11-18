import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from store import Store
from miniapp import save_settings


class QuietHours(unittest.TestCase):
    def test_range(self):
        s = Store(":memory:")
        self.addCleanup(s.db.close)
        for hour, expected in [(23,True),(0,True),(6,True),(7,False),(22,False)]:
            self.assertEqual(s.quiet(datetime(2026,1,3,hour)),expected)
        with s.db:
            save_settings(s,{"quiet_start":"12:00","quiet_end":"14:00"})
        self.assertFalse(s.quiet(datetime(2026,1,3,0)))
        self.assertTrue(s.quiet(datetime(2026,1,3,12)))
        with self.assertRaises(ValueError), s.db:
            save_settings(s,{"quiet_end":"12:00"})
        self.assertEqual(s.get("quiet_end"),"14:00")

    def test_restart_digest_and_exceptions(self):
        night = datetime(2026,1,3,23)
        morning = datetime(2026,1,4,7)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"store.db"
            s = Store(path)
            with s.db:
                s.post(1,"Письмо",delivery="background",now=night)
                s.post(1,"Ответ на кнопку")
                s.post(1,"Замена",delivery="first",now=night)
            for text in ("Ответ на кнопку","Замена"):
                row=s.next_delivery(night)
                self.assertEqual(row["text"],text)
                with s.db:
                    s.db.execute("DELETE FROM outbox WHERE id=?",(row["id"],))
            self.assertIsNone(s.next_delivery(night))
            with s.db:
                s.set("quiet_first",False)
                s.post(1,"Новая аудитория",delivery="first",now=night)
            s.db.close()
            s=Store(path)
            self.addCleanup(s.db.close)
            row=s.next_delivery(morning)
            self.assertIn("Письмо",row["text"])
            self.assertIn("Новая аудитория",row["text"])
            self.assertEqual(s.next_delivery(morning)["id"],row["id"])

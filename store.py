import json
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo


class Store:
    def __init__(self, path):
        self.delivery_event = None
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA foreign_keys = ON;
            CREATE TABLE IF NOT EXISTS prefs (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS categories (name TEXT PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY, title TEXT NOT NULL, category TEXT NOT NULL REFERENCES categories(name),
                due TEXT NOT NULL, lead INTEGER NOT NULL, done INTEGER NOT NULL DEFAULT 0,
                reminded INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS tasks_due ON tasks(done, due);
            CREATE TABLE IF NOT EXISTS steps (
                id INTEGER PRIMARY KEY, task_id INTEGER NOT NULL REFERENCES tasks(id),
                title TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS mail (
                id INTEGER PRIMARY KEY, source TEXT NOT NULL, source_id TEXT NOT NULL, sender TEXT,
                subject TEXT, body TEXT, date TEXT, UNIQUE(source, source_id)
            );
            CREATE TABLE IF NOT EXISTS outbox (
                id INTEGER PRIMARY KEY, chat INTEGER NOT NULL, text TEXT NOT NULL, keyboard TEXT
            );
        """)
        with self.db:
            if "remind_at" not in {r[1] for r in self.db.execute("PRAGMA table_info(tasks)")}:
                self.db.execute("ALTER TABLE tasks ADD COLUMN remind_at TEXT")
            self.db.execute("""CREATE INDEX IF NOT EXISTS tasks_pending ON tasks(
                COALESCE(remind_at, strftime('%Y-%m-%d %H:%M',due,'-' || lead || ' minutes')))
                WHERE done=0 AND reminded=0 AND (lead>=0 OR remind_at IS NOT NULL)""")
            columns = {row[1] for row in self.db.execute("PRAGMA table_info(outbox)")}
            if "delivery" not in columns:
                self.db.execute("ALTER TABLE outbox ADD COLUMN delivery TEXT NOT NULL DEFAULT 'direct'")
            if "rubric" not in columns:
                self.db.execute("ALTER TABLE outbox ADD COLUMN rubric TEXT")
            self.db.execute("CREATE INDEX IF NOT EXISTS outbox_delivery ON outbox(delivery,id)")
            self.db.executemany("INSERT OR IGNORE INTO categories VALUES (?)",
                                [(v,) for v in ("Учёба", "Лабораторные", "Проекты", "Личное")])

    def get(self, key, default=None):
        row = self.db.execute("SELECT value FROM prefs WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set(self, key, value):
        self.db.execute("INSERT OR REPLACE INTO prefs VALUES (?,?)",
                        (key, json.dumps(value, ensure_ascii=False)))
        if self.delivery_event is not None and key.startswith("quiet_"):
            self.delivery_event.set()

    def quiet(self, now=None):
        if not self.get("quiet_on", True):
            return False
        clock = (now or datetime.now(ZoneInfo("Europe/Moscow"))).strftime("%H:%M")
        start, end = self.get("quiet_start","23:00"), self.get("quiet_end","07:00")
        return start <= clock < end if start < end else clock >= start or clock < end

    def next_delivery(self, now=None):
        if not self.db.execute("SELECT 1 FROM outbox LIMIT 1").fetchone():
            return None
        with self.db:
            if self.quiet(now):
                self.db.execute("UPDATE outbox SET delivery='held' WHERE delivery='background'")
                if not self.get("quiet_first",True):
                    self.db.execute("UPDATE outbox SET delivery='held' WHERE delivery='first'")
            else:
                held = self.db.execute("SELECT chat,text,rubric FROM outbox WHERE delivery='held' ORDER BY id").fetchall()
                if held:
                    self.db.execute("DELETE FROM outbox WHERE delivery='held'")
                    groups = {}
                    labels = {"due":"Задания", "changes":"Изменения пар", "grades":"Баллы БаРС",
                              "mail":"Почта", "morning":"Расписание", "departure":"Дорога", "week":"За неделю"}
                    for row in held:
                        label = labels.get(row["rubric"], "Другие уведомления")
                        groups.setdefault(row["chat"], {}).setdefault(label, []).append(row["text"])
                    for chat, sections in groups.items():
                        parts = ["Сводка за тихие часы"]
                        for label, messages in sections.items():
                            parts.append(f"{label} · {len(messages)}")
                            counts = {}
                            for message in messages:
                                counts[message] = counts.get(message, 0) + 1
                            entries = []
                            for message, count in counts.items():
                                if label == "Почта" and len(message) > 300:
                                    message = message[:260].rstrip() + "…\nПолный текст в разделе «Почта»."
                                repeat = f" (×{count})" if count > 1 else ""
                                entries.append("• " + message.strip() + repeat)
                            parts[-1] += "\n" + "\n".join(entries)
                        self.post(chat, "\n\n".join(parts), delivery="background", now=now, rubric="digest")
            # Each lookup uses the (delivery, id) index and preserves order within the class.
            for priority in ("direct", "first", "background"):
                row = self.db.execute("SELECT * FROM outbox WHERE delivery=? ORDER BY id LIMIT 1",
                                      (priority,)).fetchone()
                if row:
                    return row
        return None

    def post(self, chat, message, keyboard=None, *, delivery="direct", now=None, rubric=None):
        if delivery in ("first","background") and self.quiet(now):
            if delivery == "background" or not self.get("quiet_first",True):
                delivery = "held"
        if delivery == "held" and rubric == "mail" and len(message) > 300:
            message = message[:260].rstrip() + "…\nПолный текст в разделе «Почта»."
        # Stay below Telegram's UTF-16 length limit, including long emoji-rich text.
        chunks, chunk, units = [], "", 0
        for line in message.splitlines(keepends=True):
            line_units = len(line.encode("utf-16-le")) // 2
            if chunk and units + line_units > 4000:
                chunks.append(chunk.rstrip())
                chunk, units = "", 0
            for char in line:
                size = 1 + (ord(char) > 0xffff)
                if units + size > 4000:
                    chunks.append(chunk.rstrip())
                    chunk, units = "", 0
                chunk += char
                units += size
        if chunk.strip():
            chunks.append(chunk.rstrip())
        chunks = [part for part in chunks if part]
        for i, part in enumerate(chunks):
            markup = json.dumps(keyboard, ensure_ascii=False) if keyboard and i == len(chunks)-1 else None
            self.db.execute("INSERT INTO outbox(chat,text,keyboard,delivery,rubric) VALUES (?,?,?,?,?)",
                            (chat, part, markup, delivery, rubric if i == 0 else None))
        if chunks and self.delivery_event is not None:
            self.delivery_event.set()

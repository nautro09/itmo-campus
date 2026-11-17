import json
import sqlite3


class Store:
    def __init__(self, path):
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
            self.db.executemany("INSERT OR IGNORE INTO categories VALUES (?)",
                                [(v,) for v in ("Учёба", "Лабораторные", "Проекты", "Личное")])

    def get(self, key, default=None):
        row = self.db.execute("SELECT value FROM prefs WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set(self, key, value):
        self.db.execute("INSERT OR REPLACE INTO prefs VALUES (?,?)",
                        (key, json.dumps(value, ensure_ascii=False)))

    def post(self, chat, message, keyboard=None):
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
            self.db.execute("INSERT INTO outbox(chat,text,keyboard) VALUES (?,?,?)", (chat, part, markup))

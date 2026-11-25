from datetime import date, datetime, timedelta

from itmo import MSK

HOME = "🏠 Главное меню"
TASKS = "🗂 Мои задания"
NEW = "➕ Добавить задание"
TODAY = "📅 Сегодня"
TOMORROW = "📆 Завтра"
SETTINGS = "⚙️ Настройки"
FROM_TEXT = "💬 Из сообщения"
WEEK = "📊 Моя неделя"
MAIL = "✉️ Почта"
MAIN = [[TODAY, TOMORROW], [TASKS, NEW], [FROM_TEXT, WEEK], [MAIL, SETTINGS], ["📈 Баллы БаРС"]]
BACK = "‹ Назад"
PREV, NEXT = "← Раньше", "Дальше →"
FILTERS = ["Все открытые", "На 7 дней", "Просроченные", "По категории", "Выполненные"]
REMIND = {"За сутки": 1440, "За час": 60, "За 15 минут": 15, "В момент срока": 0, "Без напоминания": -1}
PAGE = 6


def pairs(labels):
    return [labels[n:n + 2] for n in range(0, len(labels), 2)]


def short(text, n=38):
    return text if len(text) <= n else text[:n-1] + "…"


class Planner:
    """One owner's persistent, reply-keyboard-based conversation."""
    def __init__(self, store):
        self.s = store
        self.db = store.db

    def screen(self, name, message, rows, **data):
        self.s.set("screen", dict(data, name=name))
        return message, rows + ([[HOME]] if name != "home" else [])

    def home(self):
        return self.screen("home", "Что посмотрим?", MAIN)

    def filters(self):
        return self.screen("filters", "Какие задания показать?", pairs(FILTERS) + [[NEW]])

    def categories(self, data, page=0):
        names = [r[0] for r in self.db.execute("SELECT name FROM categories ORDER BY name")]
        labels = ["📁 " + n for n in names[page*PAGE:][:PAGE]]
        nav = self.navigation(page, len(names))
        extra = [["＋ Своя категория"]] if data["mode"] != "filter" else []
        return self.screen("category", "Выбери категорию.", pairs(labels) + nav + extra + [[BACK]],
                           data=data, page=page)

    @staticmethod
    def navigation(page, count):
        buttons = ([PREV] if page else []) + ([NEXT] if (page+1)*PAGE < count else [])
        return [buttons] if buttons else []

    def listing(self, filt, category="", page=0):
        now = datetime.now(MSK)
        query = "SELECT * FROM tasks WHERE done=?"
        args = [int(filt == "Выполненные")]
        if filt == "Просроченные":
            query += " AND due < ?"
            args += [now.strftime("%Y-%m-%d %H:%M")]
        if filt == "На 7 дней":
            query += " AND due >= ? AND due < ?"
            args += [now.strftime("%Y-%m-%d %H:%M"), (now.date() + timedelta(days=7)).isoformat()]
        if filt == "По категории":
            query += " AND category=?"
            args += [category]
        count = self.db.execute(query.replace("SELECT *", "SELECT COUNT(*)"), args).fetchone()[0]
        page = min(max(0, page), max(0, (count-1)//PAGE))
        visible = self.db.execute(query + " ORDER BY due, id LIMIT ? OFFSET ?", [*args, PAGE, page*PAGE]).fetchall()
        entries = [f"#{t['id']}  {short(t['title'])}" for t in visible]
        lines = [f"{category or filt} · {count}"]
        for label, t in zip(entries, visible):
            lines.append(f"{label}\n    {datetime.fromisoformat(t['due']):%d.%m.%Y в %H:%M} · {t['category']}")
        if not visible:
            lines.append("Здесь пока нет заданий.")
        rows = [[e] for e in entries] + self.navigation(page, count) + [[NEW, BACK]]
        return self.screen("list", "\n\n".join(lines), rows, filt=filt, category=category, page=page)

    def card(self, task, origin=None, note=""):
        t = self.db.execute("SELECT * FROM tasks WHERE id=?", (task,)).fetchone()
        if not t:
            return self.filters()
        steps = self.db.execute("SELECT * FROM steps WHERE task_id=? ORDER BY id", (task,)).fetchall()
        lead = (datetime.fromisoformat(t["remind_at"]).strftime("%d.%m.%Y в %H:%M МСК") if t["remind_at"]
                else next((label for label, minutes in REMIND.items() if minutes == t["lead"]), f"За {t['lead']} мин"))
        due = datetime.fromisoformat(t["due"])
        status = "✅ Выполнено" if t["done"] else "⏳ Открыто"
        if not t["done"] and due < datetime.now(MSK).replace(tzinfo=None):
            status = "🔴 Просрочено"
        text = f"{status} · #{task}\n{t['title']}\n\n📁 {t['category']}\nСдать до {due:%d.%m.%Y в %H:%M} МСК\nНапоминание · {lead}"
        text += f"\n\nПодзадачи · {sum(s['done'] for s in steps)}/{len(steps)}"
        for step in steps[:4]:
            text += "\n" + ("☑ " if step["done"] else "☐ ") + step["title"]
        if len(steps) > 4:
            text += f"\nЕщё {len(steps)-4} — открой «Подзадачи»."
        rows = [["Подзадачи", "＋ Подзадача"], ["Перенести срок", "Изменить категорию"],
                ["Напоминание", "↩ Отменить выполнение" if t["done"] else "✅ Выполнить"], [BACK]]
        return self.screen("card", (note+"\n\n" if note else "") + text, rows, task=task, origin=origin)

    def steps(self, s, page=0):
        rows = self.db.execute("SELECT * FROM steps WHERE task_id=? ORDER BY id", (s["task"],)).fetchall()
        visible = rows[page*PAGE:][:PAGE]
        labels = [("☑" if r["done"] else "☐") + f" {r['id']} · {short(r['title'])}" for r in visible]
        text = ["Нажми на подзадачу, чтобы изменить отметку."] if rows else ["Пока нет подзадач."]
        text += [("☑ " if r["done"] else "☐ ") + r["title"] for r in visible]
        return self.screen("steps", "\n\n".join(text), [[v] for v in labels] + self.navigation(page,len(rows))
                           + [["＋ Подзадача", BACK]], task=s["task"], origin=s.get("origin"), page=page)

    def date_picker(self, data, page=0):
        today = datetime.now(MSK).date()
        first = today + timedelta(days=7*page)
        days = [first+timedelta(days=i) for i in range(7)]
        labels = [d.strftime("%d.%m.%Y") for d in days]
        nav = ([PREV] if page > 0 else []) + [NEXT]
        return self.screen("date", "На какой день поставить дедлайн? Можно также ввести дату в формате ДД.ММ.ГГГГ.",
                           pairs(labels) + [nav, [BACK]], data=data, page=page)

    def time_picker(self, data):
        return self.screen("time", f"Срок на {date.fromisoformat(data['day']):%d.%m.%Y}. Выбери время или введи ЧЧ:ММ (МСК).",
                           pairs(["09:00", "12:00", "15:00", "18:00", "21:00", "23:59"]) + [[BACK]], data=data)

    def lead_picker(self, data):
        return self.screen("lead", "Когда напомнить о задании?", pairs(list(REMIND)) + [["Свои минуты", "Дата и время"], [BACK]], data=data)

    def selected_category(self, data, category):
        if data["mode"] == "filter":
            return self.listing("По категории", category)
        if data["mode"] == "recategorize":
            self.db.execute("UPDATE tasks SET category=? WHERE id=?", (category, data["task"]))
            return self.card(data["task"], data.get("origin"))
        return self.date_picker(dict(data, category=category))

    def new(self):
        return self.screen("title", "Что нужно сделать? Введи название задания.", [[BACK]])

    def handle(self, text, s):
        name = s["name"]
        task, origin = s.get("task"), s.get("origin")
        data = s.get("data", {})
        if text == NEW:
            return self.new()
        if text == TASKS:
            return self.filters()
        if text == BACK:
            if name in ("steps", "step_title"):
                return self.card(task, origin)
            if name == "card" and origin:
                return self.listing(**origin)
            if name in ("card", "list") or (name == "category" and data["mode"] == "filter"):
                return self.filters()
            if name == "category_text":
                return self.categories(data)
            if name == "time":
                return self.date_picker(data)
            if name in ("lead_exact","lead_minutes"):
                return self.lead_picker(data)
            if name == "lead" and data["mode"] == "new":
                return self.time_picker(data)
            if data.get("task"):
                return self.card(data["task"], data.get("origin"))
            if name == "date":
                return self.categories(data)
            if name == "category":
                return self.new()
            return self.home()
        if name == "filters" and text in FILTERS:
            return self.categories({"mode":"filter"}) if text == "По категории" else self.listing(text)
        if name == "title":
            if not 1 <= len(text) <= 160:
                return "Введи название длиной от 1 до 160 символов.", [[BACK, HOME]]
            return self.categories({"mode":"new", "title":text})
        if name == "category":
            if text in (PREV, NEXT):
                return self.categories(data, max(0, s["page"] + (1 if text == NEXT else -1)))
            if text == "＋ Своя категория" and data["mode"] != "filter":
                return self.screen("category_text", "Как назвать категорию?", [[BACK]], data=data)
            if text.startswith("📁 ") and self.db.execute("SELECT 1 FROM categories WHERE name=?", (text[2:],)).fetchone():
                return self.selected_category(data, text[2:])
        if name == "category_text":
            if not 1 <= len(text) <= 32 or "\n" in text:
                return "Введи название в одну строку, до 32 символов.", [[BACK, HOME]]
            self.db.execute("INSERT OR IGNORE INTO categories VALUES (?)", (text,))
            return self.selected_category(data, text)
        if name == "date":
            if text in (NEXT, PREV):
                return self.date_picker(data, min(520, max(0, s["page"] + (1 if text == NEXT else -1))))
            try:
                day = datetime.strptime(text,"%d.%m.%Y").date()
                if day < datetime.now(MSK).date():
                    raise ValueError()
            except ValueError:
                return self.date_picker(data, s["page"])
            return self.time_picker(dict(data, day=day.isoformat()))
        if name == "time":
            try:
                due = datetime.strptime(data["day"]+" "+text, "%Y-%m-%d %H:%M")
                if due <= datetime.now(MSK).replace(tzinfo=None):
                    raise ValueError()
            except ValueError:
                _, rows = self.time_picker(data)
                return "Выбери время в будущем по Москве, например 18:30.", rows
            due = due.strftime("%Y-%m-%d %H:%M")
            if data["mode"] == "reschedule":
                self.db.execute("UPDATE tasks SET due=?, reminded=CASE WHEN remind_at IS NULL THEN 0 ELSE reminded END WHERE id=?", (due, data["task"]))
                return self.card(data["task"], data.get("origin"), "Срок перенесён.")
            return self.lead_picker(dict(data, due=due))
        if name == "lead" and text in ("Дата и время", "Свои минуты"):
            exact = text == "Дата и время"
            return self.screen("lead_exact" if exact else "lead_minutes",
                               "Когда напомнить? Например, 25.11 18:00 МСК. Если год отличается от года сдачи, укажи его полностью." if exact else
                               "За сколько минут до сдачи напомнить? Введи число от 0 до 525600.", [[BACK]], data=data)
        if name in ("lead_exact","lead_minutes") or (name == "lead" and text in REMIND):
            remind_at = None
            if name == "lead_exact":
                try:
                    day, clock = text.split()
                    if day.count(".") == 1:
                        due = data.get("due") or self.db.execute("SELECT due FROM tasks WHERE id=?", (data["task"],)).fetchone()[0]
                        day += "." + due[:4]
                    remind_at = datetime.strptime(day+" "+clock,"%d.%m.%Y %H:%M").strftime("%Y-%m-%d %H:%M")
                except ValueError:
                    return "Укажи дату и время в формате ДД.ММ.ГГГГ ЧЧ:ММ.", [[BACK,HOME]]
                lead = -1
            elif name == "lead_minutes":
                if not text.isascii() or not text.isdecimal() or len(text)>6 or int(text)>525600:
                    return "Введи от 0 до 525600 минут.", [[BACK,HOME]]
                lead = int(text)
            else:
                lead = REMIND[text]
            if data["mode"] == "new":
                task = self.db.execute("INSERT INTO tasks(title,category,due,lead,remind_at) VALUES (?,?,?,?,?)",
                                       (data["title"],data["category"],data["due"],lead,remind_at)).lastrowid
                self.db.executemany("INSERT INTO steps(task_id,title) VALUES (?,?)",[(task,x) for x in data.get("steps",[])])
                return self.card(task, note="Задание сохранено.")
            self.db.execute("UPDATE tasks SET lead=?, remind_at=?, reminded=0 WHERE id=?", (lead,remind_at, data["task"]))
            return self.card(data["task"], data.get("origin"))
        if name == "list":
            origin = {k:s[k] for k in ("filt","category","page")}
            if text in (PREV, NEXT):
                origin["page"] += 1 if text == NEXT else -1
                return self.listing(**origin)
            if text.startswith("#") and text[1:].split(" ")[0].isdigit():
                return self.card(int(text[1:].split(" ")[0]), origin)
        if name == "card":
            data = {"task":task, "origin":origin}
            if text == "Подзадачи":
                return self.steps(s)
            if text == "Перенести срок":
                return self.date_picker(dict(data, mode="reschedule"))
            if text == "Изменить категорию":
                return self.categories(dict(data, mode="recategorize"))
            if text == "Напоминание":
                return self.lead_picker(dict(data, mode="remind"))
            if text in ("Вернуть в работу", "↩ Отменить выполнение", "✅ Выполнить"):
                self.db.execute("UPDATE tasks SET done=? WHERE id=?", (int(text == "✅ Выполнить"),task))
                return self.card(task, origin)
        if name in ("card", "steps") and text == "＋ Подзадача":
            return self.screen("step_title", "Введи один шаг или сразу несколько, каждый с новой строки.",
                               [[BACK]], task=task, origin=origin)
        if name == "step_title":
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            if not lines or len(lines)>30 or any(len(l)>160 for l in lines):
                return "Введи до 30 шагов, каждый в отдельной строке длиной до 160 символов.", [[BACK, HOME]]
            self.db.executemany("INSERT INTO steps(task_id,title) VALUES (?,?)", [(task,l) for l in lines])
            return self.steps(s)
        if name == "steps":
            if text in (PREV, NEXT):
                return self.steps(s, max(0, s["page"] + (1 if text == NEXT else -1)))
            parts = text.split(" ", 2)
            if len(parts)>1 and parts[0] in ("☐", "☑") and parts[1].isdigit():
                self.db.execute("UPDATE steps SET done=? WHERE id=? AND task_id=?",
                                (int(parts[0] == "☐"), int(parts[1]), task))
                return self.steps(s, s["page"])
        return "Выбери действие на панели.", self.s.get("keyboard", MAIN)

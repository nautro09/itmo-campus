import asyncio
from extras import departure, weekly_report
from datetime import datetime, timedelta

from itmo import MSK, SourceError, changes, day_text


class Monitor:
    def __init__(self, store, portal, now=lambda: datetime.now(MSK)):
        self.s = store
        self.portal = portal
        self.now = now
        self.lock = asyncio.Lock()
        self.signing_in = False

    async def fetch(self, automatic=False):
        async with self.lock:
            now = self.now()
            if automatic and not self.should_fetch(now):
                return
            chat = self.s.get("owner")
            with self.s.db:
                self.s.set("last_attempt", now.timestamp())
            try:
                week = await self.portal.read(now.date())
            except SourceError as e:
                with self.s.db:
                    self.s.set("source_error", str(e))
                    if not self.s.get("warned"):
                        self.s.post(chat, "⚠️ Не удалось обновить расписание. " + str(e))
                        self.s.set("warned", True)
                return
            cached = self.s.get("cache", {})
            old = {d:item["lessons"] for d, item in cached.items()}
            edits = changes(old, week) if self.s.get("interval", 1) else []
            with self.s.db:
                if edits:
                    self.s.post(chat, "🔔 Изменения в расписании\n\n" + "\n\n".join(edits))
                if self.s.get("warned"):
                    self.s.post(chat, "Проверка расписания снова работает.")
                for day, lessons in week.items():
                    cached[day] = {"lessons":lessons, "checked":now.isoformat()}
                self.s.set("cache", {d:v for d,v in cached.items() if d >= now.date().isoformat()})
                self.s.set("last_check", now.isoformat())
                self.s.set("source_error", "")
                self.s.set("latest_dates", list(week))
                self.s.set("warned", False)
                if getattr(self.portal, "identity", None):
                    self.s.set("profile", self.portal.identity)
                if self.morning_due(now) and (now.date().isoformat() in week or
                                              self.s.get("morning_partial") != now.date().isoformat()):
                    self.s.post(chat, "☀️ Доброе утро!\n\n" + self.show_day(now.date()))
                    if now.date().isoformat() in week:
                        self.s.set("morning_sent", now.date().isoformat())
                    else:
                        self.s.set("morning_partial", now.date().isoformat())

    def show_day(self, day):
        key = day.isoformat()
        cached = self.s.get("cache", {})
        item = cached.get(key)
        err = self.s.get("source_error", "")
        if item:
            text = day_text({key:item["lessons"]}, day)
            checked = datetime.fromisoformat(item["checked"])
            if err or key not in self.s.get("latest_dates", []):
                return f"⚠️ Сохранённая копия от {checked:%d.%m в %H:%M} МСК.\n{err or 'Свежих данных за этот день нет.'}\n\n{text}"
            return text + f"\n\nПроверено в {checked:%H:%M} МСК."
        return ("⚠️ " + err + "\n\n" if err else "") + day_text({}, day)

    def morning_due(self, now):
        return (self.s.get("morning_on", True) and now.strftime("%H:%M") >= self.s.get("morning_time","07:30")
                and self.s.get("morning_sent") != now.date().isoformat())

    def should_fetch(self, now):
        if self.signing_in or not self.s.get("connected"):
            return False
        elapsed = now.timestamp() - self.s.get("last_attempt", 0)
        interval = self.s.get("interval", 1)
        if self.morning_due(now):
            scheduled = datetime.fromisoformat(now.date().isoformat() + "T" + self.s.get("morning_time", "07:30")).replace(tzinfo=MSK)
            if self.s.get("last_attempt", 0) < scheduled.timestamp():
                return True
            # Retry an incomplete morning even when change alerts are disabled.
            if elapsed >= 300:
                return True
        if self.s.get("travel_on",False) and elapsed>=600:
            return True
        return bool(interval and elapsed >= interval * 60)

    async def tick(self):
        now = self.now()
        chat = self.s.get("owner")
        if not chat:
            return
        with self.s.db:
            for t in self.s.db.execute("SELECT * FROM tasks WHERE done=0 AND reminded=0 AND lead>=0").fetchall():
                due = datetime.fromisoformat(t["due"]).replace(tzinfo=MSK)
                if now >= due - timedelta(minutes=t["lead"]):
                    title = "Срок прошёл" if now > due + timedelta(minutes=1) else "Напоминание"
                    self.s.post(chat, f"⏰ {title} · #{t['id']}\n{t['title']}\n{t['category']} · {due:%d.%m.%Y в %H:%M} МСК")
                    self.s.db.execute("UPDATE tasks SET reminded=1 WHERE id=?", (t["id"],))
        if self.should_fetch(now):
            await self.fetch(automatic=True)
            with self.s.db:
                key = now.date().isoformat()
                if self.morning_due(now) and self.s.get("source_error") and self.s.get("morning_partial") != key:
                    self.s.post(chat, "☀️ Утреннее расписание\n\n" + self.show_day(now.date()))
                    self.s.set("morning_partial", key)
        with self.s.db:
            departure(self.s,now)
        if now.weekday()==6 and now.hour>=18 and self.s.get("weekly_on",True) and self.s.get("weekly_sent")!=now.date().isoformat():
            start=now.date()+timedelta(days=1)
            week=None
            if self.s.get("connected") and not self.signing_in:
                try:
                    week=await self.portal.read(start)
                except SourceError:
                    pass
            with self.s.db:
                self.s.post(chat,weekly_report(self.s,start,week))
                self.s.set("weekly_sent",now.date().isoformat())

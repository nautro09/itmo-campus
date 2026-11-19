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

    def recent_for(self, days, now):
        if not days or not self.s.get("interval", 1) or self.s.get("source_error"):
            return False
        checked = self.s.get("last_check")
        if not checked:
            return False
        stamp = datetime.fromisoformat(checked)
        latest = self.s.get("latest_dates", [])
        return (stamp.tzinfo is not None and stamp.date() == now.date() and 0 <= (now - stamp).total_seconds() < 30
                and all(day.isoformat() in latest for day in days))

    async def fetch(self, automatic=False, *, for_days=()):
        if self.recent_for(for_days, self.now()):
            return
        if self.lock.locked():
            # Another caller is already updating the same personal seven-day window.
            async with self.lock:
                return
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
                        self.s.post(chat, "⚠️ Не удалось обновить расписание. " + str(e), delivery="background")
                        self.s.set("warned", True)
                return
            cached = self.s.get("cache", {})
            old = {d:item["lessons"] for d, item in cached.items()}
            edits = changes(old, week, include_lessons=True) if self.s.get("interval", 1) else []
            with self.s.db:
                if edits and self.s.get("notify_schedule",True):
                    first = set()
                    for days in (old, week):
                        for date, lessons in days.items():
                            if not lessons or date not in (now.date().isoformat(), (now.date()+timedelta(days=1)).isoformat()):
                                continue
                            start = min(x["time_start"] for x in lessons)
                            if date > now.date().isoformat() or start >= now.strftime("%H:%M"):
                                first.add((date,start))
                    groups = {}
                    for affected, text in edits:
                        urgent = any((x["day"],x["time_start"]) in first for x in affected)
                        groups.setdefault("first" if urgent else "background", []).append(text)
                    for delivery, texts in groups.items():
                        self.s.post(chat, "Изменения в расписании\n\n" + "\n\n".join(texts), delivery=delivery, rubric="changes")
                if self.s.get("warned"):
                    self.s.post(chat, "Проверка расписания снова работает.", delivery="background")
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
                    self.s.post(chat, "Доброе утро!\n\n" + self.show_day(now.date()), delivery="background", rubric="morning")
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
        if (self.s.get("travel_on",False) or self.s.get("wake_on",False)) and elapsed>=600:
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
                    if self.s.get("notify_due",True):
                        self.s.post(chat, f"{title} · #{t['id']}\n{t['title']}\n{t['category']} · {due:%d.%m.%Y в %H:%M} МСК", delivery="background", rubric="due")
                    self.s.db.execute("UPDATE tasks SET reminded=1 WHERE id=?", (t["id"],))
        if self.should_fetch(now):
            await self.fetch(automatic=True)
            with self.s.db:
                key = now.date().isoformat()
                if self.morning_due(now) and self.s.get("source_error") and self.s.get("morning_partial") != key:
                    self.s.post(chat, "Утреннее расписание\n\n" + self.show_day(now.date()), delivery="background", rubric="morning")
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
                self.s.post(chat,weekly_report(self.s,start,week), delivery="background", rubric="week")
                self.s.set("weekly_sent",now.date().isoformat())

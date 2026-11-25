"""Drafting and owner-only study notifications. All dates use Moscow time."""
import re
from datetime import date, datetime, timedelta

from itmo import MSK

WEEKDAYS = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
MONTHS = "января февраля марта апреля мая июня июля августа сентября октября ноября декабря".split()
DAY_NAMES = ("понедельник", "вторник", "сред", "четверг", "пятниц", "суббот", "воскресень")


def draft_task(text, now=None):
    now = now or datetime.now(MSK)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        raise ValueError("В сообщении нет текста задания.")
    # Prefer text after a deadline marker if multiple dates occur in the message.
    low = text.casefold()
    marker = re.search(r"\b(?:дедлайн|срок сдачи|сдать до|до)\b", low)
    dates = low[marker.end():] if marker else low
    day = None
    number = re.search(r"(?<!\d)(\d{1,2})[./](\d{1,2})(?:[./](\d{4}|\d{2})(?!\d))?(?!\d)", dates)
    words = re.search(r"\b(\d{1,2})\s+("+"|".join(MONTHS)+r")(?:\s+(20\d{2}))?\b", dates)
    if number or words:
        m = number or words
        year = int(m[3]) if m[3] else now.year
        try:
            day = date(year+2000 if year<100 else year, int(m[2]) if number else MONTHS.index(m[2])+1,int(m[1]))
            if not m[3] and day<now.date():
                day = day.replace(year=day.year+1)
        except ValueError:
            day = None
    else:
        for word,delta in (("послезавтра",2),("завтра",1),("сегодня",0)):
            if word in dates:
                day = now.date()+timedelta(days=delta)
                break
        if not day:
            for idx,word in enumerate(DAY_NAMES):
                if re.search(r"\b"+word,dates):
                    day = now.date()+timedelta(days=(idx-now.weekday())%7)
                    break
    clock = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", dates)
    hour = f"{int(clock[1]):02}:{clock[2]}" if clock else "23:59"
    title = re.sub(r"^(?:задание|тема)\s*[:–-]\s*", "",lines[0], flags=re.I)[:160].strip()
    cat = "Лабораторные" if "лаб" in low else "Проекты" if "проект" in low else "Учёба"
    steps = [re.sub(r"^(?:[-•*]|\d+[.)])\s*", "",line)[:160] for line in lines[1:]
             if re.match(r"^(?:[-•*]|\d+[.)])\s+",line)][:30]
    return {"title":title or "Задание", "due":f"{day} {hour}" if day else "", "category":cat, "lead":60, "steps":steps}


def weekly_report(store, start, week=None):
    last = start+timedelta(days=6)
    tasks = store.db.execute("SELECT due,title FROM tasks WHERE done=0 AND due>=? AND due<? ORDER BY due,id",
                             (start.isoformat(),(last+timedelta(days=1)).isoformat())).fetchall()
    cache = {k:{"lessons":v} for k,v in week.items()} if week is not None else store.get("cache",{})
    text = [f"Нагрузка с {start:%d.%m} по {last:%d.%m}"]
    for offset in range(7):
        d = start+timedelta(days=offset)
        entry = cache.get(d.isoformat())
        due = [t for t in tasks if t["due"][:10]==d.isoformat()]
        lessons = f"пар — {len(entry['lessons'])}" if entry is not None else "пары уточняются"
        text.append(f"{WEEKDAYS[d.weekday()]} {d:%d.%m} · {lessons} · сдач — {len(due)}")
        text.extend(f"    {t['due'][11:]}  {t['title']}" for t in due)
    if store.get("last_check"):
        text.append("Расписание проверено " + datetime.fromisoformat(store.get("last_check")).strftime("%d.%m в %H:%M МСК"))
    return "\n".join(text)


def onsite(lesson):
    description = " ".join(str(lesson.get(k) or "") for k in ("format", "work_type", "building"))
    return not re.search(r"онлайн|дистанц|online|виртуальн|remote", description, re.I)


PESOCHNAYA = "Песочная набережная"


def campus_name(building):
    value = building or ""
    if re.search(r"песочн(?:ая|ой|ую)\s+наб|наб(?:ережная)?\.?\s+песочн", value, re.I):
        return PESOCHNAYA
    return value


def campus_overrides(overrides):
    result = {campus_name(k): v for k, v in overrides.items()}
    if PESOCHNAYA in overrides:
        result[PESOCHNAYA] = overrides[PESOCHNAYA]
    return result


def campus_travel(overrides, building, default):
    name = campus_name(building)
    if name in overrides:
        return overrides[name]
    return overrides.get(building, next((v for k,v in overrides.items() if campus_name(k)==name), default))


def campus_names(store, cache=None):
    buildings = set(store.get("campus_minutes", {}))
    for day in (cache if cache is not None else store.get("cache", {})).values():
        buildings.update(x["building"] for x in day["lessons"] if x.get("building") and onsite(x))
    return sorted({PESOCHNAYA, *(campus_name(x) for x in buildings)})


def departure(store, now):
    today = now.date().isoformat()
    entry = store.get("cache",{}).get(today)
    if not store.get("travel_on",False) or not entry or store.get("source_error"):
        return
    if today not in store.get("latest_dates",[]) or entry["checked"][:10] != today:
        return
    lessons = [x for x in entry["lessons"] if onsite(x)]
    if not lessons:
        return
    first = min(lessons, key=lambda x:x["time_start"])
    begins = datetime.fromisoformat(today+"T"+first["time_start"]).replace(tzinfo=MSK)
    minutes = store.get("travel_minutes",35)
    campuses = store.get("campus_minutes",{})
    minutes = campus_travel(campuses, first.get("building",""), minutes)
    signature = [today,first["time_start"],first["building"]]
    if begins-timedelta(minutes=minutes) <= now < begins and store.get("departure_sent") != signature:
        store.post(store.get("owner"),f"Пора выходить\n{first['subject']}\nНачало в {first['time_start']}. "
                   f"{first['building'] or 'Адрес не указан'} · дорога {minutes} мин.", delivery="background", rubric="departure")
        store.set("departure_sent",signature)

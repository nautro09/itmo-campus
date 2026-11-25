"""Telegram article layouts. All text from campus services stays literal."""
import re
from html import escape

# Telegram fetches only these public illustrations, shared by all readers.
COVER_ROOT = "https://raw.githubusercontent.com/nautro09/itmo-campus/main/artwork/"
COVERS = {"morning": "morning.jpg", "changes": "timetable.jpg"}
TITLES = {"morning": "Начало дня", "day": "Расписание", "changes": "Изменения в расписании",
          "week": "Неделя", "grades": "Баллы БаРС", "mail": "Входящие", "digest": "За тихие часы",
          "due": "Дедлайн", "departure": "Пора выходить", "tasks": "Задания"}
SLOT = re.compile(r"^(\d\d:\d\d–\d\d:\d\d)  (.+)$")
WEEKDAY = re.compile(r"^((?:Пн|Вт|Ср|Чт|Пт|Сб|Вс) \d\d\.\d\d) · (.+)$")


def literal(text):
    return escape(text.strip(), quote=False).replace("\n", "<br>")


def article(kind, text, *, cover=True):
    """Render a bounded outbox part. User input never becomes Telegram markup."""
    first, _, body = text.partition("\n")
    blocks = []
    if cover and kind in COVERS:
        blocks.append(f'<img src="{COVER_ROOT}{COVERS[kind]}"/>')
    title = TITLES[kind]
    if kind == "grades" and first == "Изменения в БаРС":
        title = first
    if kind != "morning" or not cover:
        blocks.append(f"<h1>{title}</h1>")
    if kind == "day":
        body = text
    elif kind == "mail":
        subject, _, content = body.partition("\n")
        blocks += [f"<h2>{literal(subject)}</h2>", f"<p><i>{literal(first)}</i></p>"]
        content = content.strip()
        if len(content) > 850:
            split = max(content.rfind(" ", 0, 480), content.rfind("\n", 0, 480))
            if split <= 0:
                split = 480
            blocks.append(f"<p>{literal(content[:split])}</p>")
            blocks.append(f"<details><summary>Читать дальше</summary><p>{literal(content[split:])}</p></details>")
        else:
            blocks.append(f"<p>{literal(content)}</p>")
        body = ""
    elif kind in ("week", "due", "tasks"):
        blocks.append(f"<h3>{literal(first)}</h3>")

    if kind in ("day", "morning"):
        for line in body.splitlines():
            if not line.strip():
                continue
            slot = SLOT.match(line)
            if slot:
                blocks.append(f"<h3>{slot[1]}</h3><p><b>{literal(slot[2])}</b></p>")
            elif re.match(r"^\d\d\.\d\d\.\d{4},", line):
                tag = "h1" if kind == "morning" and cover else "h2"
                blocks.append(f"<{tag}>{literal(line)}</{tag}>")
            elif line.startswith("Проверено в "):
                blocks.append(f"<footer>{literal(line)}</footer>")
            else:
                blocks.append(f"<p>{literal(line)}</p>")
    elif kind == "changes":
        for item in body.strip().split("\n\n"):
            label, _, detail = item.partition("\n")
            blocks.append(f"<h3>{literal(label)}</h3>")
            for line in detail.splitlines():
                prefix, sep, value = line.partition("  ")
                if sep and prefix in ("Было", "Стало"):
                    blocks.append(f"<p><b>{prefix}</b><br>{literal(value)}</p>")
                elif line.strip():
                    blocks.append(f"<p>{literal(line)}</p>")
    elif kind == "week":
        for line in body.splitlines():
            match = WEEKDAY.match(line)
            if match:
                blocks.append(f"<h3>{match[1]}</h3><p>{literal(match[2])}</p>")
            elif line.startswith("Расписание проверено"):
                blocks.append(f"<footer>{literal(line)}</footer>")
            elif line.strip():
                blocks.append(f"<p>{literal(line)}</p>")
    elif kind == "grades":
        for line in body.splitlines():
            name, sep, score = line.rpartition(" · ")
            if sep:
                blocks.append(f"<p><b>{literal(name)}</b><br>{literal(score)}</p>")
            elif line.strip():
                blocks.append(f"<footer>{literal(line)}</footer>")
    elif kind == "due":
        task, _, deadline = body.partition("\n")
        blocks.append(f"<h2>{literal(task)}</h2><p>{literal(deadline)}</p>")
    elif kind == "departure":
        subject, _, route = body.partition("\n")
        blocks.append(f"<h2>{literal(subject)}</h2><p>{literal(route)}</p>")
    elif kind == "digest":
        for section in body.strip().split("\n\n"):
            heading, _, entries = section.partition("\n")
            if re.fullmatch(r"(Задания|Изменения пар|Баллы БаРС|Почта|Расписание|Дорога|За неделю|Другие уведомления) · [0-9]+", heading):
                blocks.append(f"<h2>{literal(heading)}</h2>")
                if entries:
                    blocks.append(f"<p>{literal(entries)}</p>")
            elif section:
                blocks.append(f"<p>{literal(section)}</p>")
    elif body.strip():
        for item in body.strip().split("\n\n"):
            blocks.append(f"<p>{literal(item)}</p>")
    # Preserve pathological multiline input without exceeding the API's 500-block limit.
    if len(blocks) > 200:
        return {"html": f"<h1>{TITLES[kind]}</h1><p>{literal(text)}</p>"}
    return {"html": "".join(blocks)}

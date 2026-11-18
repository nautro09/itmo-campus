"""Track current-semester scores from the owner's my.itmo record book."""
import asyncio
import time
from datetime import datetime
from decimal import Decimal, InvalidOperation

from itmo import MSK, SourceError


def scores(rows):
    result = {}
    if not isinstance(rows, list):
        raise ValueError()
    for row in rows:
        key = str(row["est_id"]) + ":" + str(row.get("attempt") or "") + ":" + str(row.get("control_type_id") or "")
        if row["est_id"] is None or key in result or not row["name"]:
            raise ValueError()
        value = row["current_score"]
        if value not in (None, "", "—", "-"):
            number = Decimal(str(value).replace(",", "."))
            if not number.is_finite():
                raise ValueError()
            value = format(number.normalize(), "f")
        else:
            value = "—"
        result[key] = {"name": row["name"], "score": value}
    return result


class Grades:
    def __init__(self, store, portal):
        self.s, self.portal = store, portal
        self.lock = asyncio.Lock()
        self.last = None

    async def sync(self):
        async with self.lock:
            if not self.s.get("connected"):
                return
            if self.last is not None and time.monotonic() - self.last < 15:
                return
            self.last = time.monotonic()
            try:
                scope, rows = await self.portal.record_book()
                current = scores(rows)
                previous = self.s.get("bars_snapshot", {})
                same = previous.get("scope") == scope
                prior = previous.get("known", {}) if same else {}
                changes = []
                for key, row in current.items():
                    old = prior.get(key, {}).get("score", "—")
                    if same and old != row["score"]:
                        changes.append(f"{row['name']} · {old} → {row['score']}")
                with self.s.db:
                    self.s.set("bars_snapshot", {"scope": scope, "rows": current, "known": {**prior, **current}})
                    self.s.set("bars_status", "Проверено " + datetime.now(MSK).strftime("%d.%m в %H:%M МСК"))
                    if changes:
                        self.s.post(self.s.get("owner"), "📈 Изменения в БаРС\n" + "\n".join(changes))
            except (ValueError, TypeError, KeyError, InvalidOperation, SourceError) as exc:
                with self.s.db:
                    self.s.set("bars_status", str(exc) if isinstance(exc, SourceError) else "БаРС вернул незнакомый формат. Показана последняя копия.")

    async def run(self):
        while True:
            if self.s.get("owner") and (self.last is None or time.monotonic() - self.last >= 300):
                await self.sync()
            await asyncio.sleep(5)

    def report(self):
        rows = self.s.get("bars_snapshot", {}).get("rows", {}).values()
        return "\n".join(["📈 БаРС · баллы за семестр", self.s.get("bars_status", "Для проверки войди в my.itmo."),
                          *(f"{r['name']} · {r['score']}" for r in rows)])

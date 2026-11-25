"""Personal timetable from the signed-in my.itmo portal."""
import asyncio
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from playwright.async_api import Error as BrowserError, async_playwright

MSK = ZoneInfo("Europe/Moscow")
PORTAL = "https://my.itmo.ru/schedule"
READY = """() => location.origin === 'https://my.itmo.ru' &&
    !location.pathname.startsWith('/login') && !!window.$nuxt?.$store?.$axios"""
GET_WEEK = """async ([start, end]) => {
    if (location.origin !== 'https://my.itmo.ru') return {status: 401};
    try {
        const response = await window.$nuxt.$store.$axios.get('/api/schedule/schedule/personal', {
            params: {date_start: start, date_end: end}, timeout: 20000
        });
        return {status: response.status, body: response.data};
    } catch (e) {
        return {status: e.response?.status || 0};
    }
}"""


class SourceError(Exception):
    pass


class LoginNeeded(SourceError):
    pass


def login_browser_error(error, service, browser_started):
    # Browser exceptions may contain redirect URLs with tokens and account identifiers.
    diagnostic = str(error)
    network = re.search(r"\bnet::(ERR_[A-Z0-9_]{1,64})\b", diagnostic)
    if network:
        return SourceError(f"Браузер сервера не смог открыть {service}. Сетевая ошибка: {network[1]}.")
    if "SingletonLock" in diagnostic or "ProcessSingleton" in diagnostic:
        return SourceError(f"Браузер сервера не смог открыть профиль {service}: профиль заблокирован.")
    if "Permission denied" in diagnostic or "EACCES" in diagnostic:
        return SourceError(f"Браузеру сервера не хватает прав для открытия {service}.")
    if "No space left" in diagnostic:
        return SourceError("На сервере закончилось место для профиля браузера.")
    if "Timeout" in diagnostic:
        return SourceError(f"Сервер не дождался ответа при открытии {service}.")
    stage = "открыть страницу" if browser_started else "запустить Chromium"
    return SourceError(f"Не удалось {stage} для {service} на сервере.")


def parse_week(body, start):
    if not isinstance(body, dict) or body.get("code") != 0 or not isinstance(body.get("data"), list):
        raise SourceError("my.itmo не подтвердил загрузку расписания.")
    days = {}
    try:
        for entry in body["data"]:
            day = date.fromisoformat(entry["date"][:10])
            if not start <= day < start + timedelta(days=7):
                continue
            key = day.isoformat()
            if key in days or not isinstance(entry["lessons"], list):
                raise ValueError()
            lessons = []
            for raw in entry["lessons"]:
                subject = raw["subject"].strip()
                if not subject:
                    raise ValueError()
                fields = {k: str(raw.get(k) or "").strip() for k in (
                    "pair_id", "group", "room", "building", "teacher_name", "work_type", "format", "note"
                )}
                for k in ("time_start", "time_end"):
                    fields[k] = datetime.strptime(raw[k][:5], "%H:%M").strftime("%H:%M")
                lessons.append(dict(fields, subject=subject, day=key))
            days[key] = sorted(lessons, key=lambda x: (x["time_start"], x["subject"], x["group"]))
    except (AttributeError, KeyError, TypeError, ValueError):
        raise SourceError("Формат расписания my.itmo изменился. Не удалось прочитать все пары.") from None
    return days


def details(x):
    return " · ".join(v for v in (
        x["work_type"], x["group"], x["format"], x["building"],
        "ауд. " + x["room"] if x["room"] else "", x["teacher_name"], x["note"]
    ) if v)


def lesson_text(x):
    return f"{x['time_start']}–{x['time_end']}  {x['subject']}" + (
        "\n" + details(x) if details(x) else "")


def day_text(week, day):
    key = day.isoformat()
    weekdays = ("понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье")
    heading = f"{day:%d.%m.%Y}, {weekdays[day.weekday()]}"
    if key not in week:
        return heading + "\nmy.itmo не вернул данные за этот день."
    return heading + "\n\n" + ("\n\n".join(lesson_text(x) for x in week[key]) or "Пар нет.")


def changes(before, after, *, include_lessons=False):
    # Compare only dates covered in both responses. A sliding window or missing day
    # is not a cancellation. Ignore row order and changes to internal IDs alone.
    dates = sorted(before.keys() & after.keys())
    old = [x for d in dates for x in before[d]]
    new = [x for d in dates for x in after[d]]
    def visible(x):
        return tuple(sorted((k, v) for k, v in x.items() if k != "pair_id"))
    def unmatched(items, other):
        counts = Counter(map(visible, other))
        remaining = []
        for item in items:
            key = visible(item)
            if counts[key]:
                counts[key] -= 1
            else:
                remaining.append(item)
        return remaining
    left, right = unmatched(old, new), unmatched(new, old)
    def when(x):
        return f"{date.fromisoformat(x['day']):%d.%m} · {lesson_text(x)}"
    edits = []
    for keys in (("day", "pair_id"), ("pair_id",), ("day", "subject", "group")):
        def index(items):
            groups = defaultdict(list)
            for item in items:
                key = tuple(item[k] for k in keys)
                if all(key):
                    groups[key].append(item)
            return groups
        a, b = index(left), index(right)
        for key in sorted(a.keys() & b.keys()):
            if len(a[key]) == len(b[key]) == 1:
                x, y = a[key][0], b[key][0]
                edits.append(((x, y), "Изменили пару\nБыло  " + when(x) + "\nСтало  " + when(y)))
                left.remove(x)
                right.remove(y)
    edits.extend(((x,), "Убрали из расписания\n" + when(x)) for x in left)
    edits.extend(((x,), "Добавили пару\n" + when(x)) for x in right)
    return edits if include_lessons else [text for _, text in edits]


class Portal:
    def __init__(self, profile):
        self.profile = profile
        self.identity = {}
        self.engine = self.context = self.page = None
        self.lock = asyncio.Lock()

    async def close(self):
        try:
            if self.context:
                await self.context.close()
        finally:
            self.context = self.page = None
            if self.engine:
                await self.engine.stop()
                self.engine = None

    async def open(self, headed, env=None):
        self.engine = await async_playwright().start()
        self.context = await self.engine.chromium.launch_persistent_context(
            str(self.profile), env=env, headless=not headed, locale="ru-RU", timezone_id="Europe/Moscow"
        )
        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
        try:
            await self.page.goto(PORTAL, wait_until="commit" if headed else "domcontentloaded", timeout=30000)
        except BrowserError as error:
            # The SSO redirect can replace the first navigation before it commits.
            if not headed or "net::ERR_ABORTED" not in str(error) or self.page.is_closed():
                raise
            await self.page.wait_for_url(lambda url: urlsplit(url).scheme == "https", timeout=10000,
                                         wait_until="commit")

    async def request(self, day):
        result = await self.page.evaluate(GET_WEEK, [day.isoformat(), (day + timedelta(days=6)).isoformat()])
        if result["status"] in (401, 403):
            raise LoginNeeded("Нужно снова войти в my.itmo. Открой «Настройки» → «Войти в my.itmo».")
        if result["status"] != 200:
            raise SourceError("Сервис расписания my.itmo сейчас недоступен.")
        week = parse_week(result.get("body"), day)
        self.identity = await self.page.evaluate("""() => {
            if (location.origin !== 'https://my.itmo.ru') return {};
            const u=window.$nuxt?.$auth?.user || {};
            return {isu:String(u.isu || ''),name:[u.family_name,u.given_name,u.middle_name].filter(Boolean).join(' ')};
        }""")
        return week

    async def authorized_week(self, day, interactive):
        # my.itmo may briefly mount its app before navigating to ITMO ID and
        # back. Wait for an actual successful response across those navigations.
        loop = asyncio.get_running_loop()
        deadline = loop.time() + (300 if interactive else 30)
        rejected = False
        while loop.time() < deadline:
            if self.page.is_closed():
                raise SourceError("Окно my.itmo закрыто. Повтори вход в настройках.")
            try:
                if await self.page.evaluate(READY):
                    return await asyncio.wait_for(self.request(day), timeout=28)
            except LoginNeeded:
                if not interactive and not rejected:
                    await self.page.goto(PORTAL, wait_until="domcontentloaded", timeout=30000)
                rejected = True
            except SourceError:
                if not interactive:
                    raise
                # The login callback can mount the app before its session is ready.
                await asyncio.sleep(3)
            except BrowserError as e:
                if not any(fragment in str(e) for fragment in ("navigation", "context was destroyed")):
                    raise
            except asyncio.TimeoutError:
                raise SourceError("my.itmo не ответил вовремя. Попробую при следующей проверке.") from None
            await asyncio.sleep(1)
        url = urlsplit(self.page.url)
        if interactive or rejected or url.hostname == "id.itmo.ru" or url.path.startswith("/login"):
            raise LoginNeeded("Нужно войти в ИТМО ID. Открой «Настройки» → «Войти в my.itmo».")
        raise SourceError("Не удалось загрузить экран личного расписания my.itmo.")

    async def login(self, env=None):
        async with self.lock:
            await self.close()
            try:
                await self.open(headed=True,env=env)
                await self.authorized_week(datetime.now(MSK).date(), interactive=True)
            except BrowserError as error:
                raise login_browser_error(error, "my.itmo", self.page is not None) from None
            finally:
                await self.close()

    async def read(self, start):
        async with self.lock:
            try:
                if not self.page or self.page.is_closed():
                    await self.close()
                    await self.open(headed=False)
                return await self.authorized_week(start, interactive=False)
            except (BrowserError, SourceError) as e:
                await self.close()
                if isinstance(e, SourceError):
                    raise
                raise SourceError("Не удалось открыть личное расписание. Проверь сеть и подключение my.itmo.") from None

    async def record_book(self):
        async with self.lock:
            try:
                if not self.page or self.page.is_closed():
                    await self.close()
                    await self.open(headed=False)
                await self.page.wait_for_function(READY, timeout=12000)
                data = await self.page.evaluate("""async () => {
                    if (location.origin !== 'https://my.itmo.ru') return null;
                    const api = window.$nuxt.$store.$axios;
                    const read = async path => {
                        const {data} = await api.get(path, {timeout:12000});
                        if (!Array.isArray(data.result) || Number(data.error_code || 0)) throw Error();
                        return data.result;
                    };
                    const plans = await read('/api/record_book/specializations');
                    let selected;
                    for (const plan of plans) {
                        for (const term of plan.semesters) {
                            if (term.actual) { selected=[plan.main_plan,term.semester]; break; }
                        }
                    }
                    if (!selected && plans[0]?.semesters?.length)
                        selected=[plans[0].main_plan,plans[0].semesters[0].semester];
                    if (!selected) return null;
                    const scope=selected.map(encodeURIComponent).join('/');
                    return [scope, await read('/api/record_book/'+scope)];
                }""")
                if not data:
                    raise SourceError("БаРС пока не показал учебный план.")
                return data
            except BrowserError:
                raise SourceError("Не удалось проверить БаРС. Проверь вход в my.itmo. Последние баллы сохранены.") from None

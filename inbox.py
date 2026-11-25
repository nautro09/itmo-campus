"""Read the visible, signed-in ISU inbox without opening or marking a message."""
import asyncio
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import urlsplit

from playwright.async_api import Error as BrowserError, async_playwright

from itmo import SourceError, login_browser_error

ISU = "https://isu.ifmo.ru"
ROWS = """rows => rows.map(row => {
    const text = selector => row.querySelector(selector)?.textContent.trim() ?? null;
    return {key:row.dataset.id,sender:text('.mes_name .name_text'),subject:text('.text_h'),
            body:text('.text_text') || '',date:text('.mes_date')};
})"""


def isu_url(address):
    parts = urlsplit(address)
    return parts.scheme == "https" and parts.netloc in ("isu.ifmo.ru", "isu.itmo.ru")


# Some portal layouts put the inbox in a frame or keep the portal title.
INBOX_READY = """() => !!document.querySelector('#tet') && (
    /входящие/i.test(document.title) ||
    Array.from(document.querySelectorAll('h1,h2,[aria-current=page],.t-Breadcrumb-label'))
         .some(el => /входящие/i.test(el.textContent)) ||
    /[?&]p=2422:4(?:[:&]|$)/i.test(location.search))"""


class IsuInbox:
    def __init__(self, profile):
        self.profile = Path(profile)
        self.checkpoint = self.profile / "isu-session.json"
        self.saved_session = None
        self.frame = None
        self.lock = asyncio.Lock()
        self.engine = self.context = self.page = None

    async def close(self):
        try:
            if self.context:
                await self.context.close()
        finally:
            self.context = self.page = self.frame = None
            if self.engine:
                await self.engine.stop()
                self.engine = None

    async def open(self, interactive, env=None):
        self.engine = await async_playwright().start()
        self.context = await self.engine.chromium.launch_persistent_context(
            str(self.profile),env=env, headless=not interactive,locale="ru-RU",timezone_id="Europe/Moscow")
        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
        self.context.set_default_navigation_timeout(12000)
        target = ISU
        if self.checkpoint.is_file():
            try:
                saved = json.loads(self.checkpoint.read_text(encoding="utf-8"))
                if isu_url(saved["url"]):
                    await self.context.add_cookies(saved["cookies"])
                    if not interactive:
                        target = saved["url"]
            except (KeyError, ValueError, TypeError, BrowserError):
                pass
        try:
            await self.page.goto(target, wait_until="commit")
        except BrowserError:
            if target == ISU:
                raise
            await self.page.goto(ISU, wait_until="commit")

    async def save_session(self):
        cookies = await self.context.cookies()
        session = {"url": self.frame.url, "cookies": cookies}
        if self.saved_session == session and self.checkpoint.exists():
            return
        with NamedTemporaryFile(dir=self.profile, mode="w", encoding="utf-8", delete=False) as tmp:
            try:
                json.dump(session, tmp)
                tmp.flush()
                os.fsync(tmp.fileno())
                os.replace(tmp.name, self.checkpoint)
                self.saved_session = session
            finally:
                Path(tmp.name).unlink(missing_ok=True)

    async def reach_inbox(self, interactive):
        loop = asyncio.get_running_loop()
        deadline = loop.time() + (300 if interactive else 12)
        followed = set()
        fallback = not interactive and self.page.url != ISU and self.checkpoint.is_file()
        while loop.time() < deadline:
            pages = list(reversed(self.context.pages))
            if not pages:
                raise SourceError("Окно ИСУ закрыто. Нажми «Войти в ИСУ» повторно.")
            candidate = None
            for page in pages:
                for frame in page.frames:
                    if not isu_url(frame.url):
                        continue
                    try:
                        if await frame.evaluate(INBOX_READY):
                            self.page, self.frame = page, frame
                            return
                        link = await frame.evaluate("""() => Array.from(document.links).find(a =>
                            /[?&]p=2422:4:/i.test(a.href) ||
                            /P58_DEP_ID:715/i.test(a.href) ||
                            a.textContent.trim().toLowerCase() === 'входящие')?.href""")
                        if link and isu_url(link) and link not in followed:
                            candidate = (frame, link)
                    except BrowserError:
                        continue  # Login redirects can replace the frame during inspection.
            if candidate:
                frame, link = candidate
                followed.add(link)
                try:
                    await frame.goto(link, wait_until="commit")
                except BrowserError:
                    pass
            elif fallback and loop.time() > deadline - 9:
                fallback = False
                await self.page.goto(ISU, wait_until="commit")
            else:
                await asyncio.sleep(0.4)
        raise SourceError("Сеанс ИСУ не подтверждён. Нажми «Войти в ИСУ» и открой «Сообщения → Входящие».")

    async def login(self, env=None):
        async with self.lock:
            await self.close()
            try:
                await self.open(True,env=env)
                await self.reach_inbox(True)
                await self.save_session()
            except BrowserError as error:
                raise login_browser_error(error, "ИСУ", self.page is not None) from None
            finally:
                await self.close()

    async def read(self, seen):
        async with self.lock:
            try:
                if not self.page or self.page.is_closed():
                    await self.close()
                    await self.open(False)
                else:
                    await self.page.reload(wait_until="commit")
                await self.reach_inbox(False)
                await self.save_session()
                rows = self.frame.locator("#tet .message[data-id]")
                # Most polls see the same messages. Read only IDs before parsing bodies.
                if seen:
                    keys = await rows.evaluate_all("rows => rows.map(row => row.dataset.id)")
                    if keys and all(key in seen for key in keys):
                        return []
                while True:
                    items = await rows.evaluate_all(ROWS)
                    if any(not x["key"] or any(x[k] is None for k in ("sender","body","subject","date")) for x in items):
                        raise SourceError("Разметка входящих ИСУ изменилась.")
                    if seen is None or not items or any(x["key"] in seen for x in items):
                        break
                    more = self.frame.locator("#next")
                    if not await more.is_visible() or not (await more.inner_text()).strip():
                        break
                    count = len(items)
                    await more.click(timeout=5000)
                    await self.frame.wait_for_function(
                        "n => document.querySelectorAll('#tet .message[data-id]').length > n || !document.getElementById('next')?.offsetHeight",
                        arg=count,timeout=12000)
                    if await rows.count() == count:
                        break
                return items
            except (BrowserError, SourceError) as e:
                await self.close()
                if isinstance(e, SourceError):
                    raise
                raise SourceError("Не удалось прочитать входящие ИСУ. Проверь связь и вход.") from None

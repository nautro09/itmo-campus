"""Read the visible, signed-in ISU inbox without opening or marking a message."""
import asyncio
from urllib.parse import urlsplit

from playwright.async_api import Error as BrowserError, async_playwright

from itmo import SourceError

ISU = "https://isu.ifmo.ru"
ROWS = """rows => rows.map(row => {
    const text = selector => row.querySelector(selector)?.textContent.trim() ?? null;
    return {key:row.dataset.id,sender:text('.mes_name .name_text'),subject:text('.text_h'),
            body:text('.text_text'),date:text('.mes_date')};
})"""


class IsuInbox:
    def __init__(self, profile):
        self.profile = profile
        self.lock = asyncio.Lock()
        self.engine = self.context = self.page = None

    async def close(self):
        try:
            if self.context:
                await self.context.close()
        finally:
            self.context = self.page = None
            if self.engine:
                await self.engine.stop()
                self.engine = None

    async def open(self, interactive):
        self.engine = await async_playwright().start()
        self.context = await self.engine.chromium.launch_persistent_context(
            str(self.profile),headless=not interactive,locale="ru-RU",timezone_id="Europe/Moscow")
        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
        await self.page.goto(ISU,wait_until="domcontentloaded")

    async def reach_inbox(self, interactive):
        deadline = asyncio.get_running_loop().time() + (300 if interactive else 25)
        followed = False
        while asyncio.get_running_loop().time() < deadline:
            url = urlsplit(self.page.url)
            if url.scheme == "https" and url.hostname == "isu.ifmo.ru":
                if await self.page.locator("#tet").count() and "Входящие" in await self.page.title():
                    return
                link = self.page.locator('a[href*="P58_DEP_ID:715"]').first
                if not followed and await link.count():
                    target = await link.evaluate("a => a.href")
                    url = urlsplit(target)
                    if url.scheme == "https" and url.hostname == "isu.ifmo.ru":
                        await self.page.goto(target,wait_until="domcontentloaded")
                        followed = True
            await asyncio.sleep(1)
        raise SourceError("Открой «Войти в ИСУ» и перейди в «Сообщения → Входящие» в окне браузера.")

    async def login(self):
        async with self.lock:
            await self.close()
            try:
                await self.open(True)
                await self.reach_inbox(True)
            except BrowserError:
                raise SourceError("Вход в ИСУ не завершён. Проверь графический сеанс и окно входа.") from None
            finally:
                await self.close()

    async def read(self, seen):
        async with self.lock:
            try:
                if not self.page or self.page.is_closed():
                    await self.close()
                    await self.open(False)
                else:
                    await self.page.reload(wait_until="domcontentloaded")
                await self.reach_inbox(False)
                rows = self.page.locator("#tet .message[data-id]")
                while True:
                    items = await rows.evaluate_all(ROWS)
                    if any(not x["key"] or any(x[k] is None for k in ("sender","body","subject","date")) for x in items):
                        raise SourceError("Разметка входящих ИСУ изменилась.")
                    if seen is None or not items or any(x["key"] in seen for x in items):
                        break
                    more = self.page.locator("#next")
                    if not await more.is_visible() or not (await more.inner_text()).strip():
                        break
                    count = len(items)
                    await more.click(timeout=5000)
                    await self.page.wait_for_function(
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

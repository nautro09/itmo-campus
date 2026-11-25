import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bot import Bot, recover_container_profiles
from inbox import IsuInbox, ISU
from menu import register_menu
from miniapp import action
from store import Store


class ConnectionTests(unittest.IsolatedAsyncioTestCase):
    def test_recover_only_abandoned_foreign_browser_lock(self):
        with tempfile.TemporaryDirectory() as temp, patch("bot.socket.gethostname", return_value="campus"):
            data = Path(temp)
            profile = data / "my-itmo-browser"
            profile.mkdir()
            cookies = profile / "Cookies"
            cookies.write_bytes(b"saved session")
            lock = profile / "SingletonLock"
            lock.symlink_to("old-container-123")
            endpoint = data / "endpoint"
            endpoint.touch()
            (profile / "SingletonSocket").symlink_to(endpoint)
            recover_container_profiles(data)
            self.assertTrue(lock.is_symlink())
            endpoint.unlink()
            recover_container_profiles(data)
            self.assertFalse(lock.is_symlink())
            lock.symlink_to("campus-456")
            recover_container_profiles(data)
            self.assertTrue(lock.is_symlink())
            self.assertEqual(cookies.read_bytes(), b"saved session")

    async def test_menu_applies_to_existing_chat(self):
        api = AsyncMock()
        await register_menu(api, "https://campus.example", 123)
        first, second = api.call.await_args_list
        self.assertEqual(first.args, ("setChatMenuButton",))
        self.assertEqual(second.kwargs["chat_id"], 123)
        self.assertEqual(second.kwargs["menu_button"], first.kwargs["menu_button"])
        self.assertEqual(first.kwargs["menu_button"]["type"], "web_app")

    async def test_check_returns_while_services_are_busy(self):
        store = Store(":memory:")
        self.addCleanup(store.db.close)
        bot = Bot(store, None)
        store.set("owner", 123)
        release = asyncio.Event()
        bot.mail.sync = AsyncMock(side_effect=release.wait)
        bot.api = AsyncMock()
        self.assertTrue((await action(bot, "check_services", {}))["check_pending"])
        job = bot.check_job
        await bot.route("🔎 Проверить связь")
        self.assertIs(job, bot.check_job)
        release.set()
        await job
        bot.mail.sync.assert_awaited_once()
        self.assertIn("Telegram", store.db.execute("SELECT text FROM outbox").fetchone()[0])


@unittest.skipUnless(os.getenv("TEST_ISU_BROWSER"), "requires installed Playwright Chromium")
class InboxBrowserTest(unittest.IsolatedAsyncioTestCase):
    async def test_popup_frame_and_session_cookie_survive_restart(self):
        from playwright.async_api import async_playwright
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp) / "browser"
            url = ISU + "/pls/apex/f?p=2422:4:fixture"
            async with async_playwright() as engine:
                launch = engine.chromium.launch_persistent_context

                async def fake_site(route):
                    if route.request.url == url:
                        signed = "signed=fixture" in (await route.request.all_headers()).get("cookie", "")
                        body = '<div id="tet"></div>' if signed else '<h1>Login</h1>'
                    else:
                        body = "<h1>Portal</h1>"
                    await route.fulfill(body=body, content_type="text/html")

                async def launch_fixture(path, **settings):
                    interactive = not settings["headless"]
                    settings["headless"] = True
                    ctx = await launch(path, **settings)
                    await ctx.route("**/*", fake_site)
                    if interactive:
                        await ctx.add_cookies([{"name":"signed", "value":"fixture", "url":ISU}])
                        parent = ctx.pages[0]
                        await parent.goto(ISU)
                        async with parent.expect_popup() as opened:
                            await parent.evaluate("window.open('/messages') ? true : false")
                        popup = await opened.value
                        await popup.wait_for_load_state()
                        await popup.set_content(f'<iframe src="{url}"></iframe>')
                    return ctx

                with patch("playwright.async_api.BrowserType.launch_persistent_context", side_effect=launch_fixture):
                    first = IsuInbox(profile)
                    await asyncio.wait_for(first.login(), 12)
                    self.assertEqual(first.checkpoint.stat().st_mode & 0o777, 0o600)
                    second = IsuInbox(profile)
                    try:
                        self.assertEqual(await asyncio.wait_for(second.read(None), 12), [])
                    finally:
                        await second.close()

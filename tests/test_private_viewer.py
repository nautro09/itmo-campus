import asyncio
import os
import time
from unittest import IsolatedAsyncioTestCase, skipUnless
from unittest.mock import Mock

from aiohttp.test_utils import TestServer
from playwright.async_api import async_playwright

from miniapp import application
from test_campus import signed


@skipUnless(os.getenv("TEST_ISU_BROWSER")=="1", "requires production image")
class Viewer(IsolatedAsyncioTestCase):
    async def test_only_owner_reaches_real_virtual_screen(self):
        opened=asyncio.Event()
        stopped=asyncio.Event()
        async def fixture(env):
            try:
                async with async_playwright() as p:
                    browser=await p.chromium.launch(headless=False,env=env)
                    page=await browser.new_page()
                    await page.set_content("<h1>Private fixture</h1>")
                    opened.set()
                    await asyncio.Event().wait()
            finally:
                stopped.set()
        bot=Mock()
        bot.sign_in=fixture
        app=application(bot,"fixture")
        async with TestServer(app) as server, async_playwright() as p:
            host=str(server.make_url("/")).rstrip("/")
            bot.s.get.side_effect=lambda key: 123 if key=="owner" else host
            browser=await p.chromium.launch()
            context=await browser.new_context()
            page=await context.new_page()
            result=await context.request.post(host+"/login/open/itmo")
            self.assertEqual(result.status,403)
            result=await context.request.get(host+"/login/socket")
            self.assertEqual(result.status,403)
            result=await context.request.post(host+"/login/open/itmo",headers={"X-Telegram-Init-Data":signed(123,"fixture",int(time.time()))})
            self.assertEqual(result.status,200)
            await page.goto(host+(await result.json())["viewer"])
            try:
                await page.frame_locator("iframe").locator("html.noVNC_connected").wait_for(state="attached",timeout=20000)
            except Exception:
                self.fail("viewer failed: "+(await page.locator("body").inner_text())[:800])
            await asyncio.wait_for(opened.wait(),10)
            headers={"X-Telegram-Init-Data":signed(123,"fixture",int(time.time()))}
            # The normal issue rate is three seconds per owner.
            await asyncio.sleep(3)
            conflict=await context.request.post(host+"/login/open/isu",headers=headers)
            self.assertEqual(conflict.status,409)
            replacement={"X-Replace-Login":(await conflict.json())["window"]}
            forbidden=await context.request.post(host+"/login/open/isu",headers=replacement)
            self.assertEqual(forbidden.status,403)
            self.assertFalse(stopped.is_set())
            result=await context.request.post(host+"/login/open/isu",headers={**headers,**replacement})
            self.assertEqual(result.status,200)
            await asyncio.wait_for(stopped.wait(),10)
            await page.close()
            await browser.close()

import asyncio
import os
from unittest import IsolatedAsyncioTestCase, skipUnless
from unittest.mock import Mock

from aiohttp import web
from aiohttp.test_utils import TestServer
from playwright.async_api import async_playwright

from private_login import PrivateLogin, viewer_policy


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
        login=PrivateLogin(bot,lambda r:r.headers.get("X-Test-Owner")=="owner")
        self.assertTrue(login.available)
        policy=viewer_policy()
        @web.middleware
        async def headers(req,handler):
            res=await handler(req)
            if req.path.startswith("/viewer/"):
                res.headers["Content-Security-Policy"]=policy
            return res
        app=web.Application(middlewares=[headers])
        login.register(app)
        async with TestServer(app) as server, async_playwright() as p:
            host=str(server.make_url("/")).rstrip("/")
            bot.s.get.return_value=host
            browser=await p.chromium.launch()
            context=await browser.new_context()
            page=await context.new_page()
            result=await context.request.post(host+"/login/open/itmo")
            self.assertEqual(result.status,403)
            result=await context.request.get(host+"/login/socket")
            self.assertEqual(result.status,403)
            result=await context.request.post(host+"/login/open/itmo",headers={"X-Test-Owner":"owner"})
            self.assertEqual(result.status,200)
            await page.goto(host+(await result.json())["viewer"])
            try:
                await page.wait_for_selector("html.noVNC_connected",state="attached",timeout=20000)
            except Exception:
                self.fail("viewer failed: "+(await page.locator("body").inner_text())[:800])
            await asyncio.wait_for(opened.wait(),10)
            await page.close()
            await asyncio.wait_for(stopped.wait(),10)
            await browser.close()

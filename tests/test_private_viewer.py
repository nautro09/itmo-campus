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
    async def test_mobile_task_editor_submits_selected_reminder(self):
        async with TestServer(application(Mock(),"fixture")) as server, async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page(viewport={"width":390,"height":844}, is_mobile=True)
            await page.goto(str(server.make_url("/")) + "?demo=1#tasks")
            await page.locator('[data-action="new-task"]').click()
            form = page.locator('form[data-form="task"]')
            await form.locator('[name="title"]').fill("Подготовиться к КР")
            await form.locator('[name="day"]').fill("2026-11-26")
            await form.locator('[name="time"]').fill("08:10")
            await form.locator('[name="lead"]').select_option("custom")
            self.assertTrue(await form.locator('[name="minutes"]').is_visible())
            await form.locator('[name="lead"]').select_option("exact")
            self.assertTrue(await form.locator('[name="minutes"]').is_disabled())
            await form.locator('[name="exact"]').fill("2026-11-25T18:00")
            await form.get_by_role("button",name="Сохранить",exact=True).click()
            await form.wait_for(state="hidden")
            task = await page.evaluate("""() => JSON.parse(localStorage.getItem('para.demo.v2')).tasks.find(t=>t.title==='Подготовиться к КР')""")
            self.assertEqual((task["due"],task["remind_at"]), ("2026-11-26 08:10","2026-11-25 18:00"))
            await browser.close()

    async def test_only_owner_reaches_real_virtual_screen(self):
        opened=asyncio.Event()
        stopped=asyncio.Event()
        async def fixture(env):
            try:
                async with async_playwright() as p:
                    browser=await p.chromium.launch(headless=False,env=env)
                    page=await browser.new_page()
                    await page.route("https://id.itmo.ru/**", lambda route: route.fulfill(content_type="text/html", body="<input id='field'>"))
                    await page.goto("https://id.itmo.ru/test")
                    await page.locator("#field").focus()
                    bot.portal.page = page
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
            forbidden = await context.request.post(host+"/login/type", headers={"Origin":"https://example.org"}, data="fixture")
            self.assertEqual(forbidden.status,403)
            await page.locator("#entry").fill("Пример 123")
            await page.get_by_role("button", name="Ввести", exact=True).click()
            await page.get_by_text("Введено в выбранное поле.").wait_for(timeout=5000)
            self.assertEqual(await bot.portal.page.locator("#field").input_value(),"Пример 123")
            self.assertEqual(await page.locator("#entry").input_value(),"")
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

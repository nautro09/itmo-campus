import hashlib
import hmac
import json
import sys
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from aiohttp.test_utils import TestClient, TestServer
from itmo import MSK
from miniapp import application, save_settings
from store import Store
from wake import proposal, digest, pair_text, plan, revoke, rules


class WakeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.s=Store(":memory:")
        self.addCleanup(self.s.db.close)
        self.now=datetime(2026,11,18,21,tzinfo=MSK)
        self.day="2026-11-19"
        self.s.set("wake_on",True)
        self.s.set("latest_dates",[self.day])

    def put(self,lessons):
        self.s.set("cache",{self.day:{"checked":self.now.isoformat(),"lessons":lessons}})

    def test_rules_and_uncertain_data(self):
        for start, target in [("08:10","06:20"),("09:50","08:30")]:
            self.put([dict(time_start=start,format="очно",building="A")])
            row=plan(self.s,self.now)[1]
            self.assertEqual(datetime.fromtimestamp(row["at"],MSK).strftime("%H:%M"),target)
        self.s.set("campus_minutes",{"A":60})
        self.put([dict(time_start="12:10",building="A")])
        self.assertEqual(datetime.fromtimestamp(plan(self.s,self.now)[1]["at"],MSK).strftime("%H:%M"),"10:30")
        self.put([dict(time_start="08:10",format="онлайн")])
        self.assertEqual(datetime.fromtimestamp(plan(self.s,self.now)[1]["at"],MSK).strftime("%H:%M"),"07:50")
        self.put([])
        self.assertEqual(plan(self.s,self.now)[1]["action"],"cancel")
        self.assertEqual(plan(self.s,self.now+timedelta(hours=3))[1]["action"],"keep")
        self.s.set("source_error","offline")
        self.assertEqual(plan(self.s,self.now)[1]["action"],"keep")
        with self.assertRaises(ValueError):rules("08:10=08:30")

    def test_native_day_off_is_opt_in(self):
        self.put([])
        self.assertEqual(proposal(self.s,self.now)["action"],"free")
        self.s.set("wake_free_off",True)
        self.assertEqual(proposal(self.s,self.now)["action"],"cancel")
        self.s.set("source_error","offline")
        self.assertEqual(proposal(self.s,self.now)["action"],"keep")
        self.s.set("wake_on",False)
        self.assertEqual(proposal(self.s,self.now)["action"],"off")

    async def test_device_scope_and_auth(self):
        self.s.set("wake_origin","https://campus.example")
        code=pair_text(self.s).splitlines()[-1]
        async with TestClient(TestServer(application(SimpleNamespace(s=self.s),"bot-secret"))) as c:
            async def post(path, key, **headers):
                return await c.post(path,headers={"Authorization":"Bearer "+key,**headers})
            paired=await post("/device/pair",code)
            token=(await paired.json())["token"]
            self.assertEqual((await post("/device/pair",code)).status,401)
            self.assertEqual((await post("/api/state",token)).status,403)
            self.assertEqual((await post("/device/plan",token)).status,401)
            def headers(op,rev=""):
                nonce="ab"*16
                stamp=str(int(time.time()))
                sig=hmac.digest(digest(token).encode(),f"{op}\n{stamp}\n{nonce}\n{rev}".encode(),"sha256").hex()
                return sig,{"X-Wake-Time":stamp,"X-Wake-Nonce":nonce,"X-Wake-Revision":rev}
            sig,h=headers("plan")
            response=await post("/device/plan",sig,**h)
            body=await response.read()
            self.assertEqual(response.headers["X-Wake-MAC"],hmac.digest(digest(token).encode(),h["X-Wake-Nonce"].encode()+b"\n"+body,"sha256").hex())
            data=json.loads(body)
            self.assertEqual(set(data),{"days","revision"})
            sig,h=headers("ack",data["revision"])
            self.assertEqual((await post("/device/ack",sig,**h)).status,200)
            nsig,nh=headers("nativeplan")
            native=await (await post("/device/nativeplan",nsig,**nh)).json()
            self.assertTrue(native["settings"]["wake_on"])
            self.assertIn("09:50=08:30",native["settings"]["wake_rules"])
            with self.s.db:
                save_settings(self.s,{"wake_rules":"09:50=07:40"})
            sig_update,head_update=headers("nativeplan")
            updated=await (await post("/device/nativeplan",sig_update,**head_update)).json()
            self.assertEqual(updated["settings"]["wake_rules"],"09:50=07:40")
            rev=updated["revision"]
            nsig,nh=headers("received",rev)
            self.assertEqual((await post("/device/received",nsig,**nh)).status,200)
            self.assertIn("получил",self.s.get("wake_ack")["text"])
            nsig,nh=headers("confirmed",rev)
            self.assertEqual((await post("/device/confirmed",nsig,**nh)).status,409)
            revoke(self.s)
            self.assertEqual((await post("/device/ack",sig,**h)).status,401)

import asyncio
import hashlib
import imaplib
import json
import os
import re
import ssl
import time
from datetime import datetime
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr, parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dotenv import load_dotenv, set_key
from itmo import MSK, SourceError

ENV = Path(__file__).resolve().parent / ".env"
SCOPE = "offline_access https://outlook.office.com/IMAP.AccessAsUser.All"


class ReadableHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("style","script"):
            self.hidden += 1
        if tag in ("p","div","br","li","tr"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("style","script"):
            self.hidden = max(0,self.hidden-1)

    def handle_data(self, text):
        if not self.hidden:
            self.parts.append(text)


def parse_message(raw, key):
    msg = BytesParser(policy=policy.default).parsebytes(raw)
    sender = str(msg.get("From",""))
    part = msg.get_body(preferencelist=("plain","html"))
    content = part.get_content() if part else ""
    if part and part.get_content_type()=="text/html":
        html = ReadableHTML()
        html.feed(content)
        content = "\n".join(line.strip() for line in "".join(html.parts).splitlines() if line.strip())
    files = [str(p.get_filename()) for p in msg.iter_attachments() if p.get_filename()]
    if files:
        content += "\n\nВложения в почте: " + ", ".join(files)
    try:
        sent = parsedate_to_datetime(str(msg["Date"])).astimezone(MSK).isoformat()
    except (ValueError,TypeError,OverflowError):
        sent = ""
    return dict(key=key, sender=sender,subject=str(msg.get("subject") or "Без темы"),body=content.strip(),date=sent)


def allowed(sender, rules):
    addr = parseaddr(sender)[1].lower()
    domain = addr.partition("@")[2]
    return any(rule in ("*",addr,domain) for rule in rules if rule)


def microsoft(endpoint, data):
    tenant = os.environ.get("MS_TENANT_ID") or "organizations"
    if not re.fullmatch(r"[\w.-]+",tenant):
        raise SourceError("Проверь MS_TENANT_ID.")
    uri = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/{endpoint}"
    data = dict(data, client_id=os.environ["MS_CLIENT_ID"])
    if os.getenv("MS_CLIENT_SECRET") and endpoint == "token":
        data["client_secret"] = os.environ["MS_CLIENT_SECRET"]
    try:
        with urlopen(Request(uri,data=urlencode(data).encode()),timeout=15) as resp:
            return json.load(resp)
    except HTTPError as e:
        return {"error":json.load(e).get("error","access_denied")}


def save_refresh(value):
    if value and value != os.getenv("MS_REFRESH_TOKEN"):
        set_key(str(ENV),"MS_REFRESH_TOKEN",value)
        os.chmod(ENV,0o600)
        os.environ["MS_REFRESH_TOKEN"] = value


def outlook_login():
    if not os.getenv("MS_CLIENT_ID"):
        raise SystemExit("Добавь MS_CLIENT_ID из регистрации приложения Microsoft в .env.")
    auth = microsoft("devicecode",{"scope":SCOPE})
    if "message" not in auth:
        raise SystemExit("Microsoft не разрешил вход по коду устройства.")
    print(auth["message"],flush=True)
    pause = auth.get("interval",5)
    until = time.monotonic()+auth["expires_in"]
    while time.monotonic() < until:
        time.sleep(pause)
        result = microsoft("token",{"device_code":auth["device_code"],"grant_type":"urn:ietf:params:oauth:grant-type:device_code"})
        if result.get("refresh_token"):
            save_refresh(result["refresh_token"])
            print("Почтовый доступ сохранён в локальном .env.")
            return
        if result.get("error") == "slow_down":
            pause += 5
        elif result.get("error") != "authorization_pending":
            break
    raise SystemExit("Вход не завершён. Запусти подключение ещё раз.")


class ImapSource:
    def __init__(self):
        self.host = os.getenv("IMAP_HOST","").strip()
        self.user = os.getenv("IMAP_USER","").strip()
        self.folder = os.getenv("IMAP_FOLDER") or "INBOX"
        self.identity = hashlib.sha256("\n".join((self.host,self.user,self.folder)).encode()).hexdigest()
        self.access = ""
        self.expires = 0

    def read(self, cursor):
        if not self.host or not self.user:
            raise SourceError("Заполни IMAP_HOST и IMAP_USER в .env.")
        rules = [r.strip().lower() for r in os.getenv("MAIL_SENDERS","isu.ifmo.ru,isu.itmo.ru").split(",")]
        with imaplib.IMAP4_SSL(self.host,int(os.getenv("IMAP_PORT") or 993),timeout=20,
                               ssl_context=ssl.create_default_context()) as imap:
            if os.getenv("MS_REFRESH_TOKEN"):
                if self.expires <= time.monotonic():
                    result = microsoft("token",dict(grant_type="refresh_token",refresh_token=os.environ["MS_REFRESH_TOKEN"],scope=SCOPE))
                    if "access_token" not in result:
                        raise SourceError("Требуется повторный вход в Microsoft 365.")
                    self.access = result["access_token"]
                    self.expires = time.monotonic()+int(result.get("expires_in",300))-60
                    save_refresh(result.get("refresh_token"))
                imap.authenticate("XOAUTH2",lambda _:f"user={self.user}\x01auth=Bearer {self.access}\x01\x01".encode())
            else:
                imap.login(self.user,os.environ.get("IMAP_PASSWORD",""))
            status,_ = imap.select('"'+self.folder.replace('\\','\\\\').replace('"','\\"')+'"',readonly=True)
            if status != "OK":
                raise SourceError("Почтовая папка не найдена.")
            validity = (imap.response("UIDVALIDITY")[1] or [None])[0]
            if not validity:
                raise SourceError("Почтовый сервер не подтвердил версию папки.")
            scope = self.identity+":"+validity.decode()
            same = cursor and cursor["scope"]==scope
            last = int(cursor["uid"]) if same else 0
            status, data = imap.uid("search",None,"UID",f"{last+1}:*" if same else "1:*")
            if status!="OK":
                raise SourceError("Не удалось загрузить список писем.")
            ids = [int(i) for i in data[0].split() if int(i)>last]
            selected = ids[:40] if same else ids[-20:]
            messages = []
            for uid in selected:
                def fetch(section):
                    status, payload = imap.uid("fetch",str(uid),section)
                    chunk = next((r[1] for r in payload if isinstance(r,tuple)),None)
                    if status!="OK":
                        raise SourceError("Не удалось прочитать письмо.")
                    return chunk
                header = fetch("(BODY.PEEK[HEADER.FIELDS (FROM)])")
                if header and allowed(str(BytesParser(policy=policy.default).parsebytes(header).get("From","")),rules):
                    raw = fetch("(BODY.PEEK[]<0.2097152>)")
                    if raw:
                        parsed = parse_message(raw,f"{scope}:{uid}")
                        if len(raw)>=2097152:
                            parsed["body"]+="\n\nПисьмо большое. Полная версия и вложения доступны в почте."
                        messages.append(parsed)
            return messages, {"scope":scope,"uid":max(selected,default=last)}, bool(same)


class Mail:
    def __init__(self, store, isu):
        self.s, self.isu = store, isu
        self.imap = ImapSource()
        self.lock = asyncio.Lock()
        self.last = 0
        self.signing_in = False

    def record(self, src, messages, notify):
        for x in messages:
            created = self.s.db.execute("INSERT OR IGNORE INTO mail(source,source_id,sender,subject,body,date) VALUES (?,?,?,?,?,?)",
                                        (src,x["key"],x["sender"],x["subject"],x["body"],x["date"])).rowcount
            if created and notify and self.s.get("mail_on",True) and self.s.get("owner"):
                self.s.post(self.s.get("owner"),f"✉️ {src} · {x['sender']}\n{x['subject']}\n\n{x['body'] or 'Текст отсутствует.'}")

    async def sync(self):
        if self.lock.locked():
            async with self.lock:
                return
        async with self.lock:
            self.last = time.monotonic()
            for src,enabled in (("ИСУ",self.s.get("isu_connected")),("Email",bool(self.imap.host and self.imap.user))):
                if not enabled or (src == "ИСУ" and self.signing_in):
                    continue
                key = "isu" if src=="ИСУ" else "mail"
                try:
                    if src=="ИСУ":
                        seen = self.s.get("isu_recent")
                        items = await self.isu.read(set(seen) if seen else None)
                        with self.s.db:
                            self.record(src,reversed(items),seen is not None)
                            if items or seen is None:
                                self.s.set("isu_recent",[m["key"] for m in items[:20]])
                    else:
                        items,cursor,notify = await asyncio.to_thread(self.imap.read,self.s.get("imap_cursor"))
                        with self.s.db:
                            self.record(src,items,notify)
                            self.s.set("imap_cursor",cursor)
                    detail = "Проверено " + datetime.now(MSK).strftime("%d.%m в %H:%M МСК")
                    ok = True
                except Exception as exc:
                    ok = False
                    detail = str(exc) if isinstance(exc,SourceError) else "Проверь доступ к почте, сеть и настройки входа."
                with self.s.db:
                    self.s.set(key+"_status",dict(ok=ok,detail=detail))

    async def run(self):
        while True:
            if self.s.get("owner") and time.monotonic()-self.last>=60:
                await self.sync()
            await asyncio.sleep(3)


if __name__=="__main__":
    os.umask(0o077)
    load_dotenv(ENV,interpolate=False)
    outlook_login()

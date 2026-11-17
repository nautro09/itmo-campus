"""Interactive portal sign-in on the bot host (also works over SSH X forwarding)."""
import argparse
import asyncio
import os
import sqlite3
from pathlib import Path

from inbox import IsuInbox
from itmo import Portal, SourceError
from store import Store


async def connect(source):
    os.umask(0o077)
    data=Path(__file__).resolve().parent/"data"
    data.mkdir(mode=0o700,exist_ok=True)
    lock=sqlite3.connect(data/"instance.lock",timeout=0)
    try:
        lock.execute("BEGIN EXCLUSIVE")
    except sqlite3.OperationalError:
        raise SystemExit("Останови экземпляр бота перед отдельным входом.")
    s=Store(data/"planner.sqlite3")
    portal=IsuInbox(data/"isu-browser") if source=="isu" else Portal(data/"my-itmo-browser")
    try:
        await portal.login()
        with s.db:
            s.set("isu_connected" if source=="isu" else "connected",True)
            if source=="itmo" and portal.identity:
                s.set("profile",portal.identity)
        print("Вход сохранён. Можно запускать бота.")
    finally:
        await portal.close()
        s.db.close()
        lock.close()


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("source",choices=["itmo","isu"])
    try:
        asyncio.run(connect(parser.parse_args().source))
    except SourceError as e:
        raise SystemExit(str(e))

"""Chaos-user actions against the packaged EXE (NEXT-06).

All actions are UI-level — never widget-row injection.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tests.blackbox.harness import ExeSession


def double_click_search(session: "ExeSession") -> None:
    session.click_by_title("Jobs suchen", timeout=8)
    time.sleep(0.15)
    try:
        session.click_by_title("Jobs suchen", timeout=2)
    except Exception:
        # May already show cancel — second click on cancel is also chaos.
        try:
            session.click_by_title("Suche abbrechen", timeout=2)
        except Exception:
            pass
    session.checkpoint("chaos_double_click_search")


def spam_refresh(session: "ExeSession", *, times: int = 5) -> None:
    for i in range(times):
        try:
            session.click_by_title("Aktualisieren", timeout=2)
        except Exception:
            break
        time.sleep(0.1)
    session.checkpoint("chaos_spam_refresh")


def start_cancel_search_loop(session: "ExeSession", *, rounds: int = 3) -> None:
    for _ in range(rounds):
        try:
            session.click_by_title("Jobs suchen", timeout=3)
        except Exception:
            pass
        time.sleep(0.3)
        try:
            session.click_by_title("Suche abbrechen", timeout=3)
        except Exception:
            pass
        time.sleep(0.2)
    session.checkpoint("chaos_start_cancel_loop")


def switch_pages_during_work(session: "ExeSession") -> None:
    for aid in ("kk.nav.jobs", "kk.nav.inbox", "kk.nav.applications", "kk.nav.overview"):
        try:
            session.click_by_automation_id(aid, timeout=3)
        except Exception:
            continue
        time.sleep(0.2)
    session.checkpoint("chaos_switch_pages")


def resize_window(session: "ExeSession") -> None:
    if session.app is None:
        return
    try:
        win = session.app.top_window()
        win.move_window(x=40, y=40, width=1024, height=720)
        time.sleep(0.2)
        win.move_window(x=40, y=40, width=1280, height=800)
    except Exception:
        pass
    session.checkpoint("chaos_resize")


def kill_and_note(session: "ExeSession") -> None:
    session.checkpoint("chaos_pre_kill")
    session.close(kill=True)
    session.checkpoint("chaos_post_kill")

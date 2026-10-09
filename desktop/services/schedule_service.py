"""Native per-user scheduling for Windows, macOS and Linux."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from core.config import AppConfig
from desktop.branding import TASK_SCHEDULER_NAME
from desktop.legacy_migration import legacy_data_dir_name
from desktop.paths import project_root

TASK_NAME = TASK_SCHEDULER_NAME
_LEGACY_TASK_NAME = f"{legacy_data_dir_name()}AutoRun"


class ScheduleService:
    """Create/update/remove a Windows scheduled task without manual Task Scheduler UI."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def _python_command(self) -> list[str]:
        # Always schedule a one-shot headless pipeline run (never bare GUI EXE).
        if getattr(sys, "frozen", False):
            return [str(Path(sys.executable).resolve()), "--once"]
        return [sys.executable, "-m", "app.main", "--once"]

    def sync_from_config(self) -> tuple[bool, str]:
        settings = self.config.settings
        if not settings.run_automatically or settings.automation_paused:
            return self.remove_task()
        if sys.platform != "win32":
            from desktop.services.native_schedule import sync

            return sync(settings, self._python_command(), project_root())

        cmd = self._python_command()
        # schtasks wants a single command string
        quoted = " ".join(f'"{c}"' if " " in c else c for c in cmd)
        workdir = project_root()

        mode = settings.schedule_mode
        try:
            self.remove_task()
            if mode == "on_login":
                args = [
                    "schtasks",
                    "/Create",
                    "/TN",
                    TASK_NAME,
                    "/TR",
                    quoted,
                    "/SC",
                    "ONLOGON",
                    "/RL",
                    "LIMITED",
                    "/F",
                ]
            elif mode == "every_x_hours":
                hours = max(1, int(settings.schedule_interval_hours or 6))
                args = [
                    "schtasks",
                    "/Create",
                    "/TN",
                    TASK_NAME,
                    "/TR",
                    quoted,
                    "/SC",
                    "HOURLY",
                    "/MO",
                    str(hours),
                    "/RL",
                    "LIMITED",
                    "/F",
                ]
            elif mode == "twice_daily":
                # Create once at 08:00 and a second task for 17:00
                ok1, msg1 = self._create_daily("08:00", quoted)
                ok2, msg2 = self._create_daily("17:00", quoted, name=f"{TASK_NAME}Evening")
                if ok1 and ok2:
                    return True, "Automatischer Lauf: zweimal täglich."
                return False, f"{msg1} | {msg2}"
            elif mode == "custom":
                times = settings.schedule_times or ["08:00"]
                messages = []
                for i, t in enumerate(times):
                    name = TASK_NAME if i == 0 else f"{TASK_NAME}_{i}"
                    ok, msg = self._create_daily(t, quoted, name=name)
                    messages.append(msg)
                    if not ok:
                        return False, "; ".join(messages)
                return True, "Benutzerdefinierte Zeiten gesetzt."
            else:  # once_daily
                time_str = (settings.schedule_times or ["08:00"])[0]
                return self._create_daily(time_str, quoted)
            proc = subprocess.run(args, capture_output=True, text=True, cwd=str(workdir))
            if proc.returncode != 0:
                return False, (proc.stderr or proc.stdout or "Task konnte nicht erstellt werden.").strip()
            return True, "Automatischer Lauf aktiviert."
        except OSError as exc:
            return False, str(exc)

    def _create_daily(
        self, time_str: str, quoted_cmd: str, name: str = TASK_NAME
    ) -> tuple[bool, str]:
        args = [
            "schtasks",
            "/Create",
            "/TN",
            name,
            "/TR",
            quoted_cmd,
            "/SC",
            "DAILY",
            "/ST",
            time_str,
            "/RL",
            "LIMITED",
            "/F",
        ]
        try:
            proc = subprocess.run(args, capture_output=True, text=True)
        except OSError as exc:
            return False, str(exc)
        if proc.returncode != 0:
            return False, (proc.stderr or proc.stdout or "Fehler").strip()
        return True, f"Täglich um {time_str}."

    def remove_task(self) -> tuple[bool, str]:
        if sys.platform != "win32":
            from desktop.services.native_schedule import remove

            return remove()
        names = [
            TASK_NAME,
            f"{TASK_NAME}Evening",
            _LEGACY_TASK_NAME,
            f"{_LEGACY_TASK_NAME}Evening",
        ] + [f"{TASK_NAME}_{i}" for i in range(1, 6)] + [
            f"{_LEGACY_TASK_NAME}_{i}" for i in range(1, 6)
        ]
        any_ok = False
        for name in names:
            try:
                proc = subprocess.run(
                    ["schtasks", "/Delete", "/TN", name, "/F"],
                    capture_output=True,
                    text=True,
                )
            except OSError:
                return True, "Task-Planer nicht verfügbar."
            if proc.returncode == 0:
                any_ok = True
        return True, "Automatischer Lauf deaktiviert." if any_ok else "Kein geplanter Task vorhanden."

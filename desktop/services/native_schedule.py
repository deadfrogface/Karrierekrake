"""Per-user launchd/systemd scheduling; no administrator privileges."""
from __future__ import annotations

import os
import plistlib
import re
import subprocess
import sys
from pathlib import Path

LABEL = 'com.karrierekrake.autorun'
UNIT = 'karrierekrake-autorun'


def calendar_times(settings) -> list[tuple[int, int]]:
    mode = settings.schedule_mode
    values = ['08:00', '17:00'] if mode == 'twice_daily' else (settings.schedule_times or ['08:00'])
    if mode == 'once_daily':
        values = values[:1]
    result = []
    for value in values:
        if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', value):
            raise ValueError('Uhrzeit muss HH:MM sein (00:00 bis 23:59).')
        hour, minute = map(int, value.split(':'))
        result.append((hour, minute))
    return result


def systemd_quote(value: str) -> str:
    # Specifiers are expanded even inside quotes; escape every percent.
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%').replace('$', '$$').replace('\n', '\\n').replace('\r', '\\r') + '"'


def paths() -> tuple[Path, ...]:
    if sys.platform == 'darwin':
        return (Path.home() / 'Library' / 'LaunchAgents' / f'{LABEL}.plist',)
    xdg = Path(os.environ.get('XDG_CONFIG_HOME', '')).expanduser()
    base = xdg if xdg.is_absolute() else Path.home() / '.config'
    return (base / 'systemd' / 'user' / f'{UNIT}.service', base / 'systemd' / 'user' / f'{UNIT}.timer')


def run(command: list[str]) -> None:
    proc = subprocess.run(command, capture_output=True, text=True, timeout=20, check=False)
    if proc.returncode:
        raise RuntimeError((proc.stderr or proc.stdout or 'Zeitplaner nicht erreichbar.').strip())


def launchd_job(settings, command: list[str], workdir: Path) -> dict:
    job = {'Label': LABEL, 'ProgramArguments': command, 'WorkingDirectory': str(workdir)}
    if settings.schedule_mode == 'on_login':
        job['RunAtLoad'] = True
    elif settings.schedule_mode == 'every_x_hours':
        job['StartInterval'] = max(1, int(settings.schedule_interval_hours or 6)) * 3600
    else:
        job['StartCalendarInterval'] = [{'Hour': h, 'Minute': m} for h, m in calendar_times(settings)]
    return job


def systemd_units(settings, command: list[str], workdir: Path) -> tuple[str, str | None]:
    service = ('[Unit]\nDescription=Karrierekrake automatischer Lauf\n'
               '[Service]\nType=oneshot\n'
               f'WorkingDirectory={systemd_quote(str(workdir))}\n'
               f'ExecStart={" ".join(systemd_quote(part) for part in command)}\n')
    if settings.schedule_mode == 'on_login':
        return service + '[Install]\nWantedBy=default.target\n', None
    timer = '[Unit]\nDescription=Karrierekrake Zeitplan\n[Timer]\n'
    if settings.schedule_mode == 'every_x_hours':
        hours = max(1, int(settings.schedule_interval_hours or 6))
        timer += f'OnStartupSec={hours}h\nOnUnitActiveSec={hours}h\n'
    else:
        timer += ''.join(f'OnCalendar=*-*-* {h:02d}:{m:02d}:00\n' for h, m in calendar_times(settings))
        timer += 'Persistent=true\n'
    return service, timer + f'Unit={UNIT}.service\n[Install]\nWantedBy=timers.target\n'


def _systemd_units(files: tuple[Path, ...]) -> tuple[tuple[str, Path], ...]:
    """(unit name, unit file) pairs; the timer first so it cannot restart the service."""
    return ((f'{UNIT}.timer', files[1]), (f'{UNIT}.service', files[0]))


def _systemd_stop_by_name() -> None:
    """Stop each unit separately by name; this works without unit files.

    Errors (e.g. "Unit ... not loaded" for the timer in on_login mode) are ignored,
    except a missing systemctl binary (FileNotFoundError), which is re-raised so the
    caller knows that nothing can be loaded.
    """
    for unit in (f'{UNIT}.timer', f'{UNIT}.service'):
        try:
            run(['systemctl', '--user', 'stop', unit])
        except FileNotFoundError:
            raise
        except (OSError, RuntimeError, subprocess.TimeoutExpired):
            pass


def _systemd_disable_existing(files: tuple[Path, ...]) -> None:
    """``disable`` only units whose file exists (on_login mode writes no timer)."""
    for unit, file in _systemd_units(files):
        if file.exists():
            run(['systemctl', '--user', 'disable', unit])


def _unload() -> None:
    """Best-effort unload by name (launchctl/systemctl act on the label/unit name).

    On systemd every unit is stopped by name; units whose file still exists are
    also disabled (removes e.g. the default.target.wants symlink of on_login).
    A missing scheduler binary means nothing can be loaded; every error is ignored.
    """
    try:
        if sys.platform == 'darwin':
            run(['launchctl', 'bootout', f'gui/{os.getuid()}/{LABEL}'])
        else:
            _systemd_stop_by_name()
            for unit, file in _systemd_units(paths()):
                if file.exists():
                    try:
                        run(['systemctl', '--user', 'disable', unit])
                    except (RuntimeError, subprocess.TimeoutExpired):
                        pass
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        pass


def _discard(files: tuple[Path, ...], unload: bool = True) -> None:
    """Best-effort rollback: never leave unit/plist files behind after a failed activation.

    bootstrap/enable may already have loaded the job before failing (e.g. timeout),
    so unload by name first, while the files still exist (systemd: existing units
    are disabled, so no default.target.wants/timers.target.wants symlink remains).
    """
    if unload:
        _unload()
    for file in files:
        try:
            file.unlink(missing_ok=True)
        except OSError:
            pass
    if sys.platform != 'darwin':
        try:
            run(['systemctl', '--user', 'daemon-reload'])
        except (OSError, RuntimeError, subprocess.TimeoutExpired):
            pass


def remove() -> tuple[bool, str]:
    files = paths()
    if not any(file.exists() for file in files):
        # The job may still be loaded although its files are gone (e.g. an
        # activation that timed out after loading): unload by name anyway.
        _unload()
        return True, 'Kein geplanter Task vorhanden.'
    scheduler_available = True
    try:
        try:
            if sys.platform == 'darwin':
                run(['launchctl', 'bootout', f'gui/{os.getuid()}/{LABEL}'])
            else:
                _systemd_stop_by_name()
                _systemd_disable_existing(files)
        except FileNotFoundError:
            # No launchctl/systemctl binary: nothing can have loaded these files,
            # they are orphans (e.g. from an earlier failed activation). Remove them.
            scheduler_available = False
        for file in files:
            file.unlink(missing_ok=True)
        if not scheduler_available:
            return True, 'Automatischer Lauf deaktiviert (Zeitplaner nicht verfügbar, Zeitplandateien entfernt).'
        if sys.platform != 'darwin':
            run(['systemctl', '--user', 'daemon-reload'])
        return True, 'Automatischer Lauf deaktiviert.'
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        return False, f'Zeitplaner: {exc}'


def sync(settings, command: list[str], workdir: Path) -> tuple[bool, str]:
    try:
        # Validate before removing an existing schedule.
        if sys.platform == 'darwin':
            content = plistlib.dumps(launchd_job(settings, command, workdir))
        else:
            service, timer = systemd_units(settings, command, workdir)
        ok, message = remove()
        if not ok:
            return ok, message
        files = paths()
        files[0].parent.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform == 'darwin':
                files[0].write_bytes(content)
                files[0].chmod(0o600)
                run(['launchctl', 'bootstrap', f'gui/{os.getuid()}', str(files[0])])
            else:
                files[0].write_text(service, encoding='utf-8')
                if timer is not None:
                    files[1].write_text(timer, encoding='utf-8')
                run(['systemctl', '--user', 'daemon-reload'])
                unit = f'{UNIT}.service' if timer is None else f'{UNIT}.timer'
                command = ['systemctl', '--user', 'enable']
                if timer is not None:
                    command.append('--now')
                run(command + [unit])
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            # Activation failed: orphaned files would make every later remove() fail.
            # A missing scheduler binary cannot have loaded anything.
            _discard(files, unload=not isinstance(exc, FileNotFoundError))
            raise
        return True, 'Automatischer Lauf aktiviert (im angemeldeten Benutzerkonto).'
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        return False, f'Zeitplaner nicht verfügbar: {exc}'

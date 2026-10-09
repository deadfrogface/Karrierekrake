import plistlib
import sys
from pathlib import Path

from core.config import empty_app_config
from desktop.services import native_schedule as ns


def settings(mode):
    value = empty_app_config().settings
    value.schedule_mode = mode
    value.schedule_times = ['09:15', '18:30']
    return value


def test_launchd_calendar_interval_and_login():
    command = ['/Applications/Karrierekrake.app/Contents/MacOS/Karrierekrake', '--once']
    for mode in ['custom', 'every_x_hours', 'on_login', 'once_daily', 'twice_daily']:
        job = ns.launchd_job(settings(mode), command, Path('/Applications'))
        assert plistlib.loads(plistlib.dumps(job))['ProgramArguments'] == command
        if mode == 'custom':
            assert job['StartCalendarInterval'] == [{'Hour': 9, 'Minute': 15}, {'Hour': 18, 'Minute': 30}]
        if mode == 'on_login':
            assert job['RunAtLoad'] is True
        if mode == 'every_x_hours':
            assert job['StartInterval'] == 6 * 3600


def test_systemd_escapes_paths_and_schedules_headless():
    service, timer = ns.systemd_units(settings('custom'), ['/home/Name %/Krake".bin', '--once'], Path('/home/Name %'))
    assert 'Name %%' in service and 'Krake\\".bin' in service and '"--once"' in service
    assert 'OnCalendar=*-*-* 09:15:00' in timer
    assert 'OnCalendar=*-*-* 18:30:00' in timer
    assert 'Persistent=true' in timer
    service, timer = ns.systemd_units(settings('on_login'), ['/app', '--once'], Path('/'))
    assert timer is None and 'WantedBy=default.target' in service


def test_invalid_time_does_not_remove_previous_schedule(monkeypatch):
    monkeypatch.setattr(sys, 'platform', 'linux')
    monkeypatch.setattr(ns, 'remove', lambda: (_ for _ in ()).throw(AssertionError('destroyed valid schedule')))
    value = settings('custom')
    value.schedule_times = ['99:99']
    ok, message = ns.sync(value, ['/app', '--once'], Path('/'))
    assert not ok and 'HH:MM' in message


def test_systemd_sync_writes_owned_files_only(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, 'platform', 'linux')
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path))
    calls = []
    monkeypatch.setattr(ns, 'run', calls.append)
    assert ns.sync(settings('custom'), ['/tmp/app', '--once'], Path('/tmp'))[0]
    files = ns.paths()
    assert all(file.is_file() for file in files)
    assert calls[-1] == ['systemctl', '--user', 'enable', '--now', 'karrierekrake-autorun.timer']
    assert ns.remove()[0]
    assert not any(file.exists() for file in files)


def test_launchd_sync_and_remove(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, 'platform', 'darwin')
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    monkeypatch.setattr(ns.os, 'getuid', lambda: 501, raising=False)
    calls = []
    monkeypatch.setattr(ns, 'run', calls.append)
    assert ns.sync(settings('on_login'), ['/app', '--once'], Path('/'))[0]
    assert calls[-1][:3] == ['launchctl', 'bootstrap', 'gui/501']
    assert ns.remove()[0]
    assert calls[-1] == ['launchctl', 'bootout', 'gui/501/com.karrierekrake.autorun']

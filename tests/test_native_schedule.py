import plistlib
import subprocess
import sys
from pathlib import Path

import pytest

from core.config import empty_app_config
from desktop.services import native_schedule as ns

_REAL_POPEN = subprocess.Popen  # only for the read-only systemd-analyze verify test


@pytest.fixture(autouse=True)
def _no_real_processes(monkeypatch):
    """No test in this file may start a real process (scheduler commands act by name)."""

    def refuse(*args, **kwargs):
        raise AssertionError(f"real process started: {args!r}")

    monkeypatch.setattr(subprocess, "Popen", refuse)


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


# --- WorkingDirectory= (T04.08): systemd does not unquote this setting -------------------------

# Real directories with '"', '\\' or a POSIX absolute path cannot exist on a Windows host;
# these run on linux-pytest / macOS (systemd units are only generated on Linux).
_POSIX_ONLY = pytest.mark.skipif(sys.platform == 'win32', reason='real POSIX directory names (systemd is Linux-only)')


def _working_directory_line(service: str) -> str:
    lines = [line for line in service.splitlines() if line.startswith('WorkingDirectory=')]
    assert len(lines) == 1
    return lines[0]


@_POSIX_ONLY
@pytest.mark.parametrize('name', ['Ordner mit Leerzeichen', 'Rabatt 100% %h %i', 'a b%c$d"e\\f', 'Ünïcödé %% x'])
def test_systemd_working_directory_unquoted_real_dirs_with_space_and_percent(tmp_path, name):
    workdir = tmp_path / name
    workdir.mkdir()
    assert workdir.is_dir() and workdir.is_absolute()
    service, timer = ns.systemd_units(settings('custom'), ['/bin/true'], workdir)
    expected = 'WorkingDirectory=' + str(workdir).replace('%', '%%')
    assert _working_directory_line(service) == expected
    # no quoting around the path (the CI proof: a quoted value is "not absolute")
    assert not _working_directory_line(service).startswith('WorkingDirectory="')
    # systemd's specifier expansion of the written value gives back the real path
    assert expected.split('=', 1)[1].replace('%%', '%') == str(workdir)
    # ExecStart quoting is unchanged (systemd unquotes ExecStart=)
    assert 'ExecStart="/bin/true"\n' in service and timer is not None


@pytest.mark.parametrize(
    'bad',
    [
        'relative/dir',
        '-/leading-dash',
        '~',
        '/tmp/a/../b',
        '/tmp/new\nline',
        '/tmp/carriage\rreturn',
        '/tmp/tab\there',
        '/tmp/trailing space ',
        '/tmp/trailing-backslash\\',
        '/tmp/bad-\udcff-utf8',
    ],
)
def test_systemd_working_directory_rejects_unrepresentable_paths(bad):
    with pytest.raises(ValueError):
        ns.systemd_working_directory(bad)


def test_windows_drive_path_accepted_only_on_windows_host(monkeypatch):
    """Mocked Linux tests on the Windows CI pass project_root() (C:/...); a POSIX host never accepts it."""
    monkeypatch.setattr(ns.os, 'name', 'posix')
    with pytest.raises(ValueError):
        ns.systemd_working_directory('C:/Users/Name 100%')
    monkeypatch.setattr(ns.os, 'name', 'nt')
    assert ns.systemd_working_directory('C:/Users/Name 100%') == 'C:/Users/Name 100%%'
    with pytest.raises(ValueError):
        ns.systemd_working_directory('relative/dir')


def test_unrepresentable_workdir_does_not_remove_previous_schedule(monkeypatch):
    monkeypatch.setattr(sys, 'platform', 'linux')
    monkeypatch.setattr(ns, 'remove', lambda: (_ for _ in ()).throw(AssertionError('destroyed valid schedule')))
    ok, message = ns.sync(settings('custom'), ['/app', '--once'], Path('/tmp/new\nline'))
    assert not ok and 'Arbeitsverzeichnis' in message


@_POSIX_ONLY
def test_systemd_sync_writes_unquoted_working_directory_file(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, 'platform', 'linux')
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'cfg'))
    monkeypatch.setattr(ns, 'run', lambda command: None)
    workdir = tmp_path / 'Mein Projekt 50% %u'
    workdir.mkdir()
    assert ns.sync(settings('on_login'), ['/bin/true'], workdir)[0]
    text = ns.paths()[0].read_text(encoding='utf-8')
    assert f'\nWorkingDirectory={str(workdir).replace("%", "%%")}\n' in text


@_POSIX_ONLY
def test_systemd_analyze_verify_accepts_generated_working_directory(tmp_path, monkeypatch):
    """Real ``systemd-analyze --user verify`` on the generated unit (read-only, no manager change)."""
    import shutil

    analyze = shutil.which('systemd-analyze')
    if analyze is None:
        pytest.skip('systemd-analyze not installed on this host')
    monkeypatch.setattr(subprocess, 'Popen', _REAL_POPEN)
    workdir = tmp_path / 'Ordner 100% %h'
    workdir.mkdir()
    service, _ = ns.systemd_units(settings('on_login'), ['/bin/true'], workdir)

    import os

    env = dict(os.environ)
    if not env.get('XDG_RUNTIME_DIR'):  # verify --user needs a runtime dir (not the bus)
        runtime = tmp_path / 'run'
        runtime.mkdir(mode=0o700)
        env['XDG_RUNTIME_DIR'] = str(runtime)

    def verify(name: str, text: str) -> str:
        unit = tmp_path / name
        unit.write_text(text, encoding='utf-8')
        proc = subprocess.run([analyze, '--user', 'verify', str(unit)], capture_output=True, text=True, timeout=60, check=False, env=env)
        return proc.stdout + proc.stderr

    # positive control: the old quoted form must be reported, otherwise verify is not usable here
    quoted = service.replace(_working_directory_line(service), f'WorkingDirectory={ns.systemd_quote(str(workdir))}')
    control = verify('kk-verify-quoted.service', quoted)
    if 'not absolute' not in control:
        pytest.skip(f'systemd-analyze verify does not check WorkingDirectory= in this environment: {control.strip()[:300]!r}')
    output = verify('kk-verify-test.service', service)
    assert 'WorkingDirectory=' not in output and 'bad unit file setting' not in output, output

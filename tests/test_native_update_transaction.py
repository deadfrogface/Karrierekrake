"""Exercise the actual POSIX helper and atomic filesystem exchange offline."""
import json
import os
from pathlib import Path
import sys
import time

import pytest

from core import native_update_install as updater


@pytest.mark.skipif(sys.platform not in {'linux', 'darwin'}, reason='POSIX atomic exchange integration')
@pytest.mark.parametrize('healthy', [True, False])
def test_real_exchange_startup_and_rollback(tmp_path, monkeypatch, healthy):
    root = tmp_path / 'Karrierekrake'
    stage = tmp_path / '.kk-native-update-test'
    app = stage / 'payload/Karrierekrake'
    profile = tmp_path / 'profile.json'
    profile.write_text('{"synthetic":true}')
    project = Path(__file__).resolve().parents[1]
    code = '''#!{python}
import os, sys
from pathlib import Path
sys.path.insert(0, {project!r})
if len(sys.argv) > 1 and sys.argv[1] == '--native-update-swap':
    from core.native_update_install import exchange_bundles
    sys.frozen = True
    sys.executable = str(Path(__file__).resolve())
    exchange_bundles(sys.argv[2])
elif {healthy!r} and os.environ.get('KK_NATIVE_UPDATE_MARKER'):
    Path(os.environ['KK_NATIVE_UPDATE_MARKER']).write_text(os.environ['KK_NATIVE_UPDATE_COMMIT'])
'''
    for path, version, ok in [(root, 'old', True), (app, 'new', healthy)]:
        path.mkdir(parents=True)
        (path / 'version').write_text(version)
        exe = path / 'Karrierekrake'
        exe.write_text(code.format(python=sys.executable, project=str(project), healthy=ok))
        exe.chmod(0o700)
    (stage / 'transaction.json').write_text(json.dumps({
        'root': str(root), 'app': str(app), 'commit': 'b' * 40,
        'relative_executable': 'Karrierekrake'}))
    monkeypatch.setattr(updater, 'install_location', lambda: root)
    # A definitely absent parent: do not wait for the pytest process to exit.
    monkeypatch.setattr(updater.os, 'getpid', lambda: 999999999)
    original = updater.subprocess.Popen
    processes = []
    def spawn(*args, **kwargs):
        proc = original(*args, **kwargs)
        processes.append(proc)
        return proc
    monkeypatch.setattr(updater.subprocess, 'Popen', spawn)
    updater.launch_installer(stage)
    try:
        processes[0].wait(timeout=25)
    finally:
        if processes[0].poll() is None:
            os.killpg(processes[0].pid, 9)
            processes[0].wait()
    assert processes[0].returncode == 0
    assert (stage / 'result').read_text().strip() == ('success' if healthy else 'rollback')
    assert (root / 'version').read_text() == ('new' if healthy else 'old')
    assert (app / 'version').read_text() == ('old' if healthy else 'new')
    assert profile.read_text() == '{"synthetic":true}'

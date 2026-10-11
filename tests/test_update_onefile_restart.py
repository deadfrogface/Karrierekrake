"""Exercise the real Windows onefile bootloader after a model-only install."""
import json
from pathlib import Path
import subprocess
import sys
import time

import pytest


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows onefile installer')
def test_model_install_restarts_after_old_extraction_is_removed(tmp_path):
    # A tiny real frozen program runs the production installer. Unlike a
    # mocked Start-Process, this catches inherited _PYI_* state and DLL loss.
    source = tmp_path / 'restart_fixture.py'
    source.write_text('''
import hashlib
import json
from pathlib import Path
import sys
from core.app_updates import launch_installer

root = Path(sys.executable).parent
model = root / 'model.gguf'
if model.exists():
    (root / 'restarted.json').write_text(json.dumps({'extraction': sys._MEIPASS,
                                                  'model': model.read_text()}))
else:
    (root / 'initial.json').write_text(json.dumps({'extraction': sys._MEIPASS}))
    stage = root / 'stage'
    stage.mkdir()
    data = b'verified downloaded weights'
    (stage / 'model.gguf').write_bytes(data)
    (stage / 'plan.json').write_text(json.dumps({
        'root': str(root), 'files': ['model.gguf'],
        'hashes': {'model.gguf': hashlib.sha256(data).hexdigest()}}))
    launch_installer(stage)
''', encoding='utf-8')
    repo = Path(__file__).resolve().parents[1]
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
                    '--onefile', '--name', 'Karrierekrake', '--paths', str(repo),
                    '--distpath', str(tmp_path / 'dist'), '--workpath', str(tmp_path / 'build'),
                    '--specpath', str(tmp_path), str(source)], check=True,
                   capture_output=True, timeout=180)
    root = tmp_path / 'dist'
    proc = subprocess.Popen([str(root / 'Karrierekrake.exe')],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        assert proc.wait(timeout=60) == 0
        deadline = time.monotonic() + 60
        while not (root / 'restarted.json').exists() and time.monotonic() < deadline:
            time.sleep(.1)
        assert (root / 'restarted.json').exists(), 'Installed model but frozen restart failed'
        initial = json.loads((root / 'initial.json').read_text())
        restarted = json.loads((root / 'restarted.json').read_text())
        assert restarted['model'] == 'verified downloaded weights'
        assert restarted['extraction'] != initial['extraction']
        assert not Path(initial['extraction']).exists()
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)

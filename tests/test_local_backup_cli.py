from scripts.local_backup_cli import main


def test_backup_cli_roundtrip(tmp_path, capsys):
    src = tmp_path / "source"
    src.mkdir()
    (src / "profile.json").write_text('{"sample":true}')
    archive = tmp_path / "backup.zip"
    target = tmp_path / "restored"
    assert main(["create", str(src), str(archive)]) == 0
    assert '"status": "ok"' in capsys.readouterr().out
    assert main(["verify", str(archive)]) == 0
    assert main(["restore", str(archive), str(target)]) == 0
    assert (target / "profile.json").read_text() == '{"sample":true}'


def test_desktop_backup_entrypoint_roundtrip_without_importing_qt(tmp_path):
    import os
    from pathlib import Path
    import subprocess
    import sys
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'profile.json').write_text('{"synthetic":true}')
    archive, target = tmp_path / 'backup.zip', tmp_path / 'restored'
    code = '''import builtins, runpy, sys
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.startswith("PySide6"):
        raise RuntimeError("backup must not initialize Qt")
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
sys.argv = ["Karrierekrake", "--local-backup", *sys.argv[1:]]
runpy.run_module("desktop.app", run_name="__main__")
'''
    for arguments in [('create', source, archive), ('verify', archive), ('restore', archive, target)]:
        child = subprocess.run([sys.executable, '-c', code, *map(str, arguments)],
                               cwd=Path(__file__).resolve().parents[1],
                               env={**os.environ, 'KARRIEREKRAKE_DATA_DIR': str(tmp_path / 'data')},
                               capture_output=True, text=True, timeout=30)
        assert child.returncode == 0, child.stderr
    assert (target / 'profile.json').read_text() == '{"synthetic":true}'


def test_fresh_completion_receipt_is_written_and_cannot_be_reused(tmp_path):
    import json
    import pytest
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'profile.json').write_text('{"synthetic":true}')
    archive, receipt = tmp_path / 'backup.zip', tmp_path / 'result.json'
    assert main(['--result-json', str(receipt), 'create', str(source), str(archive)]) == 0
    assert json.loads(receipt.read_text()) == {'status': 'ok', 'files': 1, 'bytes': 18}
    second_archive = tmp_path / 'second.zip'
    with pytest.raises(FileExistsError, match='receipt_exists'):
        main(['--result-json', str(receipt), 'create', str(source), str(second_archive)])
    assert not second_archive.exists()

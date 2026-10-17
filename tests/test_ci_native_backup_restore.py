"""The native recovery harness must release its own SQLite file handles."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

from scripts import ci_native_backup_restore as harness


def test_recovery_harness_closes_both_database_connections(tmp_path, monkeypatch):
    exe = tmp_path / 'native'
    exe.write_bytes(b'\x7fELFsynthetic')
    original_connect = sqlite3.connect
    retained = []

    class TrackedConnection(sqlite3.Connection):
        closed = False

        def close(self):
            super().close()
            self.closed = True

    def connect(*args, **kwargs):
        connection = original_connect(*args, factory=TrackedConnection, **kwargs)
        retained.append(connection)  # GC must not conceal an unclosed handle.
        return connection

    def run(command, *, env, **kwargs):
        profile = Path(env['KARRIEREKRAKE_DATA_DIR'])
        if '--smoke-test' in command:
            database = profile / 'data/jobs.db'
            database.parent.mkdir(parents=True, exist_ok=True)
            with closing(original_connect(database)):
                pass
            (profile / 'smoke_test_result.txt').write_text('SMOKE_TEST_OK\ndb=' + str(database))
        else:
            from scripts.local_backup_cli import main
            assert main(command[2:]) == 0
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(harness.sqlite3, 'connect', connect)
    monkeypatch.setattr(harness.subprocess, 'run', run)
    result = harness.verify(exe, tmp_path / 'proof.json')
    assert result['ok'] is True
    assert len(retained) >= 2
    assert all(connection.closed for connection in retained)
    assert json.loads((tmp_path / 'proof.json').read_text())['synthetic_marker_preserved']

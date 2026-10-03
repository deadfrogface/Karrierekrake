import json
import sys
from types import ModuleType
import pytest
from scripts import prepare_google_desktop_client as setup


def client():
    return {"installed": {"client_id": "test.apps.googleusercontent.com", "client_secret": "test",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth", "token_uri": "https://oauth2.googleapis.com/token"}}


def test_provision_from_secret_without_logging_contents(tmp_path, monkeypatch, capsys):
    target = tmp_path / "assets/oauth/desktop_client.json"
    monkeypatch.setattr(setup, "TARGET", target)
    monkeypatch.setenv("GOOGLE_DESKTOP_CLIENT_JSON", json.dumps(client()))
    assert setup.main() == 0
    assert json.loads(target.read_text()) == client()
    assert "test.apps.googleusercontent.com" not in capsys.readouterr().out


def test_missing_secret_stops_build(monkeypatch):
    monkeypatch.delenv("GOOGLE_DESKTOP_CLIENT_JSON", raising=False)
    with pytest.raises(SystemExit, match="Missing repository Actions secret"):
        setup.main()


@pytest.mark.parametrize("data", [{"web": {}}, {"refresh_token": "x"}, {"private_key": "x"},
    {"installed": {}}, {"installed": {**client()["installed"], "refresh_token": "x"}},
    {"installed": {**client()["installed"], "token_uri": "https://example.com"}}])
def test_reject_wrong_or_private_credentials(data):
    with pytest.raises(ValueError, match="Expected Google Desktop"):
        setup.validate_client(json.dumps(data))


def test_artifact_gate_rejects_missing_client(monkeypatch, tmp_path):
    from scripts import scan_release_artifact as scan
    readers = ModuleType("PyInstaller.archive.readers")
    monkeypatch.setitem(sys.modules, "PyInstaller.archive.readers", readers)
    class Archive:
        toc = {}
    monkeypatch.setattr(readers, "CArchiveReader", lambda *a: Archive(), raising=False)
    assert scan.require_google_client_embedded(tmp_path / "app.exe")


def test_artifact_gate_validates_embedded_client(monkeypatch, tmp_path):
    from scripts import scan_release_artifact as scan
    readers = ModuleType("PyInstaller.archive.readers")
    monkeypatch.setitem(sys.modules, "PyInstaller.archive.readers", readers)
    class Archive:
        toc = {"assets/oauth/desktop_client.json": ()}
        def extract(self, name):
            return json.dumps(client()).encode()
    monkeypatch.setattr(readers, "CArchiveReader", lambda *a: Archive(), raising=False)
    assert scan.require_google_client_embedded(tmp_path / "app.exe") == []

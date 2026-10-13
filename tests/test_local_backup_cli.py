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

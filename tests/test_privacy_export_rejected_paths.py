from core.privacy import export_bundle as module


def test_rejected_document_path_not_returned(tmp_path, monkeypatch):
    private = tmp_path / "user" / "secret" / "cv.pdf"
    monkeypatch.setattr(module, "gate_export", lambda *args, **kwargs: type("Gate", (), {"allowed": False})())
    result = module.build_export_bundle(dest_dir=tmp_path / "out", profile=None,
        document_paths=[private], user_confirmed_pii=True)
    assert result.ok
    assert result.skipped == ["document_rejected"]
    assert str(tmp_path) not in repr(result.skipped)


def test_export_redacts_secret_keys_in_all_sections(tmp_path):
    import json
    import zipfile
    result = module.build_export_bundle(
        dest_dir=tmp_path / "out",
        profile={"first_name": "Demo"},
        cases=[{"token": "secret-value", "case": "application"}],
        mail_meta=[{"refresh_token": "private", "subject": "hello"}],
        hr_contacts=[{"client_secret": "private", "name": "Demo"}],
        jobs_summary=[{"access_token": "private", "job": "Analyst"}],
        user_confirmed_pii=True,
    )
    assert result.ok
    with zipfile.ZipFile(result.path) as archive:
        for name in ("cases.json", "mail_meta.json", "hr_contacts.json", "jobs_summary.json"):
            raw = archive.read(name).decode("utf-8")
            assert "secret-value" not in raw
            assert '"private"' not in raw
            assert "[REDACTED]" in raw
            assert isinstance(json.loads(raw), list)

from core.privacy import export_bundle as module


def test_rejected_document_path_not_returned(tmp_path, monkeypatch):
    private = tmp_path / "user" / "secret" / "cv.pdf"
    monkeypatch.setattr(module, "gate_export", lambda *args, **kwargs: type("Gate", (), {"allowed": False})())
    result = module.build_export_bundle(dest_dir=tmp_path / "out", profile=None,
        document_paths=[private], user_confirmed_pii=True)
    assert result.ok
    assert result.skipped == ["document_rejected"]
    assert str(tmp_path) not in repr(result.skipped)

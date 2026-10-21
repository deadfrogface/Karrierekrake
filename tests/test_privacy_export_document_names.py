import json
import zipfile

from core.privacy.export_bundle import build_export_bundle


def test_export_document_index_hides_absolute_paths_and_disambiguates(tmp_path, monkeypatch):
    import core.privacy.export_bundle as module
    monkeypatch.setattr(module, "gate_export", lambda *args, **kwargs: type("Gate", (), {"allowed": True})())
    left = tmp_path / "private-one"
    right = tmp_path / "private-two"
    left.mkdir()
    right.mkdir()
    first = left / "cv.pdf"
    second = right / "cv.pdf"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    result = build_export_bundle(
        dest_dir=tmp_path / "exports", profile=None,
        document_paths=[first, second],
        include_document_bytes=True, user_confirmed_pii=True,
    )
    assert result.ok
    with zipfile.ZipFile(result.path) as archive:
        names = archive.namelist()
        assert len(names) == len(set(names))
        assert "documents/cv.pdf" in names
        assert "documents/cv-2.pdf" in names
        index = json.loads(archive.read("documents_index.json"))
        assert [item["name"] for item in index] == ["cv.pdf", "cv-2.pdf"]
        assert all("path" not in item for item in index)
        assert str(tmp_path) not in archive.read("documents_index.json").decode()

"""Regression: a resumable model needs only the remaining disk capacity."""
from guenther import model_manager as models


def test_resume_disk_preflight_counts_existing_partial(tmp_path, monkeypatch):
    mid = models.PRODUCTION_MODEL_ID
    manager = models.ModelManager(tmp_path, catalog={mid: {
        "filename": "model.gguf", "url": "https://example.test/model.gguf",
        "sha256": "a" * 64, "approx_bytes": 1000,
    }})
    model = manager.model_path(mid)
    model.parent.mkdir()
    model.with_suffix(".gguf.part").write_bytes(b"x" * 800)
    monkeypatch.setattr(manager, "disk_free_bytes", lambda: 500_300_000)
    assert manager.can_install(mid) == (True, "ok")


def test_oversized_partial_does_not_reduce_required_space(tmp_path, monkeypatch):
    mid = models.PRODUCTION_MODEL_ID
    manager = models.ModelManager(tmp_path, catalog={mid: {
        "filename": "model.gguf", "url": "https://example.test/model.gguf",
        "sha256": "a" * 64, "approx_bytes": 1000,
    }})
    model = manager.model_path(mid)
    model.parent.mkdir()
    model.with_suffix(".gguf.part").write_bytes(b"x" * 1200)
    monkeypatch.setattr(manager, "disk_free_bytes", lambda: 500_300_000)
    assert manager.can_install(mid) == (False, "insufficient_disk")

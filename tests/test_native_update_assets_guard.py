import pytest
from core import native_updates


@pytest.mark.parametrize("assets", [None, {}, ["bad"], [None], [123]])
def test_native_update_rejects_malformed_assets(monkeypatch, assets):
    target = native_updates.runtime_target()
    if target is None:
        pytest.skip("native platform only")
    release = {"draft": False, "prerelease": False, "tag_name": "v1.2.3", "assets": assets}
    monkeypatch.setattr(native_updates, "_json", lambda url: [release])
    with pytest.raises(ValueError, match="invalid_native_release_assets"):
        native_updates.check_for_update({"target": target, "sequence": 1, "commit": "a" * 40})


def test_native_update_incomplete_installed_metadata_is_ignored(monkeypatch):
    target = native_updates.runtime_target()
    if target is None:
        pytest.skip("native platform only")
    monkeypatch.setattr(native_updates, "_json", lambda url: pytest.fail("network not expected"))
    assert native_updates.check_for_update({"target": target}) is None

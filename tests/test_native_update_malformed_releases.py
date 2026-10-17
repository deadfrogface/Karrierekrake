import pytest
from core import native_updates


@pytest.mark.parametrize("bad_entry", [None, [], "invalid", 12])
def test_native_updater_rejects_malformed_release_entries(monkeypatch, bad_entry):
    monkeypatch.setattr(native_updates, "runtime_target", lambda: "linux-x86_64")
    monkeypatch.setattr(native_updates, "_json", lambda url: [bad_entry])
    installed = {"target": "linux-x86_64", "commit": "a" * 40, "sequence": 1}
    with pytest.raises(ValueError, match="invalid_native_release_list_entry"):
        native_updates.check_for_update(installed)

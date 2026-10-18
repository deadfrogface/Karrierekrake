"""RAM rule parity: the model setup panel locks exactly what the wizard's
recommendation and the device report reject.

``guenther.model_budgets.usable_ram_fits`` is the ONE RAM rule
(``recommend_setup_model`` free_ram_ok, ``device_check`` candidates). The
panel (settings page and first-run wizard both use ``ModelSetupPanel``) must
make every RAM fit decision through it, in the normal path (the real
``recommend_setup_model`` result with its ``fits`` dict) and in the threshold
fallback (a recommendation without any ``fits``). Same pattern as the
device_check parity test of b831d584 (tests/test_setup_thresholds.py PARITY).

Runs offscreen (QT_QPA_PLATFORM=offscreen); PySide6 is imported directly so a
missing Qt fails loudly instead of skipping.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication  # noqa: F401  (loud failure without Qt)

from desktop.i18n import tr
from desktop.widgets import model_fit
from desktop.widgets import model_setup_panel as panels
from guenther import model_budgets
from guenther import setup_models as setup

M4, M8, M27 = "qwen3.5-4b-gsq", "qwen3-8b-gsq", "qwen3.8-27b-gsq-rco"
DISK_OK = 100_000_000_000

# total GiB, free GiB, free disk bytes, expected selectable models
GRID = [
    # ~8 GB laptop (7.7 GiB reported) and round 8 GiB
    (7.7, 3.0, DISK_OK, {M4}),
    (7.7, 6.5, DISK_OK, {M4}),
    (8.0, 3.0, DISK_OK, {M4}),
    (8.0, 7.0, DISK_OK, {M4}),
    # 16 GB (15.6 reported) and round 16 GiB: 8B needs free RAM, 27B never (headroom / budget)
    (15.6, 3.0, DISK_OK, {M4}),
    (15.6, 14.0, DISK_OK, {M4, M8}),
    (16.0, 3.0, DISK_OK, {M4}),
    (16.0, 14.0, DISK_OK, {M4, M8}),
    # 32 GB (31.6 reported) and round 32 GiB: low free RAM leaves only 4B
    (31.6, 3.0, DISK_OK, {M4}),
    (31.6, 28.0, DISK_OK, {M4, M8, M27}),
    (32.0, 3.0, DISK_OK, {M4}),
    (32.0, 28.0, DISK_OK, {M4, M8, M27}),
    # plus the disk rule: 27B file + reserve does not fit 5 GB
    (31.6, 28.0, 5_000_000_000, {M4, M8}),
]
IDS = [f"{t}GiB-{a}free-{d // 1_000_000_000}GB" for t, a, d, _ in GRID]


def usable_set(total, available, disk):
    """What the shared rule allows: usable_ram_fits plus file + reserve on disk."""
    allowed = set()
    for mid, entry in setup.SETUP_MODEL_CATALOG.items():
        if (model_budgets.usable_ram_fits(entry["model_class"], total_gib=total, available_gib=available,
                                          own_gib=entry.get("ram_gb_min"))
                and entry["approx_bytes"] + model_budgets.DISK_RESERVE_BYTES <= disk):
            allowed.add(mid)
    return allowed


def real_recommendation(total, available, disk, cores=8):
    return setup.recommend_setup_model(total_gib=total, available_gib=available,
                                       physical_cores=cores, free_disk_bytes=disk)


def no_fits_recommendation(total, available, disk, cores=8):
    """No fits information at all: the adapter's threshold fallback decides."""
    return SimpleNamespace(total_gib=total, available_gib=available, physical_cores=cores,
                           free_disk_bytes=disk, model_id=None)


PATHS = {"recommendation": real_recommendation, "fallback": no_fits_recommendation}


def make_panel(qtbot, monkeypatch, check, context):
    monkeypatch.setattr(panels, "inspect_setup_device", lambda: check)
    monkeypatch.setattr(panels, "selected_model_path", lambda: None)
    monkeypatch.setattr(panels, "selected_model_id", lambda: None)
    monkeypatch.setattr(panels, "install_recommended_model",
                        lambda mid, **kwargs: pytest.fail("no download in parity test"))
    panel = panels.ModelSetupPanel(context=context)
    qtbot.addWidget(panel)
    return panel


def selectable_in_panel(panel):
    """Models the user can actually choose and download, read from the widget."""
    chosen = set()
    for mid in setup.SETUP_MODEL_CATALOG:
        index = panel.model_choice.findData(mid)
        assert index >= 0, mid  # the list never hides a catalog model
        panel.model_choice.setCurrentIndex(index)
        button = panel.install_button
        if button.isEnabled() and button.text() == tr("setup.model.download_selected"):
            assert panel.fit.model(mid).fits
            chosen.add(mid)
        else:
            assert not panel.fit.model(mid).fits
    return chosen


@pytest.mark.parametrize("context", ["settings", "wizard"])
@pytest.mark.parametrize("path", list(PATHS))
@pytest.mark.parametrize("total,available,disk,expected", GRID, ids=IDS)
def test_panel_selectable_models_equal_usable_ram_fits(qtbot, monkeypatch, total, available, disk,
                                                       expected, path, context):
    assert not panels.ALLOW_UNFIT_OVERRIDE  # a locked model cannot be downloaded
    check = PATHS[path](total, available, disk)
    panel = make_panel(qtbot, monkeypatch, check, context)
    allowed = usable_set(total, available, disk)
    assert allowed == expected, (total, available, disk)
    assert selectable_in_panel(panel) == allowed
    assert panel.state == ("ready" if allowed else "no_fit")
    for mid, entry in setup.SETUP_MODEL_CATALOG.items():
        model = panel.fit.model(mid)
        if model.fits:
            assert model.block_reason is None
            continue
        cls, own = entry["model_class"], entry.get("ram_gb_min")
        if not model_budgets.installed_ram_fits(cls, total, own):
            assert model.block_reason == "ram_too_small", mid
        elif entry["approx_bytes"] + model_budgets.DISK_RESERVE_BYTES > disk:
            assert model.block_reason == "disk_too_small", mid
        else:
            # Locked only by current free RAM: a lock reason for 8B/27B, never for 4B.
            assert cls != model_budgets.CLASS_4B
            assert model.block_reason == "low_free_ram", mid


def test_grid_separates_the_shared_rule_from_other_rules():
    """The grid must catch a reintroduced own rule in either direction."""
    installed_only, free_ram_filter = 0, 0
    for total, available, disk, _ in GRID:
        allowed = usable_set(total, available, disk)
        by_installed = {mid for mid, e in setup.SETUP_MODEL_CATALOG.items()
                        if model_budgets.installed_ram_fits(e["model_class"], total, e["ram_gb_min"])
                        and e["approx_bytes"] + model_budgets.DISK_RESERVE_BYTES <= disk}
        # The old panel list filter (ram_gb_min + 2 <= free RAM).
        by_free = {mid for mid in by_installed
                   if setup.SETUP_MODEL_CATALOG[mid]["ram_gb_min"] + 2 <= available}
        installed_only += by_installed != allowed
        free_ram_filter += by_free != allowed
    assert installed_only >= 3 and free_ram_filter >= 3


@pytest.mark.parametrize("path", list(PATHS))
def test_panel_asks_model_budgets_usable_ram_fits_for_every_model(qtbot, monkeypatch, path):
    """The panel looks the rule up on guenther.model_budgets (single source)."""
    check = PATHS[path](31.6, 28.0, DISK_OK)
    calls = []

    def spy(model_class, *, total_gib, available_gib, own_gib=None):
        calls.append((model_class, total_gib, available_gib, own_gib))
        return False

    monkeypatch.setattr(model_budgets, "usable_ram_fits", spy)
    panel = make_panel(qtbot, monkeypatch, check, "settings")
    assert selectable_in_panel(panel) == set()
    assert panel.state == "no_fit"
    seen = {(c[0], c[3]) for c in calls}
    for entry in setup.SETUP_MODEL_CATALOG.values():
        assert (entry["model_class"], entry["ram_gb_min"]) in seen
    assert all(c[1] == 31.6 and c[2] == 28.0 for c in calls)


def test_adapter_uses_the_module_attribute_not_a_copy(monkeypatch):
    allowed_8b_only = {M8}
    monkeypatch.setattr(model_budgets, "usable_ram_fits",
                        lambda cls, **kw: cls == model_budgets.CLASS_8B)
    fit = model_fit.adapt_setup_recommendation(no_fits_recommendation(31.6, 28.0, DISK_OK))
    assert {m.model_id for m in fit.models if m.fits} == allowed_8b_only

"""Placement helpers for primary CTAs — bottom-right footers, not headers."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication, QHBoxLayout, QVBoxLayout

from desktop.design_system.polish import footer_actions_layout, svg_icon
from desktop.design_system.v2_chrome import SectionEditDrawer
from desktop.i18n import i18n, tr
from desktop.pages.dashboard import DashboardPage
from desktop.pages.profile import ProfilePage
from desktop.services import ConfigService
from desktop.services.schedule_service import ScheduleService


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def config_service(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    from desktop import paths as paths_mod

    def fake_dirs():
        root = tmp_path / "Karrierekrake"
        dirs = {
            "root": root,
            "config": root / "config",
            "data": root / "data",
            "logs": root / "logs",
            "browser_profile": root / "browser_profile",
            "browsers": root / "browsers",
            "cvs": root / "cvs",
            "cache": root / "cache",
            "cover_letters": root / "cover_letters",
        }
        for p in dirs.values():
            p.mkdir(parents=True, exist_ok=True)
        return dirs

    monkeypatch.setattr(paths_mod, "ensure_app_dirs", fake_dirs)
    monkeypatch.setattr("desktop.services.ensure_app_dirs", fake_dirs)
    return ConfigService()


def _button_is_after_stretch(button) -> bool:
    """True when some ancestor layout places a stretch before this button."""

    def scan(lay) -> bool:
        if lay is None:
            return False
        btn_index = None
        for i in range(lay.count()):
            item = lay.itemAt(i)
            if item is None:
                continue
            if item.widget() is button:
                btn_index = i
                break
            nested = item.layout()
            if nested is not None and scan(nested):
                return True
        if btn_index is None:
            return False
        for j in range(btn_index):
            prev = lay.itemAt(j)
            if prev is not None and prev.spacerItem() is not None:
                return True
        return False

    node = button.parentWidget()
    while node is not None:
        if scan(node.layout()):
            return True
        node = node.parentWidget()
    return False


def test_footer_actions_layout_puts_stretch_first(qapp):
    from PySide6.QtWidgets import QPushButton

    btn = QPushButton("OK")
    row = footer_actions_layout(btn)
    assert row.count() == 2
    assert row.itemAt(0).spacerItem() is not None
    assert row.itemAt(1).widget() is btn


def test_svg_icons_render(qapp):
    for kind in ("search", "save", "rocket", "close", "apply", "filter"):
        icon = svg_icon(kind)  # type: ignore[arg-type]
        assert not icon.isNull()


def test_dashboard_search_cta_not_in_header(qapp, config_service, monkeypatch):
    monkeypatch.setattr(ScheduleService, "sync_from_config", lambda self: (True, "ok"))
    i18n.set_language("de")
    page = DashboardPage(config_service)
    # Header strip must not contain the primary search button
    header_wrap = page.header.parentWidget()
    assert header_wrap is not None
    assert page.btn_search.parentWidget() is not header_wrap
    assert page.btn_search.objectName() == "PrimaryButton"
    assert page.btn_search.text() == tr("btn.find_jobs")
    assert not page.btn_search.icon().isNull()
    # Footer pattern: stretch before the CTA
    assert page._cta_footer.itemAt(0).spacerItem() is not None


def test_profile_import_not_in_title_row(qapp, config_service, monkeypatch):
    monkeypatch.setattr(ScheduleService, "sync_from_config", lambda self: (True, "ok"))
    i18n.set_language("de")
    page = ProfilePage(config_service)
    assert page.import_cv_btn.objectName() == "PrimaryButton"
    assert not page.import_cv_btn.icon().isNull()
    # Scan all HBoxLayouts under the page: none may place title + import together.
    def layouts_of(widget):
        stack = [widget]
        while stack:
            w = stack.pop()
            lay = w.layout()
            if lay is not None:
                yield lay
                for i in range(lay.count()):
                    item = lay.itemAt(i)
                    if item is None:
                        continue
                    child = item.widget()
                    if child is not None:
                        stack.append(child)

    for lay in layouts_of(page):
        if not isinstance(lay, QHBoxLayout):
            continue
        has_import = False
        has_title = False
        for i in range(lay.count()):
            item = lay.itemAt(i)
            if item is None:
                continue
            if item.widget() is page.import_cv_btn:
                has_import = True
            # title lives in a nested VBoxLayout item
            nested = item.layout()
            if nested is not None:
                for j in range(nested.count()):
                    nitem = nested.itemAt(j)
                    if nitem is not None and nitem.widget() is page.page_title:
                        has_title = True
        assert not (has_import and has_title)
    assert _button_is_after_stretch(page.import_cv_btn)


def test_section_edit_drawer_close_top_right_save_bottom(qapp):
    drawer = SectionEditDrawer("Edit")
    drawer.set_texts(title="Edit", save=tr("btn.save"), cancel=tr("btn.cancel"))
    assert drawer.close_btn is not None
    assert drawer.save_btn.objectName() == "PrimaryButton"
    assert not drawer.save_btn.icon().isNull()
    assert _button_is_after_stretch(drawer.save_btn)

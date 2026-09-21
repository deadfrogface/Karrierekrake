"""V2 shell / chrome smoke tests — nav IA + shared widgets."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication

from desktop.branding import COLOR_LIGHT_BG, COLOR_NAVY, COLOR_TEAL
from desktop.design_system.tokens import tokens_for_theme
from desktop.design_system.v2_chrome import KpiCard, PageHeader, StatusChip
from desktop.i18n import TRANSLATIONS


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_v2_brand_colors():
    assert COLOR_NAVY.lower() == "#132238"
    assert COLOR_TEAL.lower() == "#18a999"
    assert COLOR_LIGHT_BG.lower() == "#f8fafc"


def test_v2_radii_tokens():
    t = tokens_for_theme("light")
    assert t.radii.md == 8
    assert t.radii.xl == 12


def test_page_header(qapp):
    h = PageHeader("Übersicht", "Nächste Schritte")
    assert h.title.text() == "Übersicht"
    h.set_texts("Jobs", "")
    assert not h.subtitle.isVisible()


def test_status_chip_not_color_only(qapp):
    chip = StatusChip("Prüfung nötig", kind="warn")
    assert "Prüfung" in chip.text()
    assert ":" in chip.text() or "!" in chip.text()


def test_kpi_card_live_value(qapp):
    card = KpiCard("Passende Jobs", "0")
    card.set_value(12)
    assert card.value_label.text() == "12"


def test_i18n_v2_nav_keys():
    for key in ("nav.overview", "nav.inbox", "nav.help", "jobs.open_search_intent"):
        assert key in TRANSLATIONS["de"]
        assert key in TRANSLATIONS["en"]

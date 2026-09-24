"""Chips and cards pick up polish.py shadows without per-frame card reblurs."""

from __future__ import annotations

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QAbstractAnimation, QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QGraphicsDropShadowEffect, QHBoxLayout

from desktop.design_system.polish import polish_card
from desktop.design_system.primitives import KkStatusBadge
from desktop.design_system.v2_chrome import (
    ContentCard,
    KpiCard,
    ProfileSectionCard,
    StatusChip,
    TagChip,
)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _effect(widget) -> QGraphicsDropShadowEffect:
    effect = widget.graphicsEffect()
    assert isinstance(effect, QGraphicsDropShadowEffect)
    return effect


def test_chips_and_badges_get_light_shadow(qapp):
    chip = TagChip("Python", kind="wanted")
    status = StatusChip("Prüfung nötig", kind="warn")
    badge = KkStatusBadge("Bereit", kind="success")
    for widget in (chip, status, badge):
        effect = _effect(widget)
        assert 1.0 <= effect.blurRadius() <= 12.0
        assert effect.color().alpha() > 0
        assert widget.property("_kk_polish") is not None
    assert chip.cursor().shape() != Qt.CursorShape.PointingHandCursor
    assert "Prüfung" in status.text()


def test_cards_get_static_shadow_once(qapp):
    content = ContentCard()
    kpi = KpiCard("Jobs", "3")
    section = ProfileSectionCard("Skills")
    for card in (content, kpi, section):
        effect = _effect(card)
        assert effect.blurRadius() >= 18.0
        assert card.property("_kk_polish") == "card"
        again = polish_card(card)
        assert again is effect


def test_set_status_keeps_chip_shadow(qapp):
    chip = StatusChip("Offen", kind="info")
    effect = _effect(chip)
    chip.set_status("Prüfung", kind="warn")
    assert chip.graphicsEffect() is effect
    assert chip.objectName() == "BadgeWarn"


def test_chip_hover_darkens_and_lifts(qapp, monkeypatch):
    monkeypatch.setenv("KK_REDUCED_MOTION", "0")
    chip = TagChip("Python", kind="wanted")
    effect = _effect(chip)
    base_y = effect.yOffset()
    base_alpha = effect.color().alpha()
    QApplication.sendEvent(chip, QEvent(QEvent.Type.Enter))
    polish = chip.property("_kk_polish")
    assert polish.motions_enabled() is True
    assert polish._blur_anim is not None
    assert polish._blur_anim.state() == QAbstractAnimation.State.Running
    QTest.qWait(280)
    assert effect.yOffset() > base_y + 0.4
    assert effect.color().alpha() > base_alpha
    QApplication.sendEvent(chip, QEvent(QEvent.Type.Leave))
    QTest.qWait(280)
    assert abs(effect.yOffset() - base_y) < 0.8
    assert abs(effect.color().alpha() - base_alpha) <= 2


def test_reduced_motion_snaps_without_animation(qapp, monkeypatch):
    monkeypatch.setenv("KK_REDUCED_MOTION", "1")
    chip = StatusChip("Offen", kind="info")
    effect = _effect(chip)
    base_y = effect.yOffset()
    base_alpha = effect.color().alpha()
    QApplication.sendEvent(chip, QEvent(QEvent.Type.Enter))
    assert effect.yOffset() > base_y
    assert effect.color().alpha() > base_alpha
    polish = chip.property("_kk_polish")
    assert polish.motions_enabled() is False
    assert polish._blur_anim is None


def test_chip_inside_card_hovers_without_animating(qapp, monkeypatch):
    monkeypatch.setenv("KK_REDUCED_MOTION", "0")
    card = ContentCard()
    chip = TagChip("Remote", kind="wanted")
    card.body().addWidget(chip)
    effect = _effect(chip)
    base_y = effect.yOffset()
    base_alpha = effect.color().alpha()
    QApplication.sendEvent(chip, QEvent(QEvent.Type.Enter))
    assert effect.yOffset() > base_y
    assert effect.color().alpha() > base_alpha
    polish = chip.property("_kk_polish")
    assert polish.motions_enabled() is False
    assert polish._blur_anim is None


def test_many_chips_stay_responsive(qapp, monkeypatch):
    monkeypatch.setenv("KK_REDUCED_MOTION", "0")
    card = ContentCard()
    row = QHBoxLayout()
    card.body().addLayout(row)
    chips = []
    started = time.perf_counter()
    for i in range(48):
        kind = "wanted" if i % 2 == 0 else "neutral"
        chip = TagChip(f"Skill {i}", kind=kind)
        row.addWidget(chip)
        chips.append(chip)
    card.resize(1200, 180)
    card.show()
    app = QApplication.instance()
    assert app is not None
    app.processEvents()
    for _ in range(30):
        QApplication.sendEvent(chips[3], QEvent(QEvent.Type.Enter))
        QApplication.sendEvent(chips[3], QEvent(QEvent.Type.Leave))
        app.processEvents()
    elapsed = time.perf_counter() - started
    assert elapsed < 2.0
    assert isinstance(chips[0].graphicsEffect(), QGraphicsDropShadowEffect)
    card.hide()

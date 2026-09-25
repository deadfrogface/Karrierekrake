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
from desktop.theme import stylesheet_for


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _restore_stylesheet(qapp):
    previous = qapp.styleSheet()
    yield
    if qapp.styleSheet() != previous:
        qapp.setStyleSheet(previous)
        qapp.processEvents()


def _declaration_block(css: str, selector: str) -> str:
    start = 0
    while True:
        idx = css.find(selector, start)
        assert idx >= 0, selector
        after = idx + len(selector)
        if after < len(css) and css[after] == ":":
            start = after
            continue
        brace = css.find("{", idx)
        end = css.find("}", brace)
        assert brace >= 0 and end > brace
        return css[brace + 1 : end]


def _decl(block: str, name: str) -> str:
    for part in block.split(";"):
        piece = part.strip()
        if piece.startswith(name) and ":" in piece:
            return piece.split(":", 1)[1].strip().lower()
    return ""


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


def test_dark_stylesheet_chip_hover_differs_from_rest():
    dark = stylesheet_for("dark")
    light = stylesheet_for("light")
    assert "kk-theme: dark" in dark
    assert "QLabel#BadgeMuted:hover" not in light
    hover = _declaration_block(dark, "QLabel#BadgeMuted:hover")
    assert _decl(hover, "background") not in {"", "#243343"}
    assert _decl(hover, "border") not in {"", "1px solid transparent"}
    assert _decl(hover, "color")
    resting = _declaration_block(dark, "QLabel#BadgeMuted")
    assert "#243343" in resting
    assert _decl(hover, "background") != _decl(resting, "background")
    for selector in (
        "QLabel#BadgeOk:hover",
        "QLabel#BadgeWarn:hover",
        "QLabel#BadgeDanger:hover",
        "QLabel#BadgeInfo:hover",
    ):
        block = _declaration_block(dark, selector)
        assert _decl(block, "border")
        assert _decl(block, "background")


def test_dark_theme_chip_has_no_graphics_effect(qapp):
    qapp.setStyleSheet(stylesheet_for("dark"))
    chip = TagChip("Nur Suche – nie bewerben", kind="neutral")
    badge = KkStatusBadge("Bereit", kind="success")
    status = StatusChip("Offen", kind="info")
    for widget in (chip, badge, status):
        assert widget.graphicsEffect() is None
        assert widget.testAttribute(Qt.WidgetAttribute.WA_Hover)
    card = ContentCard()
    assert isinstance(card.graphicsEffect(), QGraphicsDropShadowEffect)


def test_theme_switch_restores_one_chip_shadow(qapp, monkeypatch):
    monkeypatch.setenv("KK_REDUCED_MOTION", "0")
    qapp.setStyleSheet(stylesheet_for("light"))
    qapp.processEvents()
    chip = TagChip("Python", kind="wanted")
    polish = chip.property("_kk_polish")
    light_effect = _effect(chip)
    assert light_effect.blurRadius() <= 12.0
    qapp.setStyleSheet(stylesheet_for("dark"))
    qapp.processEvents()
    assert chip.graphicsEffect() is None
    assert chip.property("_kk_polish") is polish
    qapp.setStyleSheet(stylesheet_for("light"))
    qapp.processEvents()
    restored = _effect(chip)
    assert restored is not light_effect
    assert chip.property("_kk_polish") is polish
    assert restored.blurRadius() <= 12.0
    base_y = restored.yOffset()
    base_alpha = restored.color().alpha()
    QApplication.sendEvent(chip, QEvent(QEvent.Type.Enter))
    assert polish.motions_enabled() is True
    assert polish._blur_anim is not None
    assert polish._blur_anim.state() == QAbstractAnimation.State.Running
    QTest.qWait(280)
    assert restored.yOffset() > base_y + 0.4
    assert restored.color().alpha() > base_alpha


def test_reduced_motion_dark_hover_does_not_animate(qapp, monkeypatch):
    monkeypatch.setenv("KK_REDUCED_MOTION", "1")
    qapp.setStyleSheet(stylesheet_for("dark"))
    chip = StatusChip("Offen", kind="info")
    assert chip.graphicsEffect() is None
    QApplication.sendEvent(chip, QEvent(QEvent.Type.Enter))
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

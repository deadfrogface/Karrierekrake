"""Screenshots der Modell-Setup-Karte mit ECHTEN Schriften (nur echter Windows-Rechner).

Zweck: Beleg für den OFFEN-Punkt aus PR144_COVERAGE_AND_GATES.md (L): CI läuft
``offscreen`` ohne echte Schrift; dieses Skript rendert dieselbe Karte wie
``tests/test_model_setup_lock_reason_visible.py::test_lock_reason_is_fully_painted_at_640``
(gleiche Konstruktion über ``_host``) auf einem echten Bildschirm.

Ablauf: einmal bei 100 % und einmal bei 200 % Windows-Anzeigeskalierung
(Einstellungen > Anzeige) ausführen, jeweils in einer interaktiven, angemeldeten
Desktop-Sitzung (nicht über Remote-Shell oder als Dienst). Keine Qt-Skalierung
per Umgebungsvariable; die tatsächliche Skalierung (devicePixelRatio) wird
gemessen und steht im Dateinamen (z. B. ``lock_de_wizard_ram_too_small_dpr2.0.png``).

Varianten: Fenster 640x560, DE und EN, Wizard und Einstellungen, alle
Sperrgründe (Sperrgrund-Zustand) sowie die Karte mit breiter Schrift (40 px).

Ergebnis im ``--out``-Ordner: PNGs und ``results_dpr<x>.json`` mit platformName,
aufgelöster Schriftfamilie (QFontInfo), logicalDpiX, devicePixelRatio,
Bildschirm-DPR und Prüfungen je Bild (alle Buttons/Labels im Fenster,
längstes Wort passt, Fensterbreite = 640, Mindestbreite der Karte <= 640).

Aufruf (aus dem Repo-Wurzelordner, mit Entwicklungs-Umgebung inkl. pytest):

    python scripts/capture_real_font_screenshots.py --out C:\\temp\\kk_shots
    python scripts/capture_real_font_screenshots.py --out C:\\temp\\kk_shots --expect-dpr 2.0

Exit-Codes: 0 ok, 1 Prüfung fehlgeschlagen, 2 keine echte Windows-Plattform
(``platformName != "windows"``) oder Qt-Skalierungs-Override gesetzt
(``QT_SCALE_FACTOR``, ``QT_SCREEN_SCALE_FACTORS``, ``QT_ENABLE_HIGHDPI_SCALING``),
3 gemessene DPR weicht von ``--expect-dpr`` ab.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REAL_PLATFORM = "windows"
SCALE_OVERRIDES = ("QT_SCALE_FACTOR", "QT_SCREEN_SCALE_FACTORS", "QT_ENABLE_HIGHDPI_SCALING")
LANGS = ("de", "en")
CONTEXTS = ("wizard", "settings")
WIDE_PX = 40
WINDOW_WIDTH = 640


def _refuse(reason: str) -> None:
    print(f"Abbruch: {reason}", file=sys.stderr)
    raise SystemExit(2)


def _refuse_environment(env) -> None:
    overrides = [name for name in SCALE_OVERRIDES if env.get(name, "") != ""]
    if overrides:
        _refuse(f"Qt-Skalierungs-Override gesetzt ({', '.join(overrides)}). "
                "Bitte entfernen und die Skalierung in den Windows-Anzeigeeinstellungen wählen.")
    platform = env.get("QT_QPA_PLATFORM", "")
    if platform and platform.split(":")[0].strip().lower() != REAL_PLATFORM:
        _refuse(f"QT_QPA_PLATFORM='{platform}' ist keine echte Windows-Plattform.")


def _refuse_platform(name: str) -> None:
    if name != REAL_PLATFORM:
        _refuse(f"Qt-Plattform '{name}' ist nicht '{REAL_PLATFORM}' (keine echten Windows-Schriften). "
                "Bitte in einer interaktiven Windows-Desktop-Sitzung starten.")


class _Bot:
    """Minimal stand-in for pytest-qt's qtbot (only what ``_host`` uses)."""

    def __init__(self):
        self.widgets = []

    def addWidget(self, widget):
        self.widgets.append(widget)

    def waitExposed(self, widget, timeout=5000):
        from PySide6.QtCore import QDeadlineTimer
        from PySide6.QtWidgets import QApplication
        deadline = QDeadlineTimer(timeout)
        while not widget.isVisible() and not deadline.hasExpired():
            QApplication.processEvents()
        QApplication.processEvents()

    def wait(self, ms):
        from PySide6.QtTest import QTest
        QTest.qWait(ms)


def _inside(widget, window) -> bool:
    from PySide6.QtCore import QPoint
    top_left = widget.mapTo(window, QPoint(0, 0))
    return (top_left.x() >= 0 and top_left.y() >= 0
            and top_left.x() + widget.width() <= window.width()
            and top_left.y() + widget.height() <= window.height())


def _checks(window, panel) -> dict:
    from PySide6.QtWidgets import QLabel, QPushButton
    outside = [w.text() for cls in (QPushButton, QLabel) for w in window.findChildren(cls)
               if w.isVisible() and w.text() and not _inside(w, window)]
    combo = panel.model_choice
    word_fits = True
    if combo.isVisible():
        word_fits = combo.longest_word_width() <= combo.text_rect(combo.width()).width()
    for button in (panel.install_button, panel.recheck_button, panel.cancel_button):
        if button.isVisible() and button.text():
            metrics = button.fontMetrics()
            longest = max(metrics.horizontalAdvance(w) for w in button.text().split())
            word_fits = word_fits and longest <= button.contentsRect().width()
    return {"all_buttons_labels_inside_window": not outside, "outside": outside,
            "longest_word_fits": bool(word_fits), "window_width": window.width(),
            "panel_min_width_le_640": panel.minimumSizeHint().width() <= 640}


def _font_info(app, widget) -> dict:
    from PySide6.QtGui import QFontInfo
    screen = widget.screen() or app.primaryScreen()
    return {"platformName": app.platformName(), "family": widget.font().family(),
            "resolved_family": QFontInfo(widget.font()).family(),
            "logicalDpiX": widget.logicalDpiX(), "devicePixelRatio": widget.devicePixelRatioF(),
            "screen_dpr": screen.devicePixelRatio() if screen else None}


def _save_capture(pixmap, path: Path) -> dict:
    """Save the grabbed window; report whether it was written and is not blank/single-colour."""
    if pixmap.isNull():
        return {"saved": False, "non_uniform": False}
    saved = bool(pixmap.save(str(path)))
    image = pixmap.toImage()
    non_uniform = False
    if not image.isNull() and image.width() > 0 and image.height() > 0:
        first = image.pixel(0, 0)
        non_uniform = any(image.pixel(x, y) != first
                          for y in range(image.height()) for x in range(image.width()))
    return {"saved": saved, "non_uniform": non_uniform}


def _capture(out: Path, check_platform=_refuse_platform) -> list[dict]:
    from _pytest.monkeypatch import MonkeyPatch
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv[:1])
    check_platform(app.platformName())
    from desktop.i18n import i18n
    from desktop.theme import apply_theme
    from tests import test_model_setup_lock_reason_visible as lock

    apply_theme(app, "light", high_contrast=False)
    base_sheet = app.styleSheet()
    results = []
    variants = [("lock", None), ("widefont", WIDE_PX)]
    for kind, px in variants:
        app.setStyleSheet(base_sheet + (f"\nQWidget {{ font-size: {px}px; }}\n" if px else ""))
        for lang in LANGS:
            i18n.set_language(lang)
            for context in CONTEXTS:
                for device in sorted(lock.DEVICES):
                    mp = MonkeyPatch()
                    bot = _Bot()
                    try:
                        with tempfile.TemporaryDirectory() as tmp:
                            cfg = lock.config_service.__wrapped__(Path(tmp), mp)
                            window, panel = lock._host(bot, mp, cfg, context, device)
                            if kind == "lock":
                                rows = lock._locked_rows(panel)
                                if rows:
                                    panel.model_choice.setCurrentIndex(rows[0][0])
                                    lock._fit_height(bot, window, panel)
                            info = _font_info(app, panel.model_choice)
                            name = f"{kind}_{lang}_{context}_{device}_dpr{info['devicePixelRatio']:.1f}.png"
                            capture = _save_capture(window.grab(), out / name)
                            entry = {"file": name, "kind": kind, "lang": lang,
                                     "context": context, "device": device, **info,
                                     "checks": {**_checks(window, panel), **capture}}
                            results.append(entry)
                            window.close()
                    finally:
                        mp.undo()
    return results


def _failed_files(results: list[dict]) -> list[str]:
    """Files whose checks failed (these make the exit code 1)."""
    return [r["file"] for r in results
            if not (r["checks"]["all_buttons_labels_inside_window"] and r["checks"]["longest_word_fits"]
                    and r["checks"]["window_width"] == WINDOW_WIDTH and r["checks"]["panel_min_width_le_640"]
                    and r["checks"].get("saved") is True and r["checks"].get("non_uniform") is True)]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="real_font_shots")
    parser.add_argument("--expect-dpr", type=float, default=None)
    args = parser.parse_args(argv)
    _refuse_environment(os.environ)
    out = Path(args.out).resolve()
    sys.path.insert(0, str(ROOT))
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv[:1])
    _refuse_platform(app.platformName())
    screen = app.primaryScreen()
    dpr = screen.devicePixelRatio() if screen else 1.0
    if args.expect_dpr is not None and abs(dpr - args.expect_dpr) > 0.01:
        print(f"Abbruch: gemessene DPR {dpr} != erwartet {args.expect_dpr}", file=sys.stderr)
        return 3
    out.mkdir(parents=True, exist_ok=True)
    results = _capture(out)
    (out / f"results_dpr{dpr:.1f}.json").write_text(json.dumps(results, indent=2, ensure_ascii=False),
                                                    encoding="utf-8")
    failed = _failed_files(results)
    print(f"{len(results)} Bilder in {out} (DPR {dpr}); Prüfungen fehlgeschlagen: {len(failed)}")
    for name in failed:
        print("  ", name)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

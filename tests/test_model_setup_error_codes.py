"""Model setup error text strictly by the downloader's ERROR CODE.

guenther.model_manager (#176) reports ``tls_failed`` when an SSL EOF occurs
with an empty .part file and ``connection_interrupted`` once bytes are saved
(resume case); install_recommended_model raises RuntimeError(<code>). The
panel picks its text from that code only, never from the exception type or
the diagnostic. Retry stays a deliberate user action.

Runs offscreen (QT_QPA_PLATFORM=offscreen); PySide6 is imported directly so a
missing Qt fails loudly instead of skipping.
"""
from __future__ import annotations

import ssl

import pytest
from PySide6.QtWidgets import QApplication

from desktop.i18n import TRANSLATIONS, tr
from desktop.widgets import model_setup_panel as panels
from guenther import model_manager
from guenther import setup_models as setup

SMALL = "qwen3.5-4b-gsq"
# 16 GB device: 4B fits (recommended, unverified peak), selected explicitly below.
TOTAL, FREE, CORES, DISK = 15.6, 12.0, 4, 100_000_000_000

TLS_DE = ("Die sichere Verbindung zum Download-Server kam nicht zustande. "
          "Prüfe deine Internetverbindung oder versuche es später erneut. "
          "In einem Firmennetz frage deine IT.")
INTERRUPTED_DE = ("Die Verbindung ist abgebrochen. "
                  "Prüfe deine Internetverbindung und versuche es erneut.")
# Advice to weaken security must never appear in the tls_failed text.
FORBIDDEN = ("deaktivier", "abschalt", "ausschalt", "zertifikat", "virenscanner", "virenschutz",
             "antivir", "firewall", "disable", "turn off", "switch off", "certificate", "virus")


def make_panel(qtbot, monkeypatch, install):
    check = setup.recommend_setup_model(total_gib=TOTAL, available_gib=FREE,
                                        physical_cores=CORES, free_disk_bytes=DISK)
    monkeypatch.setattr(panels, "inspect_setup_device", lambda: check)
    monkeypatch.setattr(panels, "selected_model_path", lambda: None)
    monkeypatch.setattr(panels, "selected_model_id", lambda: None)
    monkeypatch.setattr(panels, "install_recommended_model", install)
    panel = panels.ModelSetupPanel(context="settings")
    qtbot.addWidget(panel)
    panel.show()
    panel.activateWindow()
    panel.model_choice.setCurrentIndex(panel.model_choice.findData(SMALL))
    assert panel.install_button.isEnabled()
    return panel


def failing_install(make_error, calls):
    def install(mid, **kwargs):
        calls.append(mid)
        raise make_error()
    return install


def code_error(code, cause=None, diagnostic=None):
    """Like install_recommended_model: RuntimeError(<downloader code>)."""
    def make():
        error = RuntimeError(code)
        if diagnostic is not None:
            error.download_diagnostic = diagnostic
        if cause is not None:
            error.__cause__ = cause
        return error
    return make


def run_failure(qtbot, panel):
    panel.install_button.click()
    qtbot.waitUntil(lambda: panel.state == "error")


def assert_no_automatic_retry(qtbot, calls):
    qtbot.wait(300)  # give a (forbidden) automatic retry time to start
    assert calls == [SMALL]


# The diagnostic the downloader attaches to an SSL EOF with an empty .part file.
EOF_DIAGNOSTIC = "host=huggingface.co exception=SSLEOFError reason=UNEXPECTED_EOF_WHILE_READING"


@pytest.mark.parametrize("make_error", [
    code_error("tls_failed"),
    # SSL EOF details in the diagnostic / cause change nothing: the code decides.
    code_error("tls_failed", cause=ssl.SSLEOFError(8, "EOF occurred in violation of protocol"),
               diagnostic=EOF_DIAGNOSTIC),
], ids=["code-only", "ssl-eof-diagnostic"])
def test_code_tls_failed_shows_tls_text_and_deliberate_retry(qtbot, monkeypatch, make_error):
    calls = []
    panel = make_panel(qtbot, monkeypatch, failing_install(make_error, calls))
    run_failure(qtbot, panel)
    assert panel.status.text() == tr("setup.model.error.tls") == TLS_DE
    assert panel.status.text() != tr("setup.model.error.interrupted")
    assert panel.error_code.isVisible() and panel.error_code.text() == "Fehlercode: tls_failed"
    assert panel.install_button.text() == "Erneut versuchen"
    assert panel.install_button.isEnabled()
    qtbot.waitUntil(lambda: QApplication.focusWidget() is panel.install_button)
    assert_no_automatic_retry(qtbot, calls)
    panel.install_button.click()  # retry only on an explicit click
    qtbot.waitUntil(lambda: len(calls) == 2)
    qtbot.waitUntil(lambda: not panel.busy)


@pytest.mark.parametrize("make_error", [
    code_error("connection_interrupted"),
    # Resume case: bytes already saved; an SSL EOF as cause changes nothing.
    code_error("connection_interrupted", cause=ssl.SSLEOFError(8, "EOF occurred in violation of protocol"),
               diagnostic=EOF_DIAGNOSTIC),
], ids=["code-only", "ssl-eof-diagnostic"])
def test_code_connection_interrupted_shows_interrupted_text_with_retry(qtbot, monkeypatch, make_error):
    calls = []
    panel = make_panel(qtbot, monkeypatch, failing_install(make_error, calls))
    run_failure(qtbot, panel)
    assert panel.status.text() == tr("setup.model.error.interrupted") == INTERRUPTED_DE
    assert panel.status.text() != tr("setup.model.error.tls")
    assert panel.error_code.isVisible() and panel.error_code.text() == "Fehlercode: connection_interrupted"
    assert panel.install_button.text() == "Erneut versuchen"
    assert panel.install_button.accessibleName() == tr("setup.model.retry_a11y")
    qtbot.waitUntil(lambda: QApplication.focusWidget() is panel.install_button)
    assert_no_automatic_retry(qtbot, calls)
    panel.install_button.click()
    qtbot.waitUntil(lambda: len(calls) == 2)
    qtbot.waitUntil(lambda: not panel.busy)


def test_raw_ssl_errors_follow_the_downloaders_code_function():
    """Errors that reach the UI unwrapped are classified by download_failure_code only."""
    eof = ssl.SSLEOFError(8, "EOF occurred in violation of protocol")
    assert panels.model_failure_code(eof) == model_manager.download_failure_code(eof) == "tls_failed"
    try:
        raise model_manager.DownloadInterruptedError("connection_interrupted") from eof
    except model_manager.DownloadInterruptedError as wrapped:
        assert panels.model_failure_code(wrapped) == "connection_interrupted"
    assert panels.model_failure_message("tls_failed") == tr("setup.model.error.tls")
    assert panels.model_failure_message("connection_interrupted") == tr("setup.model.error.interrupted")
    # No UI-only TLS code exists any more.
    assert "tls_eof" not in panels._FAILURE_KEYS
    assert not hasattr(panels, "_is_tls_eof")


@pytest.mark.parametrize("lang", sorted(TRANSLATIONS))
def test_tls_text_never_advises_weakening_security(lang):
    text = TRANSLATIONS[lang]["setup.model.error.tls"]
    for word in FORBIDDEN:
        assert word not in text.lower(), (lang, word, text)
    assert text != TRANSLATIONS[lang]["setup.model.error.interrupted"]


def test_tls_text_languages_present():
    assert {"de", "en"} <= set(TRANSLATIONS)
    assert TRANSLATIONS["en"]["setup.model.error.tls"] == (
        "The secure connection to the download server could not be established. "
        "Check your internet connection or try again later. On a company network, ask your IT.")

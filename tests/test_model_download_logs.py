"""The setup failure reaches the logs viewer with actionable details."""
from types import SimpleNamespace
import logging

import pytest

from desktop.pages.logs import LogsPage, _humanize_line
from desktop.i18n import tr
from desktop.widgets import model_setup_panel as panels
from guenther import setup_models as setup


@pytest.mark.parametrize('stamp', ['00:48:05', '2026-10-12 00:48:05'])
def test_actual_logger_format_is_humanized(stamp):
    line = f'{stamp} ERROR model_setup_failed model_id=qwen3-8b-gsq reason=http_403'
    summary, details = _humanize_line(line)
    assert summary == '00:48:05 · ' + tr('logs.event.model_failed')
    assert details == line


def test_logs_select_latest_failure_and_show_details_immediately(qtbot, tmp_path):
    failure = '00:48:05 ERROR model_setup_failed model_id=qwen3-8b-gsq reason=http_403'
    (tmp_path / 'karrierekrake.log').write_text(
        failure + '\n00:48:06 INFO home_resolution complete\n', encoding='utf-8')
    config = SimpleNamespace(root=tmp_path, settings=SimpleNamespace(logs_dir=str(tmp_path)))
    page = LogsPage(SimpleNamespace(load=lambda: config))
    qtbot.addWidget(page)
    page.refresh()
    assert page.events.currentRow() == 0
    assert page.tech.toPlainText() == failure


def test_failed_setup_button_logs_specific_error(qtbot, monkeypatch, caplog):
    recommendation = setup.recommend_setup_model(total_gib=24, available_gib=18,
                                                 physical_cores=6, free_disk_bytes=100_000_000_000)
    monkeypatch.setattr(panels, 'inspect_setup_device', lambda: recommendation)
    monkeypatch.setattr(panels, 'selected_model_path', lambda: None)
    def fail(*args, **kwargs):
        raise RuntimeError('http_403')
    monkeypatch.setattr(panels, 'install_recommended_model', fail)
    panel = panels.ModelSetupPanel()
    qtbot.addWidget(panel)
    # PR144 setup thresholds: 8B is an alternative now; pick it explicitly.
    panel.model_choice.setCurrentIndex(panel.model_choice.findData('qwen3-8b-gsq'))
    with caplog.at_level(logging.ERROR, logger='karrierekrake'):
        panel.install_button.click()
        qtbot.waitUntil(lambda: not panel.busy)
    assert 'HTTP 403' in panel.status.text()
    assert 'model_setup_failed model_id=qwen3-8b-gsq' in caplog.text
    assert 'HTTP 403' in caplog.text
    assert panel.install_button.isEnabled()

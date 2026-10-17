"""Actual CV-import diagnostics retain counters, never identifying fields."""
import logging
from core.cv_docpick_import import _log_import_summary


def test_import_summary_does_not_log_cv_identity_or_filename(caplog):
    parsed = {'personal': {'first_name': 'SYNTHETIC_PRIVATE_FIRST',
                           'last_name': 'SYNTHETIC_PRIVATE_LAST'},
              'emails': ['synthetic-private@example.invalid'],
              'phones': ['SYNTHETIC_PRIVATE_PHONE'],
              'source_path': '/private/SYNTHETIC_PRIVATE_FILENAME.pdf'}
    with caplog.at_level(logging.INFO, logger='core.cv_docpick_import'):
        _log_import_summary(parsed, source_chars=1234, peak_rss_mb=1200.5)
    assert 'chars=1234' in caplog.text
    assert 'name_present=True' in caplog.text
    assert 'contact_present=True' in caplog.text
    assert 'SYNTHETIC_PRIVATE' not in caplog.text
    assert 'example.invalid' not in caplog.text
    assert all(not isinstance(arg, (dict, list)) for record in caplog.records for arg in record.args)


def test_empty_import_diagnostics_use_presence_flags(caplog):
    with caplog.at_level(logging.INFO, logger='core.cv_docpick_import'):
        _log_import_summary({}, source_chars=0, peak_rss_mb=1.0)
    assert 'name_present=False' in caplog.text
    assert 'contact_present=False' in caplog.text


def test_model_copy_diagnostics_omit_user_directory(tmp_path, monkeypatch, caplog):
    from core import cv_llm_runtime as runtime
    from guenther import model_manager
    destination = tmp_path / 'SYNTHETIC_PRIVATE_USER'
    monkeypatch.setattr(model_manager, 'default_models_dir', lambda: destination)
    source = tmp_path / 'SYNTHETIC_PRIVATE_SOURCE.gguf'
    source.write_bytes(b'synthetic model copy fixture')
    with caplog.at_level(logging.INFO, logger='core.cv_llm_runtime'):
        assert runtime.materialize_bundled_model_to_appdata(source).is_file()
    assert 'cv_model_materialized bytes=' in caplog.text
    assert 'SYNTHETIC_PRIVATE' not in caplog.text
    assert str(tmp_path) not in caplog.text


def test_missing_model_override_diagnostics_omit_private_filename(monkeypatch, caplog):
    from core import cv_llm_runtime as runtime
    monkeypatch.setenv('KARRIEREKRAKE_CV_LLM_MODEL', '/absent/SYNTHETIC_PRIVATE_MODEL.gguf')
    with caplog.at_level(logging.WARNING, logger='core.cv_llm_runtime'):
        runtime.resolve_cv_model_path()
    assert 'cv_model_env_missing' in caplog.text
    assert 'SYNTHETIC_PRIVATE_MODEL' not in caplog.text

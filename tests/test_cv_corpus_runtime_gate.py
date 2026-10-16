"""Production corpus checks must run without optional Docling or report failure."""
import sys
import pytest
from scripts import run_cv_corpus as corpus
from scripts import run_cv_sollwerte_corpus as soll


def test_missing_runtime_is_failure_not_successful_skip(monkeypatch):
    # Optional Docling is absent in the shipped default text backend too.
    monkeypatch.setitem(sys.modules, 'docling', None)
    from core import cv_parser
    calls = []
    def missing_model(path, *args, **kwargs):
        calls.append(path.name)
        raise RuntimeError('synthetic_model_missing')
    monkeypatch.setattr(cv_parser, 'import_cv', missing_model)
    rows, ok = corpus.run_corpus()
    assert calls and not ok
    assert all(not row['pass'] and row['cv'] != '__SKIP__' for row in rows)
    calls.clear()
    report = soll.run()
    assert calls and not report['ok']
    assert report['total'] > 0 and report['failed'] > 0
    assert not report.get('skipped')

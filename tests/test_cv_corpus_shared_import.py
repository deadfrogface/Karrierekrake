"""Only duplicate setup is reused; evaluators never share mutable data."""
import pytest


def test_same_file_reuses_import_but_copies_results(cv_corpus_importer, tmp_path, monkeypatch):
    from core import cv_parser
    calls = []
    def parse(path):
        calls.append(path)
        return {'synthetic': {'values':[1]}}
    monkeypatch.setattr(cv_parser, 'import_cv', parse)
    a, b = tmp_path / 'a.pdf', tmp_path / 'b.pdf'
    a.write_bytes(b'shared-import-fixture-original')
    b.write_bytes(a.read_bytes())
    first = cv_corpus_importer(a)
    first['synthetic']['values'].append(2)
    assert cv_corpus_importer(a) == {'synthetic':{'values':[1]}}
    assert len(calls) == 1
    cv_corpus_importer(b)
    assert len(calls) == 2  # Preserve filename/path-dependent document metadata.
    b.write_bytes(b'shared-import-fixture-modified')
    cv_corpus_importer(b)
    assert len(calls) == 3


def test_failed_import_is_never_reused_as_result(cv_corpus_importer, tmp_path, monkeypatch):
    from core import cv_parser
    calls = []
    def fail(path):
        calls.append(path)
        raise RuntimeError('synthetic failure')
    monkeypatch.setattr(cv_parser, 'import_cv', fail)
    path = tmp_path / 'error.pdf'
    path.write_bytes(b'shared-import-fixture-error')
    for _ in range(2):
        with pytest.raises(RuntimeError, match='synthetic failure'):
            cv_corpus_importer(path)
    assert len(calls) == 2

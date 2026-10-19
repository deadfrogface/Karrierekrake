"""Shared pytest fixtures for Karrierekrake tests."""

from __future__ import annotations

import pytest

# The JUnit ``nodeid`` hook for the shard gate is in the repo-root conftest.py.


class _MemoryKeyringBackend:
    """Process-local keyring so Linux CI can exercise OS-credential paths."""

    priority = 1

    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    def set_password(self, service: str, account: str, password: str) -> None:
        self._data[f"{service}:{account}"] = password

    def get_password(self, service: str, account: str) -> str | None:
        return self._data.get(f"{service}:{account}")

    def delete_password(self, service: str, account: str) -> None:
        self._data.pop(f"{service}:{account}", None)


@pytest.fixture(autouse=True)
def _reset_geo_index_around_each_test():
    """Drop the shared geo-index loader state around every test.

    ``MainWindow`` binds the UI thread and registers a ready callback in
    ``core.geo_resolve``. The first-run wizard test builds that window, so
    the process-wide index, callback list and preload thread must not leak
    into the next test.
    """
    from core.geo_resolve import reset_pgeocode_index_for_tests

    reset_pgeocode_index_for_tests()
    yield
    reset_pgeocode_index_for_tests()


@pytest.fixture(autouse=True)
def _restore_i18n_language():
    """Restore the UI language (and Qt translator) a test switched.

    ``desktop.i18n.i18n`` is process-wide; a test calling ``set_language('en')``
    would otherwise leak English into every later test. Never creates a
    QApplication; the Qt translator is only reinstalled if one exists.
    """
    try:
        from desktop.i18n import i18n
    except ImportError:
        yield
        return
    previous = i18n.language
    yield
    if i18n.language == previous:
        return
    i18n.set_language(previous)
    try:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
    except ImportError:
        app = None
    if app is not None:
        from desktop.i18n import install_qt_translator

        install_qt_translator(app, previous)


@pytest.fixture(autouse=True)
def _default_memory_keyring(monkeypatch: pytest.MonkeyPatch):
    """Prefer in-memory keyring unless a test replaces ``secure_tokens._keyring``."""
    try:
        from integrations import secure_tokens
    except Exception:
        yield
        return
    backend = _MemoryKeyringBackend()
    monkeypatch.setattr(secure_tokens, "_keyring", lambda: backend)
    yield backend


@pytest.fixture(autouse=True)
def _offline_qt_runtime(request, monkeypatch):
    """UI smoke must not download routing maps for every temporary window.

    Routing installation/lifecycle has its own tests. Qt UI tests exercise the
    real window, providers and workers, but do not provision Java/map data.
    """
    if "qapp" in request.fixturenames:
        from desktop.main_window import MainWindow

        monkeypatch.setattr(MainWindow, "_start_brouter_runtime", lambda self: None)


@pytest.fixture(scope="session")
def cv_corpus_importer():
    """Parse each identical synthetic PDF once; retain every evaluator/assertion.

    Caches raw parsed data, never pass/fail judgments. Copies isolate evaluators;
    failed imports are not cached. Production restart/load checks stay separate.
    """
    import copy
    import hashlib
    from pathlib import Path
    cache = {}
    def parse(path, **options):
        import json
        path = Path(path)
        # import_cv defaults guenther_enabled to False; equivalent calls share work.
        options = {k: v for k, v in options.items()
                   if not (k == "guenther_enabled" and v is False)}
        key = (str(path.resolve()), hashlib.sha256(path.read_bytes()).hexdigest(),
               json.dumps(options, sort_keys=True, default=str))
        if key not in cache:
            from core.cv_parser import import_cv
            cache[key] = import_cv(path, **options)
        return copy.deepcopy(cache[key])
    return parse


@pytest.fixture
def native_recovery_proofs():
    """Complete recovery evidence for isolated release-publisher fixtures."""
    def write(folder, identity):
        import json
        (folder / 'backup-restore.json').write_text(json.dumps({
            'ok': True, 'native_image': True, 'restored_database_path_confirmed': True,
            'synthetic_marker_preserved': True, 'executable_sha256': 'd' * 64,
            'steps': {key: {'exit_code': 0} for key in
                      ('initial_smoke', 'create', 'verify', 'restore', 'restored_smoke')}}))
        (folder / 'upgrade.json').write_text(json.dumps({
            'ok': True, 'result': 'success', 'startup_acknowledged': True,
            'candidate_installed': True, 'synthetic_marker_preserved': True,
            'candidate': identity,
            'baseline': {**identity, 'commit': 'f' * 40, 'sequence': identity['sequence'] - 1},
            'executable_sha256': 'd' * 64}))
        (folder / 'gui-startup.json').write_text(json.dumps({
            'ok': True, 'startup_acknowledged': True, 'identity': identity,
            'executable_sha256': 'd' * 64}))
    return write

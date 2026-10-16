"""Real SQLite cache records, inert pickle values; no executable payloads."""
import pickle

import pytest

from core.security.diskcache_guard import guard_diskcache, UnsafeCacheSerializationError


def test_pickled_keys_and_values_rejected_native_values_work(tmp_path, monkeypatch):
    import diskcache
    import diskcache.core as core
    original = core.pickle
    monkeypatch.setattr(core, "pickle", pickle)
    # Seed inert object data using the original codec, as an older install could.
    with diskcache.Cache(str(tmp_path)) as cache:
        cache['object'] = {'synthetic': [1, 2]}
        cache[('tuple',)] = 'value'
        cache['plain'] = b'bytes'
    guard_diskcache()
    assert pickle.loads(pickle.dumps({'normal': True})) == {'normal': True}
    with diskcache.Cache(str(tmp_path)) as cache:
        assert cache['plain'] == b'bytes'
        cache['number'] = 42
        assert cache['number'] == 42
        with pytest.raises(UnsafeCacheSerializationError):
            cache['object']
        with pytest.raises(UnsafeCacheSerializationError):
            list(cache.iterkeys())
        with pytest.raises(UnsafeCacheSerializationError):
            cache['new-object'] = {'x': 1}
        with pytest.raises(UnsafeCacheSerializationError):
            cache[('tuple',)]
    protected = core.pickle
    guard_diskcache()
    assert core.pickle is protected


def test_all_codec_attributes_fail_closed():
    from core.security.diskcache_guard import _DisabledPickle
    for name in ('load', 'loads', 'Unpickler', 'dumps', 'Pickler'):
        with pytest.raises(UnsafeCacheSerializationError):
            getattr(_DisabledPickle(), name)

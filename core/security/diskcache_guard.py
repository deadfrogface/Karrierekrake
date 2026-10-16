"""Disable diskcache's pickle codec in every application LLM process.

The app does not use LlamaDiskCache. Native scalar/byte diskcache values remain
supported, but serialized Python objects are rejected before deserialization.
This is a downstream mitigation for CVE-2025-69872, not an upstream version fix.
"""
from __future__ import annotations


class UnsafeCacheSerializationError(ValueError):
    pass


class _DisabledPickle:
    def __getattr__(self, name):
        raise UnsafeCacheSerializationError('diskcache_python_serialization_disabled')


def guard_diskcache():
    try:
        import diskcache.core as core
    except ModuleNotFoundError as exc:
        if exc.name == 'diskcache':
            return
        raise
    # Replace only this dependency's codec reference, never the stdlib module.
    # No loads/load/Unpickler fallback is exposed; writes also fail explicitly.
    if not isinstance(core.pickle, _DisabledPickle):
        core.pickle = _DisabledPickle()

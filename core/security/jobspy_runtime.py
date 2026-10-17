"""Load the pinned search transport offline and reject legacy frozen Go code."""
from __future__ import annotations


def verify_jobspy_runtime() -> dict[str, str]:
    from contextlib import closing
    from importlib import metadata, util
    import sys
    from curl_cffi import Curl
    from jobspy import scrape_jobs

    if metadata.version('python-jobspy') != '1.3.0' or metadata.version('curl_cffi') != '0.16.3':
        raise RuntimeError('jobspy_transport_version_mismatch')
    if not callable(scrape_jobs):
        raise RuntimeError('jobspy_search_entrypoint_missing')
    if getattr(sys, 'frozen', False) and util.find_spec('tls_client') is not None:
        raise RuntimeError('jobspy_legacy_go_transport_present')
    with closing(Curl()) as handle:
        version = handle.version().decode('ascii')
    if not version.startswith('libcurl/8.21.0-IMPERSONATE ') or ' BoringSSL ' not in version:
        raise RuntimeError('jobspy_native_transport_mismatch')
    return {'jobspy': '1.3.0', 'curl_cffi': '0.16.3', 'native': version}

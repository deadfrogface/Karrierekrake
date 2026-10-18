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


def selfcheck_search_dependencies() -> dict[str, object]:
    """Offline dependency self-check for the packaged search stack (no request is sent).

    Imports the scrapers Karrierekrake actually uses (Indeed, LinkedIn), builds their
    sessions without any I/O, resolves versions of the HTTP stack and the CA bundle and
    loads the native libcurl. ``tls_client`` must be absent in a frozen build; JobSpy
    1.3.0 has no code path that imports it (Indeed/LinkedIn use ``requests``,
    ``curl_cffi`` is imported by ``jobspy.util``).
    """
    from importlib import metadata, util
    import os
    import sys

    result: dict[str, object] = {'frozen': bool(getattr(sys, 'frozen', False))}
    transport = verify_jobspy_runtime()
    result.update(transport)
    from jobspy.indeed import Indeed
    from jobspy.linkedin import LinkedIn
    import certifi
    import requests

    for name, cls in (('indeed', Indeed), ('linkedin', LinkedIn)):
        scraper = cls()
        session = getattr(scraper, 'session', None)
        if not isinstance(session, requests.Session):
            raise RuntimeError(f'jobspy_{name}_session_unexpected')
        session.close()
        result[f'scraper_{name}'] = 'ok'
    ca = certifi.where()
    if not os.path.isfile(ca) or os.path.getsize(ca) < 1024:
        raise RuntimeError('ca_bundle_missing')
    result['ca_bundle'] = 'ok'
    # Informational only: the frozen package does not necessarily carry dist-info
    # for these, and some (e.g. pandas, pydantic) may be missing entirely. Prefer the
    # module attribute, fall back to dist-info, and record "unavailable" when the
    # module cannot be imported; reporting never fails the self-check.
    for dist, module in (('requests', 'requests'), ('urllib3', 'urllib3'),
                         ('certifi', 'certifi'), ('markdownify', 'markdownify'),
                         ('beautifulsoup4', 'bs4'), ('pandas', 'pandas'),
                         ('pydantic', 'pydantic')):
        try:
            loaded = sys.modules.get(module) or __import__(module)
        except Exception:  # noqa: BLE001 - informational, any import failure is data
            result[f'version_{dist}'] = 'unavailable'
            continue
        version = getattr(loaded, '__version__', None)
        if not version:
            try:
                version = metadata.version(dist)
            except metadata.PackageNotFoundError:
                version = 'unknown'
        result[f'version_{dist}'] = str(version)
    present = util.find_spec('tls_client') is not None
    result['tls_client'] = 'present' if present else 'absent'
    if present and result['frozen']:
        raise RuntimeError('jobspy_legacy_go_transport_present')
    result['ok'] = True
    return result


def _write_atomic(out, text: str) -> None:
    """Write via a ``.tmp`` sibling and ``os.replace`` so a poller never reads a partial file."""
    import os
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + '.tmp')
    try:
        with open(tmp, 'w', encoding='utf-8') as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, out)
    finally:
        if tmp.exists():
            tmp.unlink()


def selfcheck_main(argv: list[str]) -> int:
    """``--selfcheck-deps [OUT.json]``: print and optionally write the self-check JSON."""
    import json
    from pathlib import Path
    out = Path(argv[0]) if argv and not argv[0].startswith('--') else None
    try:
        payload: dict[str, object] = selfcheck_search_dependencies()
        code = 0
    except Exception as exc:  # noqa: BLE001 - report any import/native failure as data
        payload = {'ok': False, 'error_type': type(exc).__name__, 'error': str(exc)[:300]}
        code = 1
    text = json.dumps(payload, indent=2, sort_keys=True)
    if out is not None:
        _write_atomic(out, text)
    try:
        print(text, flush=True)
    except Exception:  # windowed EXE may have no stdout
        pass
    return code

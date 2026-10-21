"""Offline self-check of the packaged search stack: our own Indeed / LinkedIn clients on ``requests``."""
from __future__ import annotations


def verify_search_runtime() -> dict[str, str]:
    """The HTTP stack of the search clients is loadable; no foreign transport library is part of the package."""
    from importlib import util
    import sys

    import bs4  # noqa: F401 - LinkedIn result cards
    import requests

    from search import indeed_api, linkedin_api  # noqa: F401 - our own clients
    frozen = bool(getattr(sys, 'frozen', False))
    for legacy in ('jobspy', 'curl_cffi', 'tls_client'):
        if frozen and util.find_spec(legacy) is not None:
            raise RuntimeError(f'search_legacy_transport_present:{legacy}')
    return {'transport': 'requests', 'requests': requests.__version__}


def selfcheck_search_dependencies() -> dict[str, object]:
    """Offline dependency self-check for the packaged search stack (no request is sent).

    Imports the two search clients, builds a session without any I/O, resolves versions of the HTTP stack and the
    CA bundle. ``jobspy``, ``curl_cffi`` and ``tls_client`` must be absent in a frozen build.
    """
    from importlib import metadata, util
    import os
    import sys

    result: dict[str, object] = {'frozen': bool(getattr(sys, 'frozen', False))}
    result.update(verify_search_runtime())
    import certifi
    import requests

    session = requests.Session()
    session.close()
    result['client_indeed'] = result['client_linkedin'] = 'ok'
    ca = certifi.where()
    if not os.path.isfile(ca) or os.path.getsize(ca) < 1024:
        raise RuntimeError('ca_bundle_missing')
    result['ca_bundle'] = 'ok'
    # Informational only: the frozen package does not necessarily carry dist-info for these, and some
    # (e.g. pandas, pydantic) may be missing entirely. Reporting never fails the self-check.
    for dist, module in (('requests', 'requests'), ('urllib3', 'urllib3'), ('certifi', 'certifi'),
                         ('beautifulsoup4', 'bs4'), ('pandas', 'pandas'), ('pydantic', 'pydantic')):
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
    for legacy in ('jobspy', 'curl_cffi', 'tls_client'):
        result[legacy] = 'present' if util.find_spec(legacy) is not None else 'absent'
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

"""Offline beta acceptance validation and deterministic summary reporting."""
from __future__ import annotations

from collections import Counter

ALLOWED_TESTS = frozenset("B%02d" % i for i in range(1, 11))
ALLOWED_STATUSES = frozenset(("pass", "fail", "blocked", "not_tested"))


def validate(row):
    if not isinstance(row, dict):
        raise ValueError("invalid_row")
    if row.get("test_id") not in ALLOWED_TESTS:
        raise ValueError("unknown_test")
    if row.get("status") not in ALLOWED_STATUSES:
        raise ValueError("unknown_status")
    return {"test_id": row["test_id"], "status": row["status"]}


def summarize(rows):
    """Never infer beta approval from omitted or untested cases."""
    validated = [validate(row) for row in rows]
    ids = [row["test_id"] for row in validated]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate_test")
    counts = Counter(row["status"] for row in validated)
    missing = sorted(ALLOWED_TESTS.difference(ids))
    return {
        "total": len(ALLOWED_TESTS),
        "passed": counts["pass"],
        "failed": counts["fail"],
        "blocked": counts["blocked"],
        "not_tested": counts["not_tested"] + len(missing),
        "missing_test_ids": missing,
        "approved": not missing and counts["pass"] == len(ALLOWED_TESTS),
    }


EXTENDED_TESTS = frozenset('X%02d' % i for i in range(1, 13))


def session_template():
    """Blank evidence is explicitly untested, never an approval."""
    return {'schema': 2, 'commit': '', 'package_sha256': '', 'platform': '',
            'os_version': '', 'architecture': '', 'device_alias': '', 'test_date': '',
            'results': [{'test_id': identifier, 'status': 'not_tested'}
                        for identifier in sorted(ALLOWED_TESTS | EXTENDED_TESTS)]}


def summarize_session(session):
    import re
    from datetime import date
    if not isinstance(session, dict) or session.get('schema') != 2:
        raise ValueError('invalid_session')
    for key, pattern in [('commit', r'[0-9a-f]{40}'), ('package_sha256', r'[0-9a-f]{64}'),
                         ('device_alias', r'[A-Za-z0-9_-]{1,40}')]:
        if not isinstance(session.get(key), str) or not re.fullmatch(pattern, session[key]):
            raise ValueError('missing_or_invalid_' + key)
    if session.get('platform') not in {'windows', 'macos', 'linux'}:
        raise ValueError('invalid_platform')
    if session.get('architecture') not in {'x86_64', 'arm64'}:
        raise ValueError('invalid_architecture')
    version = session.get('os_version')
    if not isinstance(version, str) or not version.strip() or len(version) > 100:
        raise ValueError('invalid_os_version')
    date.fromisoformat(session['test_date'])
    results = session.get('results')
    if not isinstance(results, list):
        raise ValueError('invalid_results')
    expected = ALLOWED_TESTS | EXTENDED_TESTS
    seen, counts = set(), Counter()
    for row in results:
        if not isinstance(row, dict) or row.get('test_id') not in expected or row.get('status') not in ALLOWED_STATUSES:
            raise ValueError('invalid_result')
        if row['test_id'] in seen:
            raise ValueError('duplicate_test')
        seen.add(row['test_id']); counts[row['status']] += 1
    missing = sorted(expected - seen)
    return {'schema': 2, 'commit': session['commit'], 'package_sha256': session['package_sha256'],
            'platform': session['platform'], 'architecture': session['architecture'],
            'total': len(expected), 'passed': counts['pass'], 'failed': counts['fail'],
            'blocked': counts['blocked'], 'not_tested': counts['not_tested'] + len(missing),
            'missing_test_ids': missing, 'approved': not missing and counts['pass'] == len(expected)}


if __name__ == '__main__':
    import argparse
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('session', nargs='?', type=Path)
    parser.add_argument('--template', action='store_true')
    args = parser.parse_args()
    if args.template:
        print(json.dumps(session_template(), indent=2))
    elif args.session:
        print(json.dumps(summarize_session(json.loads(args.session.read_text(encoding='utf-8'))), indent=2))
    else:
        parser.error('Provide a session JSON or --template')

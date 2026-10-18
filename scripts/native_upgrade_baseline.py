"""Find an unexpired successful native-build baseline from this repository.

The candidate build's update sequence is ``github.run_id``. A baseline from a
run with an equal or higher run id would therefore look like a downgrade (or a
replay) and is correctly rejected by the production update validator, so only
runs with a strictly lower run id than the current one are eligible. If no such
older baseline exists the step fails visibly instead of skipping the upgrade.
"""
from __future__ import annotations

import json
import os
import re
import sys
from urllib.request import Request, urlopen

REPOSITORY = 'deadfrogface/Karrierekrake'


def current_run_id(env):
    """Return GITHUB_RUN_ID as a positive int; fail loudly instead of guessing."""
    value = env.get('GITHUB_RUN_ID')
    if not isinstance(value, str) or not re.fullmatch(r'[1-9][0-9]*', value):
        raise ValueError('native_upgrade_current_run_id_invalid')
    return int(value)


def select_baseline(runs, artifacts, *, current_sha, current_run_id, target, log=print):
    if isinstance(current_run_id, bool) or not isinstance(current_run_id, int) or current_run_id <= 0:
        raise ValueError('native_upgrade_current_run_id_invalid')
    log('native_upgrade_current_run=' + str(current_run_id))
    eligible, skipped_newer = [], []
    for run in runs:
        if (run.get('head_sha') == current_sha or run.get('conclusion') != 'success'
                or run.get('head_repository', {}).get('full_name') != REPOSITORY):
            continue
        identity = run.get('id')
        if isinstance(identity, bool) or not isinstance(identity, int):
            continue
        if identity >= current_run_id:
            # Its sequence would not be older than ours: not a valid upgrade source.
            skipped_newer.append(identity)
            continue
        eligible.append(run)
    log('native_upgrade_skipped_newer_runs=' + (','.join(map(str, sorted(skipped_newer, reverse=True))) or 'none'))
    if not eligible:
        raise ValueError('native_upgrade_baseline_unavailable:no_older_baseline')
    for run in sorted(eligible, key=lambda item: item['id'], reverse=True):
        matches = [a for a in artifacts(run['id']) if a.get('name') == 'Karrierekrake-' + target
                   and a.get('expired') is False and a.get('size_in_bytes', 0) > 0]
        if len(matches) == 1:
            return run['id']
    raise ValueError('native_upgrade_baseline_unavailable:no_usable_artifact')


def github_get(path, token):
    request = Request('https://api.github.com/repos/' + REPOSITORY + path,
                      headers={'Authorization': 'Bearer ' + token,
                               'Accept': 'application/vnd.github+json'})
    with urlopen(request, timeout=60) as response:
        return json.load(response)


def main(argv=None, env=None, get=None):
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--target', required=True)
    args = parser.parse_args(argv)
    env = os.environ if env is None else env
    try:
        run_id = current_run_id(env)
        if get is None:
            def get(path):
                return github_get(path, env['GITHUB_TOKEN'])
        runs = get('/actions/workflows/desktop-platforms.yml/runs?status=success&per_page=30')['workflow_runs']
        selected = select_baseline(runs, lambda run: get('/actions/runs/' + str(run) + '/artifacts')['artifacts'],
                                   current_sha=get('/actions/runs/' + str(run_id))['head_sha'],
                                   current_run_id=run_id, target=args.target)
    except ValueError as error:
        print('::error title=native upgrade baseline::' + str(error), file=sys.stderr, flush=True)
        return 1
    with open(env['GITHUB_OUTPUT'], 'a', encoding='utf-8') as output:
        output.write('run_id=' + str(selected) + '\n')
    print('native_upgrade_baseline_run=' + str(selected), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())

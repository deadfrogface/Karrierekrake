"""Find an unexpired successful native-build baseline from this repository."""
from __future__ import annotations
import json
import os
from urllib.request import Request, urlopen

REPOSITORY = 'deadfrogface/Karrierekrake'


def select_baseline(runs, artifacts, *, current_sha, target):
    for run in runs:
        if (run.get('head_sha') == current_sha or run.get('conclusion') != 'success'
                or run.get('head_repository', {}).get('full_name') != REPOSITORY):
            continue
        matches = [a for a in artifacts(run['id']) if a.get('name') == 'Karrierekrake-' + target
                   and a.get('expired') is False and a.get('size_in_bytes', 0) > 0]
        if len(matches) == 1:
            return run['id']
    raise ValueError('native_upgrade_baseline_unavailable')


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--target', required=True)
    args = parser.parse_args()
    def get(path):
        request = Request('https://api.github.com/repos/' + REPOSITORY + path,
                          headers={'Authorization': 'Bearer ' + os.environ['GITHUB_TOKEN'],
                                   'Accept': 'application/vnd.github+json'})
        with urlopen(request, timeout=60) as response:
            return json.load(response)
    runs = get('/actions/workflows/desktop-platforms.yml/runs?status=success&per_page=30')['workflow_runs']
    selected = select_baseline(runs, lambda run: get('/actions/runs/' + str(run) + '/artifacts')['artifacts'],
                               current_sha=get('/actions/runs/' + os.environ['GITHUB_RUN_ID'])['head_sha'],
                               target=args.target)
    with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as output:
        output.write('run_id=' + str(selected) + '\n')
    print('native_upgrade_baseline_run=' + str(selected))


if __name__ == '__main__':
    main()

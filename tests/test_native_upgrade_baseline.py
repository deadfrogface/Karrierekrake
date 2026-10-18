import pytest

from scripts import native_upgrade_baseline as baseline
from scripts.native_upgrade_baseline import REPOSITORY, select_baseline

CURRENT = 100


def run(identity=1, **changes):
    return {'id': identity, 'head_sha': str(identity) * 40, 'conclusion': 'success',
            'head_repository': {'full_name': REPOSITORY}, **changes}


def artifact(**changes):
    return {'name': 'Karrierekrake-linux-x86_64', 'expired': False, 'size_in_bytes': 100, **changes}


def select(runs, artifacts=lambda i: [artifact()], current_sha='x'*40, current_run_id=CURRENT, log=None):
    return select_baseline(runs, artifacts, current_sha=current_sha, current_run_id=current_run_id,
                           target='linux-x86_64', log=log or (lambda line: None))


def test_latest_distinct_successful_available_baseline_is_selected():
    runs = [run(3), run(2), run(1)]
    assert select(runs, lambda i: [artifact(expired=i == 2)], current_sha='3'*40) == 1


@pytest.mark.parametrize('candidate', [run(conclusion='failure'),
    run(head_repository={'full_name': 'untrusted/fork'}), run(head_sha='x'*40)])
def test_current_failed_and_foreign_builds_cannot_be_baselines(candidate):
    with pytest.raises(ValueError, match='baseline_unavailable'):
        select([candidate])


@pytest.mark.parametrize('artifacts', [[], [artifact(expired=True)], [artifact(size_in_bytes=0)],
    [artifact(name='Karrierekrake-macos-arm64')], [artifact(), artifact()]])
def test_missing_expired_wrong_target_or_ambiguous_artifacts_are_rejected(artifacts):
    with pytest.raises(ValueError, match='baseline_unavailable:no_usable_artifact'):
        select([run()], lambda i: artifacts)


# Sequence == github.run_id: a baseline from a run with a higher or equal id
# would be a downgrade/replay (e.g. #177 run 39086930936 picked 39087873965).
def test_newer_run_is_skipped_even_when_it_is_the_newest_success():
    asked, lines = [], []
    def artifacts(identity):
        asked.append(identity)
        return [artifact()]
    assert select([run(39087873965), run(39086000000)], artifacts,
                  current_run_id=39086930936, log=lines.append) == 39086000000
    assert asked == [39086000000]
    assert lines == ['native_upgrade_current_run=39086930936',
                     'native_upgrade_skipped_newer_runs=39087873965']


def test_run_with_equal_id_is_skipped():
    asked = []
    def artifacts(identity):
        asked.append(identity)
        return [artifact()]
    assert select([run(CURRENT), run(CURRENT - 1)], artifacts) == CURRENT - 1
    assert asked == [CURRENT - 1]


def test_newest_older_successful_run_with_other_sha_is_chosen_regardless_of_list_order():
    runs = [run(150), run(42), run(99, head_sha='x'*40), run(97), run(98, conclusion='failure')]
    assert select(runs) == 97


@pytest.mark.parametrize('runs', [[], [run(CURRENT)], [run(CURRENT + 1), run(CURRENT + 5)],
                                  [run(CURRENT - 1, head_sha='x'*40), run(CURRENT + 1)]])
def test_no_older_baseline_fails_visibly(runs):
    with pytest.raises(ValueError, match='no_older_baseline'):
        select(runs)


@pytest.mark.parametrize('value', [None, 0, -1, '100', 1.5, True])
def test_invalid_current_run_id_is_rejected_by_selector(value):
    with pytest.raises(ValueError, match='current_run_id_invalid'):
        select([run()], current_run_id=value)


class FakeApi:
    def __init__(self, runs, current_sha='x'*40):
        self.runs, self.current_sha, self.paths = runs, current_sha, []

    def __call__(self, path):
        self.paths.append(path)
        if path.startswith('/actions/workflows/'):
            return {'workflow_runs': self.runs}
        if path.endswith('/artifacts'):
            return {'artifacts': [artifact()]}
        return {'head_sha': self.current_sha}


def test_main_writes_older_baseline_and_logs_it(tmp_path, capsys):
    output = tmp_path / 'out'
    api = FakeApi([run(CURRENT + 3), run(CURRENT - 2)])
    env = {'GITHUB_RUN_ID': str(CURRENT), 'GITHUB_OUTPUT': str(output)}
    assert baseline.main(['--target', 'linux-x86_64'], env=env, get=api) == 0
    assert output.read_text() == 'run_id=98\n'
    out = capsys.readouterr().out.splitlines()
    assert out == ['native_upgrade_current_run=100', 'native_upgrade_skipped_newer_runs=103',
                   'native_upgrade_baseline_run=98']
    assert '/actions/runs/100' in api.paths


def test_main_without_older_baseline_exits_non_zero_without_output(tmp_path, capsys):
    output = tmp_path / 'out'
    env = {'GITHUB_RUN_ID': str(CURRENT), 'GITHUB_OUTPUT': str(output)}
    assert baseline.main(['--target', 'linux-x86_64'], env=env, get=FakeApi([run(CURRENT + 1)])) == 1
    assert not output.exists()
    assert '::error title=native upgrade baseline::native_upgrade_baseline_unavailable:no_older_baseline' \
        in capsys.readouterr().err


@pytest.mark.parametrize('env', [{}, {'GITHUB_RUN_ID': ''}, {'GITHUB_RUN_ID': 'abc'},
                                 {'GITHUB_RUN_ID': '12.5'}, {'GITHUB_RUN_ID': '-4'}, {'GITHUB_RUN_ID': '0'},
                                 {'GITHUB_RUN_ID': ' 100'}, {'GITHUB_RUN_ID': '١٠٠'}])
def test_main_missing_or_invalid_run_id_fails_before_any_api_call(tmp_path, capsys, env):
    api = FakeApi([run(1)])
    output = tmp_path / 'out'
    assert baseline.main(['--target', 'linux-x86_64'], env={**env, 'GITHUB_OUTPUT': str(output)}, get=api) == 1
    assert api.paths == [] and not output.exists()
    assert 'native_upgrade_current_run_id_invalid' in capsys.readouterr().err


def test_script_exit_code_is_non_zero_when_selection_fails(monkeypatch):
    monkeypatch.setattr(baseline.sys, 'argv', ['native_upgrade_baseline.py', '--target', 'linux-x86_64'])
    monkeypatch.delenv('GITHUB_RUN_ID', raising=False)
    assert baseline.main() == 1

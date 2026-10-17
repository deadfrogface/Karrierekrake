import pytest
from scripts.native_upgrade_baseline import select_baseline, REPOSITORY


def run(identity=1, **changes):
    return {'id': identity, 'head_sha': str(identity) * 40, 'conclusion': 'success',
            'head_repository': {'full_name': REPOSITORY}, **changes}


def artifact(**changes):
    return {'name': 'Karrierekrake-linux-x86_64', 'expired': False, 'size_in_bytes': 100, **changes}


def test_latest_distinct_successful_available_baseline_is_selected():
    runs = [run(3), run(2), run(1)]
    assert select_baseline(runs, lambda i: [artifact(expired=i == 2)],
                           current_sha='3'*40, target='linux-x86_64') == 1


@pytest.mark.parametrize('candidate', [run(conclusion='failure'),
    run(head_repository={'full_name': 'untrusted/fork'}), run(head_sha='x'*40)])
def test_current_failed_and_foreign_builds_cannot_be_baselines(candidate):
    with pytest.raises(ValueError, match='baseline_unavailable'):
        select_baseline([candidate], lambda i: [artifact()], current_sha='x'*40, target='linux-x86_64')


@pytest.mark.parametrize('artifacts', [[], [artifact(expired=True)], [artifact(size_in_bytes=0)],
    [artifact(name='Karrierekrake-macos-arm64')], [artifact(), artifact()]])
def test_missing_expired_wrong_target_or_ambiguous_artifacts_are_rejected(artifacts):
    with pytest.raises(ValueError, match='baseline_unavailable'):
        select_baseline([run()], lambda i: artifacts, current_sha='x'*40, target='linux-x86_64')

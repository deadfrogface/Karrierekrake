"""Table tests for total-RAM classification of the setup recommendation.

These prove the recommendation LOGIC only. They are no peak-memory evidence:
the i3 / 8 GB gate (A7) stays open until scripts/run_i3_peak_job_benchmark.py
has produced a real physical-i3 record.
"""
import itertools
from pathlib import Path

import pytest

from guenther import device_check
from guenther import model_budgets as budgets
from guenther import setup_models as setup

GIB = 1024 ** 3
DISK_OK = 100_000_000_000
M4, M8, M27 = 'qwen3.5-4b-gsq', 'qwen3-8b-gsq', 'qwen3.8-27b-gsq-rco'


def rec(total, avail, cores, disk=DISK_OK, attestation=None):
    return setup.recommend_setup_model(total_gib=total, available_gib=avail,
                                       physical_cores=cores, free_disk_bytes=disk,
                                       attestation=attestation)


# total, available, cores, expected model, expected warnings, expected alternatives
TABLE = [
    # 8 GB laptop (~7.7 GiB total): never a dead end
    (7.7, 3.0, 2, M4, ('low_free_ram',), ()),
    (7.7, 4.5, 2, M4, (), ()),
    (7.7, 6.0, 2, M4, (), ()),
    (7.7, 6.5, 2, M4, (), ()),
    # 16 GB (~15.7 GiB total)
    (15.7, 3.0, 2, M4, ('low_free_ram', 'slow_cpu'), (M8,)),
    (15.7, 6.0, 2, M4, ('slow_cpu',), (M8,)),
    (15.7, 9.0, 2, M4, ('slow_cpu',), (M8,)),
    (15.7, 12.0, 2, M4, ('slow_cpu',), (M8,)),
    (15.7, 6.0, 4, M4, (), (M8,)),
    (15.7, 9.0, 4, M4, (), (M8,)),
    (15.7, 12.0, 4, M4, (), (M8,)),
    # 32 GB (~31.7 GiB total)
    (31.7, 24.0, 2, M4, ('slow_cpu',), (M27, M8)),
    (31.7, 24.0, 4, M4, (), (M27, M8)),
    # 64 GB / 12 cores: 27B unchanged
    (63.7, 40.0, 12, M27, (), (M8, M4)),
]


@pytest.mark.parametrize('total,avail,cores,model,warnings,alternatives', TABLE)
def test_total_ram_classification_table(total, avail, cores, model, warnings, alternatives):
    result = rec(total, avail, cores)
    assert result.model_id == model
    assert result.reason is None
    assert result.warnings == warnings
    assert result.alternatives == alternatives
    assert set(result.fits) == set(setup.SETUP_MODEL_CATALOG)
    assert set(result.peak_unverified) == set(setup.SETUP_MODEL_CATALOG)


@pytest.mark.parametrize('avail', [3.0, 4.5, 6.0])
def test_8gb_laptop_is_never_a_dead_end_with_enough_disk(avail):
    result = rec(7.7, avail, 2)
    assert result.model_id == M4
    assert result.reason is None
    # fits is the device check on the installed device (total RAM class + disk)
    assert result.fits[M4] is True


def test_8gb_with_6_5_free_has_no_low_free_ram():
    result = rec(7.7, 6.5, 2)
    assert result.model_id == M4
    assert 'low_free_ram' not in result.warnings


def test_8gb_with_3_free_has_low_free_ram():
    result = rec(7.7, 3.0, 2)
    assert result.model_id == M4
    assert 'low_free_ram' in result.warnings


def test_low_free_ram_threshold_is_reachable_and_derived_from_peak_gate():
    warn = budgets.LOW_FREE_RAM_WARN_GIB['4b']
    assert warn == pytest.approx(3_300_000_000 / GIB + 0.5)
    assert 3.5 < warn < 3.6
    # reachable on an 8 GB laptop, unlike the 6.0 + 2.0 GiB device budget
    assert warn < 7.7
    assert budgets.LOW_FREE_RAM_WARN_GIB['8b'] == budgets.CLASS_RAM_MIN_GIB['8b']
    assert budgets.LOW_FREE_RAM_WARN_GIB['27b'] == budgets.CLASS_RAM_MIN_GIB['27b']


@pytest.mark.parametrize('delta,warned', [(-0.01, True), (-1e-9, True), (0.0, False), (0.01, False)])
def test_low_free_ram_boundary_for_4b(delta, warned):
    warn = budgets.LOW_FREE_RAM_WARN_GIB['4b']
    result = rec(7.7, warn + delta, 2)
    assert result.model_id == M4
    assert ('low_free_ram' in result.warnings) is warned


@pytest.mark.parametrize('cores', [2, 4, 8])
@pytest.mark.parametrize('total', [15.7, 31.7])
def test_8b_is_never_recommended_while_unverified(total, cores):
    result = rec(total, total - 3.0, cores)
    assert result.model_id != M8
    assert M8 in result.alternatives
    assert result.fits[M8] is True
    assert result.peak_unverified[M8] is True
    assert ('slow_cpu' in result.warnings) == (cores < 4)


def test_8b_and_27b_never_fit_below_15_gib_total():
    for total, avail in itertools.product([7.0, 7.7, 10.0, 14.9], [3.0, 6.0, 14.9, 40.0]):
        result = rec(total, avail, 16)
        assert result.fits[M8] is False
        assert result.fits[M27] is False
        assert M8 not in result.alternatives and M27 not in result.alternatives


def test_27b_thresholds_are_unchanged():
    assert rec(63.7, 40.0, 12).model_id == M27
    assert rec(63.7, 40.0, 11).model_id == M4
    assert rec(46.9, 40.0, 16).model_id == M4
    # 27B needs its 14.0 GiB budget plus 2.0 GiB free right now
    assert rec(63.7, 15.9, 16).model_id == M4
    assert rec(63.7, 16.0, 16).model_id == M27


def test_27b_never_fits_on_16gb_devices():
    # 27B needs 14.0 + 2.0 GiB of installed RAM; 16 GB devices report ~15.6-15.7
    for total in (15.0, 15.6, 15.7, 15.99):
        result = rec(total, 12.0, 16)
        assert result.fits[M27] is False, total
        assert M27 not in result.alternatives


def test_16gb_4_cores_fits_8b_but_not_27b():
    result = rec(15.6, 12.0, 4)
    assert result.fits[M27] is False
    assert result.fits[M8] is True
    assert result.fits[M4] is True
    assert result.model_id == M4


def test_32gb_2_cores_fits_27b_without_recommending_it():
    result = rec(31.6, 28.0, 2)
    assert result.fits[M27] is True
    assert result.model_id == M4
    assert result.model_id != M27
    assert M27 in result.alternatives


def test_27b_headroom_boundary_is_16_gib_total():
    assert rec(16.0, 16.0, 16).fits[M27] is True
    assert rec(15.99, 15.99, 16).fits[M27] is False


def test_alternatives_are_exactly_the_other_fitting_models():
    for total, avail, cores in itertools.product(GRID_TOTAL, GRID_AVAIL, [2, 4, 12]):
        if avail > total:
            continue
        result = rec(total, avail, cores)
        expected = {mid for mid, ok in result.fits.items() if ok and mid != result.model_id}
        assert set(result.alternatives) == expected, (total, avail, cores)


def test_disk_too_small_returns_none_with_reason():
    result = rec(31.7, 24.0, 4, disk=1_000_000_000)
    assert result.model_id is None
    assert result.reason == 'disk_too_small'
    assert result.alternatives == ()
    assert not any(result.fits.values())


def test_disk_check_is_file_plus_500_mb():
    need = setup.SETUP_MODEL_CATALOG[M4]['approx_bytes'] + 500_000_000
    assert rec(7.7, 6.0, 2, disk=need).model_id == M4
    assert rec(7.7, 6.0, 2, disk=need - 1).reason == 'disk_too_small'


def test_4gb_device_returns_none_with_ram_too_small():
    result = rec(3.8, 2.5, 2)
    assert result.model_id is None
    assert result.reason == 'ram_too_small'
    assert result.warnings == ()
    assert not any(result.fits.values())


def test_ram_too_small_wins_over_disk_too_small():
    assert rec(3.8, 2.5, 2, disk=1).reason == 'ram_too_small'


def test_new_fields_have_backward_compatible_defaults():
    old_style = setup.SetupRecommendation(16, 12, 2, DISK_OK, M4)
    assert old_style.reason is None
    assert old_style.warnings == ()
    assert old_style.alternatives == ()
    assert old_style.fits == {}
    assert old_style.peak_unverified == {}


def test_all_models_unverified_by_default():
    result = rec(63.7, 40.0, 12)
    assert all(v is None for v in setup.PEAK_ATTESTATION.values())
    assert result.peak_unverified == {mid: True for mid in setup.SETUP_MODEL_CATALOG}
    # No device-level peak warning: only per-model fields.
    assert set(result.warnings) <= {'low_free_ram', 'slow_cpu'}


def _complete_record(mid=M4, peak=3_000_000_000):
    """Fully valid physical-i3 record for one catalog artifact (test fixture)."""
    return {
        'commit': 'adc297cf27039f806066597e02b4da21a7ff8926',
        'measurement_sha256': 'ab' * 32,
        'device': 'Intel Core i3-1115G4 / 8 GB (physical)',
        'model_sha256': setup.SETUP_MODEL_CATALOG[mid]['sha256'],
        'peak_private_bytes': peak,
        'peak_bytes': peak,
        'method': 'windows_job_object_peak_job_memory',
        'ship_evidence': True,
        'hard_fail': False,
    }


def _table(**records):
    table = {mid: None for mid in setup.SETUP_MODEL_CATALOG}
    table.update(records)
    return table


def test_full_valid_record_clears_flag():
    assert setup.peak_unverified(M4, {M4: _complete_record(M4)}) is False


def test_complete_attestation_clears_flag_for_that_model_only():
    result = rec(15.7, 12.0, 4, attestation=_table(**{M4: _complete_record(M4)}))
    assert result.peak_unverified == {M4: False, M8: True, M27: True}


REQUIRED_FIELDS = ['commit', 'measurement_sha256', 'device', 'model_sha256',
                   'peak_private_bytes', 'peak_bytes', 'method', 'ship_evidence', 'hard_fail']


@pytest.mark.parametrize('missing', REQUIRED_FIELDS)
def test_record_missing_any_field_stays_unverified(missing):
    record = _complete_record(M4)
    del record[missing]
    assert setup.peak_unverified(M4, {M4: record}) is True


def test_model_sha256_mismatch_for_swapped_artifact_stays_unverified():
    # a 4B record reused for the 8B artifact must not attest the 8B
    reused = _complete_record(M4)
    assert setup.peak_unverified(M8, {M8: reused}) is True
    assert setup.peak_unverified(M4, {M4: reused}) is False


def test_peak_above_3_3e9_stays_unverified():
    assert setup.peak_unverified(M4, {M4: _complete_record(M4, 3_300_000_001)}) is True
    over_private = dict(_complete_record(M4), peak_private_bytes=3_300_000_001)
    assert setup.peak_unverified(M4, {M4: over_private}) is True


def test_attestation_gate_is_inclusive_at_3_3e9():
    assert setup.peak_unverified(M4, {M4: _complete_record(M4, 3_300_000_000)}) is False
    assert setup.peak_unverified(M4, {M4: _complete_record(M4, 0)}) is False


@pytest.mark.parametrize('field,value', [
    ('commit', ''), ('commit', 'abc12'), ('commit', 'g' * 7), ('commit', 'a' * 41),
    ('commit', 1234567), ('commit', None),
    ('measurement_sha256', 'ab' * 31), ('measurement_sha256', 'zz' * 32),
    ('measurement_sha256', None),
    ('device', ''), ('device', '   '), ('device', None), ('device', 8),
    ('model_sha256', None), ('model_sha256', '00' * 32),
    ('peak_private_bytes', True), ('peak_private_bytes', 3.0e9),
    ('peak_private_bytes', None), ('peak_private_bytes', -1), ('peak_private_bytes', '3000000000'),
    ('peak_bytes', True), ('peak_bytes', 3.0e9), ('peak_bytes', None), ('peak_bytes', -1),
    ('ship_evidence', 1), ('ship_evidence', False), ('ship_evidence', 'true'),
    ('hard_fail', 0), ('hard_fail', None),
    ('method', 'process_group_rss'), ('method', None),
])
def test_wrongly_typed_field_stays_unverified(field, value):
    record = dict(_complete_record(M4), **{field: value})
    assert setup.peak_unverified(M4, {M4: record}) is True


FULL_SHA = 'adc297cf27039f806066597e02b4da21a7ff8926'


def test_full_40_char_commit_in_valid_record_stays_verified():
    assert len(FULL_SHA) == 40
    assert _complete_record(M4)['commit'] == FULL_SHA
    record = dict(_complete_record(M4), commit=FULL_SHA)
    assert setup.peak_unverified(M4, {M4: record}) is False


@pytest.mark.parametrize('commit', [
    FULL_SHA[:7],             # 7-char short SHA
    FULL_SHA[:39],            # 39 chars, one short of a full SHA
    FULL_SHA[:12],            # common 12-char abbreviation
    FULL_SHA.upper(),         # uppercase full SHA (rule is lowercase-only)
    FULL_SHA + '\n',          # trailing newline must not slip through
], ids=['short7', 'len39', 'short12', 'upper40', 'newline'])
def test_non_full_sha_commit_stays_unverified(commit):
    record = dict(_complete_record(M4), commit=commit)
    assert setup.peak_unverified(M4, {M4: record}) is True


@pytest.mark.parametrize('record', [None, True, False, 'attested', 1, [], {}])
def test_non_record_values_stay_unverified(record):
    assert setup.peak_unverified(M4, {M4: record}) is True


def test_missing_model_in_attestation_table_stays_unverified():
    assert setup.peak_unverified(M8, {}) is True


def test_attested_8b_keeps_the_23_gib_recommendation_gate():
    table = _table(**{M8: _complete_record(M8)})
    small = rec(15.6, 12.0, 4, attestation=table)
    assert small.model_id == M4
    assert M8 in small.alternatives
    assert small.peak_unverified[M8] is False
    assert rec(24.0, 18.0, 6, attestation=table).model_id == M8
    # boundary of the unchanged gate
    assert rec(22.9, 18.0, 6, attestation=table).model_id == M4
    assert rec(23.0, 18.0, 6, attestation=table).model_id == M8
    # slow CPU keeps 4B even when 8B is attested
    slow = rec(24.0, 18.0, 2, attestation=table)
    assert slow.model_id == M4 and 'slow_cpu' in slow.warnings
    # free RAM must still cover the 8B budget + reserve
    assert rec(24.0, 10.9, 6, attestation=table).model_id == M4


def test_budget_source_is_shared_and_27b_uses_stricter_value():
    for mid, entry in setup.SETUP_MODEL_CATALOG.items():
        assert entry['ram_gb_min'] == budgets.CLASS_RAM_MIN_GIB[entry['model_class']]
    assert budgets.CLASS_RAM_MIN_GIB['27b'] == 14.0
    for cand in device_check.CANDIDATES:
        assert cand.required_gib >= budgets.CLASS_RAM_MIN_GIB[cand.model_class]
        if cand.setup_model_id:
            entry = setup.SETUP_MODEL_CATALOG[cand.setup_model_id]
            assert cand.required_gib == entry['ram_gb_min']
            assert cand.model_class == entry['model_class']
    mapped = {c.setup_model_id for c in device_check.CANDIDATES if c.setup_model_id}
    assert mapped == set(setup.SETUP_MODEL_CATALOG)


GRID_TOTAL = [3.8, 6.9, 7.0, 7.7, 8.0, 11.9, 14.9, 15.0, 15.7, 16.0, 23.0, 31.7, 46.9, 47.0, 63.7]
GRID_AVAIL = [0.5, 2.0, 3.0, 4.5, 6.0, 7.9, 8.0, 9.0, 10.9, 11.0, 12.0, 15.9, 16.0, 24.0, 40.0, 60.0]
GRID_DISK = [1, 2_440_825_248, 2_440_825_247, 4_624_161_376, 8_922_841_472, DISK_OK]


def test_device_check_never_accepts_what_setup_rejects():
    """Direction matters: device_check acceptance implies setup fits, per model."""
    by_mid = {c.setup_model_id: c for c in device_check.CANDIDATES if c.setup_model_id}
    checked = 0
    for total, avail, disk in itertools.product(GRID_TOTAL, GRID_AVAIL, GRID_DISK):
        if avail > total:
            continue
        result = rec(total, avail, 4, disk=disk)
        check = device_check.recommend(total_gib=total, available_gib=avail,
                                       physical_cores=4, free_disk_gb=disk / 1_000_000_000)
        accepted = {c.name for c in check.fitting}
        for mid, cand in by_mid.items():
            if cand.name in accepted:
                checked += 1
                assert result.fits[mid], (mid, total, avail, disk)
                # device_check also needs free RAM, so setup must not warn here
                if result.model_id == mid:
                    assert 'low_free_ram' not in result.warnings
    assert checked > 0


def test_device_check_is_stricter_on_free_ram_than_setup_fits():
    # 8 GB laptop with 3 GiB free: setup fits by class, device report rejects
    result = rec(7.7, 3.0, 2)
    check = device_check.recommend(total_gib=7.7, available_gib=3.0,
                                   physical_cores=2, free_disk_gb=100)
    assert result.fits[M4] is True
    assert not check.fitting


@pytest.mark.xfail(strict=True, reason=(
    'needs Designer adapter: ModelSetupPanel still filters the model list by '
    'ram_gb_min + 2 <= available_gib, so the recommended 4B is not selectable '
    'on an 8 GB laptop; the panel is out of scope for this patch'))
def test_wizard_offers_recommended_4b_on_8gb_laptop(qtbot, monkeypatch):
    from desktop.widgets import model_setup_panel as panels
    recommendation = rec(7.7, 3.0, 2)
    monkeypatch.setattr(panels, 'inspect_setup_device', lambda: recommendation)
    monkeypatch.setattr(panels, 'selected_model_path', lambda: None)
    monkeypatch.setattr(panels, 'selected_model_id', lambda: None)
    panel = panels.ModelSetupPanel()
    qtbot.addWidget(panel)
    assert panel.model_choice.currentData() == M4
    assert panel.install_button.isEnabled()


def test_native_download_uses_4b_on_8gb_laptop(monkeypatch):
    from core import native_model_download as native
    calls = {}
    monkeypatch.setattr(native, 'validate', lambda manifest: None)
    monkeypatch.setattr(setup, 'inspect_setup_device', lambda: rec(7.7, 3.0, 2))
    def install(mid, **kwargs):
        calls['mid'] = mid
        return Path('/tmp/never-used.gguf')
    monkeypatch.setattr(setup, 'install_recommended_model', install)
    native.install_and_activate({})
    assert calls['mid'] == M4


CHANGED_FILES = [
    'guenther/model_budgets.py', 'guenther/setup_models.py', 'guenther/device_check.py',
    'docs/device-model-setup.md',
    'tests/test_setup_thresholds.py', 'tests/test_device_model_setup.py',
    'tests/test_model_download_logs.py',
]


def test_changed_files_never_use_the_rejected_field_name():
    root = Path(__file__).resolve().parents[1]
    needle = 'peak_' + 'verified'
    for rel in CHANGED_FILES:
        assert needle not in (root / rel).read_text(encoding='utf-8'), rel

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
    (15.7, 3.0, 2, M4, ('low_free_ram', 'slow_cpu'), ()),
    (15.7, 6.0, 2, M4, ('slow_cpu',), ()),
    (15.7, 9.0, 2, M4, ('slow_cpu',), ()),
    (15.7, 12.0, 2, M4, ('slow_cpu',), (M8,)),
    (15.7, 6.0, 4, M4, (), ()),
    (15.7, 9.0, 4, M4, (), ()),
    (15.7, 12.0, 4, M4, (), (M8,)),
    # 32 GB (~31.7 GiB total)
    (31.7, 24.0, 2, M4, ('slow_cpu',), (M27, M8)),
    (31.7, 24.0, 4, M4, (), (M27, M8)),
    # 64 GB / 12 cores: 27B thresholds pass, but 27B is unattested, so the
    # recommendation is at most 4B (attestation duty for all classes > 4B).
    # Old expectation (before Teamlead decision 1): M27, alternatives (M8, M4).
    (63.7, 40.0, 12, M4, (), (M27, M8)),
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
    # Old version asserted these WITHOUT attestation (M27 for 63.7/40/12 and
    # 63.7/16/16). Since Teamlead decision 1, 27B also needs a valid 27B
    # attestation; the 47 GiB / 12-core / free-RAM thresholds are unchanged.
    table = _table(**{M27: _complete_record(M27)})
    assert rec(63.7, 40.0, 12, attestation=table).model_id == M27
    assert rec(63.7, 40.0, 11, attestation=table).model_id == M4
    assert rec(46.9, 40.0, 16, attestation=table).model_id == M4
    assert rec(47.0, 40.0, 12, attestation=table).model_id == M27
    # 27B needs its 14.0 GiB budget plus 2.0 GiB free right now
    assert rec(63.7, 15.9, 16, attestation=table).model_id == M4
    assert rec(63.7, 16.0, 16, attestation=table).model_id == M27
    # without attestation the same devices get 4B
    assert rec(63.7, 40.0, 12).model_id == M4
    assert rec(63.7, 16.0, 16).model_id == M4


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
    for entry in setup.SETUP_MODEL_CATALOG.values():
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
    """Direction matters: device_check acceptance implies setup fits, per model.

    Changed: the low_free_ram implication now only holds for 8B/27B. 4B is
    accepted by both views on installed RAM (shared usable_ram_fits), so an
    accepted, recommended 4B may carry low_free_ram (e.g. 7.7/3.0).
    """
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
                # 8B/27B: device_check also needs free RAM, so setup must not warn
                if result.model_id == mid and cand.model_class != budgets.CLASS_4B:
                    assert 'low_free_ram' not in result.warnings
    assert checked > 0


def test_device_check_uses_the_4b_rule_of_the_wizard_on_8gb_laptop():
    # Replaces test_device_check_is_stricter_on_free_ram_than_setup_fits
    # (old: `assert not check.fitting` for 7.7/3.0/2). The device report now
    # applies the same 4B rule as the wizard: 8 GB laptop with 3 GiB free ->
    # both name 4B GSQ; free RAM only sets low_free_ram.
    result = rec(7.7, 3.0, 2)
    check = device_check.recommend(total_gib=7.7, available_gib=3.0,
                                   physical_cores=2, free_disk_gb=100)
    assert result.fits[M4] is True
    assert result.model_id == M4 and 'low_free_ram' in result.warnings
    assert check.setup_model_id == M4
    assert check.recommended is not None and check.recommended.setup_model_id == M4
    assert check.recommended in check.fitting
    assert not any(c.model_class != budgets.CLASS_4B for c in check.fitting)
    # Designer wording: the report names the wizard's model under the wizard's
    # own name (old line 'Empfehlung (wie Einrichtung): DASLab Qwen3.5-4B GSQ Q2_K_XL').
    assert 'Passendes Modell für dieses Gerät: Qwen 4B · kompakt' in check.message('de')


@pytest.mark.xfail(strict=True, reason=(
    'Vorauswahl braucht zwei Bedingungen: (1) HR-Freigabe T02.09 (DE_05), '
    'eine Entscheidung, kein Code-Gate, und (2) gemessener i3-Peak '
    '(peak_unverified=False: vollstaendiger PEAK_ATTESTATION-Eintrag via '
    'scripts/run_i3_peak_job_benchmark.py --attest-physical-i3). Im Code '
    'entscheidet nur (2): SetupFit.preselected_id = Empfehlung mit fits und '
    'nicht peak_unverified. Bis dahin ist das 4B auf 8 GB angeboten und '
    'auswaehlbar, aber nicht vorausgewaehlt und nicht als empfohlen '
    'markiert. Kein RAM-Filter-Defekt: das Panel nutzt nur '
    'model_budgets.usable_ram_fits.'))
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


def test_wizard_8gb_laptop_requires_explicit_model_choice_until_t02_09(qtbot, monkeypatch):
    """Interim behaviour until Damiano decides the 8 GB default (4B GSQ vs
    Q4_K_M), T02.09 OFFEN: the recommended 4B is listed and selectable, but
    its peak is unverified, so it is not preselected and the download button
    becomes active only after the explicit choice. The original expectation
    (4B preselected) stays as strict xfail in
    test_wizard_offers_recommended_4b_on_8gb_laptop."""
    from desktop.widgets import model_setup_panel as panels
    recommendation = rec(7.7, 3.0, 2)
    monkeypatch.setattr(panels, 'inspect_setup_device', lambda: recommendation)
    monkeypatch.setattr(panels, 'selected_model_path', lambda: None)
    monkeypatch.setattr(panels, 'selected_model_id', lambda: None)
    panel = panels.ModelSetupPanel()
    qtbot.addWidget(panel)
    assert recommendation.model_id == M4
    assert panel.model_choice.findData(M4) >= 0
    assert panel.model_choice.currentIndex() == -1
    assert not panel.install_button.isEnabled()
    panel.model_choice.setCurrentIndex(panel.model_choice.findData(M4))
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
    'tests/test_model_download_logs.py', 'tests/test_device_check.py',
]


def test_changed_files_never_use_the_rejected_field_name():
    root = Path(__file__).resolve().parents[1]
    needle = 'peak_' + 'verified'
    for rel in CHANGED_FILES:
        assert needle not in (root / rel).read_text(encoding='utf-8'), rel


# --- Teamlead decision 1: attestation duty for ALL classes above 4B ---------

def test_27b_capable_device_without_attestation_recommends_4b():
    result = rec(64.0, 60.0, 16)
    assert result.model_id == M4
    assert result.alternatives == (M27, M8)
    assert result.fits[M27] is True and result.fits[M8] is True
    assert result.peak_unverified[M27] is True


def test_valid_27b_attestation_recommends_27b():
    result = rec(64.0, 60.0, 16, attestation=_table(**{M27: _complete_record(M27)}))
    assert result.model_id == M27
    assert result.alternatives == (M8, M4)
    assert result.peak_unverified == {M4: True, M8: True, M27: False}


def test_8b_attestation_does_not_unlock_27b():
    table = _table(**{M8: _complete_record(M8)})
    result = rec(64.0, 60.0, 16, attestation=table)
    assert result.model_id == M8
    assert M27 in result.alternatives
    assert result.peak_unverified[M27] is True


def test_8b_record_filed_under_27b_does_not_unlock_27b():
    # Attestation is tied to the artifact: model_sha256 must equal the 27B sha.
    table = _table(**{M27: _complete_record(M8)})
    result = rec(64.0, 60.0, 16, attestation=table)
    assert result.model_id == M4
    assert result.peak_unverified[M27] is True


def test_4b_attestation_unlocks_neither_8b_nor_27b():
    result = rec(64.0, 60.0, 16, attestation=_table(**{M4: _complete_record(M4)}))
    assert result.model_id == M4
    assert result.alternatives == (M27, M8)


def test_27b_and_8b_attested_prefers_27b_when_27b_gate_passes():
    table = _table(**{M8: _complete_record(M8), M27: _complete_record(M27)})
    assert rec(64.0, 60.0, 16, attestation=table).model_id == M27
    # 27B gate fails (cores) -> attested 8B
    assert rec(64.0, 60.0, 8, attestation=table).model_id == M8
    # 27B gate fails (total) -> attested 8B
    assert rec(46.9, 40.0, 16, attestation=table).model_id == M8


@pytest.mark.parametrize('field,value', [
    ('model_sha256', '00' * 32), ('peak_bytes', 3_300_000_001), ('hard_fail', True),
    ('ship_evidence', False), ('commit', FULL_SHA[:12]),
])
def test_invalid_27b_attestation_keeps_4b(field, value):
    record = dict(_complete_record(M27), **{field: value})
    result = rec(64.0, 60.0, 16, attestation=_table(**{M27: record}))
    assert result.model_id == M4
    assert M27 in result.alternatives


def test_attested_27b_still_needs_free_ram_and_installed_fit():
    table = _table(**{M27: _complete_record(M27)})
    assert rec(64.0, 15.9, 16, attestation=table).model_id == M4
    # 32 GB / 16 cores: below the 47 GiB recommendation gate
    assert rec(31.6, 28.0, 16, attestation=table).model_id == M4
    # 16 GB: 27B never fits, attestation does not change that
    small = rec(15.6, 15.0, 16, attestation=table)
    assert small.fits[M27] is False and small.model_id == M4


def test_no_class_above_4b_is_recommended_without_attestation_on_grid():
    for total, avail, cores in itertools.product(GRID_TOTAL, GRID_AVAIL, [2, 4, 12, 16]):
        if avail > total:
            continue
        result = rec(total, avail, cores)
        assert result.model_id in (M4, None), (total, avail, cores)


# --- Teamlead decision 2: device report and wizard name the same model ------

T8, T27 = _table(**{M8: _complete_record(M8)}), _table(**{M27: _complete_record(M27)})

# total GiB, free GiB, cores, disk bytes, attestation, expected model (both views)
PARITY = [
    # Designer real values
    (7.7, 3.0, 2, DISK_OK, None, M4),
    (7.7, 6.5, 2, DISK_OK, None, M4),
    (7.7, 6.0, 4, DISK_OK, None, M4),
    (15.6, 3.0, 2, DISK_OK, None, M4),
    (15.6, 12.0, 4, DISK_OK, None, M4),
    (15.6, 12.0, 4, DISK_OK, T8, M4),
    (31.6, 6.0, 4, DISK_OK, None, M4),
    (31.6, 28.0, 2, DISK_OK, None, M4),
    (31.6, 28.0, 8, DISK_OK, None, M4),
    (31.6, 28.0, 8, DISK_OK, T8, M8),
    (31.6, 10.9, 8, DISK_OK, T8, M4),
    # round sizes
    (8.0, 2.0, 2, DISK_OK, None, M4),
    (8.0, 7.5, 4, DISK_OK, None, M4),
    (16.0, 14.0, 2, DISK_OK, None, M4),
    (16.0, 4.0, 8, DISK_OK, None, M4),
    (24.0, 18.0, 6, DISK_OK, None, M4),
    (24.0, 18.0, 6, DISK_OK, T8, M8),
    (24.0, 5.0, 6, DISK_OK, T8, M4),
    (24.0, 18.0, 2, DISK_OK, T8, M4),
    (32.0, 24.0, 4, DISK_OK, None, M4),
    (32.0, 30.0, 12, DISK_OK, T27, M4),
    (64.0, 40.0, 16, DISK_OK, None, M4),
    (64.0, 40.0, 16, DISK_OK, T27, M27),
    (64.0, 40.0, 16, DISK_OK, T8, M8),
    (64.0, 15.9, 16, DISK_OK, T27, M4),
    (64.0, 60.0, 8, DISK_OK, T27, M4),
    # disk boundaries and dead ends
    (7.7, 6.0, 2, 2_440_825_248, None, M4),
    (7.7, 6.0, 2, 2_440_825_247, None, None),
    (64.0, 40.0, 16, 8_922_841_472, T27, M27),
    (64.0, 40.0, 16, 8_922_841_471, T27, M4),
    (3.8, 2.5, 2, DISK_OK, None, None),
]


@pytest.mark.parametrize('total,avail,cores,disk,attestation,expected', PARITY)
def test_device_report_and_wizard_name_the_same_model(total, avail, cores, disk,
                                                       attestation, expected):
    wizard = rec(total, avail, cores, disk=disk, attestation=attestation)
    check = device_check.recommend(total_gib=total, available_gib=avail, physical_cores=cores,
                                   free_disk_gb=disk / 1_000_000_000, attestation=attestation)
    assert wizard.model_id == expected
    assert check.setup_model_id == expected
    if expected is None:
        assert check.recommended is None
        assert 'Passendes Modell für dieses Gerät' not in check.message('de')
    else:
        # the named model must also pass the device report's own fit check
        assert check.recommended is not None
        assert check.recommended.setup_model_id == expected
        assert check.recommended in check.fitting
        name = setup.SETUP_MODEL_CATALOG[expected]['display_name']
        assert f'Passendes Modell für dieses Gerät: {name}' in check.message('de')


def test_device_report_and_wizard_agree_on_whole_grid():
    by_mid = {c.setup_model_id: c for c in device_check.CANDIDATES if c.setup_model_id}
    for total, avail, disk in itertools.product(GRID_TOTAL, GRID_AVAIL, GRID_DISK):
        if avail > total:
            continue
        for cores, table in itertools.product([2, 4, 12], [None, T8, T27]):
            wizard = rec(total, avail, cores, disk=disk, attestation=table)
            check = device_check.recommend(total_gib=total, available_gib=avail,
                                           physical_cores=cores,
                                           free_disk_gb=disk / 1_000_000_000,
                                           attestation=table)
            key = (total, avail, cores, disk)
            assert check.setup_model_id == wizard.model_id, key
            if wizard.model_id is not None:
                assert by_mid[wizard.model_id] in check.fitting, key
            # catalog candidates: device report fit == wizard fit on current RAM
            for mid, cand in by_mid.items():
                assert (cand in check.fitting) == (
                    wizard.fits[mid] and budgets.usable_ram_fits(
                        cand.model_class, total_gib=total, available_gib=avail,
                        own_gib=cand.runtime_gib)), (mid, key)


# ---- PO contract: panel list == recommendation fits (test-only, on #191) ----
# The panel must never loosen or tighten what recommend_setup_model says fits.
# Locked entries stay visible with a reason, but can never be chosen.

def _po_panel(qtbot, monkeypatch, recommendation, installed=None, starts=None):
    from desktop.widgets import model_setup_panel as panels
    monkeypatch.setattr(panels, 'inspect_setup_device', lambda: recommendation)
    monkeypatch.setattr(panels, 'selected_model_path',
                        lambda: Path('/tmp/installed.gguf') if installed else None)
    monkeypatch.setattr(panels, 'selected_model_id', lambda: installed)
    if starts is not None:
        monkeypatch.setattr(panels, 'start_worker', lambda worker: starts.append(worker))
        monkeypatch.setattr(panels, 'install_recommended_model',
                            lambda *a, **k: starts.append(('download', a, k)))
    panel = panels.ModelSetupPanel()
    qtbot.addWidget(panel)
    return panel


def _po_rows(panel):
    from PySide6.QtCore import Qt
    combo = panel.model_choice
    rows = []
    for i in range(combo.count()):
        item = combo.model().item(i)
        rows.append((combo.itemData(i), combo.itemText(i),
                     combo.itemData(i, Qt.ItemDataRole.AccessibleTextRole),
                     bool(item.flags() & Qt.ItemFlag.ItemIsEnabled)
                     and bool(item.flags() & Qt.ItemFlag.ItemIsSelectable)))
    return rows


def _po_ram_ok(mid, total, avail):
    entry = setup.SETUP_MODEL_CATALOG[mid]
    return budgets.usable_ram_fits(entry.get('model_class') or {M4: '4b', M8: '8b', M27: '27b'}[mid],
                                   total_gib=total, available_gib=avail,
                                   own_gib=entry.get('ram_gb_min'))


def _po_disk_ok(mid, disk):
    return setup.SETUP_MODEL_CATALOG[mid]['approx_bytes'] + budgets.DISK_RESERVE_BYTES <= disk


def _po_check_locked_reason(text, spoken, mid, total, avail, disk, installed):
    from desktop.i18n import tr
    ram_reasons = {'ram_too_small', 'low_free_ram'}
    shown = [r for r in ('ram_too_small', 'low_free_ram', 'disk_too_small', 'not_released')
             if tr('setup.model.item_locked_suffix', reason=tr('setup.model.block.' + r)) in text]
    assert len(shown) == 1, (mid, total, avail, disk, text)
    reason = shown[0]
    # Same reason as accessible text, not only colour or visible suffix.
    assert spoken and tr('setup.model.block.' + reason) in spoken, (mid, spoken)
    # Exact reason, recomputed from budgets (never from the adapter), fixed order
    # (Designer, #191 2d25bb14): ram_too_small > low_free_ram > disk_too_small
    # > not_released; the installed model never gets a disk reason.
    entry = setup.SETUP_MODEL_CATALOG[mid]
    cls = entry.get('model_class') or {M4: '4b', M8: '8b', M27: '27b'}[mid]
    if not budgets.installed_ram_fits(cls, total, entry.get('ram_gb_min')):
        expected = 'ram_too_small'
    elif not _po_ram_ok(mid, total, avail):
        expected = 'low_free_ram'
    elif not installed and not _po_disk_ok(mid, disk):
        expected = 'disk_too_small'
    else:
        expected = 'not_released'
    assert reason == expected, (mid, total, avail, disk, installed, reason, expected)
    if installed:
        assert reason in ram_reasons, (mid, total, avail, disk, reason)


def _po_assert_contract(panel, recommendation, total, avail, disk, installed=None):
    rows = _po_rows(panel)
    ids = [r[0] for r in rows]
    # Every catalog model exactly once, nothing foreign.
    assert sorted(ids) == sorted(setup.SETUP_MODEL_CATALOG), (total, avail, disk, ids)
    selectable = {r[0] for r in rows if r[3]}
    expected = {mid for mid, ok in recommendation.fits.items() if ok}
    if installed is not None:
        # Reactivation: installed model is judged by RAM only, not by download space.
        expected.discard(installed)
        if _po_ram_ok(installed, total, avail):
            expected.add(installed)
    assert selectable == expected, (total, avail, disk, installed, selectable, expected)
    if recommendation.model_id:
        assert recommendation.model_id in selectable, (total, avail, disk, recommendation.model_id)
    for mid, text, spoken, ok in rows:
        if not ok:
            _po_check_locked_reason(text, spoken, mid, total, avail, disk, mid == installed)
    return rows


def _po_grid(disks=GRID_DISK):
    for total, avail, disk in itertools.product(GRID_TOTAL, GRID_AVAIL, disks):
        if avail <= total:
            yield total, avail, disk


def test_panel_list_uses_the_same_fits_as_the_recommendation(qtbot, monkeypatch):
    from PySide6.QtCore import Qt
    for total, avail, disk in _po_grid():
        recommendation = rec(total, avail, 4, disk=disk)
        starts = []
        panel = _po_panel(qtbot, monkeypatch, recommendation, starts=starts)
        rows = _po_assert_contract(panel, recommendation, total, avail, disk)
        combo = panel.model_choice
        locked = [i for i, r in enumerate(rows) if not r[3]]
        free = [i for i, r in enumerate(rows) if r[3]]
        # Arrow keys never land on a locked entry.
        if free:
            combo.setCurrentIndex(free[0])
            for key in [Qt.Key.Key_Down] * len(rows) + [Qt.Key.Key_Up] * len(rows):
                qtbot.keyClick(combo, key)
                assert combo.currentIndex() not in locked, (total, avail, disk, combo.currentData())
        # Even when forced onto a locked entry, install() starts no download and no worker.
        for i in locked:
            combo.setCurrentIndex(i)
            panel.install()
            assert not starts and not panel.busy, (total, avail, disk, rows[i][0])
        panel.close()


def test_panel_locked_entry_ignores_a_click(qtbot, monkeypatch):
    from PySide6.QtCore import Qt
    for total, avail, disk in [(7.7, 3.0, DISK_OK), (15.7, 6.0, DISK_OK), (31.7, 24.0, 1),
                               (7.7, 6.0, 2_440_825_247)]:
        recommendation = rec(total, avail, 4, disk=disk)
        panel = _po_panel(qtbot, monkeypatch, recommendation)
        rows = _po_assert_contract(panel, recommendation, total, avail, disk)
        combo = panel.model_choice
        free = [i for i, r in enumerate(rows) if r[3]]
        combo.setCurrentIndex(free[0] if free else -1)
        before = combo.currentData()
        for i, r in enumerate(rows):
            if r[3]:
                continue
            combo.showPopup()
            view = combo.view()
            rect = view.visualRect(combo.model().index(i, 0))
            qtbot.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
            combo.hidePopup()
            assert combo.currentData() == before, (total, avail, disk, r[0])
        panel.close()


def test_panel_never_shows_a_recommendation_with_an_empty_list(qtbot, monkeypatch):
    for total, avail, disk in _po_grid():
        recommendation = rec(total, avail, 4, disk=disk)
        panel = _po_panel(qtbot, monkeypatch, recommendation)
        if recommendation.model_id:
            assert panel.model_choice.findData(recommendation.model_id) >= 0, (total, avail, disk)
        if panel.install_button.isEnabled():
            assert panel.model_choice.count() > 0, (total, avail, disk)
        panel.close()


def test_panel_install_without_choice_explains_instead_of_returning_silently(qtbot, monkeypatch):
    from desktop.i18n import tr
    starts = []
    panel = _po_panel(qtbot, monkeypatch, rec(7.7, 3.0, 2), starts=starts)
    panel.model_choice.setCurrentIndex(-1)
    panel.status.setText('')
    panel.install()
    assert not panel.busy and not starts
    assert panel.status.text() == tr('setup.model.choose_first_message')


def test_panel_install_on_insufficient_device_explains(qtbot, monkeypatch):
    from desktop.i18n import tr
    starts = []
    panel = _po_panel(qtbot, monkeypatch, rec(6.0, 3.0, 2), starts=starts)
    assert panel.recommendation.model_id is None
    assert tr('setup.model.no_fit') in panel.recommended.text()
    panel.status.setText('')
    panel.install()
    assert not panel.busy and not starts
    assert panel.status.text() == tr('setup.model.continue_without_ai')


def test_panel_keeps_installed_model_without_download_space(qtbot, monkeypatch):
    recommendation = rec(7.7, 3.0, 2, disk=100_000_000)
    assert recommendation.fits[M4] is False
    panel = _po_panel(qtbot, monkeypatch, recommendation, installed=M4)
    _po_assert_contract(panel, recommendation, 7.7, 3.0, 100_000_000, installed=M4)
    assert panel.model_choice.findData(M4) >= 0


def test_panel_installed_model_contract_on_the_grid(qtbot, monkeypatch):
    # Installed model: selectable iff RAM fits; locked only with a RAM reason.
    for mid in setup.SETUP_MODEL_CATALOG:
        for total, avail, disk in _po_grid(disks=[1, DISK_OK]):
            recommendation = rec(total, avail, 4, disk=disk)
            panel = _po_panel(qtbot, monkeypatch, recommendation, installed=mid)
            _po_assert_contract(panel, recommendation, total, avail, disk, installed=mid)
            panel.close()

"""Parity: recommend_setup_model().fits/alternatives follow usable_ram_fits.

The setup panel and the device report decide by model_budgets.usable_ram_fits.
The recommendation's own fields must decide the same way, otherwise any other
consumer of ``fits``/``alternatives`` is offered a model the app cannot load
now (e.g. 8B at 15.7 GiB total with 3 GiB free). Logic only, no peak-memory or
target-hardware evidence.
"""
import itertools

import pytest

from guenther import model_budgets as budgets
from guenther import setup_models as setup

M4, M8, M27 = 'qwen3.5-4b-gsq', 'qwen3-8b-gsq', 'qwen3.8-27b-gsq-rco'
DISK_OK = 100_000_000_000
# Same RAM classes as the designer's panel parity test (8/16/32 GB devices as
# reported by the OS and nominal), each with 3 GiB free and with plenty free,
# plus intermediate free-RAM values around the 8B/27B budgets.
TOTALS = [7.7, 8.0, 15.6, 15.7, 16.0, 23.0, 24.0, 31.6, 32.0, 47.0, 63.7]
FREE = [3.0, 6.0, 9.0, 10.9, 11.0, 15.9, 16.0, 'plenty']
CORES = [2, 4, 12]


def _disk_values():
    four = setup.SETUP_MODEL_CATALOG[M4]['approx_bytes'] + setup.DISK_RESERVE_BYTES
    return [DISK_OK, four, four - 1]


def _expected_fits(total, avail, disk):
    out = {}
    for mid, entry in setup.SETUP_MODEL_CATALOG.items():
        out[mid] = (budgets.usable_ram_fits(entry['model_class'], total_gib=total,
                                            available_gib=avail, own_gib=entry['ram_gb_min'])
                    and entry['approx_bytes'] + setup.DISK_RESERVE_BYTES <= disk)
    return out


@pytest.fixture(params=['unverified', 'all_attested'])
def attested(request, monkeypatch):
    if request.param == 'all_attested':
        monkeypatch.setattr(setup, 'peak_unverified', lambda mid, attestation=None: False)
    return request.param


@pytest.mark.parametrize('total,free,cores,disk_idx',
                         list(itertools.product(TOTALS, FREE, CORES, range(3))))
def test_fits_and_alternatives_match_usable_ram_fits(total, free, cores, disk_idx, attested):
    avail = total - 0.3 if free == 'plenty' else min(float(free), total)
    disk = _disk_values()[disk_idx]
    result = setup.recommend_setup_model(total_gib=total, available_gib=avail,
                                         physical_cores=cores, free_disk_bytes=disk)
    expected = _expected_fits(total, avail, disk)
    assert result.fits == expected
    order = list(setup.SETUP_MODEL_CATALOG)
    assert result.alternatives == tuple(m for m in reversed(order)
                                        if expected[m] and m != result.model_id)
    if result.model_id is not None:
        # The recommendation (incl. the >= 23 GiB 8B path) is chosen from fits,
        # so a fallback built from fits never drops it.
        assert result.fits[result.model_id] is True


def test_8b_not_offered_at_15_7_gib_with_3_gib_free():
    result = setup.recommend_setup_model(total_gib=15.7, available_gib=3.0,
                                         physical_cores=4, free_disk_bytes=DISK_OK)
    assert result.model_id == M4
    assert result.fits[M8] is False and result.fits[M27] is False
    assert result.alternatives == ()
    assert 'low_free_ram' in result.warnings


def test_8_and_16_gb_devices_always_keep_4b():
    for total, avail in itertools.product([7.7, 8.0, 15.6, 16.0], [0.5, 3.0, 6.0]):
        result = setup.recommend_setup_model(total_gib=total, available_gib=avail,
                                             physical_cores=2, free_disk_bytes=DISK_OK)
        assert result.model_id == M4
        assert result.fits[M4] is True


@pytest.mark.parametrize('free', [5.0, 8.0])
def test_24_gib_8b_path_falls_back_to_4b_when_8b_budget_misses_free_ram(free, monkeypatch):
    # 8B is never added to fits after the fact: on the >= 23 GiB / >= 4 core
    # path, an attested 8B whose 9.0 GiB budget does not fit min(total, free)
    # - 2 GiB must not be recommended; the recommendation falls back to 4B.
    monkeypatch.setattr(setup, 'peak_unverified', lambda mid, attestation=None: False)
    result = setup.recommend_setup_model(total_gib=24.0, available_gib=free,
                                         physical_cores=6, free_disk_bytes=DISK_OK)
    assert result.fits[M8] is False
    assert result.model_id == M4
    assert M8 not in result.alternatives

from guenther.device_check import recommend


def test_free_ram_not_total_controls_recommendation():
    result = recommend(total_gib=24, available_gib=5, physical_cores=6, free_disk_gb=100)
    assert not result.fitting


def test_laptop_recommends_fast_ready_model_without_switching():
    result = recommend(total_gib=24, available_gib=21, physical_cores=6, free_disk_gb=100)
    assert result.fitting[0].ready
    assert any('IQ3_S' in c.name for c in result.fitting)
    assert 'kein automatischer Wechsel' in result.message()
    assert 'kein Geschwindigkeitstest' in result.message()


def test_disk_space_and_ram_reserve_are_enforced():
    result = recommend(total_gib=16, available_gib=14, physical_cores=2, free_disk_gb=4)
    assert len(result.fitting) == 1
    assert result.fitting[0].ready

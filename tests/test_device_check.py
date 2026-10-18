from guenther.device_check import recommend


def test_free_ram_not_total_controls_recommendation():
    # PR144 Teamlead decision 2, changed expectation: old `assert not
    # result.fitting`. Free RAM still controls 8B/27B; 4B now follows the
    # wizard's rule (installed RAM, 7.0 GiB class gate), so the device report
    # names the same 4B GSQ the wizard recommends for 24/5/6.
    result = recommend(total_gib=24, available_gib=5, physical_cores=6, free_disk_gb=100)
    assert result.fitting
    assert all(c.model_class == '4b' for c in result.fitting)
    assert result.setup_model_id == 'qwen3.5-4b-gsq'
    assert result.recommended.setup_model_id == 'qwen3.5-4b-gsq'


def test_laptop_recommends_fast_ready_model_without_switching():
    result = recommend(total_gib=24, available_gib=21, physical_cores=6, free_disk_gb=100)
    assert result.fitting[0].ready
    assert any('IQ3_S' in c.name for c in result.fitting)
    assert 'kein automatischer Wechsel' in result.message()
    assert 'kein Geschwindigkeitstest' in result.message()


def test_disk_space_and_ram_reserve_are_enforced():
    result = recommend(total_gib=16, available_gib=14, physical_cores=2, free_disk_gb=4)
    assert result.fitting[0].ready
    assert all(c.disk_gb + 0.5 <= 4 for c in result.fitting)
    assert not any('27B' in c.name for c in result.fitting)


def test_smaller_daslab_models_fit_without_a_27b_recommendation():
    result = recommend(total_gib=16, available_gib=12, physical_cores=2, free_disk_gb=100)
    assert any('4B GSQ' in c.name for c in result.fitting)
    assert any('8B GSQ' in c.name for c in result.fitting)
    assert not any('27B' in c.name for c in result.fitting)
    assert all(not c.ready for c in result.fitting if 'DASLab' in c.name)


def test_report_warns_low_free_ram_when_4b_is_recommended_on_8gb():
    # PR144 Kritiker finding on b831d58: 4B is now recommended on 7.7/3.0/2,
    # so the report must carry the wizard's low_free_ram warning too.
    from guenther.device_check import LOW_FREE_RAM_LINE, LOW_FREE_RAM_WARNING
    from guenther.setup_models import WARNING_LOW_FREE_RAM
    assert LOW_FREE_RAM_WARNING == WARNING_LOW_FREE_RAM
    result = recommend(total_gib=7.7, available_gib=3.0, physical_cores=2, free_disk_gb=100)
    assert result.setup_model_id == 'qwen3.5-4b-gsq'
    assert LOW_FREE_RAM_WARNING in result.setup_warnings
    message = result.message()
    assert 'Empfehlung (wie Einrichtung)' in message
    assert LOW_FREE_RAM_LINE in message


def test_report_has_no_low_free_ram_line_with_enough_free_ram():
    from guenther.device_check import LOW_FREE_RAM_LINE
    result = recommend(total_gib=7.7, available_gib=5.0, physical_cores=2, free_disk_gb=100)
    assert result.setup_model_id == 'qwen3.5-4b-gsq'
    assert result.setup_warnings == ()
    assert LOW_FREE_RAM_LINE not in result.message()

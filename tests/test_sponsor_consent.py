from core.commercial import sponsors


def test_campaign_change_requires_fresh_consent(tmp_path, monkeypatch):
    current = {'id': 'synthetic-partner', 'version': '1', 'advertiser': 'Example',
               'title': 'Example', 'body': 'Local text', 'url': 'https://example.com'}
    monkeypatch.setattr(sponsors, 'load_policy', lambda: {'sponsor': current})
    monkeypatch.setattr(sponsors, 'user_data_dir', lambda: tmp_path)
    monkeypatch.setattr(sponsors, 'feature_allowed', lambda feature: False)
    assert sponsors.visible_campaign() is None
    sponsors.set_consent(True)
    assert sponsors.visible_campaign() == current
    current['version'] = '2'
    assert sponsors.visible_campaign() is None
    sponsors.set_consent(True)
    sponsors.set_consent(False)
    assert sponsors.visible_campaign() is None
    assert not sponsors.consent_path().exists()

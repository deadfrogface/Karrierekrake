from core.commercial.offline_free_policy import FREE_OFFLINE, feature_allowed, requires_network


def test_all_offline_free_features_work_without_paid_or_network():
    for feature in FREE_OFFLINE:
        assert feature_allowed(feature, paid=False, online=False)
        assert not requires_network(feature)


def test_paid_features_never_implicitly_unlock():
    assert not feature_allowed("premium_assistance", paid=False, online=True)
    assert feature_allowed("premium_assistance", paid=True, online=False)
    assert not feature_allowed("unknown_feature", paid=True, online=True)

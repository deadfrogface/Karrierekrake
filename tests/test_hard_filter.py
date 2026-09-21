"""Hard exclusion: distance filter and remote exception."""

from __future__ import annotations

from core.config import AppConfig, LocationConfig, ProfileConfig, SettingsConfig
from core.hard_filter import hard_exclude
from core.models import Job, RemoteType


def _cfg(*, max_km: float = 20.0, allow_remote: bool = True, allow_hybrid: bool = True) -> AppConfig:
    return AppConfig(
        profile=ProfileConfig(
            location=LocationConfig(
                home_address="",
                max_distance_km=max_km,
                allow_remote_germany=allow_remote,
                allow_hybrid=allow_hybrid,
                country="DE",
            )
        ),
        settings=SettingsConfig(published_within_days=30),
    )


def test_onsite_over_distance_excluded():
    from core.hard_filter import distance_exclude

    job = Job(
        id="1",
        source="test",
        title="Sachbearbeiter",
        company="Acme",
        description="",
        city="Faraway",
        distance_km=55.0,
        remote_type=RemoteType.ONSITE.value,
        url="https://example.com/1",
    )
    # Radius is applied after fachliches matching (distance_exclude), not hard_exclude.
    assert hard_exclude(job, _cfg(max_km=20.0)) is None
    reason = distance_exclude(job, _cfg(max_km=20.0))
    assert reason is not None
    assert "km" in reason


def test_remote_germany_exempt_from_distance():
    job = Job(
        id="2",
        source="test",
        title="Remote Support",
        company="Acme",
        description="Vollständig remote DE",
        city="Berlin",
        distance_km=500.0,
        remote_type=RemoteType.REMOTE.value,
        url="https://example.com/2",
    )
    assert hard_exclude(job, _cfg(max_km=20.0, allow_remote=True)) is None


def test_remote_blocked_when_not_allowed():
    job = Job(
        id="3",
        source="test",
        title="Remote Support",
        company="Acme",
        description="",
        city="Berlin",
        distance_km=500.0,
        remote_type=RemoteType.REMOTE.value,
        url="https://example.com/3",
    )
    reason = hard_exclude(job, _cfg(max_km=20.0, allow_remote=False))
    assert reason is not None
    assert "remote" in reason.lower()

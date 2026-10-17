"""Public release policy plus signed entitlement; sales remain disabled by default."""
from enum import Enum


class PremiumFeature(str, Enum):
    AUTOMATIC_REPLY = "automatic_reply"
    GOOGLE_CONNECTION = "google_connection"
    GOOGLE_MAPS = "google_maps"
    CLOUD_MODELS = "cloud_models"


PREMIUM_MESSAGE = (
    "Bald verfügbar mit Premium-Abo\n\n"
    "Diese Funktion benötigt ein Premium-Abo und ist noch in Arbeit. "
    "Premium kann derzeit noch nicht gebucht werden.\n\n"
    "Der kostenlose lokale Sortierer und Antwortentwürfe bleiben verfügbar."
)


class PremiumUnavailable(RuntimeError):
    pass


def require_premium(feature: PremiumFeature) -> None:
    """Fail before any network, credential or billing side effect."""
    feature = PremiumFeature(feature)
    from core.commercial.license_file import feature_allowed
    if feature_allowed(feature.value):
        return
    raise PremiumUnavailable(PREMIUM_MESSAGE)

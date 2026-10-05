"""Release availability, independent of licenses: Premium is not launched yet."""
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
    PremiumFeature(feature)  # Reject unknown feature IDs too.
    raise PremiumUnavailable(PREMIUM_MESSAGE)

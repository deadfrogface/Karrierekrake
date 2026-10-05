"""Shared coming-soon popup. No checkout or outbound action."""
from PySide6.QtWidgets import QMessageBox
from core.commercial.features import PremiumFeature, PremiumUnavailable, require_premium


def show_premium(parent, feature: PremiumFeature) -> None:
    try:
        require_premium(feature)
    except PremiumUnavailable as exc:
        QMessageBox.information(parent, "Wird später integriert", str(exc))

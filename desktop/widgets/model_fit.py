"""UI-facing view of the offline setup-device check.

The model setup panel never interprets ``recommend_setup_model`` directly.
``adapt_setup_recommendation`` maps whatever the recommendation returns onto
one small, stable interface:

* ``reason``   – ``"ram_too_small"``, ``"disk_too_small"`` or ``None``
* ``warnings`` – tuple containing ``"low_free_ram"`` and/or ``"slow_cpu"``
* per model    – ``fits`` (bool) and ``peak_unverified`` (bool)

When the recommendation already carries these fields (``reason``,
``warnings`` and a per-model mapping ``models[model_id]`` with ``fits`` /
``peak_unverified``) they are taken as-is. Today's
``SetupRecommendation`` has none of them; for that shape ``reason``, ``fits``
and the per-model block reason are derived from the same numbers the
recommendation used. ``peak_unverified`` has no fallback: a model counts as
measured only when ``peak_unverified`` is exactly ``False`` and no
contradicting ``peak_verified`` field is present (a present ``peak_verified``
that is not ``True`` makes the model unverified).
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

REASONS = frozenset({"ram_too_small", "disk_too_small"})
WARNINGS = frozenset({"low_free_ram", "slow_cpu"})
# Per-model block reasons shown to the user (plain German via i18n).
BLOCK_REASONS = ("ram_too_small", "low_free_ram", "disk_too_small", "not_released")

DOWNLOAD_RESERVE_BYTES = 500_000_000
FREE_RAM_HEADROOM_GIB = 2.0
# Total-RAM / core gate per model class. Only used to map today's
# SetupRecommendation, which has no per-model ``fits`` flag yet.
CLASS_GATES = {
    "qwen3.5-4b-gsq": (7.0, 1),
    "qwen3-8b-gsq": (15.0, 1),
    "qwen3.8-27b-gsq-rco": (47.0, 12),
}
SMALL_MODEL_ID = "qwen3.5-4b-gsq"


@dataclass(frozen=True)
class ModelFit:
    model_id: str
    display_name: str
    approx_bytes: int
    fits: bool
    peak_unverified: bool
    block_reason: str | None
    installed: bool


@dataclass(frozen=True)
class SetupFit:
    total_gib: float
    available_gib: float
    physical_cores: int
    free_disk_bytes: int
    recommended_id: str | None
    reason: str | None
    warnings: tuple[str, ...]
    models: tuple[ModelFit, ...]

    def model(self, model_id) -> ModelFit | None:
        return next((m for m in self.models if m.model_id == model_id), None)

    @property
    def any_fits(self) -> bool:
        return any(m.fits for m in self.models)

    @property
    def preselected_id(self) -> str | None:
        """Model the list starts on.

        A larger model whose memory peak was not measured is offered only as
        an alternative and never preselected; the compact model is preferred.
        """
        rec = self.model(self.recommended_id)
        if rec is not None and rec.fits and (not rec.peak_unverified or rec.model_id == SMALL_MODEL_ID):
            return rec.model_id
        small = self.model(SMALL_MODEL_ID)
        if small is not None and small.fits:
            return small.model_id
        verified = next((m for m in self.models if m.fits and not m.peak_unverified), None)
        return verified.model_id if verified else None

    @property
    def labelled_recommended_id(self) -> str | None:
        """Only a measured model may be called "Empfohlen"."""
        rec = self.model(self.preselected_id)
        return rec.model_id if rec is not None and not rec.peak_unverified else None


def _field(obj, name, default=None):
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _has_field(obj, name) -> bool:
    if isinstance(obj, Mapping):
        return name in obj
    return hasattr(obj, name)


def is_peak_unverified(entry) -> bool:
    """True unless ``peak_unverified`` is exactly False and nothing contradicts it."""
    if entry is None or _field(entry, "peak_unverified", None) is not False:
        return True
    # A present peak_verified that is not True contradicts peak_unverified=False.
    return _has_field(entry, "peak_verified") and _field(entry, "peak_verified") is not True


def _derived_block_reason(mid, entry, total_gib, available_gib, cores, free_disk, installed):
    min_total, min_cores = CLASS_GATES.get(mid, (float("inf"), 0))
    if total_gib < min_total or cores < min_cores:
        return "ram_too_small" if total_gib < min_total else "not_released"
    if not installed and entry["approx_bytes"] + DOWNLOAD_RESERVE_BYTES > free_disk:
        return "disk_too_small"
    if entry["ram_gb_min"] + FREE_RAM_HEADROOM_GIB > available_gib:
        return "low_free_ram"
    return None


def adapt_setup_recommendation(recommendation, *, installed_model_id=None, catalog=None) -> SetupFit:
    if catalog is None:
        from guenther.setup_models import SETUP_MODEL_CATALOG as catalog
    total = float(_field(recommendation, "total_gib", 0.0) or 0.0)
    available = float(_field(recommendation, "available_gib", 0.0) or 0.0)
    cores = int(_field(recommendation, "physical_cores", 1) or 1)
    free_disk = int(_field(recommendation, "free_disk_bytes", 0) or 0)
    recommended = _field(recommendation, "model_id", None)
    recommended = recommended if recommended in catalog else None
    per_model = _field(recommendation, "models", None)
    per_model = per_model if isinstance(per_model, Mapping) else None
    models = []
    for mid, entry in catalog.items():
        installed = mid == installed_model_id
        derived = _derived_block_reason(mid, entry, total, available, cores, free_disk, installed)
        given = per_model.get(mid) if per_model is not None else None
        if given is not None and isinstance(_field(given, "fits", None), bool):
            fits = _field(given, "fits")
            if not fits and installed and derived is None:
                fits = True  # an installed model needs no further download space
            block = None if fits else (derived or "not_released")
        else:
            fits = derived is None
            block = derived
        models.append(ModelFit(mid, entry["display_name"], int(entry["approx_bytes"]),
                               bool(fits), is_peak_unverified(given), block, installed))
    if recommended is not None:
        # The recommended model is offered even when only a warning applies.
        models = [m if m.model_id != recommended or m.fits else
                  ModelFit(m.model_id, m.display_name, m.approx_bytes, True,
                           m.peak_unverified, None, m.installed) for m in models]
    reason = _field(recommendation, "reason", None)
    if reason not in REASONS:
        reason = None
        if recommended is None and not any(m.fits for m in models):
            blocks = {m.block_reason for m in models}
            reason = "disk_too_small" if blocks <= {"disk_too_small", "not_released"} and "disk_too_small" in blocks \
                else "ram_too_small"
    if recommended is not None:
        reason = None
    raw_warnings = _field(recommendation, "warnings", None) or ()
    if isinstance(raw_warnings, str):
        raw_warnings = (raw_warnings,)
    warnings = tuple(w for w in dict.fromkeys(raw_warnings) if w in WARNINGS)
    return SetupFit(total, available, cores, free_disk, recommended, reason, warnings, tuple(models))

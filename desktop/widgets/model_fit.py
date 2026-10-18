"""UI-facing view of the offline setup-device check.

The model setup panel never interprets ``recommend_setup_model`` directly.
``adapt_setup_recommendation`` maps whatever the recommendation returns onto
one small, stable interface:

* ``reason``   – ``"ram_too_small"``, ``"disk_too_small"`` or ``None``
* ``warnings`` – tuple containing ``"low_free_ram"`` and/or ``"slow_cpu"``
* per model    – ``fits`` (bool) and ``peak_unverified`` (bool)

Primary input (guenther.setup_models.SetupRecommendation): dicts on the
recommendation, ``recommendation.fits[mid]`` and
``recommendation.peak_unverified[mid]``, plus ``reason`` and ``warnings``.
A per-model mapping ``recommendation.models[mid]`` with the same keys is still
accepted as a legacy fallback.

Rules:

* A ``fits`` value that is exactly ``bool`` is taken unchanged. It is never
  overridden – not for an installed model and not for ``model_id``.
* As soon as the recommendation carries a ``fits`` dict (or legacy ``models``
  entries with ``fits``), the threshold fallback is used for no model; a model
  missing from that dict, or with a non-bool value, is locked.
* Only when no ``fits`` information exists at all are ``fits``/``reason``/
  ``warnings`` derived from the numbers via ``guenther.model_budgets``
  (``derive_fallback_fits``; single source, no local copy).
* ``model_id`` naming a model with ``fits=False`` is a
  ``recommendation_conflict``: the model stays locked, nothing is
  preselected, and the conflict is logged.
* ``peak_unverified`` has no fallback: a model counts as measured only when
  ``peak_unverified`` is exactly ``False`` and no contradicting
  ``peak_verified`` is present (a present ``peak_verified`` that is not
  ``True`` makes it unverified). Only a measured, fitting recommendation may
  be preselected or called "Empfohlen".
"""
from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass

from guenther import model_budgets

LOG = logging.getLogger("karrierekrake")

REASONS = frozenset({"ram_too_small", "disk_too_small"})
WARNINGS = frozenset({"low_free_ram", "slow_cpu"})
# Per-model block reasons shown to the user (plain German via i18n).
BLOCK_REASONS = ("ram_too_small", "low_free_ram", "disk_too_small", "not_released")
CONFLICT_CODE = "recommendation_conflict"

_MISSING = object()


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
    conflict: str | None = None

    def model(self, model_id) -> ModelFit | None:
        return next((m for m in self.models if m.model_id == model_id), None)

    @property
    def any_fits(self) -> bool:
        return any(m.fits for m in self.models)

    @property
    def preselected_id(self) -> str | None:
        """Only a measured (peak_unverified=False), fitting recommendation is preselected."""
        rec = self.model(self.recommended_id)
        if rec is not None and rec.fits and not rec.peak_unverified:
            return rec.model_id
        return None

    @property
    def labelled_recommended_id(self) -> str | None:
        """Only a measured model may be called "Empfohlen"."""
        return self.preselected_id


def _field(obj, name, default=None):
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _has_field(obj, name) -> bool:
    if isinstance(obj, Mapping):
        return name in obj
    return hasattr(obj, name)


def is_peak_unverified(entry) -> bool:
    """True unless ``peak_unverified`` is exactly False and nothing contradicts it.

    ``entry`` is a mapping/object with ``peak_unverified`` and optionally
    ``peak_verified`` for one model, or None when nothing is known.
    """
    if entry is None or _field(entry, "peak_unverified", None) is not False:
        return True
    # A present peak_verified that is not True contradicts peak_unverified=False.
    return _has_field(entry, "peak_verified") and _field(entry, "peak_verified") is not True


def _per_model_value(recommendation, models, name, mid):
    """``recommendation.<name>[mid]`` first, then legacy ``recommendation.models[mid].<name>``."""
    table = _field(recommendation, name, None)
    if isinstance(table, Mapping) and mid in table:
        return table[mid]
    entry = models.get(mid) if models is not None else None
    if entry is not None and _has_field(entry, name):
        return _field(entry, name)
    return _MISSING


# Catalog entries before the threshold patch have no model_class.
_CLASS_BY_MODEL_ID = {"qwen3.5-4b-gsq": "4b", "qwen3-8b-gsq": "8b", "qwen3.8-27b-gsq-rco": "27b"}


def _model_class(entry, mid=None):
    return entry.get("model_class") or _CLASS_BY_MODEL_ID.get(mid) or "4b"


def _disk_ok(entry, free_disk, installed):
    return installed or entry["approx_bytes"] + model_budgets.DISK_RESERVE_BYTES <= free_disk


def explain_block(entry, total_gib, available_gib, free_disk, installed, mid=None) -> str:
    """Best plain reason for a model that does not fit (never changes ``fits``)."""
    budgets = model_budgets  # looked up per call (single source)
    cls, own = _model_class(entry, mid), entry.get("ram_gb_min")
    if not budgets.installed_ram_fits(cls, total_gib, own):
        return "ram_too_small"
    if not _disk_ok(entry, free_disk, installed):
        return "disk_too_small"
    if not budgets.ram_fits(cls, total_gib=total_gib, available_gib=available_gib, own_gib=own):
        return "low_free_ram"
    return "not_released"


def derive_fallback_fits(entry, total_gib, available_gib, free_disk, installed, mid=None):
    """Threshold fallback, used ONLY when the recommendation has no fits at all.

    Returns ``(fits, block_reason, low_free_ram)``; same budgets as
    recommend_setup_model (installed RAM + disk lock, free RAM only warns).
    """
    budgets = model_budgets  # looked up per call (single source)
    cls = _model_class(entry, mid)
    fits = (budgets.installed_ram_fits(cls, total_gib, entry.get("ram_gb_min"))
            and _disk_ok(entry, free_disk, installed))
    if not fits:
        return False, explain_block(entry, total_gib, available_gib, free_disk, installed, mid), False
    low_free = not budgets.ram_fits(cls, total_gib=total_gib, available_gib=available_gib,
                                    own_gib=entry.get("ram_gb_min"))
    return True, None, low_free


def adapt_setup_recommendation(recommendation, *, installed_model_id=None, catalog=None) -> SetupFit:
    if catalog is None:
        from guenther.setup_models import SETUP_MODEL_CATALOG as catalog
    total = float(_field(recommendation, "total_gib", 0.0) or 0.0)
    available = float(_field(recommendation, "available_gib", 0.0) or 0.0)
    cores = int(_field(recommendation, "physical_cores", 1) or 1)
    free_disk = int(_field(recommendation, "free_disk_bytes", 0) or 0)
    recommended = _field(recommendation, "model_id", None)
    recommended = recommended if recommended in catalog else None
    models_map = _field(recommendation, "models", None)
    models_map = models_map if isinstance(models_map, Mapping) else None
    # Any fits information at all disables the threshold fallback for every model.
    has_fits = isinstance(_field(recommendation, "fits", None), Mapping) or (
        models_map is not None and any(_has_field(e, "fits") for e in models_map.values()))
    models = []
    low_free_fallback = False
    for mid, entry in catalog.items():
        installed = mid == installed_model_id
        if has_fits:
            given = _per_model_value(recommendation, models_map, "fits", mid)
            fits = given if isinstance(given, bool) else False  # missing / non-bool: locked
            # Explain the device check as it stands; an installed file gets no disk exemption here.
            block = None if fits else explain_block(entry, total, available, free_disk, False, mid)
        else:
            fits, block, low_free = derive_fallback_fits(entry, total, available, free_disk, installed, mid)
            low_free_fallback = low_free_fallback or (fits and low_free)
        peak_entry = {}
        for name in ("peak_unverified", "peak_verified"):
            value = _per_model_value(recommendation, models_map, name, mid)
            if value is not _MISSING:
                peak_entry[name] = value
        models.append(ModelFit(mid, entry["display_name"], int(entry["approx_bytes"]),
                               bool(fits), is_peak_unverified(peak_entry or None), block, installed))
    conflict = None
    rec_model = next((m for m in models if m.model_id == recommended), None)
    if rec_model is not None and not rec_model.fits:
        conflict = CONFLICT_CODE
        LOG.warning("model_setup_recommendation_conflict code=%s model_id=%s", CONFLICT_CODE, recommended)
    reason = _field(recommendation, "reason", None)
    reason = reason if reason in REASONS else None
    if any(m.fits for m in models):
        reason = None
    elif reason is None:
        blocks = {m.block_reason for m in models}
        reason = ("disk_too_small" if "disk_too_small" in blocks
                  and blocks <= {"disk_too_small", "not_released"} else "ram_too_small")
    raw_warnings = _field(recommendation, "warnings", None)
    if raw_warnings is None or (not has_fits and not raw_warnings):
        raw_warnings = ("low_free_ram",) if low_free_fallback else ()
    if isinstance(raw_warnings, str):
        raw_warnings = (raw_warnings,)
    warnings = tuple(w for w in dict.fromkeys(raw_warnings) if w in WARNINGS)
    return SetupFit(total, available, cores, free_disk, recommended, reason, warnings,
                    tuple(models), conflict)

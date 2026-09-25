"""Search page — explicit SearchIntent editor (what do I want to find *now*?).

UI binds to ``core.search_intent.SearchIntent`` only. No ranking / filter
domain logic lives here. Profile evidence (CV skills, experience) must never
be silently copied into intent fields.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from core.search_intent import (
    REMOTE_MODE_VALUES,
    SearchIntent,
    Strictness,
    empty_search_intent,
    parse_search_intent,
    sync_legacy_jobs_from_intent,
)
from desktop.design_system.polish import apply_button_icon, footer_actions_layout, polish_interactive
from desktop.i18n import escape_mnemonic, tr
from desktop.services import ConfigService
from desktop.widgets import ListEditor
from desktop.widgets.scroll_page import wrap_scrollable
from desktop.widgets.wheel_guard import IntentionalWheelDoubleSpinBox


class SearchPage(QWidget):
    """Dedicated SearchIntent surface — separate from Profile (who am I?)."""

    DACH_COUNTRIES = ("DE", "AT", "CH")

    def __init__(self, config_service: ConfigService, parent=None) -> None:
        super().__init__(parent)
        self.config_service = config_service

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(8, 8, 16, 16)
        layout.setSpacing(14)
        outer.addWidget(wrap_scrollable(inner))

        self.page_title = QLabel()
        self.page_title.setObjectName("PageTitle")
        self.page_subtitle = QLabel()
        self.page_subtitle.setObjectName("PageSubtitle")
        self.page_subtitle.setWordWrap(True)
        layout.addWidget(self.page_title)
        layout.addWidget(self.page_subtitle)

        # --- Roles / skills / keywords ---
        self.roles_box = QGroupBox()
        roles_form = QFormLayout(self.roles_box)
        self.target_roles = ListEditor("placeholder.job_title", visible_rows=4)
        self.mandatory_skills = ListEditor("placeholder.skill", visible_rows=3)
        self.excluded_roles = ListEditor("placeholder.exclude", visible_rows=3)
        self.excluded_skills = ListEditor("placeholder.exclude", visible_rows=2)
        self.excluded_keywords = ListEditor("placeholder.exclude", visible_rows=2)
        self.required_keywords = ListEditor("placeholder.add_entry", visible_rows=3)
        self.lbl_target_roles = QLabel()
        self.lbl_mandatory_skills = QLabel()
        self.lbl_excluded_roles = QLabel()
        self.lbl_excluded_skills = QLabel()
        self.lbl_excluded_keywords = QLabel()
        self.lbl_required_keywords = QLabel()
        roles_form.addRow(self.lbl_target_roles, self.target_roles)
        roles_form.addRow(self.lbl_mandatory_skills, self.mandatory_skills)
        roles_form.addRow(self.lbl_excluded_roles, self.excluded_roles)
        roles_form.addRow(self.lbl_excluded_skills, self.excluded_skills)
        roles_form.addRow(self.lbl_excluded_keywords, self.excluded_keywords)
        roles_form.addRow(self.lbl_required_keywords, self.required_keywords)
        layout.addWidget(self.roles_box)

        # --- Work mode / geo / employment ---
        self.conditions_box = QGroupBox()
        cond_form = QFormLayout(self.conditions_box)

        self.remote_group = QButtonGroup(self)
        self.remote_group.setExclusive(True)
        self.remote_unset = QRadioButton()
        self.remote_remote = QRadioButton()
        self.remote_hybrid = QRadioButton()
        self.remote_onsite = QRadioButton()
        for i, btn in enumerate(
            (self.remote_unset, self.remote_remote, self.remote_hybrid, self.remote_onsite)
        ):
            self.remote_group.addButton(btn, i)
        remote_row = QHBoxLayout()
        for btn in (
            self.remote_unset,
            self.remote_remote,
            self.remote_hybrid,
            self.remote_onsite,
        ):
            remote_row.addWidget(btn)
        remote_row.addStretch()
        self.lbl_remote = QLabel()
        cond_form.addRow(self.lbl_remote, remote_row)

        self.radius_km = IntentionalWheelDoubleSpinBox()
        self.radius_km.setRange(0, 500)
        self.radius_km.setSuffix(" km")
        self.radius_km.setSpecialValueText("—")
        self.radius_km.setDecimals(0)
        self.lbl_radius = QLabel()
        cond_form.addRow(self.lbl_radius, self.radius_km)

        self.country_de = QCheckBox("DE")
        self.country_at = QCheckBox("AT")
        self.country_ch = QCheckBox("CH")
        country_row = QHBoxLayout()
        for cb in (self.country_de, self.country_at, self.country_ch):
            country_row.addWidget(cb)
        country_row.addStretch()
        self.lbl_countries = QLabel()
        cond_form.addRow(self.lbl_countries, country_row)

        self.full_time = QCheckBox()
        self.part_time = QCheckBox()
        wt_row = QHBoxLayout()
        wt_row.addWidget(self.full_time)
        wt_row.addWidget(self.part_time)
        wt_row.addStretch()
        self.lbl_working_time = QLabel()
        cond_form.addRow(self.lbl_working_time, wt_row)

        self.emp_permanent = QCheckBox()
        self.emp_temporary = QCheckBox()
        self.emp_contract = QCheckBox()
        emp_row = QHBoxLayout()
        for cb in (self.emp_permanent, self.emp_temporary, self.emp_contract):
            emp_row.addWidget(cb)
        emp_row.addStretch()
        self.lbl_employment = QLabel()
        cond_form.addRow(self.lbl_employment, emp_row)

        self.salary_min = IntentionalWheelDoubleSpinBox()
        self.salary_min.setRange(0, 500_000)
        self.salary_min.setSuffix(" €")
        self.salary_min.setSpecialValueText("—")
        self.salary_min.setDecimals(0)
        self.salary_min.setSingleStep(1000)
        self.lbl_salary = QLabel()
        cond_form.addRow(self.lbl_salary, self.salary_min)

        layout.addWidget(self.conditions_box)

        # --- Strictness (explicit; never invent BALANCED) ---
        self.strictness_box = QGroupBox()
        strict_form = QFormLayout(self.strictness_box)
        self.strictness = QComboBox()
        self.strictness.setObjectName("KkInput")
        self.lbl_strictness = QLabel()
        self.strictness_hint = QLabel()
        self.strictness_hint.setObjectName("PageSubtitle")
        self.strictness_hint.setWordWrap(True)
        strict_form.addRow(self.lbl_strictness, self.strictness)
        strict_form.addRow(self.strictness_hint)
        layout.addWidget(self.strictness_box)

        self.review_banner = QLabel()
        self.review_banner.setObjectName("PageSubtitle")
        self.review_banner.setWordWrap(True)
        self.review_banner.setVisible(False)
        layout.addWidget(self.review_banner)

        self.save_btn = QPushButton()
        self.save_btn.setObjectName("PrimaryButton")
        self.save_btn.clicked.connect(self.save)
        polish_interactive(self.save_btn)
        layout.addLayout(footer_actions_layout(self.save_btn))
        layout.addStretch()

        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        self.page_title.setText(tr("nav.search"))
        self.page_subtitle.setText(tr("search.subtitle"))
        self.roles_box.setTitle(escape_mnemonic(tr("search.roles_skills")))
        self.lbl_target_roles.setText(tr("search.target_roles"))
        self.lbl_mandatory_skills.setText(tr("search.mandatory_skills"))
        self.lbl_excluded_roles.setText(tr("search.excluded_roles"))
        self.lbl_excluded_skills.setText(tr("search.excluded_skills"))
        self.lbl_excluded_keywords.setText(tr("search.excluded_keywords"))
        self.lbl_required_keywords.setText(tr("search.required_keywords"))
        for editor in (
            self.target_roles,
            self.mandatory_skills,
            self.excluded_roles,
            self.excluded_skills,
            self.excluded_keywords,
            self.required_keywords,
        ):
            editor.retranslate()

        self.conditions_box.setTitle(escape_mnemonic(tr("search.conditions")))
        self.lbl_remote.setText(tr("search.remote_mode"))
        self.remote_unset.setText(tr("search.remote_unset"))
        self.remote_remote.setText(tr("remote"))
        self.remote_hybrid.setText(tr("hybrid"))
        self.remote_onsite.setText(tr("onsite"))
        self.lbl_radius.setText(tr("search.radius"))
        self.lbl_countries.setText(tr("search.countries"))
        self.lbl_working_time.setText(tr("search.working_time"))
        self.full_time.setText(tr("full_time"))
        self.part_time.setText(tr("part_time"))
        self.lbl_employment.setText(tr("search.employment_types"))
        self.emp_permanent.setText(tr("search.emp_permanent"))
        self.emp_temporary.setText(tr("search.emp_temporary"))
        self.emp_contract.setText(tr("search.emp_contract"))
        self.lbl_salary.setText(tr("search.salary_min"))

        self.strictness_box.setTitle(tr("search.strictness"))
        self.lbl_strictness.setText(tr("search.strictness_label"))
        self.strictness_hint.setText(tr("search.strictness_hint"))
        current = self.strictness.currentData()
        self.strictness.blockSignals(True)
        self.strictness.clear()
        self.strictness.addItem(tr("search.strictness_unset"), None)
        self.strictness.addItem(tr("search.strictness_strict"), Strictness.STRICT.value)
        self.strictness.addItem(tr("search.strictness_balanced"), Strictness.BALANCED.value)
        self.strictness.addItem(tr("search.strictness_explore"), Strictness.EXPLORE.value)
        idx = self.strictness.findData(current)
        self.strictness.setCurrentIndex(idx if idx >= 0 else 0)
        self.strictness.blockSignals(False)

        self.save_btn.setText(tr("btn.save_search"))
        apply_button_icon(self.save_btn, "save", color="#ffffff")

    def _resolve_intent(self, profile) -> SearchIntent:
        raw = getattr(profile, "search_intent", None)
        if raw is None:
            return empty_search_intent()
        if hasattr(raw, "model_dump"):
            return raw  # type: ignore[return-value]
        if isinstance(raw, dict):
            return parse_search_intent(raw)
        return empty_search_intent()

    def load_from_config(self) -> None:
        cfg = self.config_service.load()
        intent = self._resolve_intent(cfg.profile)
        self.target_roles.set_items(list(intent.target_roles or []))
        self.mandatory_skills.set_items(list(intent.mandatory_skills or []))
        self.excluded_roles.set_items(list(intent.excluded_roles or []))
        self.excluded_skills.set_items(list(intent.excluded_skills or []))
        self.excluded_keywords.set_items(list(intent.excluded_keywords or []))
        self.required_keywords.set_items(list(intent.required_keywords or []))

        mode = (intent.remote_mode or "").strip().lower()
        mapping = {
            "": self.remote_unset,
            "remote": self.remote_remote,
            "hybrid": self.remote_hybrid,
            "onsite": self.remote_onsite,
            "flexible": self.remote_unset,
        }
        btn = mapping.get(mode, self.remote_unset)
        btn.setChecked(True)

        if intent.radius_km is None:
            self.radius_km.setValue(0)
        else:
            self.radius_km.setValue(float(intent.radius_km))

        countries = {c.upper() for c in (intent.countries or [])}
        self.country_de.setChecked("DE" in countries)
        self.country_at.setChecked("AT" in countries)
        self.country_ch.setChecked("CH" in countries)

        wt = {w.casefold() for w in (intent.working_time or [])}
        self.full_time.setChecked("full_time" in wt)
        self.part_time.setChecked("part_time" in wt)

        emp = {e.casefold() for e in (intent.employment_types or [])}
        self.emp_permanent.setChecked("permanent" in emp or "unbefristet" in emp)
        self.emp_temporary.setChecked("temporary" in emp)
        self.emp_contract.setChecked("contract" in emp)

        if intent.salary_min is None:
            self.salary_min.setValue(0)
        else:
            self.salary_min.setValue(float(intent.salary_min))

        strict_val = intent.strictness.value if intent.strictness else None
        idx = self.strictness.findData(strict_val)
        self.strictness.setCurrentIndex(idx if idx >= 0 else 0)

        review = list(intent.needs_user_review or [])
        if review:
            self.review_banner.setText(
                tr("search.needs_review") + "\n• " + "\n• ".join(review[:8])
            )
            self.review_banner.setVisible(True)
        else:
            self.review_banner.clear()
            self.review_banner.setVisible(False)

    def collect_intent(self) -> SearchIntent:
        """Build SearchIntent from widgets — no silent STRICT expansion."""
        remote_mode = None
        if self.remote_remote.isChecked():
            remote_mode = "remote"
        elif self.remote_hybrid.isChecked():
            remote_mode = "hybrid"
        elif self.remote_onsite.isChecked():
            remote_mode = "onsite"
        if remote_mode is not None and remote_mode not in REMOTE_MODE_VALUES:
            remote_mode = None

        countries: list[str] = []
        if self.country_de.isChecked():
            countries.append("DE")
        if self.country_at.isChecked():
            countries.append("AT")
        if self.country_ch.isChecked():
            countries.append("CH")

        working_time: list[str] = []
        if self.full_time.isChecked():
            working_time.append("full_time")
        if self.part_time.isChecked():
            working_time.append("part_time")

        employment_types: list[str] = []
        if self.emp_permanent.isChecked():
            employment_types.append("permanent")
        if self.emp_temporary.isChecked():
            employment_types.append("temporary")
        if self.emp_contract.isChecked():
            employment_types.append("contract")

        radius_val = float(self.radius_km.value())
        radius_km = None if radius_val <= 0 else radius_val
        salary_val = float(self.salary_min.value())
        salary_min = None if salary_val <= 0 else salary_val

        strict_data = self.strictness.currentData()
        strictness = None
        if strict_data:
            strictness = Strictness(str(strict_data))

        # Preserve review flags from existing intent except conflicts recompute.
        cfg = self.config_service.load()
        existing = self._resolve_intent(cfg.profile)
        preserved_review = [
            f
            for f in (existing.needs_user_review or [])
            if not str(f).startswith("conflict:")
        ]

        return SearchIntent(
            target_roles=self.target_roles.get_items(),
            mandatory_skills=self.mandatory_skills.get_items(),
            excluded_roles=self.excluded_roles.get_items(),
            excluded_skills=self.excluded_skills.get_items(),
            excluded_keywords=self.excluded_keywords.get_items(),
            required_keywords=self.required_keywords.get_items(),
            preferred_skills=list(existing.preferred_skills or []),
            preferred_industries=list(existing.preferred_industries or []),
            excluded_industries=list(existing.excluded_industries or []),
            required_roles=list(existing.required_roles or []),
            remote_mode=remote_mode,
            countries=countries,
            radius_km=radius_km,
            working_time=working_time,
            employment_types=employment_types,
            salary_min=salary_min,
            strictness=strictness,
            needs_user_review=preserved_review,
            legacy_fields_deprecated=list(existing.legacy_fields_deprecated or []),
        )

    def save(self) -> None:
        cfg = self.config_service.load()
        intent = self.collect_intent()
        cfg.profile.search_intent = intent
        # Dual-write clearly mapped mirrors for pre-cutover readers (no invention).
        sync_legacy_jobs_from_intent(intent, cfg.profile.jobs)
        loc = cfg.profile.location
        emp = cfg.profile.employment
        if intent.radius_km is not None:
            loc.max_distance_km = float(intent.radius_km)
        if intent.countries:
            # Keep primary residence country if single; else leave location.country.
            if len(intent.countries) == 1:
                loc.country = intent.countries[0]
        if intent.salary_min is not None:
            emp.minimum_salary = float(intent.salary_min)
        emp.full_time = "full_time" in intent.working_time
        emp.part_time = "part_time" in intent.working_time
        emp.remote = intent.remote_mode == "remote"
        emp.hybrid = intent.remote_mode == "hybrid"
        emp.onsite = intent.remote_mode == "onsite"
        excl = list(intent.excluded_keywords or [])
        cfg.profile.filters.exclusion_keywords = excl

        errors = self.config_service.validate(cfg)
        if errors:
            QMessageBox.warning(self, tr("nav.search"), "\n".join(errors))
            return
        self.config_service.save(cfg)
        self.load_from_config()
        QMessageBox.information(self, tr("nav.search"), tr("search.saved"))

    def refresh(self) -> None:
        self.load_from_config()

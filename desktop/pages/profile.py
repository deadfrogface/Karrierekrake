"""Profile page — demo-aligned read cards + edit drawers (not an endless form).

SearchIntent editing lives on ``desktop.pages.search.SearchPage``.
Legacy combined Berufswunsch UI is feature-flaggable for rollback.
"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.salary import normalize_to_annual_gross_eur
from desktop.design_system.a11y import set_accessible_name
from desktop.design_system.polish import (
    apply_button_icon,
    footer_actions_layout,
    polish_card,
    polish_interactive,
)
from desktop.design_system.v2_chrome import (
    DataItem,
    ProfileSectionCard,
    SectionEditDrawer,
    TagChip,
)
from desktop.i18n import TRANSLATIONS, tr
from desktop.pages.profile_sections import (
    ApplicantSection,
    CareerSection,
    CvSection,
    EducationSection,
    ExperienceSection,
    LanguagesSection,
    LocationWorkSection,
    QualificationsSection,
)
from desktop.services import ConfigService
from desktop.services.profile_merge import (
    clear_cv_personal,
    keep_manual_qualifications,
    sync_application_summaries,
)
from desktop.widgets.confirm_dialog import confirm_action
from desktop.widgets.cv_import_dialog import CvImportDialog
from desktop.widgets.scroll_page import wrap_scrollable
from desktop.widgets.wheel_guard import apply_wheel_guard_to_spinboxes


def legacy_profile_search_ui_enabled(settings=None) -> bool:
    """Rollback: show combined Bewerbungswunsch UI on Profile.

    Env ``KARRIEREKRAKE_LEGACY_PROFILE_SEARCH=1`` or
    ``settings.legacy_profile_search_ui`` (temporary).
    """
    env = (os.environ.get("KARRIEREKRAKE_LEGACY_PROFILE_SEARCH") or "").strip().lower()
    if env in {"1", "true", "yes", "on"}:
        return True
    if settings is not None and bool(getattr(settings, "legacy_profile_search_ui", False)):
        return True
    return False


def _dash(value: object) -> str:
    text = str(value or "").strip()
    return text if text else "—"


def _entry_title(entry: object) -> str:
    for attr in ("title", "qualification", "degree", "name", "value"):
        val = getattr(entry, attr, None)
        if val:
            return str(val)
    if hasattr(entry, "label"):
        try:
            label = entry.label()
            if label:
                return str(label)
        except Exception:
            pass
    return "—"


def _entry_subtitle(entry: object) -> str:
    parts: list[str] = []
    for attr in ("company", "institution", "school", "city", "location"):
        val = getattr(entry, attr, None)
        if val:
            parts.append(str(val))
    start = getattr(entry, "start", None) or getattr(entry, "start_date", None) or ""
    end = getattr(entry, "end", None) or getattr(entry, "end_date", None) or ""
    if start or end:
        parts.append(f"{start or '?'} – {end or tr('profile.present')}")
    return " · ".join(parts)


def _entry_description(entry: object) -> str:
    """Full experience/education body text — never silently truncate responsibilities."""
    for attr in ("description", "summary"):
        val = getattr(entry, attr, None)
        if val and str(val).strip():
            return str(val).strip()
    resp = getattr(entry, "responsibilities", None)
    if isinstance(resp, (list, tuple)):
        lines = [str(x).strip() for x in resp if str(x).strip()]
        if lines:
            return "\n".join(f"• {line}" for line in lines)
    return ""


class ProfilePage(QWidget):
    def __init__(self, config_service: ConfigService, parent=None) -> None:
        super().__init__(parent)
        self.config_service = config_service
        self._career_persist = False  # True when Berufsziel drawer saves profile.jobs
        self._exp_limit = 2
        self._skill_limit = 8

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        # Hidden host keeps section editors alive for tests + drawers.
        self._editors_host = QWidget(self)
        self._editors_host.hide()
        host_layout = QVBoxLayout(self._editors_host)
        host_layout.setContentsMargins(0, 0, 0, 0)

        self.career = CareerSection()
        self.career.suggest_titles_btn.clicked.connect(self.suggest_titles_from_cv)
        self.experience = ExperienceSection()
        self.education = EducationSection()
        self.qualifications = QualificationsSection()
        self.languages = LanguagesSection()
        self.location_work = LocationWorkSection(include_search_fields=False)
        self.applicant = ApplicantSection()
        self.cv = CvSection()
        self.cv.cv_select.clicked.connect(self.select_cv)
        self.cv.cv_import.clicked.connect(self.import_from_cv)
        self.cv.cv_reset.clicked.connect(self.reset_profile)
        for section in (
            self.career,
            self.experience,
            self.education,
            self.qualifications,
            self.languages,
            self.location_work,
            self.applicant,
            self.cv,
        ):
            host_layout.addWidget(section)
            section.hide()

        self._drawer = SectionEditDrawer(parent=self)

        # Visible demo composition
        shell = QWidget()
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(8, 8, 16, 16)
        shell_layout.setSpacing(16)

        header = QHBoxLayout()
        self.page_title = QLabel()
        self.page_title.setObjectName("PageTitle")
        self.page_subtitle = QLabel()
        self.page_subtitle.setObjectName("PageSubtitle")
        self.page_subtitle.setWordWrap(True)
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title_col.addWidget(self.page_title)
        title_col.addWidget(self.page_subtitle)
        header.addLayout(title_col, stretch=1)
        # Top-right reserved for secondary icon-actions only (no primary CTAs)
        shell_layout.addLayout(header)

        self.import_cv_btn = QPushButton()
        self.import_cv_btn.setObjectName("PrimaryButton")
        self.import_cv_btn.setAccessibleDescription("kk.profile.import_cv")
        self.import_cv_btn.clicked.connect(self.import_from_cv)
        polish_interactive(self.import_cv_btn)

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(16)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        self.card_personal = ProfileSectionCard()
        self.card_personal.action_btn.clicked.connect(lambda: self._edit_section("personal"))
        self._personal_grid = QGridLayout()
        self._personal_items = [DataItem() for _ in range(8)]
        for i, item in enumerate(self._personal_items):
            self._personal_grid.addWidget(item, i // 2, i % 2)
        self.card_personal.body().addLayout(self._personal_grid)

        self.card_career = ProfileSectionCard()
        self.card_career.action_btn.clicked.connect(lambda: self._edit_section("career"))
        self._wanted_row = QHBoxLayout()
        self._wanted_row.setSpacing(8)
        self._unwanted_row = QHBoxLayout()
        self._unwanted_row.setSpacing(8)
        self._wanted_label = QLabel()
        self._wanted_label.setObjectName("KkHint")
        self._unwanted_label = QLabel()
        self._unwanted_label.setObjectName("KkHint")
        self.card_career.body().addWidget(self._wanted_label)
        self.card_career.body().addLayout(self._wanted_row)
        self.card_career.body().addWidget(self._unwanted_label)
        self.card_career.body().addLayout(self._unwanted_row)

        self.card_application = ProfileSectionCard()
        self.card_application.action_btn.clicked.connect(lambda: self._edit_section("application"))
        self._app_grid = QGridLayout()
        self._app_items = [DataItem() for _ in range(6)]
        for i, item in enumerate(self._app_items):
            self._app_grid.addWidget(item, i // 2, i % 2)
        self.card_application.body().addLayout(self._app_grid)

        self.card_docs = ProfileSectionCard()
        self.card_docs.action_btn.clicked.connect(lambda: self._edit_section("docs"))
        self._cv_name = QLabel()
        self._cv_name.setObjectName("PageSubtitle")
        self._cv_meta = QLabel()
        self._cv_meta.setObjectName("KkHint")
        self.replace_cv_btn = QPushButton()
        self.replace_cv_btn.setObjectName("SecondaryButton")
        self.replace_cv_btn.clicked.connect(self.select_cv)
        doc_row = QHBoxLayout()
        doc_info = QVBoxLayout()
        doc_info.addWidget(self._cv_name)
        doc_info.addWidget(self._cv_meta)
        doc_row.addLayout(doc_info, stretch=1)
        doc_row.addWidget(self.replace_cv_btn)
        self.card_docs.body().addLayout(doc_row)
        self._linkedin = QLabel()
        self._linkedin.setObjectName("PageSubtitle")
        self._linkedin.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self._linkedin.setOpenExternalLinks(True)
        self.card_docs.body().addWidget(self._linkedin)
        self.reset_btn = QPushButton()
        self.reset_btn.setObjectName("SecondaryButton")
        self.reset_btn.clicked.connect(self.reset_profile)
        self.card_docs.body().addWidget(self.reset_btn)

        self.card_experience = ProfileSectionCard()
        self.card_experience.action_btn.clicked.connect(lambda: self._edit_section("experience"))
        self._exp_body = self.card_experience.body()
        self._exp_more = QPushButton()
        self._exp_more.setObjectName("SecondaryButton")
        self._exp_more.setFlat(True)
        self._exp_more.clicked.connect(self._show_more_experience)

        self.card_education = ProfileSectionCard()
        self.card_education.action_btn.clicked.connect(lambda: self._edit_section("education"))
        self._edu_body = self.card_education.body()

        self.card_skills = ProfileSectionCard()
        self.card_skills.action_btn.clicked.connect(lambda: self._edit_section("skills"))
        self._skills_row = QHBoxLayout()
        self._skills_row.setSpacing(8)
        self.card_skills.body().addLayout(self._skills_row)

        self.card_languages = ProfileSectionCard()
        self.card_languages.action_btn.clicked.connect(lambda: self._edit_section("languages"))
        self._lang_body = self.card_languages.body()

        left = QVBoxLayout()
        left.setSpacing(16)
        for card in (self.card_personal, self.card_career, self.card_application, self.card_docs):
            left.addWidget(card)
        left.addStretch()
        right = QVBoxLayout()
        right.setSpacing(16)
        for card in (self.card_experience, self.card_education, self.card_skills, self.card_languages):
            right.addWidget(card)
        right.addStretch()
        left_w = QWidget()
        left_w.setLayout(left)
        right_w = QWidget()
        right_w.setLayout(right)
        grid.addWidget(left_w, 0, 0)
        grid.addWidget(right_w, 0, 1)
        shell_layout.addLayout(grid)

        # Compatibility: keep a save button (hidden) for callers that click it.
        self.save_btn = QPushButton()
        self.save_btn.setObjectName("PrimaryButton")
        self.save_btn.clicked.connect(self.save)
        self.save_btn.hide()

        # Primary import CTA — bottom-right of the profile shell
        shell_layout.addLayout(footer_actions_layout(self.import_cv_btn, self.save_btn))

        for card in (
            self.card_personal,
            self.card_career,
            self.card_application,
            self.card_docs,
            self.card_experience,
            self.card_education,
            self.card_skills,
            self.card_languages,
        ):
            polish_card(card)

        outer.addWidget(wrap_scrollable(shell))

        apply_wheel_guard_to_spinboxes(self)
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        no_cv = {table.get("profile.no_cv", "") for table in TRANSLATIONS.values()}
        self.page_title.setText(tr("nav.profile"))
        self.page_subtitle.setText(tr("profile.subtitle"))
        self.import_cv_btn.setText(tr("profile.import_from_cv"))
        set_accessible_name(self.import_cv_btn, tr("profile.import_from_cv"))
        apply_button_icon(self.import_cv_btn, "import", color="#ffffff")
        self.card_personal.set_title(tr("profile.card_personal"))
        self.card_personal.set_action_text(tr("profile.edit"))
        self.card_career.set_title(tr("profile.card_career"))
        self.card_career.set_action_text(tr("profile.edit"))
        self.card_application.set_title(tr("profile.card_application"))
        self.card_application.set_action_text(tr("profile.edit"))
        self.card_docs.set_title(tr("profile.card_docs"))
        self.card_docs.set_action_text(tr("profile.edit"))
        self.card_experience.set_title(tr("profile.experience"))
        self.card_experience.set_action_text(tr("profile.add"))
        self.card_education.set_title(tr("profile.education"))
        self.card_education.set_action_text(tr("profile.add"))
        self.card_skills.set_title(tr("profile.card_skills_certs"))
        self.card_skills.set_action_text(tr("profile.edit"))
        self.card_languages.set_title(tr("profile.languages"))
        self.card_languages.set_action_text(tr("profile.edit"))
        self._wanted_label.setText(tr("profile.desired_short"))
        self._unwanted_label.setText(tr("profile.excluded"))
        self.replace_cv_btn.setText(tr("profile.replace_cv"))
        self.reset_btn.setText(tr("profile.reset"))
        self.save_btn.setText(tr("btn.save_profile"))
        self.career.retranslate()
        self.experience.retranslate()
        self.education.retranslate()
        self.qualifications.retranslate()
        self.languages.retranslate()
        self.location_work.retranslate()
        self.applicant.retranslate()
        self.cv.retranslate(no_cv_tokens=no_cv)
        self._drawer.set_texts(
            title=tr("profile.edit"),
            save=tr("btn.save"),
            cancel=tr("btn.cancel"),
        )

    def _apply_legacy_visibility(self) -> None:
        cfg = self.config_service.load()
        legacy = legacy_profile_search_ui_enabled(cfg.settings)
        self.location_work._set_search_fields_visible(legacy)
        self.location_work.retranslate()
        # Editors stay in hidden host; flag must flip isHidden() for tests.
        self.career.setHidden(not legacy)

    def _clear_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _edit_section(self, key: str) -> None:
        mapping = {
            "personal": (self.applicant, tr("profile.card_personal")),
            "career": (self.career, tr("profile.card_career")),
            "application": (self.applicant, tr("profile.card_application")),
            "docs": (self.cv, tr("profile.card_docs")),
            "experience": (self.experience, tr("profile.experience")),
            "education": (self.education, tr("profile.education")),
            "skills": (self.qualifications, tr("profile.card_skills")),
            "languages": (self.languages, tr("profile.languages")),
        }
        section, title = mapping[key]
        self._career_persist = key == "career"
        self._drawer.set_texts(
            title=title,
            save=tr("btn.save"),
            cancel=tr("btn.cancel"),
        )
        # Detach from hidden host
        section.setParent(None)
        section.show()
        result = self._drawer.present(section)
        self._drawer.take_content()
        section.setParent(self._editors_host)
        self._editors_host.layout().addWidget(section)
        legacy = legacy_profile_search_ui_enabled(self.config_service.load().settings)
        if key == "career":
            section.setHidden(not legacy)
        else:
            section.hide()
        if result == SectionEditDrawer.DialogCode.Accepted:
            self.save()
            self.refresh_cards()

    def load_from_config(self) -> None:
        self._apply_legacy_visibility()
        cfg = self.config_service.load()
        p = cfg.profile
        self.career.load(p.jobs)
        self.experience.load(p.qualifications)
        self.education.load(p.qualifications)
        self.qualifications.load(p.qualifications)
        self.languages.load(p.qualifications)
        self.location_work.load(p.location, p.employment, p.filters)
        self.applicant.load(
            cfg.application,
            sync_address_to_search=self.config_service.get_sync_address_to_search(),
        )
        self.cv.cv_label.setText(
            self.config_service.get_active_cv_info().get("label")
            or cfg.application.cv_path
            or tr("profile.no_cv")
        )
        self.refresh_cards()

    def refresh_cards(self) -> None:
        cfg = self.config_service.load()
        a = cfg.application
        pairs = [
            (tr("field.first_name"), a.first_name),
            (tr("field.last_name"), a.last_name),
            (tr("field.street"), a.street),
            (tr("field.postal") + " / " + tr("field.city"), f"{a.postal_code} {a.city}".strip()),
            (tr("field.country"), a.country or cfg.profile.location.country),
            (tr("field.dob"), a.date_of_birth),
            (tr("field.email"), a.email),
            (tr("field.phone"), a.phone),
        ]
        for item, (label, value) in zip(self._personal_items, pairs):
            item.set_pair(label, _dash(value))

        self._clear_layout(self._wanted_row)
        wanted = list(cfg.profile.jobs.desired_titles or [])
        for title in wanted[:6]:
            self._wanted_row.addWidget(TagChip(str(title), kind="wanted"))
        if not wanted:
            self._wanted_row.addWidget(TagChip(tr("profile.empty_tags"), kind="more"))
        self._wanted_row.addStretch()

        self._clear_layout(self._unwanted_row)
        unwanted = list(cfg.profile.jobs.unwanted_titles or [])
        for title in unwanted[:6]:
            self._unwanted_row.addWidget(TagChip(str(title), kind="unwanted"))
        if not unwanted:
            self._unwanted_row.addWidget(TagChip(tr("profile.empty_tags"), kind="more"))
        self._unwanted_row.addStretch()

        app_pairs = [
            (tr("field.notice"), a.notice_period),
            (tr("field.start"), a.earliest_start_date),
            (tr("field.salary"), a.salary_expectation),
            (tr("field.current_job"), a.current_employment),
            (tr("field.work_auth"), a.work_authorization),
            (tr("field.remote_pref"), a.remote_preference),
        ]
        for item, (label, value) in zip(self._app_items, app_pairs):
            item.set_pair(label, _dash(value))

        info = self.config_service.get_active_cv_info()
        self._cv_name.setText(info.get("label") or a.cv_path or tr("profile.no_cv"))
        self._cv_meta.setText(tr("profile.cv_meta"))
        linkedin = (getattr(a, "linkedin_url", None) or "").strip()
        if linkedin:
            self._linkedin.setText(f'<a href="{linkedin}">LinkedIn</a>')
        else:
            self._linkedin.setText(tr("profile.no_linkedin"))

        # Experience timeline (progressive)
        while self._exp_body.count():
            item = self._exp_body.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        experiences = list(cfg.profile.qualifications.work_experience or [])
        for entry in experiences[: self._exp_limit]:
            block = QVBoxLayout()
            title = QLabel(_entry_title(entry))
            title.setObjectName("NextActionTitle")
            title.setWordWrap(True)
            title.setToolTip(_entry_title(entry))
            sub = QLabel(_entry_subtitle(entry))
            sub.setObjectName("KkHint")
            sub.setWordWrap(True)
            body = _entry_description(entry)
            desc = QLabel(_dash(body) if body else "—")
            desc.setObjectName("PageSubtitle")
            desc.setWordWrap(True)
            if body:
                desc.setToolTip(body)
            wrap = QWidget()
            vl = QVBoxLayout(wrap)
            vl.setContentsMargins(0, 0, 0, 8)
            vl.setSpacing(2)
            vl.addWidget(title)
            vl.addWidget(sub)
            if body:
                vl.addWidget(desc)
            self._exp_body.addWidget(wrap)
        if len(experiences) > self._exp_limit:
            self._exp_more.setText(tr("profile.show_more_entries", n=len(experiences) - self._exp_limit))
            self._exp_body.addWidget(self._exp_more)
        if not experiences:
            empty = QLabel(tr("profile.empty_section"))
            empty.setObjectName("KkHint")
            self._exp_body.addWidget(empty)

        while self._edu_body.count():
            item = self._edu_body.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        education = list(cfg.profile.qualifications.education or [])
        for entry in education[:8]:
            wrap = QWidget()
            vl = QVBoxLayout(wrap)
            vl.setContentsMargins(0, 0, 0, 8)
            title = QLabel(_entry_title(entry))
            title.setObjectName("NextActionTitle")
            sub = QLabel(_entry_subtitle(entry))
            sub.setObjectName("KkHint")
            vl.addWidget(title)
            vl.addWidget(sub)
            self._edu_body.addWidget(wrap)
        if not education:
            empty = QLabel(tr("profile.empty_section"))
            empty.setObjectName("KkHint")
            self._edu_body.addWidget(empty)

        self._clear_layout(self._skills_row)
        skills = list(cfg.profile.qualifications.skill_values() or [])
        software = list(cfg.profile.qualifications.software_values() or [])
        certs = list(cfg.profile.qualifications.certificates or [])
        chips: list[tuple[str, str]] = []
        for s in skills:
            if str(s).strip():
                chips.append((str(s), "neutral"))
        for s in software:
            if str(s).strip():
                chips.append((str(s), "wanted"))
        for cert in certs:
            title = _entry_title(cert)
            if title and title != "—":
                chips.append((title, "more"))
        for chip, kind in chips[: self._skill_limit]:
            self._skills_row.addWidget(TagChip(chip, kind=kind))
        remaining = len(chips) - self._skill_limit
        if remaining > 0:
            self._skills_row.addWidget(TagChip(tr("profile.more_tags", n=remaining), kind="more"))
        if not chips:
            self._skills_row.addWidget(TagChip(tr("profile.empty_tags"), kind="more"))
        self._skills_row.addStretch()

        while self._lang_body.count():
            item = self._lang_body.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        langs = list(cfg.profile.qualifications.languages or [])
        for lang in langs[:8]:
            name = getattr(lang, "language", None) or getattr(lang, "name", None) or getattr(lang, "value", "")
            level = getattr(lang, "level", None) or getattr(lang, "proficiency", "") or ""
            text = f"{name}" + (f" ({level})" if level else "")
            chip = TagChip(str(text), kind="neutral")
            chip.setToolTip(str(text))
            self._lang_body.addWidget(chip)
        if not langs:
            empty = QLabel(tr("profile.empty_section"))
            empty.setObjectName("KkHint")
            self._lang_body.addWidget(empty)

    def _show_more_experience(self) -> None:
        self._exp_limit = 50
        self.refresh_cards()

    def suggest_titles_from_cv(self) -> None:
        """Propose job titles from stored CV / qualifications — never overwrite manuals."""
        from core.cv_parser import parse_cv_text
        from core.job_title_suggestions import suggest_job_titles

        cfg = self.config_service.load()
        parsed: dict = {}
        cv_path = (cfg.application.cv_path or "").strip()
        if cv_path:
            try:
                from core.cv_extract import extract_text

                text = extract_text(Path(cv_path))
                parsed = parse_cv_text(text or "")
            except Exception:
                parsed = {}
        if not parsed:
            quals = cfg.profile.qualifications
            parsed = {
                "work_experience": [
                    {
                        "title": getattr(e, "title", "") or getattr(e, "value", ""),
                        "description": getattr(e, "description", ""),
                    }
                    for e in (getattr(quals, "work_experience", None) or [])
                ],
                "education": [
                    {
                        "degree": getattr(e, "degree", "") or getattr(e, "value", ""),
                        "field": getattr(e, "field", ""),
                    }
                    for e in (getattr(quals, "education", None) or [])
                ],
                "skills": [
                    getattr(s, "value", s) for s in (getattr(quals, "skills", None) or [])
                ],
                "software": [
                    getattr(s, "value", s) for s in (getattr(quals, "software", None) or [])
                ],
                "certificates": [
                    getattr(s, "name", getattr(s, "value", s))
                    for s in (getattr(quals, "certificates", None) or [])
                ],
            }
        desired = list(self.career.desired_titles.get_items())
        suggestions = suggest_job_titles(
            parsed, existing_desired=desired, existing_alternative=[]
        )
        # Only propose desired titles — never silently prefill exclusions.
        # User must add Ausschlüsse explicitly (or confirm via a future picker).
        proposed = list(
            dict.fromkeys(
                suggestions.get("desired", []) + suggestions.get("alternative", [])
            )
        )
        if not proposed:
            QMessageBox.information(self, tr("app.name"), tr("msg.titles_suggested"))
            return
        merged_d = list(dict.fromkeys(desired + proposed))
        self.career.desired_titles.set_items(merged_d)
        QMessageBox.information(self, tr("app.name"), tr("msg.titles_suggested"))

    def select_cv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("btn.select_cv"),
            "",
            "Dokumente (*.pdf *.docx);;Alle Dateien (*.*)",
        )
        if not path:
            return
        dest = self.config_service.copy_cv_into_storage(
            Path(path), label="Default CV", role="cv"
        )
        info = self.config_service.get_active_cv_info()
        self.cv.cv_label.setText(info.get("label") or str(dest))
        self.refresh_cards()
        QMessageBox.information(self, tr("profile.cv"), tr("profile.cv_saved"))

    def import_from_cv(self) -> None:
        cfg = self.config_service.load()
        cv_path = Path(cfg.application.cv_path) if cfg.application.cv_path else None
        if not cv_path or not cv_path.exists():
            path, _ = QFileDialog.getOpenFileName(
                self,
                tr("btn.import_cv"),
                "",
                "Dokumente (*.pdf *.docx)",
            )
            if not path:
                return
            cv_path = self.config_service.copy_cv_into_storage(Path(path), role="cv")
            info = self.config_service.get_active_cv_info()
            self.cv.cv_label.setText(info.get("label") or str(cv_path))
            cfg = self.config_service.load()

        dlg = CvImportDialog(cv_path, cfg.profile.qualifications, cfg.application, self)
        if dlg.exec() != dlg.DialogCode.Accepted or dlg.result_quals is None:
            return
        cfg.profile.qualifications = dlg.result_quals
        if dlg.result_application is not None:
            cfg.application = dlg.result_application
        cfg.application.cv_path = str(cv_path)
        self.config_service.save(cfg)
        self.load_from_config()
        QMessageBox.information(self, tr("profile.cv"), tr("profile.cv_updated"))

    def reset_profile(self) -> None:
        """Offer explicit reset/delete scopes — UX text must match what is removed."""
        msg = QMessageBox(self)
        msg.setWindowTitle(tr("profile.reset_title"))
        msg.setText(tr("profile.reset"))
        msg.setInformativeText(tr("profile.reset_choose_scope"))
        cv_btn = msg.addButton(tr("profile.reset_cv_only"), QMessageBox.ButtonRole.AcceptRole)
        profile_btn = msg.addButton(tr("profile.reset_all"), QMessageBox.ButtonRole.DestructiveRole)
        wipe_btn = msg.addButton(
            tr("profile.reset_wipe_all_local"), QMessageBox.ButtonRole.DestructiveRole
        )
        cancel_btn = msg.addButton(tr("btn.cancel"), QMessageBox.ButtonRole.RejectRole)
        msg.setDefaultButton(cancel_btn)
        msg.setEscapeButton(cancel_btn)
        msg.exec()
        clicked = msg.clickedButton()
        if clicked is None or clicked is cancel_btn:
            return
        if clicked is wipe_btn:
            if not confirm_action(
                self,
                tr("profile.reset_title"),
                tr("profile.reset_confirm_wipe_all"),
                confirm_text=tr("privacy.delete_all_confirm_btn"),
                destructive=True,
            ):
                return
            result = self.config_service.delete_all_local_data()
            if not result.get("ok") or not result.get("verified"):
                QMessageBox.warning(
                    self,
                    tr("profile.reset_title"),
                    tr("profile.reset_wipe_failed"),
                )
                self.load_from_config()
                return
            done_msg = tr("profile.reset_wipe_done")
        elif clicked is profile_btn:
            if not confirm_action(
                self,
                tr("profile.reset_title"),
                tr("profile.reset_confirm_all"),
                confirm_text=tr("profile.reset_all"),
                destructive=True,
            ):
                return
            self.config_service.reset_profile_and_documents(clear_search_prefs=False)
            done_msg = tr("profile.reset_done")
        elif clicked is cv_btn:
            if not confirm_action(
                self,
                tr("profile.reset_title"),
                tr("profile.reset_confirm_cv"),
                confirm_text=tr("profile.reset_cv_only"),
                destructive=True,
            ):
                return
            self.config_service.clear_cv_storage()
            cfg = self.config_service.load()
            cfg.profile.qualifications = keep_manual_qualifications(cfg.profile.qualifications)
            cfg.application = clear_cv_personal(cfg.application)
            cfg.application.cv_path = ""
            self.config_service.save(cfg)
            done_msg = tr("profile.reset_done")
        else:
            return
        self.load_from_config()
        QMessageBox.information(self, tr("profile.reset_title"), done_msg)

    def save(self) -> None:
        cfg = self.config_service.load()
        p = cfg.profile
        legacy = legacy_profile_search_ui_enabled(cfg.settings)
        # Persist career goals when legacy OR when user edited Berufsziel drawer.
        # Never push into SearchIntent unless legacy combined UI is on — except
        # when clearing/editing Berufsziel: deleted profile values must not stay
        # in SearchIntent (matching / hard filters).
        if legacy or self._career_persist:
            self.career.save_into(p.jobs)
            from core.search_intent import (
                apply_clear_jobs_edit_to_intent,
                empty_search_intent,
                parse_search_intent,
            )

            raw_intent = getattr(p, "search_intent", None)
            if raw_intent is None:
                intent = empty_search_intent()
            elif hasattr(raw_intent, "model_dump"):
                intent = raw_intent
            elif isinstance(raw_intent, dict):
                intent = parse_search_intent(raw_intent)
            else:
                intent = empty_search_intent()
            p.search_intent = apply_clear_jobs_edit_to_intent(intent, p.jobs)
        self.experience.save_into(p.qualifications)
        self.education.save_into(p.qualifications)
        self.qualifications.save_into(p.qualifications)
        self.languages.save_into(p.qualifications)
        self.location_work.save_into(p.location, p.employment, p.filters)

        if legacy:
            from core.search_intent import (
                apply_clear_jobs_edit_to_intent,
                apply_location_employment_to_intent,
                empty_search_intent,
                parse_search_intent,
            )

            raw_intent = getattr(p, "search_intent", None)
            if raw_intent is None:
                intent = empty_search_intent()
            elif hasattr(raw_intent, "model_dump"):
                intent = raw_intent
            elif isinstance(raw_intent, dict):
                intent = parse_search_intent(raw_intent)
            else:
                intent = empty_search_intent()
            p.search_intent = apply_clear_jobs_edit_to_intent(intent, p.jobs)
            p.search_intent = apply_location_employment_to_intent(
                p.search_intent, location=p.location, employment=p.employment
            )
            excl = [
                str(x).strip()
                for x in (p.filters.exclusion_keywords or [])
                if str(x).strip()
            ]
            if excl != list(p.search_intent.excluded_keywords):
                data = p.search_intent.model_dump()
                data["excluded_keywords"] = excl
                p.search_intent = parse_search_intent(data)

        a = cfg.application
        sync_addr = self.applicant.save_into(a)
        self.config_service.set_sync_address_to_search(sync_addr)
        if sync_addr:
            parts = [
                part
                for part in (
                    a.street.strip(),
                    f"{a.postal_code} {a.city}".strip(),
                    (a.country or "").strip(),
                )
                if part
            ]
            if parts:
                new_home = ", ".join(parts)
                if new_home != (p.location.home_address or "").strip():
                    p.location.home_latitude = None
                    p.location.home_longitude = None
                    p.location.home_geocoded_address = ""
                p.location.home_address = new_home
                self.location_work.home_address.setText(p.location.home_address)

        sync_application_summaries(a, p.qualifications, fill_empty=False)

        annual, _why = normalize_to_annual_gross_eur(text=a.salary_expectation or "")
        if annual and not p.employment.minimum_salary:
            p.employment.minimum_salary = float(annual)
        elif p.employment.minimum_salary and not (a.salary_expectation or "").strip():
            a.salary_expectation = f"{int(p.employment.minimum_salary)} EUR brutto/Jahr"

        errors = self.config_service.validate(cfg)
        if errors:
            QMessageBox.warning(self, tr("nav.profile"), "\n".join(errors))
            return
        self.config_service.save(cfg)
        self._career_persist = False
        self.refresh_cards()
        QMessageBox.information(self, tr("nav.profile"), tr("profile.saved"))

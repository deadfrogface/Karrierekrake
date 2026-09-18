"""Profile page — orchestrates section widgets and CV import/reset."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QFileDialog,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
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
from core.salary import normalize_to_annual_gross_eur
from desktop.services import ConfigService
from desktop.services.profile_merge import (
    clear_cv_personal,
    keep_manual_qualifications,
    sync_application_summaries,
)
from desktop.widgets.cv_import_dialog import CvImportDialog
from desktop.widgets.scroll_page import wrap_scrollable


class ProfilePage(QWidget):
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

        self.career = CareerSection()
        self.career.suggest_titles_btn.clicked.connect(self.suggest_titles_from_cv)
        self.experience = ExperienceSection()
        self.education = EducationSection()
        self.qualifications = QualificationsSection()
        self.languages = LanguagesSection()
        self.location_work = LocationWorkSection()
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
            layout.addWidget(section)

        self.save_btn = QPushButton()
        self.save_btn.setObjectName("PrimaryButton")
        self.save_btn.clicked.connect(self.save)
        layout.addWidget(self.save_btn)
        layout.addStretch()

        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        no_cv = {table.get("profile.no_cv", "") for table in TRANSLATIONS.values()}
        self.career.retranslate()
        self.experience.retranslate()
        self.education.retranslate()
        self.qualifications.retranslate()
        self.languages.retranslate()
        self.location_work.retranslate()
        self.applicant.retranslate()
        self.cv.retranslate(no_cv_tokens=no_cv)
        self.save_btn.setText(tr("btn.save_profile"))

    def load_from_config(self) -> None:
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
        merged_d = list(dict.fromkeys(desired + suggestions.get("desired", []) + suggestions.get("alternative", [])))
        self.career.desired_titles.set_items(merged_d)
        unwanted = list(self.career.unwanted_titles.get_items())
        if not unwanted:
            self.career.unwanted_titles.set_items(
                suggestions.get("exclusions_suggested", [])
            )
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
        msg.addButton(QMessageBox.StandardButton.Cancel)
        msg.exec()
        clicked = msg.clickedButton()
        if clicked is None or clicked == msg.button(QMessageBox.StandardButton.Cancel):
            return
        if clicked is wipe_btn:
            confirm = QMessageBox.question(
                self,
                tr("profile.reset_title"),
                tr("profile.reset_confirm_wipe_all"),
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return
            self.config_service.delete_all_local_data()
            done_msg = tr("profile.reset_wipe_done")
        elif clicked is profile_btn:
            confirm = QMessageBox.question(
                self,
                tr("profile.reset_title"),
                tr("profile.reset_confirm_all"),
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return
            # Profile + documents; search prefs kept (PR22).
            self.config_service.reset_profile_and_documents(clear_search_prefs=False)
            done_msg = tr("profile.reset_done")
        elif clicked is cv_btn:
            confirm = QMessageBox.question(
                self,
                tr("profile.reset_title"),
                tr("profile.reset_confirm_cv"),
            )
            if confirm != QMessageBox.StandardButton.Yes:
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
        self.career.save_into(p.jobs)
        self.experience.save_into(p.qualifications)
        self.education.save_into(p.qualifications)
        self.qualifications.save_into(p.qualifications)
        self.languages.save_into(p.qualifications)
        self.location_work.save_into(p.location, p.employment, p.filters)

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

        # Never fill_empty on normal save — user CLEAR must stick (PR20).
        sync_application_summaries(a, p.qualifications, fill_empty=False)

        # Keep Mindestgehalt and free-text Gehaltsvorstellung from drifting apart.
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
        QMessageBox.information(self, tr("nav.profile"), tr("profile.saved"))

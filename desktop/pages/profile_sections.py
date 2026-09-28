"""Profile page section widgets (one concern per section)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from core.config import (
    ApplicationProfile,
    EmploymentConfig,
    FiltersConfig,
    JobsConfig,
    LocationConfig,
    QualificationsConfig,
)
from desktop.i18n import tr
from desktop.services.profile_merge import (
    SOURCE_MANUAL,
    preserve_sourced_on_edit,
)
from desktop.widgets import ListEditor
from desktop.widgets.structured_editors import (
    CertificateEditor,
    EducationEditor,
    ExperienceEditor,
    LanguageEditor,
)
from desktop.widgets.wheel_guard import IntentionalWheelDoubleSpinBox


class CareerSection(QGroupBox):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.desired_titles = ListEditor("placeholder.job_title", visible_rows=4)
        self.unwanted_titles = ListEditor("placeholder.exclude", visible_rows=3)
        self.desired_industries = ListEditor("placeholder.industry", visible_rows=3)
        self.excluded_industries = ListEditor("placeholder.exclude", visible_rows=3)
        form = QFormLayout(self)
        self.lbl_desired = QLabel()
        self.lbl_unwanted = QLabel()
        self.lbl_industries = QLabel()
        self.lbl_industries_ex = QLabel()
        form.addRow(self.lbl_desired, self.desired_titles)
        self.suggest_titles_btn = QPushButton()
        self.suggest_titles_btn.setObjectName("SecondaryButton")
        form.addRow("", self.suggest_titles_btn)
        form.addRow(self.lbl_unwanted, self.unwanted_titles)
        form.addRow(self.lbl_industries, self.desired_industries)
        form.addRow(self.lbl_industries_ex, self.excluded_industries)
        # Soft-compat: keep attribute so older tests/callers do not crash.
        self.alt_titles = self.desired_titles
        self.lbl_alt = QLabel()
        self.lbl_alt.setVisible(False)

    def retranslate(self) -> None:
        self.setTitle(tr("profile.career"))
        self.lbl_desired.setText(tr("profile.desired"))
        self.lbl_unwanted.setText(tr("profile.excluded"))
        self.lbl_industries.setText(tr("profile.industries"))
        self.lbl_industries_ex.setText(tr("profile.industries_ex"))
        for editor in (
            self.desired_titles,
            self.unwanted_titles,
            self.desired_industries,
            self.excluded_industries,
        ):
            editor.retranslate()

    def load(self, jobs: JobsConfig) -> None:
        # Soft-migrate legacy alternatives into desired for display.
        merged = list(jobs.desired_titles or [])
        for t in jobs.alternative_titles or []:
            if t and t not in merged:
                merged.append(t)
        self.desired_titles.set_items(merged)
        self.unwanted_titles.set_items(jobs.unwanted_titles)
        self.desired_industries.set_items(jobs.desired_industries)
        self.excluded_industries.set_items(jobs.excluded_industries)

    def save_into(self, jobs: JobsConfig) -> None:
        jobs.desired_titles = self.desired_titles.get_items()
        jobs.alternative_titles = []  # retired user-facing field
        jobs.unwanted_titles = self.unwanted_titles.get_items()
        jobs.desired_industries = self.desired_industries.get_items()
        jobs.excluded_industries = self.excluded_industries.get_items()


class ExperienceSection(QGroupBox):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.experience = ExperienceEditor()
        layout = QVBoxLayout(self)
        layout.addWidget(self.experience)

    def retranslate(self) -> None:
        self.setTitle(tr("profile.experience"))
        if hasattr(self.experience, "retranslate"):
            self.experience.retranslate()

    def load(self, quals: QualificationsConfig) -> None:
        self.experience.set_items(quals.work_experience)

    def save_into(self, quals: QualificationsConfig) -> None:
        quals.work_experience = self.experience.get_items()


class EducationSection(QGroupBox):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.education = EducationEditor()
        layout = QVBoxLayout(self)
        layout.addWidget(self.education)

    def retranslate(self) -> None:
        self.setTitle(tr("profile.education"))
        if hasattr(self.education, "retranslate"):
            self.education.retranslate()

    def load(self, quals: QualificationsConfig) -> None:
        self.education.set_items(quals.education)

    def save_into(self, quals: QualificationsConfig) -> None:
        quals.education = self.education.get_items()


def _has_stored_entry_before(stored: list, item: object) -> bool:
    for current in stored or []:
        if current is item:
            return False
        if _licence_item_value(current):
            return True
    return False


def _licence_item_value(item: object) -> str:
    if isinstance(item, str):
        return item.strip()
    return str(getattr(item, "value", "") or "").strip()


def _stored_licence_values(stored: list) -> set[str]:
    values: set[str] = set()
    for item in stored or []:
        value = _licence_item_value(item).upper()
        if value:
            values.add(value)
    return values


def _fragment_joined_displayed_class(fragment: str, display: list[str], stored_values: set[str]) -> bool:
    """True when this one character and another stored entry form a class on screen.

    ``C`` and ``1`` form ``C1``, ``B`` and ``E`` form ``BE``, ``A`` and ``M``
    form ``AM``. A character that merely sits beside a class does not.
    """
    piece = fragment.strip().upper()
    if len(piece) != 1 or piece not in stored_values:
        return False
    parts = [token for token in stored_values if token and any(token in code.upper() for code in display)]

    def joins(code: str) -> bool:
        target = code.upper()
        if len(target) < 2 or piece not in target:
            return False

        def walk(pos: int, used_piece: bool, others: int) -> bool:
            if pos == len(target):
                return used_piece and others >= 1
            for token in parts:
                if target.startswith(token, pos) and walk(
                    pos + len(token),
                    used_piece or token == piece,
                    others + (token != piece),
                ):
                    return True
            return False

        return walk(0, False, 0)

    return any(joins(code) for code in display)


def _licence_token_was_rebuilt(
    token: str,
    reading: object,
    recognised: frozenset[str],
    stored_values: set[str],
) -> bool:
    """True when recovery folded this stored token into a class on screen.

    A recognised code counts when a longer class on screen starts with it
    (``C`` inside ``C1``). Any other single character counts only when that
    character and another stored entry together make the class on screen.
    """
    if reading is None or not getattr(reading, "recovered", False) or not getattr(reading, "display", None):
        return False
    text = token.strip()
    display = list(reading.display)
    if text in display or text.upper() in display:
        return False
    upper = text.upper()
    if upper in recognised:
        return any(len(code) > len(upper) and code.upper().startswith(upper) for code in display)
    return _fragment_joined_displayed_class(text, display, stored_values)


def _visible_and_unknown_licence(stored: list, reading: object) -> tuple[list[str], list]:
    """Rows the drawer shows, and stored entries that are not a class.

    Display classes come first. A recognised code the parser left off that
    list (an uncertain ``C`` or ``D``) is a row. ``M`` is a row when it was
    not folded into ``AM``. A lone ``E`` is a row only when nothing is on
    screen, as with ``[C, E, 9, 5]``. An ``E`` beside a shown class, and
    leftovers such as ``9``, ``5`` and ``95``, stay out of the list. They
    are returned as the original stored objects. An ``E`` with no stored
    entry before it is dropped when a class is already on screen (``[E, B]``).
    """
    from core.cv_parser import _RECOGNISED_LICENCE_CLASSES

    display = list(getattr(reading, "display", None) or [])
    shown = {item.upper() for item in display}
    stored_values = _stored_licence_values(stored)
    rows = list(display)
    unknown: list = []
    for item in stored or []:
        value = _licence_item_value(item)
        if not value:
            continue
        upper = value.upper()
        if value in display or upper in shown:
            continue
        if _licence_token_was_rebuilt(value, reading, _RECOGNISED_LICENCE_CLASSES, stored_values):
            continue
        if upper == "E" and display and not _has_stored_entry_before(stored, item):
            continue
        lone_letter_on_empty = not display and len(value) == 1 and value.isalpha()
        if upper in _RECOGNISED_LICENCE_CLASSES or upper == "M" or lone_letter_on_empty:
            if upper not in shown:
                rows.append(upper)
                shown.add(upper)
            continue
        unknown.append(item)
    return rows, unknown


def _with_unknown_licence_entries(visible: list, unknown: list) -> list:
    """Visible classes first, then the original unknown entries, without duplicates."""
    merged = list(visible)
    seen = {_licence_item_value(item) for item in merged}
    for item in unknown:
        value = _licence_item_value(item)
        if value and value not in seen:
            merged.append(item)
            seen.add(value)
    return merged


class QualificationsSection(QGroupBox):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.skills = ListEditor("placeholder.skill", visible_rows=3)
        self.software = ListEditor("placeholder.software", visible_rows=3)
        self.certificates = CertificateEditor()
        self.driving = ListEditor("placeholder.license", visible_rows=3)
        form = QFormLayout(self)
        self.lbl_skills = QLabel()
        self.lbl_software = QLabel()
        self.lbl_certificates = QLabel()
        self.lbl_license = QLabel()
        self.licence_notice = QLabel()
        self.licence_notice.setObjectName("WarningLabel")
        self.licence_notice.setWordWrap(True)
        self.licence_notice.hide()
        self.licence_unknown = QLabel()
        self.licence_unknown.setObjectName("KkHint")
        self.licence_unknown.setWordWrap(True)
        self.licence_unknown.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.licence_unknown.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.licence_unknown.hide()
        form.addRow(self.lbl_skills, self.skills)
        form.addRow(self.lbl_software, self.software)
        form.addRow(self.lbl_certificates, self.certificates)
        form.addRow(self.licence_notice)
        form.addRow(self.lbl_license, self.driving)
        form.addRow(self.licence_unknown)

    def retranslate(self) -> None:
        self.setTitle(tr("profile.qualifications"))
        self.lbl_skills.setText(tr("profile.skills"))
        self.lbl_software.setText(tr("profile.software"))
        self.lbl_certificates.setText(tr("profile.certificates"))
        self.lbl_license.setText(tr("profile.license"))
        self._refresh_licence_notice()
        for editor in (self.skills, self.software, self.driving):
            editor.retranslate()
        if hasattr(self.certificates, "retranslate"):
            self.certificates.retranslate()

    def load(self, quals: QualificationsConfig) -> None:
        from core.cv_parser import read_driving_classes

        self.skills.set_items(quals.skill_values())
        self.software.set_items(quals.software_values())
        # Recognised classes are rows. Unknown leftovers stay beside the list.
        # Loading itself does not write the config object.
        self._licence_reading = read_driving_classes(quals.driving_license)
        rows, unknown = _visible_and_unknown_licence(
            quals.driving_license, self._licence_reading
        )
        self._licence_loaded_display = list(rows)
        self._licence_unknown = list(unknown)
        self.driving.set_items(self._licence_loaded_display)
        self._refresh_licence_notice()
        self.certificates.set_items(quals.certificates)

    def _refresh_licence_notice(self) -> None:
        reading = getattr(self, "_licence_reading", None)
        if reading is not None and reading.recovered:
            self.licence_notice.setText(tr("profile.licence_recovered"))
            self.licence_notice.show()
        else:
            self.licence_notice.hide()
            self.licence_notice.clear()
        labels = [
            _licence_item_value(item)
            for item in getattr(self, "_licence_unknown", [])
        ]
        labels = [label for label in labels if label]
        if labels:
            self.licence_unknown.setText(
                tr("profile.licence_unknown_kept", entries=", ".join(labels))
            )
            self.licence_unknown.show()
        else:
            self.licence_unknown.hide()
            self.licence_unknown.clear()

    def save_into(self, quals: QualificationsConfig) -> None:
        quals.skills = preserve_sourced_on_edit(quals.skills, self.skills.get_items())
        quals.software = preserve_sourced_on_edit(quals.software, self.software.get_items())
        self._save_driving_license(quals)
        quals.certificates = self.certificates.get_items()

    def _save_driving_license(self, quals: QualificationsConfig) -> None:
        """Save the classes on screen and keep unknown entries verbatim.

        Every recognised class is a row the user can remove. ``M`` is a row
        when it was not folded into ``AM``. A lone ``E`` is a row only when
        the drawer has no class on screen. An ``E`` that did not join a shown
        class, and entries such as ``9``, ``5`` and ``95``, stay in the file
        unchanged and are not classes. Removing a visible class drops it.
        It is not written back as a hidden entry.

        An unchanged row list does not rewrite the file when the stored
        values already match, so ``[C, 95]`` stays byte-identical. A recovered
        ``[B, E]`` still saves as ``B, BE`` because those are the classes on
        screen and they differ from storage.
        """
        edited = self.driving.get_items()
        loaded = getattr(self, "_licence_loaded_display", None)
        unknown = getattr(self, "_licence_unknown", None)
        if loaded is None or unknown is None:
            quals.driving_license = preserve_sourced_on_edit(quals.driving_license, edited)
            return
        proposed = preserve_sourced_on_edit(quals.driving_license, edited)
        merged = _with_unknown_licence_entries(proposed, unknown)
        stored_values = [_licence_item_value(item) for item in quals.driving_license]
        merged_values = [_licence_item_value(item) for item in merged]
        if edited == list(loaded) and merged_values == stored_values:
            return
        quals.driving_license = merged


class LanguagesSection(QGroupBox):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.languages = LanguageEditor()
        layout = QVBoxLayout(self)
        layout.addWidget(self.languages)

    def retranslate(self) -> None:
        self.setTitle(tr("profile.languages"))
        if hasattr(self.languages, "retranslate"):
            self.languages.retranslate()

    def load(self, quals: QualificationsConfig) -> None:
        self.languages.set_items(quals.languages)

    def save_into(self, quals: QualificationsConfig) -> None:
        langs = self.languages.get_items()
        for lang in langs:
            if getattr(lang, "source", None) in (None, ""):
                lang.source = SOURCE_MANUAL
        quals.languages = langs


class LocationWorkSection(QGroupBox):
    """Profile location — identity (where I live), not search wish.

    Search wish fields (radius, remote mode, salary, working time) live on
    SearchPage. Pass ``include_search_fields=True`` for legacy rollback UI.
    """

    def __init__(self, parent=None, *, include_search_fields: bool = False) -> None:
        super().__init__(parent)
        self.include_search_fields = include_search_fields
        self.home_address = QLineEdit()
        self.postal_code = QLineEdit()
        self.postal_code.setPlaceholderText("PLZ")
        self.max_distance = IntentionalWheelDoubleSpinBox()
        self.max_distance.setRange(1, 300)
        self.max_distance.setSuffix(" km Luftlinie")
        self.allow_remote = QCheckBox()
        self.allow_hybrid = QCheckBox()
        self.country = QLineEdit()
        self.geo_status = QLabel()
        self.geo_status.setWordWrap(True)
        self.geo_update_btn = QPushButton()
        self.geo_update_btn.setObjectName("SecondaryButton")
        self.geo_update_btn.clicked.connect(self._update_geo_dataset)
        self.full_time = QCheckBox()
        self.part_time = QCheckBox()
        self.remote = QCheckBox()
        self.hybrid = QCheckBox()
        self.onsite = QCheckBox()
        self.min_salary = IntentionalWheelDoubleSpinBox()
        self.min_salary.setRange(0, 500000)
        self.min_salary.setSuffix(" €")
        self.preferred_companies = ListEditor("placeholder.add_entry", visible_rows=3)
        self.excluded_companies = ListEditor("placeholder.add_entry", visible_rows=3)
        form = QFormLayout(self)
        self.lbl_home = QLabel()
        self.lbl_postal = QLabel()
        self.lbl_commute = QLabel()
        self.lbl_country = QLabel()
        self.lbl_work_model = QLabel()
        self.lbl_min_salary = QLabel()
        self.lbl_pref_companies = QLabel()
        self.lbl_ex_companies = QLabel()
        self.lbl_geo = QLabel()
        form.addRow(self.lbl_home, self.home_address)
        form.addRow(self.lbl_postal, self.postal_code)
        self.home_notice = QLabel()
        self.home_notice.setWordWrap(True)
        self.home_notice.setObjectName("WarningLabel")
        form.addRow(self.home_notice)
        self.home_address.editingFinished.connect(self.refresh_home_notice)
        self.postal_code.editingFinished.connect(self.refresh_home_notice)
        self.country.editingFinished.connect(self.refresh_home_notice)
        form.addRow(self.lbl_country, self.country)
        form.addRow(self.lbl_geo, self.geo_status)
        form.addRow(self.geo_update_btn)
        form.addRow(self.allow_remote)
        form.addRow(self.allow_hybrid)
        form.addRow(self.lbl_pref_companies, self.preferred_companies)
        form.addRow(self.lbl_ex_companies, self.excluded_companies)
        # Legacy search-wish widgets — hidden unless rollback flag is on.
        form.addRow(self.lbl_commute, self.max_distance)
        row = QHBoxLayout()
        for w in (self.full_time, self.part_time, self.remote, self.hybrid, self.onsite):
            row.addWidget(w)
        form.addRow(self.lbl_work_model, row)
        form.addRow(self.lbl_min_salary, self.min_salary)
        self._set_search_fields_visible(include_search_fields)

    def _set_search_fields_visible(self, visible: bool) -> None:
        self.include_search_fields = visible
        for w in (
            self.lbl_commute,
            self.max_distance,
            self.lbl_work_model,
            self.full_time,
            self.part_time,
            self.remote,
            self.hybrid,
            self.onsite,
            self.lbl_min_salary,
            self.min_salary,
        ):
            w.setVisible(visible)

    def retranslate(self) -> None:
        self.setTitle(
            tr("profile.location") if not self.include_search_fields else tr("profile.location_work")
        )
        self.lbl_home.setText(tr("profile.home"))
        self.lbl_postal.setText(tr("profile.postal"))
        self.lbl_commute.setText(tr("profile.commute_airline"))
        self.allow_remote.setText(tr("profile.allow_remote"))
        self.allow_hybrid.setText(tr("profile.allow_hybrid"))
        self.lbl_country.setText(tr("profile.country"))
        self.lbl_geo.setText(tr("profile.geo_dataset"))
        self.geo_update_btn.setText(tr("profile.geo_update"))
        self.lbl_work_model.setText(tr("profile.work_model"))
        self.full_time.setText(tr("full_time"))
        self.part_time.setText(tr("part_time"))
        self.remote.setText(tr("remote"))
        self.hybrid.setText(tr("hybrid"))
        self.onsite.setText(tr("onsite"))
        self.lbl_min_salary.setText(tr("profile.min_salary"))
        self.lbl_pref_companies.setText(tr("profile.pref_companies"))
        self.lbl_ex_companies.setText(tr("profile.ex_companies"))
        self.preferred_companies.retranslate()
        self.excluded_companies.retranslate()
        self._refresh_geo_status()
        self.refresh_home_notice()

    def _refresh_geo_status(self) -> None:
        try:
            from core.geo_dataset import get_geo_dataset_manager

            info = get_geo_dataset_manager().current_info()
            if info.valid:
                self.geo_status.setText(
                    tr(
                        "profile.geo_status_ok",
                        version=info.version,
                        source=info.source,
                    )
                )
            else:
                self.geo_status.setText(
                    tr("profile.geo_status_bad", message=info.message or "—")
                )
        except Exception:
            self.geo_status.setText(tr("profile.geo_status_bad", message="—"))

    def _update_geo_dataset(self) -> None:
        try:
            from core.geo_dataset import get_geo_dataset_manager

            info = get_geo_dataset_manager().update_from_upstream()
            self._refresh_geo_status()
            if not info.valid:
                self.geo_status.setText(
                    tr("profile.geo_status_bad", message=info.message or "Update fehlgeschlagen")
                )
        except Exception as exc:
            self.geo_status.setText(
                tr("profile.geo_status_bad", message=type(exc).__name__)
            )

    def refresh_home_notice(self, location: LocationConfig | None = None) -> None:
        """Re-read resolver status for the home fields. Does not guess a PLZ."""
        from core.location import home_location_notice

        if location is None:
            location = LocationConfig(
                home_address=self.home_address.text().strip(),
                postal_code=self.postal_code.text().strip(),
                country=self.country.text().strip() or "DE",
            )
        from desktop.pages.dashboard import bind_home_notice_label

        bind_home_notice_label(self.home_notice, home_location_notice(location))

    def load(
        self,
        location: LocationConfig,
        employment: EmploymentConfig,
        filters: FiltersConfig,
    ) -> None:
        self.home_address.setText(location.home_address)
        self.postal_code.setText(getattr(location, "postal_code", "") or "")
        self.max_distance.setValue(float(location.max_distance_km))
        self.allow_remote.setChecked(location.allow_remote_germany)
        self.allow_hybrid.setChecked(location.allow_hybrid)
        self.country.setText(location.country)
        self.full_time.setChecked(employment.full_time)
        self.part_time.setChecked(employment.part_time)
        self.remote.setChecked(employment.remote)
        self.hybrid.setChecked(employment.hybrid)
        self.onsite.setChecked(employment.onsite)
        self.min_salary.setValue(float(employment.minimum_salary or 0))
        self.preferred_companies.set_items(filters.preferred_companies)
        self.excluded_companies.set_items(filters.excluded_companies)
        self._refresh_geo_status()
        self.refresh_home_notice(location)

    def save_into(
        self,
        location: LocationConfig,
        employment: EmploymentConfig,
        filters: FiltersConfig,
    ) -> None:
        new_home = self.home_address.text().strip()
        new_plz = self.postal_code.text().strip()
        if new_home != (location.home_address or "").strip() or new_plz != (
            getattr(location, "postal_code", "") or ""
        ):
            location.home_latitude = None
            location.home_longitude = None
            location.home_geocoded_address = ""
        location.home_address = new_home
        location.postal_code = new_plz
        location.allow_remote_germany = self.allow_remote.isChecked()
        location.allow_hybrid = self.allow_hybrid.isChecked()
        location.country = self.country.text().strip() or "DE"
        filters.preferred_companies = self.preferred_companies.get_items()
        filters.excluded_companies = self.excluded_companies.get_items()
        self.refresh_home_notice(location)
        if self.include_search_fields:
            location.max_distance_km = float(self.max_distance.value())
            employment.full_time = self.full_time.isChecked()
            employment.part_time = self.part_time.isChecked()
            employment.remote = self.remote.isChecked()
            employment.hybrid = self.hybrid.isChecked()
            employment.onsite = self.onsite.isChecked()
            employment.minimum_salary = self.min_salary.value() or None


class ApplicantSection(QGroupBox):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.first_name = QLineEdit()
        self.last_name = QLineEdit()
        self.street = QLineEdit()
        self.postal_code = QLineEdit()
        self.city = QLineEdit()
        self.app_country = QLineEdit()
        self.email = QLineEdit()
        self.phone = QLineEdit()
        self.dob = QLineEdit()
        self.drv = QLineEdit()
        self.work_auth = QLineEdit()
        self.notice = QLineEdit()
        self.start = QLineEdit()
        self.salary_exp = QLineEdit()
        self.current_job = QLineEdit()
        self.edu_text = QLineEdit()
        self.lang_text = QLineEdit()
        self.travel = QLineEdit()
        self.relocate = QLineEdit()
        self.remote_pref = QLineEdit()
        self.sync_home_from_address = QCheckBox()
        self.sync_home_from_address.setChecked(False)
        form = QFormLayout(self)
        self.app_field_labels: list[tuple[QLabel, str]] = []
        for key, widget in [
            ("field.first_name", self.first_name),
            ("field.last_name", self.last_name),
            ("field.street", self.street),
            ("field.postal", self.postal_code),
            ("field.city", self.city),
            ("field.country", self.app_country),
            ("field.email", self.email),
            ("field.phone", self.phone),
            ("field.dob", self.dob),
            ("field.license_form", self.drv),
            ("field.work_auth", self.work_auth),
            ("field.notice", self.notice),
            ("field.start", self.start),
            ("field.salary", self.salary_exp),
            ("field.current_job", self.current_job),
            ("field.edu_short", self.edu_text),
            ("field.lang_short", self.lang_text),
            ("field.travel", self.travel),
            ("field.relocate", self.relocate),
            ("field.remote_pref", self.remote_pref),
        ]:
            lbl = QLabel()
            self.app_field_labels.append((lbl, key))
            form.addRow(lbl, widget)
        form.addRow(self.sync_home_from_address)

    def retranslate(self) -> None:
        self.setTitle(tr("profile.app_data"))
        for lbl, key in self.app_field_labels:
            lbl.setText(tr(key))
        self.sync_home_from_address.setText(tr("profile.sync_home_address"))

    def load(self, app: ApplicationProfile, *, sync_address_to_search: bool) -> None:
        self.first_name.setText(app.first_name)
        self.last_name.setText(app.last_name)
        self.street.setText(app.street)
        self.postal_code.setText(app.postal_code)
        self.city.setText(app.city)
        self.app_country.setText(app.country or "DE")
        self.email.setText(app.email)
        self.phone.setText(app.phone)
        self.dob.setText(app.date_of_birth)
        from core.cv_parser import driving_classes_for_display

        classes = driving_classes_for_display(app.driving_license)
        self.drv.setText(", ".join(classes) if classes else (app.driving_license or ""))
        self.work_auth.setText(app.work_authorization)
        self.notice.setText(app.notice_period)
        self.start.setText(app.earliest_start_date)
        self.salary_exp.setText(app.salary_expectation)
        self.current_job.setText(app.current_employment)
        self.edu_text.setText(app.education)
        self.lang_text.setText(app.languages)
        self.travel.setText(app.willingness_to_travel)
        self.relocate.setText(app.willingness_to_relocate)
        self.remote_pref.setText(app.remote_preference)
        self.sync_home_from_address.setChecked(sync_address_to_search)

    def save_into(self, app: ApplicationProfile) -> bool:
        """Apply form values to ``app`` via explicit CLEAR/SET semantics.

        Empty / whitespace-only inputs become CLEAR with ``SOURCE_MANUAL`` origin
        so CV summary sync cannot resurrect them. Returns sync-address checkbox.
        """
        from desktop.services.profile_patch import (
            PatchOp,
            ProfilePatch,
            apply_profile_patch,
            build_application_patches,
        )
        from core.config import QualificationsConfig

        proposed = {
            "first_name": self.first_name.text(),
            "last_name": self.last_name.text(),
            "street": self.street.text(),
            "postal_code": self.postal_code.text(),
            "city": self.city.text(),
            "country": self.app_country.text(),
            "email": self.email.text(),
            "phone": self.phone.text(),
            "date_of_birth": self.dob.text(),
            "driving_license": self.drv.text(),
            "education": self.edu_text.text(),
            "languages": self.lang_text.text(),
            "current_employment": self.current_job.text(),
            "work_authorization": self.work_auth.text(),
            "notice_period": self.notice.text(),
            "earliest_start_date": self.start.text(),
            "salary_expectation": self.salary_exp.text(),
            "willingness_to_travel": self.travel.text(),
            "willingness_to_relocate": self.relocate.text(),
            "remote_preference": self.remote_pref.text(),
        }
        patches = build_application_patches(app, proposed)
        patches = {k: v for k, v in patches.items() if v.op is not PatchOp.UNCHANGED}
        # Blank country → CLEAR resets to DE inside apply_profile_patch
        if patches:
            apply_profile_patch(app, QualificationsConfig(), ProfilePatch(application=patches))
        if not str(app.country or "").strip():
            app.country = "DE"
        app.sync_address()
        return self.sync_home_from_address.isChecked()


class CvSection(QGroupBox):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.cv_label = QLabel()
        self.cv_select = QPushButton()
        self.cv_select.setObjectName("SecondaryButton")
        self.cv_import = QPushButton()
        self.cv_import.setObjectName("PrimaryButton")
        self.cv_reset = QPushButton()
        self.cv_reset.setObjectName("SecondaryButton")
        layout = QVBoxLayout(self)
        layout.addWidget(self.cv_label)
        row = QHBoxLayout()
        row.addWidget(self.cv_select)
        row.addWidget(self.cv_import)
        row.addWidget(self.cv_reset)
        row.addStretch()
        layout.addLayout(row)

    def retranslate(self, *, no_cv_tokens: set[str]) -> None:
        self.setTitle(tr("profile.cv"))
        if not self.cv_label.text() or self.cv_label.text() in no_cv_tokens:
            self.cv_label.setText(tr("profile.no_cv"))
        self.cv_select.setText(tr("btn.select_cv"))
        self.cv_import.setText(tr("btn.import_cv"))
        self.cv_reset.setText(tr("btn.reset_profile"))

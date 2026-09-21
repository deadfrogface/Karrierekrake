# V2 UI Feature-Preservation-Matrix (Desktop inventory)

Inventory of **end-user-facing** Karrierekrake desktop features as of the current `desktop/` tree.  
Source scan: `main_window.py`, `pages/*`, `widgets/*`, `wizard/`, `tray.py`, settings/privacy, apply preview, lifecycle/Günther.

**Nav order (primary):** Profil → Suche → Jobs → Bewerbungen → Günther → Einstellungen → Dashboard → Protokolle  
**Suggested V2 surfaces:** Übersicht, Jobs, Bewerbungen (detail), Postfach, Profil, Suche, Einstellungen (>Diagnose / >Datenschutz), Tray, Wizard

Categories: `KEEP` | `MOVE` | `REDESIGN` | `MERGE` | `HIDE_FROM_NORMAL_UI` | `UNKNOWN`

| id | current_location | user_visible_name | description | suggested_v2_category | suggested_v2_target | notes |
| --- | --- | --- | --- | --- | --- | --- |
| shell-brand | MainWindow sidebar | Karrierekrake + Tagline | Brand mark and “FINDE. BEWIRB. BEHALTE DEN ÜBERBLICK.” in sidebar | KEEP | Shell / Übersicht | Brand-first requirement for V2 |
| shell-nav-profile | MainWindow nav | Profil | Navigate to profile page | KEEP | Profil | First nav item; mental model “who I am” |
| shell-nav-search | MainWindow nav | Suche | Navigate to SearchIntent page | KEEP | Suche | Separate from Profil |
| shell-nav-jobs | MainWindow nav | Jobs | Navigate to jobs list | KEEP | Jobs | |
| shell-nav-applications | MainWindow nav | Bewerbungen | Navigate to applications history | KEEP | Bewerbungen | |
| shell-nav-guenther | MainWindow nav | Günther | Navigate to lifecycle / Günther surface | REDESIGN | Bewerbungen detail / Günther | Maps lifecycle; no dedicated “Lebenszyklus” nav label in UI |
| shell-nav-settings | MainWindow nav | Einstellungen | Navigate to settings tabs | KEEP | Einstellungen | |
| shell-nav-dashboard | MainWindow nav | Dashboard | Navigate to overview / next-action page | MOVE | Übersicht | Currently last-but-one; i18n title “Übersicht” on page vs nav “Dashboard” |
| shell-nav-logs | MainWindow nav | Protokolle | Navigate to logs viewer | HIDE_FROM_NORMAL_UI | Einstellungen>Diagnose | Power-user / support |
| shell-status-bar | MainWindow status bar | Bereit / Laufstatus | Permanent progress/status label | KEEP | Shell | Pipeline progress, pause/resume messages |
| shell-window-geometry | MainWindow | (implicit) | Persist/restore window size/position/maximized | KEEP | Shell | Not labeled; must preserve |
| shell-minimize-to-tray | MainWindow close + settings | Beim Schließen im Hintergrund weiterlaufen | Close hides to tray when enabled | KEEP | Einstellungen>Allgemein + Tray | Destructive if users expect quit |
| shell-quit-busy-confirm | MainWindow closeEvent | Vorgang läuft — beenden? | Confirm quit while pipeline running | KEEP | Shell | Safety |
| shell-single-instance | app.py | Karrierekrake läuft bereits | Single-instance lock + raise existing window | KEEP | Shell | Message DE hard-coded in app.py |
| shell-appearance-live | MainWindow + Settings | Theme/Sprache/Kontrast | Apply stylesheet + language after settings save | KEEP | Einstellungen>Allgemein | Language full apply may need restart |
| wizard-first-run | FirstRunWizard | Erste Einrichtung | Gate on first run when config flag set | KEEP | Onboarding | 3-step wizard |
| wizard-step-cv | wizard CvStepPage | 1 · Lebenslauf | Optional CV pick (PDF/DOCX) | KEEP | Onboarding | Skip allowed |
| wizard-step-cv-pick | wizard CvStepPage | Lebenslauf auswählen | File dialog for CV | KEEP | Onboarding / Profil | Copies into storage on finish |
| wizard-step-prefs | wizard PrefsStepPage | 2 · Sucheinstellungen | Titles, home address, distance, remote | MERGE | Onboarding → Suche+Profil | Overlaps SearchIntent + location |
| wizard-step-prefs-titles | wizard PrefsStepPage | Gewünschte Jobtitel | ListEditor for desired titles | KEEP | Onboarding / Suche | |
| wizard-step-prefs-address | wizard PrefsStepPage | Heimatadresse | Home address line | KEEP | Onboarding / Profil | |
| wizard-step-prefs-distance | wizard PrefsStepPage | Max. Pendelweg | Distance spinbox km | KEEP | Onboarding / Suche | |
| wizard-step-prefs-remote | wizard PrefsStepPage | Voll remote (DE) erlauben | Remote Germany checkbox | KEEP | Onboarding / Suche | |
| wizard-step-ready | wizard ReadyStepPage | 3 · Bereit | Safe defaults messaging | KEEP | Onboarding | Always forces dry_run=True on accept |
| wizard-mode-search-only | wizard ReadyStepPage | Nur Suche – nie bewerben | Default mode radio | KEEP | Onboarding / Einstellungen | Default checked |
| wizard-mode-review | wizard ReadyStepPage | Vor Absenden prüfen | Alternate first-run mode | KEEP | Onboarding / Einstellungen | |
| wizard-dry-run-locked | wizard ReadyStepPage | Dry Run (nie endgültig absenden) | Shown checked, disabled | KEEP | Onboarding | Always-on safety messaging |
| wizard-finish-cta | FirstRunWizard | Jobs finden | Finish button label | REDESIGN | Onboarding | CTA implies search; does not auto-start search |
| tray-open | AppTray | Karrierekrake öffnen | Show/raise main window | KEEP | Tray | Also tray icon click |
| tray-search | AppTray | Jetzt suchen | Start search_only pipeline | KEEP | Tray / Übersicht | Same as dashboard search |
| tray-pause | AppTray | Automation pausieren | Set automation_paused true | KEEP | Tray / Übersicht | Fail-closed mid-pipeline |
| tray-resume | AppTray | Automation fortsetzen | Clear automation_paused | KEEP | Tray / Übersicht | |
| tray-exit | AppTray | Beenden | Force quit (bypass minimize-to-tray) | KEEP | Tray | |
| tray-balloon-running | AppTray | Läuft weiter im Infobereich | Balloon after hide-to-tray | KEEP | Tray | |
| dash-page | DashboardPage | Übersicht | Next-action hero + stats + run controls | REDESIGN | Übersicht | Nav label still “Dashboard” |
| dash-next-action-search | DashboardPage hero | Als Nächstes: Jobs finden | Primary CTA → search | KEEP | Übersicht | |
| dash-next-action-review | DashboardPage hero | Als Nächstes: Warteschlange prüfen | Primary CTA → applications review filter | KEEP | Übersicht → Bewerbungen | |
| dash-next-action-profile | DashboardPage hero | Als Nächstes: Profil ergänzen | Primary CTA → navigate profile | KEEP | Übersicht → Profil | Index hardcoded; fragile if nav order changes |
| dash-stat-matches | DashboardPage | Treffer ≥75% | Stat card | MERGE | Übersicht | Consider fewer KPIs in V2 |
| dash-stat-needs-review | DashboardPage | Prüfung nötig | Stat card | KEEP | Übersicht | |
| dash-stat-found-today | DashboardPage | Heute gefunden | Stat card | MERGE | Übersicht | |
| dash-stat-applied | DashboardPage | Beworben | Stat card applications today | MERGE | Übersicht | |
| dash-stat-new | DashboardPage | Neu | Stat card | MERGE | Übersicht | |
| dash-stat-this-run | DashboardPage | Dieser Lauf | Stat card | HIDE_FROM_NORMAL_UI | Übersicht advanced | |
| dash-stat-captcha | DashboardPage | CAPTCHA | Stat card | KEEP | Übersicht | Safety signal |
| dash-stat-errors | DashboardPage | Fehler | Stat card | KEEP | Übersicht / Diagnose | |
| dash-mode-line | DashboardPage | Modus / Dry-Run / Automation | Live mode summary | KEEP | Übersicht | |
| dash-last-search | DashboardPage | Letzte Suche | Meta timestamp | KEEP | Übersicht | |
| dash-next-run | DashboardPage | Nächster geplanter Lauf | Schedule meta | KEEP | Übersicht | |
| dash-home-warning | DashboardPage | Warnung: Such-Heimatadresse fehlt | Distance filter inactive warning | KEEP | Übersicht / Profil | |
| dash-run-detail | DashboardPage | Lauf-Statistik | raw/dup/dist/neu/match/ATS breakdown | HIDE_FROM_NORMAL_UI | Einstellungen>Diagnose | Dense technical line |
| dash-btn-search | DashboardPage | Jetzt suchen | Start search_only pipeline | KEEP | Übersicht | |
| dash-btn-cancel | DashboardPage | Suche abbrechen | Cancel in-flight pipeline | KEEP | Übersicht | Enabled only while running |
| dash-btn-apply | DashboardPage | Bewerbungen starten | Start apply pipeline (respects mode; upgrades search_only→review) | KEEP | Übersicht / Bewerbungen | |
| dash-btn-apply-test | DashboardPage | Bewerbungstest | Dry-run apply with deep-copied config | KEEP | Übersicht / Einstellungen | Never mutates saved dry_run |
| dash-btn-pause | DashboardPage | Automation pausieren / fortsetzen | Toggle automation_paused | KEEP | Übersicht | Label swaps |
| dash-btn-review | DashboardPage | Zur Prüfung | Jump to applications Needs Review | KEEP | Bewerbungen | |
| dash-btn-clear-jobs | DashboardPage | Jobs leeren | Wipe jobs/apps/source status/search runs (confirm) | HIDE_FROM_NORMAL_UI | Einstellungen>Datenschutz / Diagnose | Destructive; profile kept |
| pipeline-guard-running | MainWindow | Es läuft bereits ein Auftrag | Block concurrent pipeline | KEEP | Shell | |
| pipeline-guard-paused | MainWindow | Automatisierung ist pausiert | Block start while paused | KEEP | Shell | |
| pipeline-guard-no-titles | MainWindow | Keine Suchbegriffe… | Require searchable titles/discovery evidence | KEEP | Suche / Profil | |
| pipeline-guard-no-location | MainWindow | Kein Wohnort und Remote nicht erlaubt | Require home or remote | KEEP | Profil / Suche | |
| pipeline-result-dialog | MainWindow | Lauf fertig / abgebrochen | Stats dialog new/matches/applied/review + extras | REDESIGN | Übersicht | ATS unknown counts in extras |
| search-page | SearchPage | Suche | Explicit SearchIntent editor | KEEP | Suche | Must not silently copy CV evidence |
| search-target-roles | SearchPage | Zielberufe | ListEditor | KEEP | Suche | |
| search-mandatory-skills | SearchPage | Pflicht-Skills | ListEditor | KEEP | Suche | |
| search-excluded-roles | SearchPage | Ausgeschlossene Berufe | ListEditor | KEEP | Suche | |
| search-excluded-skills | SearchPage | Ausgeschlossene Skills | ListEditor | KEEP | Suche | |
| search-excluded-keywords | SearchPage | Ausschluss-Keywords | ListEditor | KEEP | Suche | Dual-writes filters.exclusion_keywords |
| search-required-keywords | SearchPage | Keywords (Pflicht) | ListEditor | KEEP | Suche | |
| search-remote-mode | SearchPage | Remote / Hybrid / Vor Ort / Nicht festgelegt | Exclusive radio group | KEEP | Suche | |
| search-radius | SearchPage | Radius (Pendelweg) | km spin; 0 = unset | KEEP | Suche | Mirrors location.max_distance_km on save |
| search-countries | SearchPage | Länder (DE / AT / CH) | DACH country checkboxes | KEEP | Suche | Cross-border |
| search-working-time | SearchPage | Arbeitszeit | Vollzeit / Teilzeit | KEEP | Suche | |
| search-employment-types | SearchPage | Beschäftigungsart | Unbefristet / Befristet / Werkvertrag | KEEP | Suche | |
| search-salary-min | SearchPage | Mindestgehalt (EUR brutto / Jahr) | Salary floor | KEEP | Suche | Mirrors employment.minimum_salary |
| search-strictness | SearchPage | Suchstrenge | Unset / STRICT / BALANCED / EXPLORE | KEEP | Suche | STRICT never silently expanded |
| search-needs-review-banner | SearchPage | Bitte prüfen (Migration / Konflikte) | Shows intent.needs_user_review flags | KEEP | Suche | Migration UX |
| search-save | SearchPage | Suchwunsch speichern | Persist intent + legacy mirrors | KEEP | Suche | |
| profile-page | ProfilePage | Profil | Identity / evidence editor | KEEP | Profil | |
| profile-experience | ProfilePage ExperienceSection | Berufserfahrung | Structured experience list add/edit/remove | KEEP | Profil | |
| profile-education | ProfilePage EducationSection | Ausbildung | Structured education editor | KEEP | Profil | |
| profile-skills | ProfilePage QualificationsSection | Skills | ListEditor with source-preserving edit | KEEP | Profil | |
| profile-software | ProfilePage QualificationsSection | Software | ListEditor | KEEP | Profil | |
| profile-certificates | ProfilePage QualificationsSection | Zertifikate / Weiterbildungen | CertificateEditor | KEEP | Profil | |
| profile-license | ProfilePage QualificationsSection | Führerschein | Driving license list | KEEP | Profil | |
| profile-languages | ProfilePage LanguagesSection | Sprachen | Language + level editor | KEEP | Profil | |
| profile-home-address | ProfilePage LocationWorkSection | Heimatadresse | Home address; invalidates geocode on change | KEEP | Profil | |
| profile-country | ProfilePage LocationWorkSection | Land | Residence country | KEEP | Profil | |
| profile-allow-remote | ProfilePage LocationWorkSection | Voll remote (DE) erlauben | allow_remote_germany | KEEP | Profil / Suche | Overlaps SearchIntent remote |
| profile-allow-hybrid | ProfilePage LocationWorkSection | Hybrid erlauben | allow_hybrid | KEEP | Profil | |
| profile-pref-companies | ProfilePage LocationWorkSection | Bevorzugte Firmen | Filter list | KEEP | Profil / Suche | |
| profile-ex-companies | ProfilePage LocationWorkSection | Ausgeschlossene Firmen | Filter list | KEEP | Profil / Suche | |
| profile-legacy-career | ProfilePage CareerSection (flag) | Berufswünsche | Desired/unwanted titles + industries | HIDE_FROM_NORMAL_UI | Legacy / Suche | Visible only with `legacy_profile_search_ui` or env |
| profile-suggest-titles | ProfilePage CareerSection | Berufsvorschläge aus Lebenslauf | Suggest titles from CV/quals | MOVE | Suche or Profil CV | Hidden unless legacy career visible |
| profile-legacy-search-fields | LocationWorkSection (flag) | Pendelweg / Arbeitsmodell / Mindestgehalt | Search-wish fields on profile | HIDE_FROM_NORMAL_UI | Suche | Legacy rollback only |
| profile-applicant-data | ProfilePage ApplicantSection | Bewerbungsdaten | Name, address, contact, DOB, work auth, notice, start, salary, travel, relocate, remote pref, short texts | KEEP | Profil | Large form — redesign layout, keep fields |
| profile-sync-home | ApplicantSection | Diese Adresse auch als Standort für die Jobsuche verwenden | Sync application address → search home | KEEP | Profil | Clears geocode when home changes |
| profile-cv-label | CvSection | Lebenslauf / Kein CV ausgewählt | Active CV path/label display | KEEP | Profil | |
| profile-cv-select | CvSection | Lebenslauf auswählen | Pick/copy CV into storage | KEEP | Profil | |
| profile-cv-import | CvSection | Profil aus Lebenslauf einlesen | Open CvImportDialog | KEEP | Profil | |
| profile-reset | CvSection | Profil zurücksetzen | Scoped reset dialog | KEEP | Profil / Datenschutz | Three scopes |
| profile-reset-cv-only | reset dialog | Nur CV-Daten löschen | Clear CV-derived quals + CV files; keep manuals | KEEP | Profil / Datenschutz | |
| profile-reset-profile-docs | reset dialog | Profil + Dokumente löschen | Wipe profile+docs; keep search prefs | KEEP | Datenschutz | |
| profile-reset-wipe-all | reset dialog | Alle lokalen Karrierekrake-Daten löschen | Full local wipe | KEEP | Datenschutz | Same as privacy delete-all |
| profile-save | ProfilePage | Profil speichern | Validate + save; salary sync heuristics | KEEP | Profil | |
| cv-import-dialog | CvImportDialog | Profil aus Lebenslauf | Preview import with replace/merge | KEEP | Profil | |
| cv-import-mode-replace | CvImportDialog | Profil aus CV ersetzen (empfohlen) | Replace CV-derived data | KEEP | Profil | Default |
| cv-import-mode-merge | CvImportDialog | Mit bestehendem Profil zusammenführen | Merge without duplicates | KEEP | Profil | |
| cv-import-conflicts | CvImportDialog | Konflikte (manuell vs. CV) | Per-field keep/use-CV chooser | KEEP | Profil | Default keep manual |
| cv-import-confidence | CvImportDialog | Erkennungsstatus | Per-section detection confidence | KEEP | Profil | |
| jobs-page | JobsPage | Jobs | Filtered job table + detail | KEEP | Jobs | |
| jobs-filter-min-match | JobsPage | Min. Match | Numeric filter | REDESIGN | Jobs | Fit labels replaced % in UI; filter still numeric |
| jobs-filter-max-km | JobsPage | Max. km | Distance filter | KEEP | Jobs | |
| jobs-filter-city | JobsPage | Stadt | Text filter | KEEP | Jobs | |
| jobs-filter-title | JobsPage | Titel | Text filter | KEEP | Jobs | |
| jobs-filter-company | JobsPage | Firma | Text filter | KEEP | Jobs | |
| jobs-filter-source | JobsPage | Quelle | Text filter | KEEP | Jobs | |
| jobs-filter-status | JobsPage | Status | JobStatus combo | KEEP | Jobs | |
| jobs-filter-remote-types | JobsPage | Remote / Hybrid / Vor Ort | Work-model checkboxes | KEEP | Jobs | |
| jobs-filter-age-days | JobsPage (widget only) | (age_days spinbox) | Created but **not wired into filter form** | UNKNOWN | Jobs or drop | Dead control — implement or remove |
| jobs-btn-filter | JobsPage | Filtern | Apply filters / refresh | KEEP | Jobs | |
| jobs-btn-open | JobsPage | Job öffnen | Open application_url or url in browser | KEEP | Jobs | Double-click also opens |
| jobs-btn-prepare | JobsPage | Bewerbung vorbereiten | Build preview → ApplyPreviewDialog | KEEP | Jobs / Bewerbungen detail | |
| jobs-table | JobsPage | Jobliste | Columns: Titel, Firma, Stadt, Distanz, Remote, Passung, Begründung, Quelle, Status | REDESIGN | Jobs | Sorting; empty state |
| jobs-count | JobsPage | {n} Treffer | Result count | KEEP | Jobs | |
| jobs-detail-panel | JobsPage detail | Job details | Title, meta, status, description | KEEP | Jobs | |
| jobs-fit-panel | JobFitPanel on Jobs | Passung (Sehr passend…) | Explainable fit headline + bullets | KEEP | Jobs | No fake % headline |
| jobs-fit-sort-hint | JobFitPanel | Sortierhinweis (intern) | Optional sort score | HIDE_FROM_NORMAL_UI | Jobs advanced | |
| jobs-empty | JobsPage | Noch keine Jobs… | Empty state | KEEP | Jobs | |
| apply-preview-dialog | ApplyPreviewDialog | Bewerbungsvorschau (vor Absenden) | Form values, docs, cover, warnings, quality gate | KEEP | Jobs / Bewerbungen detail | |
| apply-preview-gate | ApplyPreviewDialog | READY / WARNING / BLOCKED | Quality gate banner | KEEP | Bewerbungen detail | |
| apply-preview-submit-note | ApplyPreviewDialog | Finales Absenden wäre erlaubt / blockiert | Dry-run / review messaging | KEEP | Bewerbungen detail | |
| apply-preview-open-manual | ApplyPreviewDialog | Manuell öffnen | Open ATS URL | KEEP | Bewerbungen detail | |
| apps-page | ApplicationsPage | Bewerbungen | Application history table + timeline | KEEP | Bewerbungen | |
| apps-filter-status | ApplicationsPage | Status | Includes queued/applying/applied/needs_review/captcha/failed/closed | KEEP | Bewerbungen | |
| apps-btn-refresh | ApplicationsPage | Aktualisieren | Reload list | KEEP | Bewerbungen | |
| apps-btn-open | ApplicationsPage | Manuell öffnen | Open job URL | KEEP | Bewerbungen | |
| apps-btn-preview | ApplicationsPage | Bewerbungsvorschau | Preview from job or fallback from record | KEEP | Bewerbungen detail | |
| apps-btn-review-only | ApplicationsPage | Nur Needs Review | Filter to NEEDS_REVIEW | KEEP | Bewerbungen | Entry from dashboard/tray path |
| apps-table | ApplicationsPage | Bewerbungstabelle | Datum, Firma, Titel, ATS, Passung, Status, CV, Anschreiben, Fehler | KEEP | Bewerbungen | |
| apps-timeline | CaseTimelinePanel | Timeline | Case lifecycle path + event log on selection | KEEP | Bewerbungen detail | Shared widget with Günther |
| apps-empty | ApplicationsPage | Noch keine Bewerbungen | Empty state | KEEP | Bewerbungen | |
| life-page | LifecyclePage | Günther | Cases, ambiguous mail, tasks, approvals, Günther bar | REDESIGN | Bewerbungen detail / Postfach / Günther | Dense multi-panel page |
| life-stats | LifecyclePage | Fälle / Mehrdeutige E-Mails / Offene Aufgaben | Dashboard counts | KEEP | Übersicht or Günther | |
| life-cases-table | LifecyclePage | Fallliste | Status, Firma, Stelle, Aktualisiert, ID | KEEP | Bewerbungen | |
| life-case-picker | LifecyclePage | Case combo | Target case for mail association | KEEP | Postfach | |
| life-ambiguous-emails | LifecyclePage | Mehrdeutige E-Mails | Subject/sender/category/id table | KEEP | Postfach | Needs Gmail connect |
| life-open-tasks | LifecyclePage | Offene Aufgaben | Text list of lifecycle tasks | KEEP | Bewerbungen / Übersicht | |
| life-timeline | CaseTimelinePanel | Timeline | Stages ●/○ path + corrections | KEEP | Bewerbungen detail | Stages: created→…→offer/archived etc. |
| life-btn-refresh | LifecyclePage | Aktualisieren | Reload cases/emails/tasks | KEEP | Günther | |
| life-btn-followups | LifecyclePage | Nachfassen vorschlagen | Generate follow-up/ghosting tasks (no send) | KEEP | Bewerbungen detail | |
| life-btn-link-email | LifecyclePage | E-Mail zuordnen | Prep ambiguous-mail approval | KEEP | Postfach | Requires email + case selection |
| life-btn-draft-reply | LifecyclePage | Antwort-Entwurf | Deterministic follow-up draft → approval | KEEP | Postfach / Bewerbungen detail | Send gated |
| life-btn-calendar | LifecyclePage | Kalender-Vorschlag | Calendar proposal → approval (ack only; no write) | KEEP | Kalender / Bewerbungen detail | Write behind CalendarWriteGate |
| life-btn-interview-prep | LifecyclePage | Interview-Prep | Talking points dialog from case/job | KEEP | Bewerbungen detail | |
| life-approval-panel | ApprovalPanel | Freigeben / Abbrechen | Explicit approve for consequential actions | KEEP | Bewerbungen detail / Postfach | Never auto-approve |
| life-approval-mail | ApprovalPanel | Mehrdeutige E-Mail zuordnen | Confirm mail→case link | KEEP | Postfach | |
| life-approval-reply | ApprovalPanel | Antwort-Entwurf freigeben | Confirm draft; still draft-only unless send enabled | KEEP | Postfach | |
| life-approval-calendar | ApprovalPanel | Kalender-Vorschlag freigeben | Ack proposal; no calendar write | KEEP | Kalender | Mockup gap: real write UX missing |
| guenther-bar | GuentherActionsBar | Günther — kontextuelle Hilfe | Contextual action buttons (not chatbot) | KEEP | Günther / Bewerbungen detail | Disabled when guenther off |
| guenther-action-improve-cover | GuentherActionsBar | Anschreiben verbessern | Hint dialog (local LLM when enabled) | KEEP | Günther | Stub/message today |
| guenther-action-draft-reply | GuentherActionsBar | Antwort erstellen | Same as draft reply flow | MERGE | Postfach | Works without LLM |
| guenther-action-explain-job | GuentherActionsBar | Job erklären | Fit explanation dialog | KEEP | Jobs / Günther | Needs guenther_enabled |
| guenther-action-prep-interview | GuentherActionsBar | Interview vorbereiten | Same as interview prep | MERGE | Bewerbungen detail | Status-gated |
| settings-tabs | SettingsPage | Einstellungen | Tabbed settings shell | KEEP | Einstellungen | |
| settings-tab-general | Settings tab 0 | Allgemein | Language, theme, a11y, Windows, about | KEEP | Einstellungen>Allgemein | |
| settings-language | General | Sprache | Deutsch / English | KEEP | Einstellungen | Restart note |
| settings-theme | General | Theme | System / Hell / Dunkel | KEEP | Einstellungen | |
| settings-high-contrast | General | Hoher Kontrast | A11y contrast mode | KEEP | Einstellungen>Barrierefreiheit | |
| settings-start-windows | General | Mit Windows starten | Autostart | KEEP | Einstellungen | |
| settings-minimize-tray | General | Beim Schließen im Hintergrund… | Tray minimize preference | KEEP | Einstellungen | |
| settings-about | General | Über Karrierekrake… | AboutDialog | KEEP | Einstellungen / Hilfe | |
| about-dialog | AboutDialog | Über Karrierekrake | Logo, version, tagline, tech identity paths | KEEP | Hilfe | |
| settings-tab-search | Settings tab 1 | Suche | Sources + search knobs | KEEP | Einstellungen>Suche | Overlaps Search page — clarify |
| settings-sources | Search tab | Jobquellen | BA, Indeed, LinkedIn, StepStone, XING, Unternehmensseiten | KEEP | Einstellungen>Suche | Per-source enable |
| settings-source-status | Search tab | Quellenstatus lines | Last-run health per source | MOVE | Einstellungen>Diagnose | |
| settings-search-mode | Search tab | Suchmodus | Profil-Entdeckung / Explizite Wunschberufe | KEEP | Einstellungen>Suche | |
| settings-jobs-per-search | Search tab | Jobs pro Suche (pro Quelle) | Cap including Max | KEEP | Einstellungen>Suche | |
| settings-published-days | Search tab | Veröffentlichungsalter (Tage) | Recency window | KEEP | Einstellungen>Suche | |
| settings-min-match-dash | Search tab | Min. Match Anzeige | Dashboard threshold | KEEP | Einstellungen>Suche | |
| settings-max-distance | Search tab | Max. Distanz (km) | Writes profile.location.max_distance_km | MERGE | Suche | Duplicate of SearchIntent radius |
| settings-tab-applications | Settings tab 2 | Bewerbungen | Mode, auto-apply, lifecycle, Günther | KEEP | Einstellungen>Bewerbungen | |
| settings-mode-search | Applications tab | Nur Suche – nie bewerben | Application mode | KEEP | Einstellungen | |
| settings-mode-review | Applications tab | Vor Absenden prüfen | Application mode | KEEP | Einstellungen | |
| settings-mode-auto | Applications tab | Vollautomatisch (sichere Bewerbungen) | Application mode | KEEP | Einstellungen | High-risk; gate carefully |
| settings-dry-run | Applications tab | Dry Run (nie endgültig absenden) | Global dry-run | KEEP | Einstellungen | First-run default on |
| settings-min-match-apply | Auto-Apply | Min. Match Auto-Apply | Threshold | KEEP | Einstellungen | |
| settings-max-per-run | Auto-Apply | Max. Bewerbungen / Lauf | Cap | KEEP | Einstellungen | |
| settings-max-per-day | Auto-Apply | Max. Bewerbungen / Tag | Cap | KEEP | Einstellungen | |
| settings-max-fail | Auto-Apply | Max. Fehler / Lauf | Cap | KEEP | Einstellungen | |
| settings-delay | Auto-Apply | Pause zwischen Bewerbungen (s) | Delay | KEEP | Einstellungen | |
| settings-auto-cover | Auto-Apply | Automatische Anschreiben | Toggle | KEEP | Einstellungen | |
| settings-auto-submit | Auto-Apply | Automatisch absenden | Toggle | KEEP | Einstellungen | Dangerous with dry_run off |
| settings-lifecycle-box | Applications tab | Nach der Bewerbung | Post-apply contact/follow-up prefs | KEEP | Einstellungen>Lifecycle | |
| settings-preferred-contact | Lifecycle | Bevorzugter Kontakt | E-Mail / Telefon / Beides | KEEP | Einstellungen | Combo labels partially DE hard-coded |
| settings-phone-available | Lifecycle | Telefonische Erreichbarkeit anbieten | Toggle | KEEP | Einstellungen | |
| settings-telephone-availability | Lifecycle | Telefon-Zeitfenster | Free text | KEEP | Einstellungen | |
| settings-working-hours | Lifecycle | Arbeitszeiten (Kalender) | Free text default 09:00-17:00 | KEEP | Einstellungen / Kalender | |
| settings-follow-up-days | Lifecycle | Nachfassen nach (Tagen) | Policy | KEEP | Einstellungen | |
| settings-ghosted-days | Lifecycle | Ghosting-Hinweis nach (Tagen) | Policy | KEEP | Einstellungen | |
| settings-followup-enabled | Lifecycle | Nachfassen / Ghosting-Hinweise aktiv | Toggle | KEEP | Einstellungen | |
| settings-followup-reminders | Lifecycle | Persistente Nachfass-Erinnerungen | Toggle (no auto-send) | KEEP | Einstellungen | |
| settings-email-draft-only | Lifecycle | Arbeitgeber-Mails nur als Entwurf | Default-safe send policy | KEEP | Einstellungen / Postfach | |
| settings-allow-employer-email-send | Lifecycle | Echten Versand freigeben… | Explicit send unlock | KEEP | Einstellungen / Postfach | High-risk |
| settings-guenther-box | Applications tab | Günther die Krake | Local assist enable + model | KEEP | Einstellungen>Günther | |
| settings-guenther-enabled | Günther | Günther einschalten (nur lokal…) | Toggle | KEEP | Einstellungen | |
| settings-guenther-model | Günther | Modell | auto / Phi / light / legacy 4B | KEEP | Einstellungen | |
| settings-guenther-hint | Günther | Günther denkt mit… | Privacy/local-AI explanation | KEEP | Einstellungen | |
| settings-tab-advanced | Settings tab 3 | Erweitert | Automation schedule + browser | KEEP | Einstellungen>Erweitert | |
| settings-run-auto | Advanced | Automatisch ausführen | Schedule enable | KEEP | Einstellungen | |
| settings-schedule-mode | Advanced | Zeitplan | on_login / every_x_hours / once / twice / custom | KEEP | Einstellungen | |
| settings-interval | Advanced | Intervall (Stunden) | For every_x_hours | KEEP | Einstellungen | |
| settings-custom-times | Advanced | Zeiten | Comma HH:MM list | KEEP | Einstellungen | |
| settings-paused | Advanced | Automation pausiert | Same flag as tray/dashboard | KEEP | Einstellungen / Übersicht | Duplicate control OK if synced |
| settings-browser-status | Advanced | Browser-Automatisierung: bereit/fehlt | Playwright readiness | MOVE | Einstellungen>Diagnose | |
| settings-browser-check | Advanced | Browser-Komponente prüfen | Async check worker | MOVE | Einstellungen>Diagnose | |
| settings-browser-repair | Advanced | Browser-Automatisierung installieren / reparieren | Async repair/install worker | MOVE | Einstellungen>Diagnose | |
| settings-tab-privacy | Settings tab 4 | Datenschutz | OAuth + export + destructive deletes | KEEP | Einstellungen>Datenschutz | DSGVO surface |
| privacy-intro | Privacy | Datenschutz intro | Legal/UNSPECIFIED disclaimer | KEEP | Datenschutz | |
| privacy-connect-gmail | Privacy | Gmail verbinden (nur Lesen) | OAuth gmail.readonly | KEEP | Postfach / Datenschutz | Confirm dialog; opens system browser |
| privacy-connect-calendar | Privacy | Kalender FreeBusy verbinden | OAuth freebusy (feature-flagged) | KEEP | Kalender / Datenschutz | Requires calendar_freebusy_enabled |
| privacy-export | Privacy | Meine Daten exportieren… | Export PII without tokens | KEEP | Datenschutz | Folder picker |
| privacy-disconnect-google | Privacy | Google-Verbindung trennen | Revoke + wipe tokens | KEEP | Datenschutz | Destructive |
| privacy-delete-mail | Privacy | Mail-Cache löschen | Delete mail cache | KEEP | Datenschutz | |
| privacy-delete-calendar | Privacy | Kalender-Cache löschen | Delete calendar cache | KEEP | Datenschutz | |
| privacy-delete-logs | Privacy | Logs löschen | Delete logs | KEEP | Datenschutz / Diagnose | |
| privacy-delete-all | Privacy | ALLE lokalen Daten löschen | Full wipe via delete_all_local_data | KEEP | Datenschutz | Confirm; verify |
| settings-save | SettingsPage | Einstellungen speichern | Persist + ScheduleService.sync | KEEP | Einstellungen | |
| logs-page | LogsPage | Protokolle | Humanized event list + technical detail | MOVE | Einstellungen>Diagnose | |
| logs-refresh | LogsPage | Aktualisieren | Reload latest log file | KEEP | Diagnose | |
| logs-event-list | LogsPage | Ereignisliste | Plain-language CAPTCHA/review/search/apply/error lines | KEEP | Diagnose | |
| logs-technical | LogsPage | Technische Details | Raw log line for selected event | KEEP | Diagnose | |
| list-editor-add-remove | ListEditor (shared) | Hinzufügen / Entfernen | Generic list CRUD used across Profil/Suche | KEEP | Shared | |
| structured-editor-crud | structured_editors | Hinzufügen / Bearbeiten / Entfernen | Experience/education/language/certificate dialogs | KEEP | Profil | |
| a11y-nav-annotations | design_system.a11y | (screen reader names) | Nav position, form wiring, list editor names | KEEP | Shell a11y | Not visual copy |
| status-labels | status_labels + tables | Job/app status DE labels | Localized JobStatus display | KEEP | Jobs / Bewerbungen | |

## Coverage checklist (requested areas)

| Area | Covered? | Primary rows |
| --- | --- | --- |
| Navigation | Yes | `shell-nav-*` |
| Every page | Yes | dash / search / profile / jobs / apps / life / settings / logs |
| Widgets / dialogs | Yes | fit, timeline, approval, guenther bar, apply preview, CV import, about, list/structured editors |
| Wizard / first-run | Yes | `wizard-*` |
| Tray | Yes | `tray-*` |
| Settings tabs + controls | Yes | `settings-*` |
| Privacy / OAuth connect-disconnect | Yes | `privacy-*` |
| Jobs / apply / preview | Yes | `jobs-*`, `apply-preview-*`, dash apply/test |
| Applications / lifecycle | Yes | `apps-*`, `life-*` |
| Search | Yes | `search-*` (+ settings search knobs) |
| Profile / CV import | Yes | `profile-*`, `cv-import-*` |
| Email / inbox / association | Yes | ambiguous mail table + link + Gmail OAuth (no full inbox UI) |
| Calendar / interview | Yes | calendar proposal + interview prep (+ FreeBusy connect) |
| Logs / diagnose | Yes | `logs-*`, browser check/repair, source status, clear jobs |
| Günther / lifecycle UI | Yes | `guenther-*`, `life-*`, settings Günther |
| Dry-run / automation modes | Yes | wizard dry-run, settings mode/dry-run/auto, dash/tray pause, apply-test |
| Destructive privacy | Yes | profile reset scopes + privacy deletes |

## Notable gaps / risks for V2 mockups

1. **No dedicated Postfach or Kalender pages** — mail association and calendar live inside Günther/Lifecycle + Privacy OAuth.
2. **Dashboard vs Übersicht naming mismatch** (nav `Dashboard`, page title `Übersicht`).
3. **Duplicate distance / remote controls** across Profil, Suche, Einstellungen>Suche.
4. **`jobs.age_days` spinbox is dead UI** (constructed, never shown/applied).
5. **Günther “Anschreiben verbessern”** is largely a hint stub vs full editor.
6. **Calendar approve acknowledges only** — real calendar write not end-user complete.
7. **Legacy Profile Berufswunsch UI** still shippable via flag; V2 should decide KEEP-as-hidden vs delete.
8. **Fully automatic + auto_submit + dry_run off** is the highest-risk mode cluster — preserve but redesign gating.
9. **Hide applied/duplicates** are config defaults used by Jobs list, not exposed as on-page toggles.
10. **Email “inbox”** is ambiguous-mail queue only, not a full mailbox browser.

## Suggested V2 IA (preservation-oriented)

| V2 target | Absorb from V1 |
| --- | --- |
| Übersicht | Dashboard next-action, primary CTAs, key stats, pause, last/next run |
| Suche | SearchPage + (optional) settings search mode/sources summary |
| Jobs | Jobs filters, table, fit panel, prepare/open |
| Bewerbungen | Applications table + timeline + prepare/preview + follow-ups |
| Postfach | Ambiguous mail, link email, reply draft, Gmail connect |
| Kalender | FreeBusy connect, calendar proposal, working hours |
| Profil | Profile sections, CV import/reset scopes, applicant data |
| Günther | Contextual actions bar + model settings (assist, not chat) |
| Einstellungen | Modes, dry-run, automation, schedule, lifecycle prefs |
| Einstellungen>Datenschutz | Privacy tab + destructive wipes |
| Einstellungen>Diagnose | Logs, browser check/repair, source status, clear jobs, run stats |
| Tray / Onboarding | Tray actions; 3-step wizard |

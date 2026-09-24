# Merge-Gates (Kritiker)

**Stand gelesen:** `main` `cca25fcfb16fc8a23376e52a5f2f1af829ac7142`  
(Commit-Betreff: UI-Primäraktionen, bereits gemergtes #63).  
**Datum:** 2026-09-24.  
**Rolle:** Checkliste für Merge-Entscheidungen. Dieses Dokument implementiert kein Job Object, kein Matching und keinen Parser.

Ein Fail in einem harten Gate bleibt ein Fail. Ein PASS in einem anderen Gate hebt ihn nicht auf. Zahlen aus der Agent-VM gelten nicht als Windows-Nachweis.

Branches und PRs **#62** (`cursor/docpick-qwen35-cv-replace-d85b`) und **#63** (`cursor/primary-actions-ui-polish-d85b`, bereits auf `main`) werden von dieser Review nicht angefasst.

---

## 1. Peak Prozessgruppe (DevOps, Job Object)

| | |
|---|---|
| Grenze | Peak der **Prozessgruppe** ≤ `3_300_000_000` Bytes |
| Messort | Echtes **i3 / 8 GB Windows**, Messung über ein **Job Object** |
| Zählt nicht | Agent-VM, Linux-Container, „hat bei mir geladen“ |
| Fail | Zuerst kleineres Modell. Bleibt der Peak darüber: **lokales LLM-CV-Parsing aus** |
| Owner | DevOps. Hier nur das Gate, keine Implementierung |

#62 nennt in der PR-Beschreibung eine andere Annahme (Peak RSS ≤ 12 GB). Diese Annahme ist **kein** Ersatz für die 3_300_000_000-Byte-Grenze auf der Zielhardware.

---

## 2. Extrakt-Flow (hart)

Alle Punkte müssen gleichzeitig gelten, sobald ein schweres Parse (Docling / lokales LLM) im Lebenslauf-Import hängt:

1. Kein synchrones Parse auf dem UI-Thread.
2. Sichtbarer Fortschritt und Abbruch, der den Lauf wirklich beendet.
3. Leerzustand und Fehlerzustand jeweils mit einer Handlungsaufforderung (CTA).
4. OOM und Timeout: nur **manueller** erneuter Versuch. Kein automatischer Retry im selben Lauf.

### Beleg auf `main`: synchrones `import_cv` im Dialog-Konstruktor

**Hypothese bestätigt** für `main` @ `cca25fc`.

`ProfilePage.import_from_cv` erzeugt den Dialog direkt im UI-Slot. `CvImportDialog.__init__` ruft `import_cv` auf, **bevor** `dlg.exec()` läuft. In `desktop/workers.py` auf `main` gibt es `PipelineWorker` und Browser-Worker, keinen CV-Import-Worker.

Aufrufkette:

| Schritt | Ort |
|---|---|
| UI-Slot | `desktop/pages/profile.py` — `ProfilePage.import_from_cv` |
| Konstruktor | `desktop/widgets/cv_import_dialog.py` — `CvImportDialog.__init__` |
| Synchroner Parse | `import_cv(...)` in dem `try` des Konstruktors |
| Delegation | `core/cv_parser.py` — `import_cv` → `core/cv_intelligence.py` — `import_cv_canonical` (`extract_text` + `parse_cv_text`, blockierend) |

Der Abbrechen-Button wird im Konstruktor verdrahtet (`buttons.rejected.connect(self.reject)`), die Ereignisschleife des Dialogs startet erst mit `exec()` **nach** dem Parse. Während `import_cv` läuft, kann niemand abbrechen. Es gibt keine Fortschrittsanzeige. Bei einer Exception erscheint `QMessageBox.warning` noch im Konstruktor; der Dialog öffnet danach mit dem Fehlertext in der Vorschau, ohne eigene Leer-/Fehler-CTA. `Übernehmen` ruft bei fehlendem `incoming` nur `reject()` auf.

Auf `main` ist dieser Pfad noch der deterministische DET-Import (`guenther_enabled=False`, Phi wird ignoriert). Das ändert die Thread-Tatsache nicht.

### Merge-Blocker

Jeder Pfad, der ein schweres LLM-Parse in `CvImportDialog` hängt, solange der Parse im Konstruktor auf dem UI-Thread läuft, ist ein **Merge-Blocker**. Das gilt insbesondere für die Richtung von **#62**.

### Gegengelesen, nicht geändert: #62-Spitze

Stand der gelesenen Spitze von `cursor/docpick-qwen35-cv-replace-d85b` (nur `git show` / `git diff`, kein Commit auf dem Branch):

- `CvImportDialog.__init__` ruft dort `import_cv` nicht mehr direkt auf. `_start_extract` startet `CvImportWorker` (`desktop/workers.py`) über `start_worker`.
- `import_cv_docpick` (`core/cv_docpick_import.py`) prüft `should_cancel` zwischen Preflight, PDF und Modell. Der Kommentar im Code sagt: Abbruch zwischen Docling und dem LLM-Aufruf.
- `_llm_extract` blockiert im `VLLMProvider`-Aufruf mit `timeout=300`. Ein Cancel-Flag innerhalb dieses Aufrufs ist an den genannten Stellen nicht sichtbar.
- In `core/cv_docpick_import.py`, `desktop/widgets/cv_import_dialog.py` und `desktop/workers.py` auf diesem Branch gibt es keine Treffer für `retry`, `OOM` oder `MemoryError`.

Damit ist der Extrakt-Flow auf der #62-Spitze **nicht** als erfüllt abgehakt. Fortschritt ist angefangen. Abbruch während des Modellaufrufs, Leer/Fehler mit Retry-CTA und „kein Auto-Retry bei OOM/Timeout“ bleiben offen. Diese Review schreibt den Parser nicht um.

---

## 3. Blind-F1 und Seal

| Regel | Inhalt |
|---|---|
| Blind-Schwelle | Frozen **Blind-F1 0,980** auf **NV3** |
| Audit | Ein späterer Audit-F1 ist ein anderes Maß. Er ersetzt den Blind-Score nicht und ist kein 99-%-Claim |
| Seal | Erst wenn **Owner** und eine **zweite Person auf #62** den Blind-Seal zeichnen |

Quelle (liegt auf dem #62-Branch, nicht auf `main`): `docs/project/DOCPICK_NV3_PHASE_B_AUDIT.md`.

Dort steht: Frozen Blind-F1 **0,980** (Phase B, Seal `169624a3…`, Commit `2d0d610`). Dieselbe Datei führt einen Audit nach DOB-Tagesnorm mit F1 **0,990** und schreibt ausdrücklich: kein Blindnachweis, kein 99-%-Claim, kein erneuter Blindtest. Diese Review hat den Score nicht neu gerechnet.

---

## 4. Parser-Schulden (hart für unbestätigte Folgepfade)

Belegt in denselben #62-Dokumenten, nicht durch einen neuen Lauf auf `main`:

| Schuld | Beleg | Folge |
|---|---|---|
| Fehlende Ausbildung | `DOCPICK_NV3_PHASE_B_AUDIT.md` Abschnitt 2 und 6: 10 Dokumente mit `education=[]`, obwohl der Ausbildungstext im PDF steht (Beispiel NV3_005) | Block |
| Falsche aktuelle Stellen | Dieselbe Datei: `heute`, obwohl das PDF ein datiertes Ende zeigt (5 Docs). `DOCPICK_ROUND4_KEEP_REVERT.md`: Prompt „current job → heute“ hat `end_date=heute` erfunden | Block |

**Harter Block:** unüberwachter Import, Matching und Anschreiben, solange diese Schulden offen sind und die betroffenen Felder nicht vom Nutzer bestätigt wurden.

Der DET-Pfad auf `main` setzt in `_parse_experience` (`core/cv_parser.py`) bei „Seit …“ das Ende auf `aktuell`. Das ist ein anderer Codepfad als das erfundene `heute` des Qwen-Prompts. Die Schuld oben bezieht sich auf den Docpick/Qwen-Audit, nicht auf eine neue DET-Änderung.

Diese Review ändert Modellqualität und Parser nicht.

---

## 5. Matching-Vertrag (zitiert, nicht erfunden)

Implementierung von Matching liegt bei einem anderen Agenten. Verbindlich ist das Schema, das auf `main` schon existiert:

`core/models.py`, Klasse `MatchResult`:

- `score: int`
- `match_reasons: list[str]`
- `rejection_reasons: list[str]`
- `excluded: bool`
- `exclude_reason: str | None`
- `evidence: list[dict]`
- `ranking_version: str`
- `intent_explanation: dict`

`core/matcher.py`: `EvidenceClass = Literal["DIRECT", "RELATED", "NOT_SUPPORTED"]`. `MatchEvidence.label` mappt `NOT_SUPPORTED` auf „Nicht belegt“. Moduldoc: kein LLM; Glue-Wörter zählen nicht als Erfahrung.

`docs/search-intent-filtering.md`: harte Filter bleiben hart; `MatchResult.intent_explanation` / `rejection_reasons` / `match_reasons` sind Begründung, **kein Marketing-Prozent**.

**Unbelegte Claims:** ein Treffer der Klasse `NOT_SUPPORTED` darf in Matching, UI und Anschreiben nicht als belegte Qualifikation erscheinen. Ein neues Matching-Schema wird hier nicht definiert.

---

## 6. PR #64 — UI-QA-Gates

PR: https://github.com/deadfrogface/Karrierekrake/pull/64  
Branch: `cursor/ui-qa-fixes-4ee6` (Draft). Basis beim Lesen: `main` `cca25fc`. Diff etwa +1145 / −158, 21 Dateien.

### Was als UI-QA durchgehen kann

Beschriftete Bestätigungen und die dazu gehörende Barrierefreiheit der Button-Namen:

- Neu `desktop/widgets/confirm_dialog.py`: `label_button_box`, `build_confirm_box`, `confirm_action` setzen i18n-Text und `set_accessible_name` (`desktop/design_system/a11y.py`).
- Auf dem #64-Branch findet `QMessageBox.question(` in `desktop/**/*.py` nicht mehr als Aufruf statt (nur Kommentar plus Test, der das verbietet).
- Tests: `tests/test_ui_qa_findings.py` (`test_confirm_box_buttons_carry_i18n_labels`, `test_destructive_confirm_defaults_to_cancel`, `test_no_unlabeled_question_boxes_in_desktop_sources`, KPI-Tastatur/Klick).

Rechtlicher BFSG-Status bleibt der aus `docs/accessibility/bfsg-engineering-report.md`: technische Namen und Fokus, keine Konformitätsbehauptung.

`desktop/widgets/cv_import_dialog.py` auf #64 tauscht nur die Button-Box gegen `label_button_box`. Der synchrone `import_cv`-Aufruf im Konstruktor bleibt. **Ein UI-QA-PASS von #64 ist kein Extrakt-Flow-PASS.**

### Dark: vollständig belegt oder nur Hell

Dark ist auf #64 **nicht** vollständig belegt.

Vorhanden: `test_apply_theme_dark_sets_matching_palette`, `test_dark_settings_body_is_not_light`, plus PR-Screenshots für Einstellungen (Dark) und einen Export-Dialog. Die Übersicht im PR-Text ist als Light beschrieben.

Für einen Dark-Merge müssen die Primärflächen im Dark-Theme lesbar sein: Übersicht, Jobs, Profil, Suche, Einstellungen, Hilfe, Bestätigungsdialoge (Text auf Buttons, Scrollflächen, GroupBox). Bis dieser Durchlauf vorliegt, gilt das Paket als **nur Hell**.

### Dateien, die kein reines UI-QA sind

Die Behauptung „nur UI, kein Qwen-RAM“: **Qwen/RAM trifft zu. „Nur UI“ trifft nicht zu.**

Im Diff von `origin/main...origin/cursor/ui-qa-fixes-4ee6` gibt es keine Treffer auf Qwen, Docling, llama, GGUF oder RSS-Limits.

| Datei | Klasse | Was sich ändert |
|---|---|---|
| `core/geo_resolve.py` | **Verhalten / Scope** | `resolve_city_pgeocode`: zuerst exakter Ortsname auf der vollen lokalen Tabelle (`_exact_city_rows`), Fuzzy nur als Fallback. Streuung nicht mehr 0,5°, sondern `CITY_SPREAD_MAX_KM = 35` über Haversine um den Mittelpunkt. Berlin kann dadurch `RESOLVED` werden. |
| `core/location.py` | **Verhalten, Nutzertext** | Warnung bei ungelöstem Wohnort in Alltagssprache, mit Bitte um PLZ. Die Auflösung selbst bleibt in `geo_resolve`. |
| `app/main.py` | **Verhalten / Scope** | `run_pipeline(..., recover_interrupted: bool = True)`. Die DB-Recovery (`applying` → `needs_review`) ist steuerbar. Default bleibt `True` für Headless/Scheduler. |
| `desktop/workers.py` | **Verhalten, eine Zeile** | `PipelineWorker` übergibt `recover_interrupted=False`. GUI-Suche heilt nicht bei jedem Start erneut. |
| `desktop/widgets/cv_import_dialog.py` | **UI-QA** | Nur beschriftete Standardbuttons. Parse-Pfad unverändert synchron. |

### Überlappung Data Engine / Standort

Kanonisch auf `main`: `docs/architecture/local_first_google_calendar_and_geo.md` und `docs/architecture/canonical-product-decisions.md` — lokale DACH-Auflösung, Reihenfolge Koordinaten → Land+PLZ → eindeutiges Land+Ort → UNKNOWN, nie raten. #64 ändert genau die Stadtauflösung (Berlin-PLZ versus Fuzzy-Top-100, 35-km-Streuung). Das ist Standortlogik, die der Data-Engine-Arbeit gehört. Vor dem Merge von #64 braucht dieser Hunk eine Sicht des Standort-Owners. Halle/Frankfurt sollen laut den neuen Tests in `tests/test_local_first_geo.py` `AMBIGUOUS` bleiben; das ersetzt die Owner-Sicht nicht.

### CI beim Lesen (2026-09-24)

`mergeable: MERGEABLE`, `mergeStateStatus: UNSTABLE`.  
Windows Smoke `qt-smoke` und `build-and-exe-smoke`: Erfolg.  
CI: `privacy`, `cv-regression`, `database-migration-tests`, `static-smoke`, `lifecycle-e2e-benchmark`, `security`: Erfolg.  
`unit-tests`: beim ersten Lesen noch `IN_PROGRESS` (Run `36059840760`). Mergen, solange `UNSTABLE` ist, ist untersagt. Den Status vor dem Merge neu lesen.

---

## 7. Diffs der 76k-Klasse zerschneiden

#62 zum Zeitpunkt dieser Review: **+78740 / −167, 561 Dateien** (Draft). Ein Diff dieser Größe wird nur in Scheiben gemergt:

| Scheibe | Inhalt |
|---|---|
| Import | Dialog, Worker, Fortschritt, Abbruch, Fehler-CTA |
| Extraction-Mapping | Schema, Feldzuordnung, Postprocess |
| Model ops | Server, Modelldatei, Speicher, Timeout |
| Tests-Scorer | Freeze, Seal, Scorer, Fixtures |
| Docs | Berichte, Gates, Lizenzen |

Ein Monolith-Merge von #62 ist untersagt. Diese Review schneidet den Branch nicht um.

---

## 8. Tester-Skript (manuell, für #64)

Branch unter Test: `cursor/ui-qa-fixes-4ee6`. Diese Review-Branch enthält die Checkliste und keinen UI-Fix.

1. **Beschriftungen.** Sprache DE, dann EN. Auslösen: Export, Löschen (Mail/Kalender/Logs), Verbindung trennen, Profil zurücksetzen. Jeder Button zeigt ein Wort (Exportieren, Löschen, Trennen, Abbrechen, …). Kein leeres Icon auf heller Fläche. Bei destruktiven Dialogen ist der Default Abbrechen; Enter löscht nicht. Tab erreicht die Buttons; der zugängliche Name entspricht der Beschriftung.
2. **Dark oder nur Hell.** Wenn Dark im Build an ist: Übersicht, Jobs, Profil, Suche, Einstellungen (Scroll-Inhalt), Hilfe, ein Bestätigungsdialog. Text, Buttons und GroupBox-Titel müssen lesbar sein. Eine unlesbare Fläche: Dark gilt als nicht bestanden, Auslieferung nur Hell. Ein einzelner Einstellungs-Screenshot reicht nicht.
3. **Explizit außerhalb eines #64-PASS.** Lebenslauf-Import auf Fortschritt, Abbruch während des Parsens, leere Extraktion mit CTA, Fehler mit CTA. Diese vier Punkte nicht als bestanden werten, auch wenn der Dialog sich öffnet. Der Parse auf `main` und in der #64-Button-Änderung läuft weiter synchron in `CvImportDialog.__init__`.
4. **Getrennte Verhaltenschecks, kein UI-QA-Haken.** Wohnort „Berlin, Deutschland“: Auflösung oder Klartext-Hinweis mit PLZ-Bitte. „Halle“ und „Frankfurt“ bleiben mehrdeutig. Suche starten und abbrechen: Zähler „Prüfung nötig“ steigt dadurch nicht, nur weil ein Job `applying` war.

---

## 9. Was diese Review nicht entscheidet

- Kein Commit auf #62 oder #63.
- Kein Umschreiben von Qwen, Docling oder DET-Qualität.
- Kein Job-Object-Code, kein Matching-Code.
- Der Blind-Seal wird hier nicht erteilt.

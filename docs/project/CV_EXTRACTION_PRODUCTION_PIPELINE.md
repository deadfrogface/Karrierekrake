# CV Extraction — Production Pipeline

**CV Extraction: deterministic**  
**Writing Assistance: optional local AI**

Phi / C1 / Hybrid extraction are **not** part of this path.

## Diagram

```text
CV / PDF / DOCX / TXT / …
↓
Document extraction (core.cv_extract.extract_text)
↓
DET: parse_cv_text (core.cv_parser)
↓
Section-/Block-Erkennung (core.cv_sections)
↓
Deterministische Feldextraktion
↓
Schema- / Evidence- / Cross-Field-Validierung
↓
Deterministische Targeted Repairs (core.cv_verify_repair)
↓
Verifiziertes Profil → Preview / Approval / Persist
```

## Komponenten

| Stufe | Modul / Funktion | Hinweis |
| ----- | ---------------- | ------- |
| Einstiegspunkt UI | `desktop/widgets/cv_import_dialog.py` | ruft `import_cv(..., guenther_enabled=False)` |
| Einstiegspunkt API | `core.cv_parser.import_cv` → `core.cv_intelligence.import_cv_canonical` | `guenther_*` Parameter werden ignoriert |
| Dateitypen | PDF, DOCX, TXT (+ Backends in `cv_document_backends`) | Born-digital; OCR separat |
| Dokumentextraktor | `core.cv_extract.extract_text` | kein Phi |
| Text-/Blockdarstellung | Zeilen/Blöcke in `parse_cv_text` | |
| Section Detection | `core.cv_sections` | Praxis, Werkzeuge, Kenntnisse, … |
| Persönliche Daten | Parser personal helpers | Name, Kontakt |
| Adresse | Adress-Fixes (EU/DE) | |
| Kontakt | E-Mail, Telefon aus Text | |
| Employment | `work_experience` | |
| Education | `education` | |
| Languages | `languages` (+ Level) | |
| Licences | Führerschein etc. | |
| Skills / Software | Kenntnisse-Routing, Wrap-Fixes | |
| Certificates | `certificates` | |
| Evidence | `cv_evidence` / verify pipeline | |
| Schema Validation | verify/repair | |
| Cross-Field Validation | verify/repair | |
| Deterministic Repairs | `apply_verify_repair_pipeline` | |
| Fehlermeldungen | `intelligence_notes`, Confidence-Texte | |
| UNCERTAIN | leere / unklare Felder bleiben leer | **kein** Phi-Aufruf |
| Ausgabe Profil | Dialog → Qualifications / Personal | |

## Explizit ausgeschlossen

* PHI_EXTRACT / `suggest_cv_extract`
* C1 Thin Routing / Fallback
* Phi Verify / Repair / Field Arbitration
* parallele DET/Phi-Extraktion
* Phi-Dokumentklassifizierung / Confidence / Kategorie
* Modellladung beim CV-Import

Wenn DET unsicher ist: `NULL` / `UNKNOWN` / `UNCERTAIN` — niemals erfunden und niemals Phi.

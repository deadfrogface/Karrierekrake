# Extrakt-UX — Upload → Extract (Zustände)

Status: **Spezifikation und Abnahmeskript**. Dieser Stand enthält keinen Dialog-Code, keinen Worker und keine Parser-Änderung.

Stand der Beschreibung: `main` @ `cca25fc` (`CvImportDialog` liest den Lebenslauf noch synchron in `__init__`, vor `exec()`).

## Entscheidung dieses PR

**docs-only.** Kein zweiter `CvImportDialog`-Rewrite und kein eigener QThread.

Worker, Fortschritt, Abbruch sowie Peak-/Job-Object-Gate (≤ 3,3 GB) bleiben bei DevOps, Agent `bc-49012cc4-da3e-5086-badf-9f7fbb7eddf8`. Sobald deren PR einen Parse-Worker hat, setzt die Dialog-UX die Zustände aus diesem Dokument darauf. Bis dahin ist dieses Dokument der Vertrag für Copy, Zustände und Tester.

Parser, Qwen, Prompt und F1 bleiben bei Damiano (PRs #62 und #63). Dieses Dokument ändert keine Modell- oder Prompt-Pfade und beansprucht kein Extrakt-PASS aus #64 (Confirm/Dark ist ein anderes Thema).

## Latte (ChatGPT-UX) — Sollzustände

Harte Regel: **kein toter Klick**. Ein sichtbarer, aktiv wirkender Knopf muss den beschrifteten Zustandswechsel auslösen. Aktionen, die im aktuellen Zustand nichts tun dürfen, sind **ausgeblendet**, nicht nur grau und klickbar ohne Wirkung.

| Zustand | Wann | Sichtbar und wirksam | Ausgeblendet |
|---|---|---|---|
| **Progress** | Parse läuft | Dateiname/Pfad, Fortschrittstext, **Abbrechen** | Übernehmen, Modus, Konflikte, Erneut versuchen, Leer-CTA |
| **Cancel** | Nutzer bricht laufenden Parse ab | Kurztext „nichts übernommen“, erhaltener Pfad, **Erneut einlesen**, **Schließen** | Übernehmen |
| **Success** | Parse ok und mindestens ein verwertbares Feld | Bisherige Vorschau (Modus Ersetzen/Zusammenführen, Konflikte), **Übernehmen**, **Abbrechen** | Fehler-, Leer- und Fortschrittsfläche |
| **Empty** | Parse ok, aber kein verwertbares Feld | Leerer Zustand mit nächstem Schritt, erhaltener Pfad, **Andere Datei wählen**, **Schließen** | Übernehmen |
| **Error** | Lesefehler, OOM oder Timeout | Klarer Fehlertext, erhaltener Pfad, **Erneut versuchen**, **Schließen** | Übernehmen, Modus |

Success bleibt in der Sache die heutige Vorschau. Confirm-Texte (`cv_import.apply` = „Übernehmen“, Modus-Labels) werden von diesem Vertrag **nicht** geändert.

## Zustandswechsel

```text
Dialog öffnet sich sichtbar
        │
        ▼
    Progress ──Abbrechen──► Cancel ──Erneut einlesen──► Progress
        │                      │
        │                      └──Schließen──► Dialog zu, nichts übernommen
        │
        ├── Inhalt ──────────► Success ──Übernehmen──► Profil schreiben (bestehender Apply-Pfad)
        │                         └──Abbrechen──► Dialog zu, nichts übernommen
        │
        ├── leer ────────────► Empty ──Andere Datei──► neuer Pfad, dann Progress
        │                         └──Schließen──► Dialog zu, nichts übernommen
        │
        └── Exception ───────► Error ──Erneut versuchen──► Progress (ein manueller Lauf)
                                  └──Schließen──► Dialog zu, nichts übernommen
```

Regeln:

- Der Dialog ist **sichtbar, bevor** der Parse startet. Fortschritt und Abbrechen gibt es nur, wenn der Parse nicht mehr den UI-Thread in `__init__` blockiert. Das ist die DevOps-Worker-Voraussetzung, kein zweiter Worker in diesem PR.
- Abbrechen während Progress fordert den Abbruch des laufenden Laufs an und übernimmt **keine** Qualifikationen und **keine** persönlichen Felder.
- Nach Cancel, Empty und Error bleibt der Dateipfad stehen. Ein bereits in den Speicher kopierter Lebenslauf wird nicht gelöscht. Profilseite schreibt Qualifikationen nur bei angenommenem Dialog (`Accepted`) — diese Zustände nehmen den Dialog nicht an.
- „Andere Datei wählen“ ist eine neue Nutzeraktion (Dateidialog). Bricht der Nutzer den Dateidialog ab, bleibt Empty mit dem alten Pfad.

## Leer-Extrakt

Leer ist ein **erfolgreicher** Parse ohne verwertbare Daten, kein Fehler.

Leer genau dann, wenn nach dem bestehenden Filter (`filter_parsed_for_import`) gilt:

- `personal_from_parsed` ist leer, und
- `summarize_incoming` hat in Sprachen, Führerschein, Ausbildung, Berufserfahrung, Zertifikate, Software und Skills keine Einträge.

Nur `uncertain_items` oder Confidence-Zeilen „nicht gefunden“ zählen nicht als Inhalt. Teilweise Erkennung (mindestens ein Personenfeld oder ein Qualifikationspunkt) bleibt **Success**; leere Abschnitte dort weiter als bisherige „(nichts erkannt)“-Zeilen. Die eigene Leerfläche ersetzt nur den Fall, in dem die ganze Vorschau inhaltlich leer wäre.

Copy (DE): Die Extrakt-UX-i18n-Keys führt PR #70 ein (noch nicht auf `main`, bis #70 gemergt ist):

- Titel: „Nichts erkannt“
- Text: „In dieser Datei wurden keine Profildaten erkannt. Es wurde nichts übernommen. Wähle eine andere Datei oder schließe den Dialog.“
- Primär: „Andere Datei wählen“
- Sekundär: „Schließen“

## Fehler, OOM, Timeout

Kein generisches MessageBox-only und kein Fehlertext allein in der Vorschau. Die Fehlerfläche zeigt Titel, Klartext, Dateipfad und die beiden Knöpfe. Technische Exception darf zusätzlich als auswählbarer Nebenhinweis stehen, ersetzt die Fläche nicht.

Klassifikation nur an der Exception-Art, **ohne** Parser- oder Modellwechsel:

| Art | Erkennung (UI) | DE-Klartext |
|---|---|---|
| OOM | `MemoryError` oder Meldung mit OOM / out of memory / cannot allocate | „Nicht genug Arbeitsspeicher, um diese Datei einzulesen. Es wurde nichts übernommen. Karrierekrake startet den Vorgang nicht automatisch neu.“ |
| Timeout | `TimeoutError` oder Meldung mit Timeout / Zeitüberschreitung | „Das Einlesen hat zu lange gedauert und wurde abgebrochen. Es wurde nichts übernommen. Es wird nicht automatisch erneut versucht.“ |
| Sonst | übrige Exception | „Die Datei konnte nicht gelesen werden. Pfad und Eingaben bleiben erhalten.“ |

### Kein Auto-Retry

- Nach OOM, Timeout und jedem anderen Fehler startet **kein** zweiter `import_cv`-Lauf von selbst.
- Kein Modellwechsel, kein Fallback-Lauf, kein erneutes Starten desselben Modell-Laufs.
- „Erneut versuchen“ startet **genau einen** neuen Lauf der **gleichen** Datei und nur nach Klick.
- Schlägt der manuelle Retry fehl, bleibt Error; der Pfad bleibt sichtbar.
- Peak-Messung und Job-Object-Kill bleiben DevOps. Die UI behandelt das Ergebnis als Fehlerzustand und retry’t nicht selbst.

## Progress- und Cancel-Copy

Progress (DE):

- „Lebenslauf wird eingelesen…“
- Dateiname sichtbar
- Unbestimmter Fortschritt, solange der Worker keine echten Stufen meldet. Kein erfundener Prozentwert.
- Knopf: „Abbrechen“

Cancel (DE):

- „Einlesen abgebrochen. Es wurde nichts übernommen.“
- Pfad bleibt sichtbar
- „Erneut einlesen“ (manuell), „Schließen“

## Vorgeschlagene i18n-Keys (noch nicht einbauen)

Erst nach dem DevOps-Worker, als dünner Overlay auf dessen Dialog. Bestehende Keys (`cv_import.apply`, Modus, `cv_import.none`, `cv_import.read_error`) nicht umwidmen.

| Key | DE |
|---|---|
| `cv_import.progress` | Lebenslauf wird eingelesen… |
| `cv_import.cancelled` | Einlesen abgebrochen. Es wurde nichts übernommen. |
| `cv_import.retry` | Erneut versuchen |
| `cv_import.read_again` | Erneut einlesen |
| `cv_import.choose_other` | Andere Datei wählen |
| `cv_import.close` | Schließen |
| `cv_import.empty_title` | Nichts erkannt |
| `cv_import.empty_body` | In dieser Datei wurden keine Profildaten erkannt. Es wurde nichts übernommen. Wähle eine andere Datei oder schließe den Dialog. |
| `cv_import.error_oom` | Nicht genug Arbeitsspeicher, um diese Datei einzulesen. Es wurde nichts übernommen. Karrierekrake startet den Vorgang nicht automatisch neu. |
| `cv_import.error_timeout` | Das Einlesen hat zu lange gedauert und wurde abgebrochen. Es wurde nichts übernommen. Es wird nicht automatisch erneut versucht. |
| `cv_import.error_generic` | Die Datei konnte nicht gelesen werden. Pfad und Eingaben bleiben erhalten. |

EN-Pendants im selben Zug in `desktop/i18n.py`, gleiche Keys. Confirm-Labels unangetastet.

## Ist-Lücken auf `main` (nicht hier gefixt)

- `import_cv` in `CvImportDialog.__init__` blockiert vor `exec()`: kein Fortschritt, Abbrechen erst nach dem Parse.
- Leerer Extrakt ist nur die weiche Zeile „(nichts erkannt)“, ohne eigene Fläche und ohne nächsten Schritt.
- Fehler: `QMessageBox` plus Preview-Text, ohne Fehlerfläche und ohne Retry.
- Kein eigener OOM-/Timeout-Text und kein Verbot eines automatischen zweiten Laufs in der UI.

## Tester-Abnahmeskript (DE)

Voraussetzung: DevOps-Worker ist gemergt und die Zustände aus diesem Dokument sitzen darauf. Auf heutigem `main` ohne Worker sind Progress, Cancel während des Parse und die eigenen Leer-/Fehlerflächen **erwartete Fehlschläge** — kein Extrakt-PASS.

- [ ] **Progress sichtbar.** Lebenslauf einlesen starten. Der Dialog ist offen, solange gelesen wird. Text „Lebenslauf wird eingelesen…“ und der Dateiname sind sichtbar. Die Oberfläche reagiert (Fenster lässt sich verschieben). „Übernehmen“ ist nicht sichtbar.
- [ ] **Cancel mitten im Parse.** Während Progress „Abbrechen“. Der Lauf endet, ohne Qualifikationen zu schreiben. Text sagt, dass nichts übernommen wurde. Der Pfad steht noch da. Es startet kein neuer Lauf von selbst.
- [ ] **Leerer Lebenslauf / leerer Extrakt.** Datei, die erfolgreich gelesen wird, aber keine Personen- und keine Qualifikationsdaten liefert. Eigene Leerfläche mit „Nichts erkannt“ und „Andere Datei wählen“. „Übernehmen“ ist nicht sichtbar. „Schließen“ schreibt nichts ins Profil. „Andere Datei wählen“ und Abbruch des Dateidialogs lassen den alten Pfad stehen.
- [ ] **Kaputte Datei.** Ungültiges PDF/DOCX. Fehlerfläche mit Klartext, Pfad bleibt stehen. Kein alleiniges MessageBox-Ende. Nichts wird ins Profil geschrieben.
- [ ] **Retry behält den Pfad.** Auf der Fehlerfläche „Erneut versuchen“. Genau ein neuer Lauf derselben Datei. Pfadlabel unverändert. Kein zweiter Lauf ohne weiteren Klick.
- [ ] **OOM ohne Auto-Retry.** Speicherfehler (oder vom Peak-Gate abgebrochener Lauf) zeigt den OOM-Text. Es startet kein zweiter Lauf und kein anderes Modell. „Erneut versuchen“ geht nur per Klick, einmal.
- [ ] **Timeout ohne Auto-Retry.** Zeitüberschreitung zeigt den Timeout-Text. Kein automatischer neuer Lauf. Pfad bleibt. Retry nur manuell.
- [ ] **Success unverändert im Geist.** Datei mit erkannten Daten: Modus Ersetzen/Zusammenführen, Vorschau, Konflikte, „Übernehmen“. Teilweise leere Abschnitte bleiben „(nichts erkannt)“ in der Vorschau, nicht die Leerfläche.
- [ ] **Confirm-Labels.** „Übernehmen“ und die Modus-Texte sind unverändert, wenn dieser UX-Schritt sie nicht anfasst. #64 Confirm/Dark nicht als Extrakt-PASS werten.

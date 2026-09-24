# Hartes Peak-RSS-Gate: Intel Core i3 (11. Gen.) / 8 GB RAM

Zielhardware: Windows-Laptop mit Intel Core i3 (11. Generation) und genau 8 GB RAM.

Prozessgruppen-Peak **≤ 3_300_000_000 Bytes**. Ein höherer Peak ist ein harter Fehlschlag. Gleichheit besteht das Gate (`<=`, nicht `<`).

Ein weiches ≤12-GB-Kriterium ist **kein** Erfolg. 12 GB dezimal (`12_000_000_000`) und 12 GiB liegen beide über dem harten Limit und fallen durch `evaluate_peak`. Auf `main` gab es zum Zeitpunkt dieses Schnitts kein Laufzeit-/CI-Erfolgskriterium „≤ 12 GB“. Die Annahme „Peak RSS ≤ 12 GB“ steht in Damianos Parser-PR #62 und wird hier nicht angefasst.

Zahlen aus dieser Agent-VM oder aus GitHub Actions sind **keine** Ship-Evidenz. Ship-Evidenz ist nur ein Lauf des Windows Job Objects auf dem physischen Laptop (`ship_evidence: true`).

## Was der Harness misst

Der Runner legt Karrierekrake, optional Docling und ein explizites llama.cpp-/Qwen-Kommando in **eine** Prozessgruppe:

- Windows: ein Job Object. Der Prozess wird mit `CREATE_SUSPENDED` erzeugt, per `AssignProcessToJobObject` zugeordnet und erst danach mit `ResumeThread` fortgesetzt. `JOB_OBJECT_LIMIT_BREAKAWAY_OK`, `JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK` und `CREATE_BREAKAWAY_FROM_JOB` werden nicht gesetzt. `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` ist gesetzt, damit Kinder beim Schließen des Jobs enden. Der gemeldete Peak ist `JOBOBJECT_EXTENDED_LIMIT_INFORMATION.PeakJobMemoryUsed` (High-Water der Prozessgruppe, Commit-Stand des Job Objects).
- Andere Systeme: neue Session/Prozessgruppe und Summe der `VmRSS` über den Prozessbaum als Gerüst. Das prüft, dass gewöhnliche Kinder nicht aus der Gruppe fallen. Es ersetzt das Job Object nicht.

`--enforce-limit` setzt auf Windows zusätzlich `JOB_OBJECT_LIMIT_JOB_MEMORY` auf 3_300_000_000. Das schützt den 8-GB-Laptop vor Swap-Tod. Ein OOM-Exit in diesem Modus ist ebenfalls ein harter Fehlschlag. Ohne das Flag wird der echte Peak gemeldet, auch wenn er über dem Gate liegt.

## Auf dem echten Laptop ausführen

Andere schwere Programme schließen. Im Repo-Root, mit dem Windows-Python der Installation:

```bat
set KARRIEREKRAKE_PHYSICAL_I3_8GB=1
python scripts\run_i3_peak_job_benchmark.py --self-test
python scripts\run_i3_peak_job_benchmark.py --cv C:\Pfad\lebenslauf.pdf --attest-physical-i3 --json-out C:\Temp\kk-peak.json
```

Exit-Code 0: Peak ≤ 3_300_000_000. Exit-Code 2: harter Fehlschlag. `ship_evidence` wird nur wahr, wenn alle drei gelten: Windows-Job-Object-Messung, `--attest-physical-i3`, und `KARRIEREKRAKE_PHYSICAL_I3_8GB=1`.

Optional Docling und ein **explizites** lokales Modellkommando (kein Phi, kein automatischer Modellwechsel). Dafür muss lokales LLM-CV-Parsing an sein (`local_llm_cv_parsing_enabled: true` oder `KARRIEREKRAKE_LOCAL_LLM_CV_PARSING=1`):

```bat
python scripts\run_i3_peak_job_benchmark.py --cv C:\Pfad\lebenslauf.pdf --backend docling --llm-cmd "C:\llama\llama-server.exe -m C:\models\kleines-modell.gguf -c 2048" --attest-physical-i3 --enforce-limit
```

Ist der Schalter aus, startet `--llm-cmd` nicht. Der Prozess endet mit Code 4 und dem Satz:

wird lokales LLM-CV-Parsing auf dieser Hardware gestrichen; der manuelle Profilimport bleibt möglich.

Es gibt keinen automatischen Phi-Fallback.

## Kill-Switch

Einstellung `local_llm_cv_parsing_enabled` (Standard **aus**, wie der heutige deterministische Import). Umgebung `KARRIEREKRAKE_LOCAL_LLM_CV_PARSING=0|1` überschreibt die Einstellung.

- Aus: kein lokales LLM-CV-Parsing. Der manuelle Profilimport und der deterministische CV-Import bleiben. Der Dialog zeigt den Kill-Satz.
- An: erlaubt ein explizites Modellkommando im Harness bzw. den Engpass `invoke_local_llm_cv_extract`. Es wird kein Modell geladen, nur weil der Schalter an ist, und es wird nicht auf Phi gewechselt.

Erster Eskalationsschritt, bevor der Schalter dauerhaft aus bleibt: ein kleineres lokales Modell unter **denselben** Qualitäts-, RAM- und Laufzeit-Gates messen. Dieses Slice liefert kein neues Modell, keine neuen Gewichte und keine Prompt-Änderung.

OOM und Timeout starten denselben Modelllauf nicht erneut. Im Importdialog bleiben die bisherigen Profilangaben erhalten; ein neuer Versuch ist nur der Button „Erneut versuchen“.

## UI-Freeze

`import_cv` läuft nicht mehr in `CvImportDialog.__init__`. Ein Worker startet `python -m desktop.cv_import_child` in der Prozessgruppe. Der Dialog zeigt Fortschrittsbalken und Status „Lebenslauf wird gelesen …“, bevor das Ergebnis in der Vorschau steht. Der erste Klick auf „Abbrechen“ während des Laufs bleibt im Dialog: Status „Wird abgebrochen …“, danach „Import abgebrochen.“ Die Vorschau übernimmt das Parse-Ergebnis nicht. Ein zweiter Klick auf „Abbrechen“ schließt den Dialog. Die Oberfläche bleibt bedienbar.

Deterministische Parses sind oft kürzer als ein Frame. Ohne gesetzte Variable startet der Kindprozess sofort (Produktionspfad). Zum Prüfen von Fortschritt und Abbruch vor dem Ergebnis:

```bat
set KARRIEREKRAKE_CV_IMPORT_OBSERVE_S=8
```

PowerShell:

```powershell
$env:KARRIEREKRAKE_CV_IMPORT_OBSERVE_S = "8"
```

Dann einen Lebenslauf importieren. Balken und „Lebenslauf wird gelesen …“ bleiben etwa 8 Sekunden, **bevor** der Parser startet. In diesem Fenster „Abbrechen“ klicken. Der Dialog bleibt offen und zeigt „Import abgebrochen.“ Variable löschen oder auf `0` setzen, bevor normal gearbeitet wird. Leere, ungültige und negative Werte gelten als aus. Die Obergrenze ist 120 Sekunden.

## Was nur am physischen Gerät geklärt werden kann

- Ob Docling plus das von Damiano gewählte lokale Modell (PR #62, nicht dieser Branch) unter 3_300_000_000 Bytes Peak bleibt.
- Ob ein kleineres Modell dieselben Qualitäts-Gates schafft. Das ist Parser-Arbeit und hier nicht implementiert.
- Die Job-Object-Zahl auf genau diesem i3/8-GB-Laptop. CI prüft nur, dass das Gate als harter Vergleich verdrahtet ist und dass das Gerüst Kinder enthält.

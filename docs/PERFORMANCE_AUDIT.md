# Performance-Audit (gemessen)

Stand: 2026-09-25. Skript: `tools/perf/benchmark.py`, fünf Läufe, Median und Maximum. LLM aus (`KARRIEREKRAKE_LOCAL_LLM_CV_PARSING=0`, `import_cv(..., guenther_enabled=False)`). In allen CV-Läufen war `phi_invoked` falsch und `local_llm_cv_parsing_allowed` falsch.

**VM, nicht i3.** Maschine dieser Läufe: Intel Xeon, 4 logische CPUs, 16_791_945_216 Bytes RAM, Python 3.12.3, Linux, Qt offscreen. Die Zahlen ordnen Engpässe. Sie sind keine Schwellen, keine i3-Grenzen und kein Nachweis, dass das Prozessgruppen-Limit von 3_300_000_000 Bytes auf einem i3 mit 8 GB eingehalten wird. Das Gate in CI bleibt unverändert. Der höchste hier gesampelte Prozessgruppen-RSS lag bei 291_860_480 Bytes (Startup-Worker).

Das Skript ist manuell. Es hängt nicht an `unit-tests` und an keinem Workflow. Der im Report geführte Peak ist eine Stichprobe (Worker 50 ms, importtime 20 ms). Unter Linux läuft die Summe der VmRSS gegen die Abbruchgrenze; VmHWM ist der Einzelprozess-Peak und läuft nicht dagegen. Unter Windows ist die Kennzahl `PeakJobMemoryUsed`, dieselbe wie das Job-Object-Gate.

## Kalter Start

`python -X importtime -c "import desktop.app"` (fünf Prozesse):

| | Median | Maximum |
| --- | ---: | ---: |
| cumulative von `desktop.app` | 0.303 s | 0.343 s |
| Prozess-Wallclock | 0.358 s | 0.398 s |
| Prozessgruppen-RSS (Sample) | 83_329_024 Bytes | 83_468_288 Bytes |

Top 25 nach self time, Lauf am nächsten am Median:

| self | cumulative | Modul |
| ---: | ---: | --- |
| 0.015 s | 0.082 s | `core.search_intent` |
| 0.014 s | 0.303 s | `desktop.app` |
| 0.011 s | 0.019 s | `core.cv_parser` |
| 0.008 s | 0.040 s | `PySide6.QtCore` |
| 0.008 s | 0.029 s | `core.config` |
| 0.008 s | 0.009 s | `shibokensupport.signature.lib.pyi_generator` |
| 0.008 s | 0.009 s | `pydantic_core.core_schema` |
| 0.007 s | 0.007 s | `annotated_types` |
| 0.007 s | 0.007 s | `shibokensupport.signature.parser` |
| 0.006 s | 0.006 s | `PySide6.QtGui` |
| 0.005 s | 0.005 s | `pydantic.types` |
| 0.004 s | 0.004 s | `desktop.design_system.tokens` |
| 0.004 s | 0.189 s | `desktop.main_window` |
| 0.004 s | 0.010 s | `pydantic._internal._generate_schema` |
| 0.004 s | 0.005 s | `integrations.email_normalize` |
| 0.003 s | 0.003 s | `PySide6.QtWidgets` |
| 0.003 s | 0.003 s | `PySide6.QtNetwork` |
| 0.003 s | 0.005 s | `pydantic._internal._decorators` |
| 0.003 s | 0.003 s | `shibokensupport.signature.mapping` |
| 0.003 s | 0.004 s | `core.models` |
| 0.003 s | 0.030 s | `shiboken6.Shiboken` |
| 0.003 s | 0.125 s | `desktop.pages.applications` |
| 0.003 s | 0.003 s | `core.lifecycle` |
| 0.003 s | 0.009 s | `integrations.email_associate` |
| 0.003 s | 0.003 s | `yaml.reader` |

Fenster, offscreen, `MainWindow.show()` plus ein `processEvents`:

| | Median | Maximum |
| --- | ---: | ---: |
| Kaltes AppData, Zeit bis sichtbar | 4.818 s | 5.328 s |
| Danach dasselbe AppData (Flag gesetzt) | 0.535 s | 0.556 s |
| Importe vor dem kalten Fenster | 0.280 s | 0.302 s |
| VmHWM nach kaltem Fenster | 135_806_976 Bytes | 135_852_032 Bytes |
| VmHWM am Ende desselben Prozesses | 171_245_568 Bytes | 171_270_144 Bytes |
| Prozessgruppen-RSS über den ganzen Worker | 284_491_776 Bytes | 291_860_480 Bytes |

Kalt, jeder Lauf gleich: 212 `ConfigService.load`, 194 `save`, 582 `os.fsync`, 634 `yaml.safe_load`. Warm: 19 `load`, 0 `save`, 0 `fsync`, 57 `yaml.safe_load`. Summe der äußersten `load`-Aufrufe: kalt Median 4.083 s, warm Median 0.158 s. `llm_parsing_allowed` war falsch. Ein `QTimer` (120 ms, Postfach-Spinner) war nicht aktiv.

Der warme VmHWM ist derselbe Prozess nach dem kalten Lauf und deshalb kein sauberer Vorher/Nachher-Speicherwert. Ein eigener warmer UI-Lauf (Flag schon gesetzt) hatte VmHWM Median 149_581_824 Bytes und Prozessgruppen-RSS Maximum 263_958_528 Bytes.

## CV-Import

Zwölf Dateien je Lauf: elf PDF unter `tests/fixtures/cv_corpus/` (2–3 KB) plus ein DOCX, das das Skript aus `tests/fixtures/cv_structured_de.txt` baut. Im Repo liegt kein DOCX. Docling und ein warmes Modell wurden nicht geladen.

Wanduhr für `import_cv` über alle zwölf Dateien: Median 0.186 s, Maximum 0.249 s. VmHWM Median 56_643_584 Bytes, Maximum 56_778_752 Bytes. Prozessgruppen-RSS um 57 MB.

Größte Einzeldatei im ersten Import (Parser noch nicht heiß): `DE_01_Klassisch.pdf`, `import_cv` Median 0.061 s (max 0.078 s). Die folgenden PDF liegen bei etwa 0.007–0.023 s. Das DOCX: Median 0.015 s (max 0.018 s). Stufen am Beispiel `DE_01` (Median): Extrakt 0.006 s, Parse 0.004 s, Verify/Repair 0.0001 s, Profilbau (`filter_parsed_for_import` + `parsed_to_qualifications` + `personal_from_parsed`) 0.0001 s. Diese Fixtures sind klein; das ist keine Messung eines langen Scans.

cProfile über einen zweiten Import aller zwölf Dateien, Spitze nach cumulative time: `import_cv` / `import_cv_canonical`, dann `extract_text` (vor allem `pypdf` `extract_text` und `_page_text_prefer_layout`) und `parse_cv_text`. `core/cv_sections.py:320 is_heading` ist die teuerste eigene Parser-Funktion in diesem Profil (tottime etwa 0.039 s über 1010 Aufrufe in dem einen Profillauf). Das volle Top-30 schreibt das Skript nach JSON.

tracemalloc, ein Lauf, nur `DE_05_Zweiseitig.pdf`: Peak 10_257_512 Bytes, oben Import-Machinery und `pypdf/_codecs/adobe_glyphs.py`.

## Matching, Filter, Sort

5000 synthetische Jobs aus `tests/fixtures/intent_jobs_corpus.json` (300 Vorlagen, zyklisch). Profil aus `DE_01_Klassisch.pdf`, Suchintent mit Lohnbuchhalter/Sachbearbeiter/Disponentin. Deterministisch, kein LLM.

Zeit pro Job ist von 500 auf 5000 flach. Das ist linear, nicht quadratisch. `deduplicate` bleibt bei etwa 12 µs pro Job.

| n | `score_job` Median (max) | `filter_jobs` Median (max) | `deduplicate` Median |
| ---: | --- | --- | ---: |
| 50 | 0.109 s (0.123 s) | 0.047 s (0.050 s) | 0.0007 s |
| 500 | 0.698 s (0.729 s) | 0.618 s (0.688 s) | 0.006 s |
| 5000 | 7.105 s (7.779 s) | 6.397 s (6.548 s) | 0.060 s |

`re.compile` während `score_job`: 12 Aufrufe bei n=50, danach 0. Wiederholtes Kompilieren ist nach dem Regex-Cache nicht der Treiber. Der Treiber ist `re.sub` innerhalb von `_fuzzy_against_aliases`.

cProfile für n=500, `score_job` plus `filter_jobs`, aus dem zweiten Match-Lauf, der der Wandzeit-Summe am nächsten liegt (Wandzeit Score plus Filter 1.322 s, Median der fünf Läufe 1.322 s). Der Profiler bläht die Zeit; die Rangfolge kommt aus der Wanduhr, nicht aus cProfile. In diesem Profillauf: `apply_search_intent` 1000 Aufrufe, cumulative 2.618 s, weil beide Pässe ihn rufen. `_fuzzy_against_aliases` 29_680 Aufrufe, cumulative 1.968 s. `re.Pattern.sub` 1_185_876 Aufrufe, tottime 0.675 s. `score_job` selbst: cumulative 1.508 s für 500 Jobs.

SQLite, jeweils neue Datei:

| n | Upsert pro `connection()` Median (max) | `list_jobs` alle Zeilen Median (max) | Python-Sort darüber | selektives `title_query="buch"` |
| ---: | --- | --- | ---: | --- |
| 50 | 0.161 s (0.279 s) | 0.0014 s, 50 Zeilen | <0.001 s | 0.0007 s, 6 Zeilen |
| 500 | 1.861 s (2.088 s) | 0.012 s, 500 Zeilen | 0.0001 s | 0.0012 s, 10–12 Zeilen |
| 5000 | 19.633 s (22.330 s) | 0.130 s (0.137 s), 5000 Zeilen | 0.0011 s | 0.008 s, 88–92 Zeilen |

Filtern und Sortieren der Jobliste bleibt klein. Die teuren SQL-Stufen sind der Upsert pro Verbindung und `has_applied`.

`has_applied` gegen n bereits als applied markierte Zeilen, n Abfragen. Fünf Läufe, **VM, nicht i3**, Abschnitt `has_applied` (dieselbe Funktion wie im Match-Lauf). Die Zeilen werden in einer Transaktion angelegt; die Uhr läuft nur über `has_applied`, und der Produktpfad öffnet dabei weiter eine Verbindung pro Aufruf. Jeder Probe-Treffer ging über Firma plus Titel, also über den vollen Scan. Diese Reihe ersetzt die frühere Messung bis n=800.

| n | Median (max) | pro Aufruf | Set-Lookup Median (max) | RSS-Delta des Sets |
| ---: | --- | ---: | ---: | ---: |
| 50 | 0.019 s (0.020 s) | 0.39 ms | 0.00019 s | 0 Bytes |
| 200 | 0.177 s (0.182 s) | 0.88 ms | 0.00076 s | 0 Bytes |
| 800 | 1.151 s (1.180 s) | 1.44 ms | 0.0030 s | 0 Bytes |
| 2000 | 4.946 s (5.015 s) | 2.47 ms | 0.0074 s | 0 Bytes |
| 5000 | 26.121 s (26.321 s) | 5.22 ms | 0.0182 s (0.0185 s) | 0 Bytes |

Von n=800 auf n=5000 wächst die Zeilenzahl um den Faktor 6,25 und die Zeit um den Faktor 22,7 (1.151 s → 26.121 s). Die Zeit pro Aufruf steigt in der Reihe 0,39 / 0,88 / 1,44 / 2,47 / 5,22 ms. VmHWM dieses Workers Median 43_372_544 Bytes, Prozessgruppen-RSS Median 43_556_864 Bytes (Maximum 43_618_304).

PLZ, `resolve_postal_pgeocode`, Status jedes Erstlaufs `RESOLVED`:

| | Median | Maximum |
| --- | ---: | ---: |
| erster Aufruf | 0.437 s | 0.550 s |
| 30 weitere | 0.204 s | 0.215 s |
| dieselben 30 mit gecachter `validate_dataset` | 0.067 s | 0.072 s |
| RSS vor dem ersten Aufruf | 108_388_352 Bytes | 108_400_640 Bytes |
| RSS nach dem ersten Aufruf | 162_283_520 Bytes | 163_270_656 Bytes |
| RSS nach dem Cache-Lauf | 162_349_056 Bytes | 164_642_816 Bytes |

Der erste Aufruf legt das pgeocode-Dataframe an: etwa +53_895_168 Bytes RSS (162_283_520 − 108_388_352). Der Validierungs-Cache darüber sind Median 65_536 Bytes. `ensure_active` hasht die GeoNames-Dateien bei jedem Resolve (`validate_dataset` → `_sha256`), auch wenn der Index schon im Speicher liegt.

Alias-Probe, nur im Benchmark-Prozess, n=500, `score_job` plus `filter_jobs`:

| Variante | Median | Maximum | RSS |
| --- | ---: | ---: | --- |
| Produktion | 1.346 s | 1.476 s | 108_388_352 Bytes, Delta 0 |
| `re.sub` aus der Alias-Schleife gehoben | 0.697 s | 0.721 s | Delta 0 |
| dazu Cache für `role_family_id_for_label` (6 Einträge) | 0.453 s | 0.478 s | Delta 0 |

tracemalloc für 200 Jobs: Peak 20_140_563 Bytes, oben wieder Importe, dann `re._compiler` und `json`. Das erklärt die CPU-Spitze nicht; dafür ist cProfile da.

## UI

Warmes AppData (Migrationsflag schon gesetzt), offscreen. 29 `QGraphicsDropShadowEffect` am Hauptfenster, 1041 Widgets beim Startup-Lauf. Schatten je Seite: Übersicht 8, Jobs 5, Profil 10, Postfach 2, Einstellungen 1, Bewerbungen 1, Suche 1, Protokolle 1. `TagChip` hat heute keinen Schatten.

| | Median | Maximum |
| --- | ---: | ---: |
| 20× `repaint` des Fensters, Effekte an | 0.014 s | 0.016 s |
| dieselben 20×, Effekte aus | 0.006 s | 0.007 s |
| 40 Chips ohne Schatten, 20× repaint | 0.008 s | 0.012 s |
| 40 Chips mit `soft_shadow`, 20× repaint | 0.031 s | 0.032 s |
| RSS-Delta der 40 Schatten | 368_640 Bytes | 376_832 Bytes |

`JobsPage.refresh` auf dem aufrufenden Thread, Produktlimit 500 Zeilen, alle Treffer Match 80:

| eingefügt | Median (max) | `build_job_fit_viewmodel`-Aufrufe | Karten |
| ---: | --- | ---: | ---: |
| 50 | 0.070 s (0.071 s) | 51 | 50 |
| 500 | 0.384 s (0.423 s) | 501 | 500 |

Widget-Zahl der Jobseite bleibt 115. Die Liste baut Items, keine 500 Kind-Widgets. Der zusätzliche Fit-Aufruf kommt vom Selektieren der ersten Zeile.

`refresh_cards`: zwei Aufrufe je Lauf (`load_from_config` plus der gemessene). Ein Aufruf Median 0.012 s (max 0.013 s). Es wird nichts repariert.

Gemessen an der sichtbaren Profilseite, 18 ersetzte Widgets (Erfahrung, Ausbildung, Sprachen, Skills, Wunsch-Tags):

- Vor dem nächsten Event-Loop: 18 lebendig, 18 sichtbar, 0 explizit `hide()`.
- Während `refresh_cards`: 0 Paint-Events.
- Nach `repaint` plus `processEvents` ohne DeferredDelete: immer noch 18 lebendig und sichtbar, 8 Paints. Widget-Zahl 399 (alte und neue gleichzeitig).
- Nach `sendPostedEvents(..., DeferredDelete)`: 0 der alten lebendig, Widget-Zahl 346.

Musterprobe, 30 Labels, Elternwidget sichtbar, fünf Läufe identisch: ohne `hide()` 30 sichtbar und 31 Paints, mit `hide()` vorher 0 sichtbar und 1 Paint. In beiden Fällen leben alle 30 bis zum DeferredDelete weiter. `processEvents()` allein räumt `deleteLater` nicht ab.

## Top 10 nach CPU- und Wandzeit

Rang nach der größten gemessenen Wandzeit der Stufe. **VM, nicht i3.** Kleine absolute UI-Zeiten stehen unten, auch wenn das Verhältnis groß ist.

### 1. `has_applied` liest bei jedem Job alle bisherigen Versuche

`core/database.py:805` `has_applied` selektiert alle Zeilen in den Vor-Status und vergleicht in Python. Die Pipeline ruft das pro Job (`app/main.py` um den `score_job`-Aufruf).

Gemessen, n=5000: Median 26.121 s (max 26.321 s), 5.22 ms pro Aufruf. Set-Lookup derselben Schlüssel: Median 0.0182 s (max 0.0185 s). Zeit: 26.121 s → 0.018 s. RSS-Delta des Sets: 0 Bytes bei n=50, 200, 800, 2000 und 5000. Ein Set der Schlüssel ist ein Cache. **Kostet RAM, Peak-Prüfung nötig**, auch bei gemessenem Delta 0 (unter einer Seite auf dieser VM; VM-RSS ist kein i3-Beweis).

Risiko: URL-Identität und Firmen/Titel-Schlüssel müssen exakt die von `has_applied` bleiben, inklusive der Vor-Status, nicht nur APPLIED.

Konflikt: `#67` ändert `app/main.py`, nicht `database.py`.

### 2. Upsert öffnet jedes Mal eine SQLite-Verbindung

`core/database.py:288` `_connect`, `:295` `connection` (commit und close), `:661` `upsert_job`. Pro Job eine neue Verbindung, ein Commit, ein Close. Die Pipeline in `app/main.py` ruft das in einer Schleife.

Gemessen, 5000 Jobs: Median 19.633 s, Maximum 22.330 s. VmHWM des Match-Workers Median 167_784_448 Bytes.

Fix: eine Transaktion für den Schwung. Im Benchmark Median 0.188 s (max 0.209 s). Zeit: 19.633 s → 0.188 s. RSS der Ein-Transaktion-Variante: Median +1_691_648 Bytes (max +1_703_936). **Kostet RAM, Peak-Prüfung nötig** (klein gegen 3_300_000_000, aber ein Tausch Zeit gegen Speicher, und VM-RSS ist kein i3-Beweis).

Risiko: ein Abbruch schreibt den Schwung nicht zeilenweise; die Status-Regeln in `upsert_job` (APPLIED nicht herabstufen) müssen in der gemeinsamen Transaktion dieselben bleiben.

Konflikt: `#67` ändert `app/main.py`, nicht `database.py`. Ein Batch nur in `Database` trifft den Diff von #67 nicht. `#77` ändert `app/main.py` ebenfalls.

### 3. `re.sub` in der Alias-Schleife

`core/intent_aliases.py:60` `_fuzzy_against_aliases`, der `re.sub` ab `:79` hängt im `for alias`-Loop und hängt nicht von `alias` ab. `_norm_alias` (`:51`) baut bei jedem Aufruf neue Muster. `title_matches_role_label` (`:179`) und `role_family_id_for_label` (`:145`) rufen das sehr oft. `apply_search_intent` (`core/intent_filter.py:367`) sitzt in `score_job` (`core/matcher.py:344`) und noch einmal in `filter_jobs` (`:823`).

Gemessen: `score_job` 5000 Jobs Median 7.105 s, `filter_jobs` weitere 6.397 s. Zusammen 13.5 s, linear in n. Bei n=500 senkt das Herausheben des `re.sub` 1.346 s auf 0.697 s, RSS-Delta 0. Übertragen auf 5000, weil die Zeit pro Job flach ist: etwa die Hälfte von 13.5 s, also rund 6.5 s weniger. **Schätzung** für n=5000; der Vorher/Nachher-Wert bei n=500 ist gemessen. Kein Speicherzuwachs gemessen, deshalb kein RAM-Tausch.

Risiko: die Fuzzy-Schwelle und die Treffer-Menge müssen gleich bleiben. Nur die Arbeit pro Alias darf sinken, nicht die Regel.

Konflikt: `#67` ändert `intent_filter.py`, `matcher.py`, `job_fit.py`. `intent_aliases.py` ist nicht in dem Diff. Signatur beibehalten, dann kollidiert der eine Funktionsrumpf nicht mit #67; die Aufrufer schon, falls der Fix dort landet.

### 4. Intent-Filter läuft zweimal

Dieselbe Funktion wie in Rang 3, zweiter Aufruf. `score_job` und danach `filter_jobs`: je 5000 Jobs Median 7.105 s und 6.397 s. Die UI ruft `build_job_fit_viewmodel` (`desktop/viewmodels/job_fit.py:142`) pro Zeile noch einmal: 501 Aufrufe bei 500 Karten.

Fix, der nichts speichert: das `IntentFilterResult` aus dem ersten Aufruf weiterreichen statt neu zu rechnen. Zeitgewinn des reinen Weglassens ist der zweite Pass, Median 6.397 s bei 5000, gemessen als eigene Stufe, nicht als gepatchter Lauf. Wenn das Ergebnis behalten wird, ist das ein Cache. Größe eines Results mal 5000 ist **nicht gemessen**. **Kostet RAM, Peak-Prüfung nötig**, sobald die Objekte liegen bleiben. Die Regex-Hebung aus Rang 3 und dieser zweite Pass addieren sich nicht voll: die Hebung verbilligt beide Pässe, das Weglassen entfernt den zweiten.

Risiko: `filter_jobs` sortiert nach `rank_score`. Wer den zweiten Pass streicht, muss diese Sortierung behalten.

Konflikt: `#67` (`intent_filter.py`, `matcher.py`, `job_fit.py`, `jobs.py`).

### 5. Erster Start: `save` ruft `load`, bevor das Migrationsflag liegt

`desktop/services/__init__.py:110` `_apply_shutdown_fix_migration` ruft `:118` `save`, und `save` (`:133`) ruft `:151` wieder `load`, bevor `:119` `save_meta` das Flag `shutdown_fix_v1` schreibt. `load` (`:61`) läuft also wieder in die Migration. Dazu `core/config.py:831` `os.fsync` pro YAML-Datei.

Gemessen: kaltes Fenster Median 4.818 s (max 5.328 s) gegen warmes Fenster Median 0.535 s (max 0.556 s). 194 Saves und 582 fsyncs gegen 0. Zeit: 4.818 s → 0.535 s, das ist der gemessene Abstand der beiden Zustände, kein gepatchter Produktcode. RSS: kein sauberer Rückgang gemessen (kaltes VmHWM 135_806_976 Bytes, warmer UI-Prozess 149_581_824 Bytes, anderer Ablauf). Kein RAM-Tausch.

Risiko: das Flag muss genau einmal gelten, `minimize_to_tray` bleibt falsch, und ein echter Speicherfehler darf nicht als Erfolg durchgehen. Heute schluckt `except Exception` auch die Rekursion.

Konflikt: der genannte ConfigService-Rekursionsfix. Unter den offenen PRs war keiner mit diesem Titel; die Datei ist `desktop/services/__init__.py`. Nicht mit einem zweiten Patch daneben arbeiten.

### 6. PLZ-Validierung hasht bei jedem Resolve die Geo-Dateien

`core/geo_resolve.py:243` ruft `_ensure_geo_data` (`:181`) auch dann, wenn `_pgeocode_index` den Nominatim schon hält. `core/geo_dataset.py:238` `ensure_active` → `:193` `validate_dataset` → `:117` `_sha256` über DE/AT/CH.

Gemessen: 30 Resolves Median 0.204 s gegen 0.067 s mit gecachter Validierung. Erster Aufruf Median 0.437 s und etwa +54 MB RSS (Dataframe). Der Cache der Validierung selbst: +65_536 Bytes Median.

Zwei Fixes, nicht vermischen:

- Validierungsergebnis behalten, Dataframe nicht neu lesen. Zeit 0.204 s → 0.067 s je 30 Aufrufe, RSS-Delta etwa 64 KB. Kaum ein RAM-Tausch.
- Verzeichnis beim Start vorladen. Das verschiebt die gemessenen +54 MB und 0.437 s nach vorn. **Kostet RAM, Peak-Prüfung nötig.** VM-RSS ist kein Beweis für den i3. Docling oder ein Modell warmzuhalten ist hier nicht gemessen und nicht vorgeschlagen; der deterministische Import nutzt sie nicht.

Risiko: ein Update der Geo-Dateien muss den Cache invalidieren, sonst bleibt ein alter Hash gültig.

Konflikt: `#67` ändert `core/geo_resolve.py`.

### 7. Jobliste rechnet den Fit auf dem UI-Thread

`desktop/pages/jobs.py:553` `refresh`, `:509` `build_job_fit_viewmodel` pro Zeile, `:494` `_populate_table`. Median 0.384 s bei 500 Zeilen (max 0.423 s), 501 Fit-Aufrufe. Das Produktlimit ist 500; 5000 Zeilen baut die Seite heute nicht.

Fix: die Fit-Rechnung vom UI-Thread nehmen. Gesamte CPU bleibt in der gleichen Größenordnung. **Schätzung**, nicht gemessen: der Thread wechselt, die 0.384 s Blockade (gemessen) fällt am UI weg. Kein zweites Job-Array anlegen. Ein Kopieren der 500 Jobs wäre extra RAM und ist nicht vorgeschlagen.

Risiko: Qt-Widgets bleiben im UI-Thread; nur die reine Rechnung wandert.

Konflikt: `#67` und `#77` berühren `jobs.py`. `#73` nicht.

### 8. `QGraphicsDropShadowEffect` auf Karten

`desktop/design_system/polish.py:156` `soft_shadow`, `:246` `polish_card`. 29 Effekte am Fenster. 20 Repaints: Median 0.014 s an, 0.006 s aus. 40 Chips mit Schatten: 0.031 s gegen 0.008 s, RSS +368_640 Bytes. Offscreen-Software-Raster dieser VM, kein iGPU-Messwert. Der Rang folgt der absoluten Zeit; das Verhältnis (etwa 2,2× am Fenster, etwa 4× an 40 Chips) beschreibt die CPU-Last.

Fix: statische Karten ohne Live-Effekt (Stylesheet oder gar kein Schatten). Zeit und RSS sinken beide; das ist kein RAM-Tausch. Ein vorberechnetes Blur-Pixmap wäre das Gegenteil und ist nicht vorgeschlagen.

Risiko: Hover in `polish_interactive` nutzt denselben Effekt. Optik ist Designer-Sache.

Konflikt: `#71` ändert `polish.py` und will mehr Schatten auf Chips. Genau dort war der 4-fache Repaint.

### 9. Warmes Fenster lädt die YAML 19-mal

Nach dem Flag: 19 `ConfigService.load`, 57 `yaml.safe_load`, Summe der äußersten Loads Median 0.158 s von 0.535 s Fensterzeit. `load` liest immer neu (`desktop/services/__init__.py:61`), obwohl `config` den Stand schon hält.

Fix: beim Aufbau der Seiten den schon geladenen Stand nutzen, nicht 19 Disk-Loads. Zeitgewinn in der Größenordnung der gemessenen 0.158 s. RSS: das `AppConfig`-Objekt ist danach schon da, Delta nicht extra gemessen, erwartet klein. Kein Preload.

Risiko: ein Load, der absichtlich die Disk neu liest (nach Speichern), darf nicht am Cache vorbeilaufen. Heute ruft `save` am Ende selbst `load`.

Konflikt: derselbe ConfigService-Fix wie Rang 5. `#67` ändert Seiten, die `load` rufen (`dashboard.py`, `profile.py`, `jobs.py`).

### 10. `refresh_cards` entfernt Widgets nur mit `deleteLater`

`desktop/pages/profile.py:433` `refresh_cards`, `:486`–`:490` und `_clear_layout` `:371`. Kein `hide()`. Gemessen, nicht geändert: 18 Widgets bleiben sichtbar und lebendig über `refresh_cards` und ein normales `processEvents` hinweg, 8 Paints beim Repaint der Seite. Muster 30 Labels: 31 Paints ohne `hide`, 1 Paint mit `hide`. Die Funktion selbst ist Median 0.012 s. Der Paint-Unterschied ist gemessen, eine iGPU-Hochrechnung nicht.

Fix gehört dem Designer. Erwarteter Paint-Rückgang aus der Musterprobe: 31 → 1 Events auf 30 Labels, Wandzeit der Profilfunktion bleibt klein. RSS nicht als Hebel gemessen. Kein RAM-Tausch.

Risiko: `#73` repariert genau diese Methode (`_exp_more` nach erneutem `refresh_cards`). Ein zweiter Eingriff in denselben Block kollidiert damit.

## Was gemessen klein ist

- CV-Korpus gesamt Median 0.186 s. Nicht angreifen, bevor größere Dokumente gemessen sind.
- `list_jobs` über 5000 Zeilen Median 0.130 s, Sort 0.001 s.
- `deduplicate` 5000 Jobs Median 0.060 s, linear (Dict, keine n²-Schleife im Profil).
- `re.compile` nach dem ersten Scoring-Schwung: 0 weitere Aufrufe.
- Postfach-Timer 120 ms: vorhanden, im Leerlauf nicht aktiv.
- Docling, Phi, lokales LLM: nicht geladen. Warmhalten wäre RAM ohne gemessenen CPU-Gewinn auf diesem Pfad.

## Zuerst diese drei

1. `has_applied` über ein Set der bisherigen Schlüssel (`database.py:805`). Gemessen bei 5000 Jobs 26.121 s → 0.018 s. RSS-Delta 0 Bytes. Trotzdem ein Cache: kostet RAM, Peak-Prüfung nötig.
2. Upserts in einer Transaktion (`database.py:295` / `:661`). Gemessen 19.633 s → 0.188 s bei 5000 Jobs. RSS +1.7 MB, kostet RAM, Peak-Prüfung nötig.
3. `re.sub` in `_fuzzy_against_aliases` aus der Schleife heben (`intent_aliases.py:79`). Gemessen bei 500 Jobs 1.346 s → 0.697 s, RSS-Delta 0. Auf 5000 Jobs **Schätzung** rund 6.5 s von den gemessenen 13.5 s für Score plus Filter.

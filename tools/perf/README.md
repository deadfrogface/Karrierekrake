# Performance-Benchmark (manuell)

Dieses Skript misst den Desktop-Start, den deterministischen CV-Import, Matching/Filter/Sort und ein paar UI-Pfade. Es ändert kein Produktverhalten.

## Nicht in CI

`tools/perf/benchmark.py` ist **kein** Test und **keine** Pflichtprüfung. Nicht in `unit-tests` aufnehmen, nicht in GitHub-Actions-Workflows aufrufen, nicht von pytest einsammeln. Nur von Hand starten.

## Aufruf

```bash
.venv/bin/python tools/perf/benchmark.py --runs 5 --out /tmp/kk-perf
```

Mindestens 5 Läufe. Die Zusammenfassung steht in `/tmp/kk-perf/report.json` (`median` und `max`). Einzelabschnitte: `--sections importtime,startup,cv,match,ui`.

LLM-Parsing bleibt aus: das Skript setzt `KARRIEREKRAKE_LOCAL_LLM_CV_PARSING=0` und ruft `import_cv(..., guenther_enabled=False)`. Docling und Modell-Warmhalten werden nicht gestartet.

## Was die Zahlen sind

Zeiten und RSS stammen von der Maschine, auf der das Skript läuft. In `docs/PERFORMANCE_AUDIT.md` sind sie als **VM, nicht i3** gekennzeichnet. Sie ordnen Engpässe. Sie sind keine Schwellen und kein Ersatz für das Prozessgruppen-Limit von 3_300_000_000 Bytes auf dem i3.

Das Skript bricht einen Worker ab, wenn die Prozessgruppe 3_200_000_000 Bytes RSS überschreitet, damit der Lauf unter dem bestehenden Gate bleibt. Unter Linux liest es `/proc` (VmRSS der Prozessgruppe, VmHWM als Peak). Ohne `/proc` (Windows) braucht es **psutil**, optional, nicht in den Produkt-Abhängigkeiten: Prozess plus Kinder, rekursiv; Peak über `memory_info().peak_wset`, ersatzweise `peak_pagefile`, wenn das Feld existiert. Fehlen beide Quellen, endet das Skript mit einer Fehlermeldung und Exit-Code 2. Ein nicht gelesener Wert steht im JSON als `null` und auf der Konsole als `n/a`, nie als 0. Der Abbruch gilt für beide Lesewege.

`tests/test_perf_benchmark_rss.py` prüft nur diesen Leser (monkeypatch, kein Benchmark-Lauf). Der Benchmark selbst bleibt manuell.

## Abschnitte

- `importtime`: `python -X importtime -c "import desktop.app"`, Summe und die 25 langsamsten Importe (self time).
- `startup`: Zeit bis `MainWindow.show()` auf der offscreen-Qt-Plattform, einmal mit leerem AppData (erste Migration) und einmal danach.
- `cv`: PDF-Fixtures unter `tests/fixtures/cv_corpus/` plus ein DOCX, das je Lauf aus `tests/fixtures/cv_structured_de.txt` erzeugt wird (im Repo liegt kein DOCX). Stufen: Extrakt, Parse, Verify/Repair, Profilbau. cProfile, Top 30 nach cumulative time.
- `match`: 50/500/5000 Jobs aus `tests/fixtures/intent_jobs_corpus.json`. Scoring, Intent-Filter, Dedup, SQL-Filter/Sort, `has_applied` bei 50/200/800/2000/5000. Nur diese letzte Stufe erneut: `--sections has_applied`.
- `ui`: `refresh_cards` (nur Messung, inklusive `deleteLater` ohne `hide`), Widget-Zahlen, `QGraphicsDropShadowEffect` auf den vorhandenen Seiten.

Speicher: VmRSS/VmHWM je Lauf. tracemalloc-Top-20 ist ein eigener Einzelsnapshot (warmer Start, ein CV, 200 Jobs), nicht der Wall-Clock-Median.

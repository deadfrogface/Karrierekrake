# Laptop-RAM-Gate — Status (PR #62)

## Status: **OFFEN / UNGEPRÜFT** (Messung ausgesetzt)

| Feld | Wert |
|------|------|
| Gate | `PeakJobMemoryUsed ≤ 3_300_000_000` Bytes (unverändert) |
| Zielgerät | Intel Core i3 (11th gen) / genau 8 GB RAM / Windows |
| Messung | **ausgesetzt** — Tester konnte Job-Object-Messung nicht zuverlässig durchführen |
| Ergebnis | **weder bestanden noch fehlgeschlagen** |
| Agent-VM | **kein Ersatz** für Ship-Evidence |

**Wortlaut:** Laptop-RAM-Gate: **OFFEN – Messung ausgesetzt**.

Laptoptest erst wieder anfordern, wenn eine verlässliche Messmöglichkeit (funktionierendes Job-Object-Protokoll auf dem Zielgerät) besteht.

Code-Konstante unverändert: `CV_IMPORT_PEAK_RSS_BYTES_MAX = 3300000000`.

> Begriff: „RSS“ in Titel, Dateinamen und Symbolen (`CV_IMPORT_PEAK_RSS_BYTES_MAX`, `HARD_PEAK_RSS_BYTES`) ist historisch. Das In-App-Gate misst kein Working Set: Windows **privaten Commit** (`PeakPagefileUsage` / `PeakJobMemoryUsed`), Linux **residenten anonymen Speicher** (`Anonymous` aus `smaps_rollup`, kein Commit). `JOB_OBJECT_LIMIT_JOB_MEMORY` ist ein Commit-Limit. Details: `docs/devops/i3-8gb-peak-rss-gate.md`.


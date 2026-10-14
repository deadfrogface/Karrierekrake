# T01 – Kernfunktionen und CI: reproduzierbare Baseline

## Ausgangsstand und gemessene CI-Laufzeiten

PR #144, geprüfter Commit `89f0c92caa5e67ee47af517ef4572fe192c7817c`.

- CI: https://github.com/deadfrogface/Karrierekrake/actions/runs/38563764844 – **success**.
- Windows Smoke: https://github.com/deadfrogface/Karrierekrake/actions/runs/38563764974 – **success**.
- Desktop Platforms: https://github.com/deadfrogface/Karrierekrake/actions/runs/38563765092 – **success**.

Gemessene Job-Wandzeiten aus GitHub Actions (Start bis Ende, inklusive Setup/Installationen; **nicht** reine Pytest-Zeiten):

| Job | Sekunden | Ergebnis |
|---|---:|---|
| unit-tests-shard 1 | 184 | success |
| unit-tests-shard 2 | 144 | success |
| unit-tests-shard 3 | 202 | success |
| unit-tests-shard 4 | 195 | success |
| unit-tests-shard 5 | 202 | success |
| unit-tests-shard 6 | 185 | success |
| unit-tests (Coverage-/Node-ID-Aggregator) | 10 | success |
| cv-regression | 94 | success |
| static-smoke | 110 | success |
| database-migration-tests | 87 | success |
| lifecycle-e2e-benchmark | 125 | success |
| privacy | 83 | success |
| security | 189 | success |

Die längsten Unit-Shards dauern 202 Sekunden einschließlich Einrichtung. Diese Messung ist eine **Baseline**, kein behaupteter Beschleunigungsgewinn gegenüber einer nicht gemessenen Vorversion.

## Vollständigkeits- und Sicherheitsgates

- `.github/workflows/ci.yml` führt sechs parallele Windows-Unit-Shards aus. `scripts/unit_test_shards.py check` verlangt identische Node-ID-Mengen zwischen Collection und ausgeführten JUnit-Fällen, genau eine Ausführung je Test, und erfolgreiche Shard-Jobs.
- `scripts/unit_test_shards.py build-durations` schreibt nur eine vollständige, eindeutige Testlaufzeitliste. Nach den T01-Fixes werden außerdem fehlgeschlagene/error-Testfälle und ungültige, negative oder nicht-endliche JUnit-Laufzeiten abgewiesen.
- `static-smoke` prüft u.a. Suche, Filter, Dry-Run, Pause/Resume, Shutdown, Datenschutz-Löschung und Pipeline. `cv-regression` prüft CV-Korpus und Parser; `database-migration-tests` prüft Migrationen und Reset; `lifecycle-e2e-benchmark` schreibt einen eigenen Benchmarkbericht.
- Keine Testentfernung oder Umgehung der Node-ID-Abdeckung zur Beschleunigung.

## Abschlussgrenze

Die drei grünen Workflows gelten **nur** für den oben genannten Commit. Der nachfolgende Fix zur Zeitmessung (Commits `3b45d6d` und `48d2daf`) muss auf seinem eigenen HEAD die CI bestehen. Erst dann ist die neue Implementierung **CI-bestätigt**. Reale UI-Freeze-/Endnutzerprüfungen werden nicht aus Headless-Tests abgeleitet.

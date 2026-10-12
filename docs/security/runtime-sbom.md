# Runtime-SBOM (T08)

`python scripts/export_runtime_sbom.py artifacts/runtime-sbom.json` im **identischen** Python-Environment des Release-Builds ausführen. Das Ergebnis ist eine CycloneDX-1.5-Komponentenliste installierter Python-Distributionen; kein vollständiger Software-Lieferkettennachweis.

**Offen:** Packaging-Hook, direkte und transitive native Bibliotheken, Qt-Binaries, GGUF-Modellgewichte, Datensätze, Lizenztexte und automatisierte Advisory-Prüfung müssen für eine vollständige Release-SBOM zusätzlich erfasst werden. Nicht als vollständige Release-SBOM veröffentlichen, bevor diese Punkte abgedeckt sind.

# Release-SBOM (T08)

`packaging/Karrierekrake.spec` ruft nach der PyInstaller-Analyse `scripts/export_release_sbom.py` auf. Ausgabe: `build/release-compliance/`.

- `release-sbom.json`: CycloneDX 1.5, Python-Distributionen der aufgelösten Module, native Build-Eingaben mit SHA256, enthaltene GeoNames-Daten mit Manifestprüfung, optional separat heruntergeladene Modelle.
- `THIRD_PARTY_NOTICES.txt`: vorhandene Lizenz-/NOTICE-Dateien aus den Distributionen und GeoNames-Attribution.
- `license-review.json`: fehlende Lizenzzuordnungen und explizite Inventargrenzen.

Native Pakete und der Windows-Komponentenworkflow legen diese Dateien ihren Artefakten bei. Die gemeinsame Release-Publikation verlangt sie und nutzt plattformspezifische Namen. Der bestehende `export_runtime_sbom.py` bleibt für eine allgemeine Inventur installierter Python-Pakete verfügbar.

Die nativen Hashes beziehen sich auf die PyInstaller-Eingaben, vor etwaigem Signieren. Systembibliotheken außerhalb des Pakets sowie fehlende Lizenztexte werden nicht als vollständig geprüft ausgegeben. Der Reviewbericht ist keine rechtliche Freigabe; offene Einträge müssen vor einem entsprechenden Distributionsversprechen geklärt werden.

PR144 ergänzt sämtliche Setup-Modelle (einschließlich GSQ-Varianten) sowie die tatsächlich von PyInstaller aufgelösten Daten-/Assetdateien einschließlich vorhandener Schriften. Jede Datei erhält einen Hash; soweit einer Distribution zugeordnet, deren Lizenzmetadaten. Nicht zuordenbare Rechte bleiben ausdrücklich im Reviewbericht.

Für jede vor Weitergabe relevante Copyleft-Komponente ist zusätzlich zu Metadaten festzuhalten: genaue Version/Quelle, mitgelieferter Lizenztext, eigene Änderungen/Patches, erforderlicher Quellcodezugang und gegebenenfalls Austausch-/Relinkingmöglichkeit. Eine SBOM allein erfüllt diese Pflichten nicht. Insbesondere Qt/PySide und native Bibliotheken anhand der tatsächlich gewählten Lizenz prüfen. Buildquellen und gepinnte Versionen archivieren; Rechte an Marke/Bildern/Schriften durch den Rechteinhaber bestätigen lassen. Ungeklärte Einträge sind kein automatisch erteilter Distributionsnachweis.

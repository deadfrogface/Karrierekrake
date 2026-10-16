# Release-SBOM (T08)

`packaging/Karrierekrake.spec` ruft nach der PyInstaller-Analyse `scripts/export_release_sbom.py` auf. Ausgabe: `build/release-compliance/`.

- `release-sbom.json`: CycloneDX 1.5, Python-Distributionen der aufgelösten Module, native Build-Eingaben mit SHA256, enthaltene GeoNames-Daten mit Manifestprüfung, optional separat heruntergeladene Modelle.
- `THIRD_PARTY_NOTICES.txt`: vorhandene Lizenz-/NOTICE-Dateien aus den Distributionen und GeoNames-Attribution.
- `license-review.json`: fehlende Lizenzzuordnungen und explizite Inventargrenzen.

Native Pakete und der Windows-Komponentenworkflow legen diese Dateien ihren Artefakten bei. Die gemeinsame Release-Publikation verlangt sie und nutzt plattformspezifische Namen. Der bestehende `export_runtime_sbom.py` bleibt für eine allgemeine Inventur installierter Python-Pakete verfügbar.

Die nativen Hashes beziehen sich auf die PyInstaller-Eingaben, vor etwaigem Signieren. Systembibliotheken außerhalb des Pakets sowie fehlende Lizenztexte werden nicht als vollständig geprüft ausgegeben. Der Reviewbericht ist keine rechtliche Freigabe; offene Einträge müssen vor einem entsprechenden Distributionsversprechen geklärt werden.

PR144 ergänzt sämtliche Setup-Modelle (einschließlich GSQ-Varianten) sowie die tatsächlich von PyInstaller aufgelösten Daten-/Assetdateien einschließlich vorhandener Schriften. Jede Datei erhält einen Hash; soweit einer Distribution zugeordnet, deren Lizenzmetadaten. Nicht zuordenbare Rechte bleiben ausdrücklich im Reviewbericht.

Für jede vor Weitergabe relevante Copyleft-Komponente ist zusätzlich zu Metadaten festzuhalten: genaue Version/Quelle, mitgelieferter Lizenztext, eigene Änderungen/Patches, erforderlicher Quellcodezugang und gegebenenfalls Austausch-/Relinkingmöglichkeit. Eine SBOM allein erfüllt diese Pflichten nicht. Insbesondere Qt/PySide und native Bibliotheken anhand der tatsächlich gewählten Lizenz prüfen. Buildquellen und gepinnte Versionen archivieren; Rechte an Marke/Bildern/Schriften durch den Rechteinhaber bestätigen lassen. Ungeklärte Einträge sind kein automatisch erteilter Distributionsnachweis.

OpenSSL-3-Dylibs werden zusätzlich anhand ihrer eingebetteten Releasekennung versioniert. Die SONAME `libcrypto.3.dylib` allein unterscheidet keine Minorversion. Kann die Version nicht gelesen werden, enthält der Reviewbericht einen Eintrag `native-version:`. Das ersetzt weder einen nativen Advisory-Abgleich noch die weiterhin offenen Lizenzzuordnungen. Regressionen: `tests/test_release_sbom.py`.

Beim Build werden auch Distributionen aufgenommen, die nur native Dateien oder gesammelte Daten beitragen. Für Linux ermittelt `scripts/native_package_metadata.py` Paketname und vollständige Distributionsversion über `dpkg-query`; Architektur und Betriebssystemversion fließen in Debian-/Ubuntu-PURLs ein. Sicherheits-Backportrevisionen bleiben erhalten. Diese Paketversion wird als eigener Komponentenbeleg geführt, nicht als erfundene Upstreamversion der einzelnen Binärdatei. Unbekannte Bibliotheken und offene Lizenzzuordnungen bleiben im Reviewbericht. Ein Advisory-Abgleich dieser nativen Paketkomponenten steht weiterhin aus.

Die Linux-Zuordnung bewahrt zusätzlich `kk:source-package` und `kk:source-version`, sofern dpkg sie liefert: z. B. Binärpaket `libssl3` gegenüber Quellpaket `openssl`. Advisory-Datenbanken können das Quellpaket statt des Binärnamens führen; ein erfolgloser Namensabgleich ist kein Negativbefund. Tatsächlich vorhandene `/usr/share/doc/<Paket>/copyright`-Texte und darin referenzierte gemeinsame Lizenztexte werden in die Notices übernommen. Fehlende Texte bleiben als `native-notice:` offen; daraus wird keine SPDX-Lizenz oder Rechtsfreigabe abgeleitet.

`scripts/audit_native_packages.py <release-sbom.json> --report <report.json>` fragt für explizit zugeordnete Ubuntu-Quellpakete die exakte Distributionsversion bei OSV ab, einschließlich Folgeseiten. Exit 1 bedeutet Befunde, Exit 2 unvollständige Zuordnung/Abfrage; leere Inventare und fehlerhafte Antworten gelten nicht als erfolgreicher Scan. Andere native Komponenten bleiben sichtbar unbestätigt. Der Prüfer verändert keine bestehenden Security-Gates. Er muss auf dem tatsächlichen Release-Inventar ausgeführt und jeder Befund bewertet werden; der lokale Entwicklungscontainer ist kein Ersatz dafür.

`NATIVE_LOCAL_AUDIT_2026-10-16.json` dokumentiert ausschließlich eine reale Funktionsprobe gegen die im Entwicklungscontainer installierte OpenSSL-Quellpaketversion. Die Abfrage lieferte Befunde; keine Behebung oder Übertragung auf ausgelieferte Pakete wird behauptet. Bei der Releaseprüfung sind Binärpakete, Quellpakete und gepatchte Distributionsversionen auseinanderzuhalten.

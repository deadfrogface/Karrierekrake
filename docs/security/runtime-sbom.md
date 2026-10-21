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

Fehlende Distributionslizenzfelder werden nur aus eindeutigen Erklärungen ergänzt: ein einzelner exakter MIT-Trove-Classifier oder die überprüften Lizenzdateien in `packaging/license_evidence.json`. Die Datei-Zuordnungen (Liste in der JSON, Konsistenz mit `constraints-runtime.txt` prüft `tests/test_license_evidence_pins.py`) sind an Paketname, Version und SHA256 gebunden; andere Versionen oder veränderte Texte bleiben offen. Ein generischer BSD-Classifier wird nicht automatisch einer BSD-Variante zugeordnet. Die Herkunft steht als `kk:license-evidence` im Inventar. Diese Zuordnung gilt für die erklärte Paketlizenz, nicht pauschal für eingebettete/transitive Fremdkomponenten. `DISTRIBUTION_LICENSE_EVIDENCE_2026-10-16.json` prüft die tatsächlich mitgelieferten Texte von sieben zuvor unzugeordneten Distributionen gegen das Linux-Artefakt 12042181192.

Für ältere Ubuntu-Inventare ohne Quellpaketfelder kann `scripts/enrich_ubuntu_sbom_sources.py <sbom> --out <new-sbom>` genaue Binärversion/Architektur und zugehörige Builds im offiziellen Launchpad-Archiv abgleichen. Die Ausgabe ist eine neue Datei; widersprüchliche oder fehlende Herkunft bleibt offen. Die Quellversion stammt aus den Builddaten und wird nicht aus der Binärversion geraten. Der tatsächliche Lauf auf dem Linux-Artefakt 12042181192 steht in `NATIVE_LINUX_ARTIFACT_AUDIT_2026-10-16.json`: 82 Paketkomponenten/64 Quellabfragen, 50 mögliche Advisory-IDs, 271 nicht durch diesen Quellpaketpfad bestätigte native Dateien. Die Kandidaten sind nicht automatisch alle als ausgelieferte, erreichbare Schwachstellen bestätigt; Komponentenbezug und Abhilfe bleiben zu untersuchen. Keine zusätzlichen Scanner-Ignoren wurden eingeführt.

CPython-eigene native Eingaben erhalten eine separate `runtime:cpython`-Komponente mit der tatsächlichen Version des Buildinterpreters und Verweis `kk:python-runtime`. Ausschließlich die konkreten Interpreterbibliotheken und Standardbibliothekserweiterungen in `lib-dynload` beziehungsweise `DLLs/*.pyd` werden zugeordnet. Drittanbieter-Extensions und OpenSSL-/SQLite-DLLs werden nicht allein wegen ihres Installationsorts als CPython deklariert. Fehlende Interpreter-Lizenz-/Quellnachweise bleiben ausdrücklich im Review; Versionserfassung ist noch keine native Advisory-Prüfung.

Linux-Builder sind auf das im offiziellen Actions-Manifest vorhandene CPython 3.12.15 gepinnt. Windows/macOS besitzen dort keine entsprechende Patch-Binary; diese Runtimeprüfung ist ausdrücklich weiterhin offen. `CPYTHON_RUNTIME_AUDIT_2026-10-17.json` vergleicht verfügbare Upstream-Tags, nicht vermeintlich bereits neu gebaute Endnutzerpakete. Der tatsächlich vorhandene Interpreter-Lizenztext wird mit SHA256 in die Notices übernommen; fehlende Texte bleiben als `runtime-notice:CPython` sichtbar. `runtime-license:CPython` bleibt bis zur vollständigen Lizenz-/Quellenzuordnung offen.

Der native Linux-Updater prüft vor `tarfile.extractall` zusätzlich eindeutige Archivnamen und reguläre direkte Hardlinkziele. Damit hängt seine Abwehr des in CPython gh-157190 beschriebenen Hardlink-/Symlink-Bypasses nicht allein vom Interpreter-Filter ab. Die Python-Laufzeit wird trotzdem aktualisiert; dies ist keine pauschale Mitigation sämtlicher CPython-Advisories. Entpackte Nutzlastgröße und Metadatenreserve werden vor dem Schreiben gegen den freien Platz geprüft.

Windows/macOS security-only CPython builds are pinned by URL, byte size and SHA256 in `packaging/ci_python_runtimes.json`. CI uses a verified isolated venv and asserts live Python 3.12.15 / stdlib OpenSSL 3.5.9 before changing PATH; frozen smoke repeats the policy. CPython build provenance must match the committed pins. The production inventory now fails if the actual Python native library is not identified. These are technical evidence requirements, not a license or whole-product security clearance.

## JobSpy-Netzstack (PR144, Stand 18.10.2026)

Quelle der Versionen: `constraints-runtime.txt` (Build-Pins). Quelle von Lizenz und SHA256: pip-Metadaten (`License-Expression`/`License`/Classifier) und die installierte Lizenzdatei im venv `/workspace/kk-144-venv` (Box-VM Linux x86_64, Python 3.12, nicht das gebaute Paket). Die Einträge stehen in `packaging/license_evidence.json`. Für diese Pakete greift im Exporter ohnehin zuerst die Metadaten-Deklaration; die Dateieinträge sind der hashgebundene Beleg dazu.

| Distribution | Pin | Lizenz (Metadaten) | Rolle |
|---|---|---|---|
| python-jobspy | 1.3.0 | MIT (`License-Expression`) | Indeed-/LinkedIn-Scraper (`search/indeed.py`, `search/linkedin.py`) |
| curl_cffi | 0.16.3 | MIT (`License-Expression`) | von `jobspy.util` importiert (`TLSRotating`); Indeed/LinkedIn nutzen in 1.3.0 `create_session(is_tls=False)`, also `requests` |
| cffi | 2.1.1 | MIT-0 | FFI für die curl_cffi-Native |
| requests | 2.34.2 | Apache-2.0 | HTTP-Session von Indeed/LinkedIn (`RequestsRotating`) |
| urllib3 | 2.8.0 | MIT | Transport unter requests |
| certifi | 2026.10.19 | MPL-2.0 | CA-Bundle für requests/curl_cffi |
| idna | 3.20 | BSD-3-Clause | Hostnamen-Kodierung requests |
| charset-normalizer | 3.5.1 | MIT | Antwort-Dekodierung requests |
| markdownify | 1.2.3 | MIT (Classifier) | jobspy-Beschreibungen HTML→Markdown (kein Netz) |

Native Komponenten in `curl_cffi/_wrapper.abi3.so` (Linux-x86_64-Wheel, Laufzeitstring aus `curl_version()`: `libcurl/8.21.0-IMPERSONATE BoringSSL zlib/1.3.1 brotli/1.2.0 zstd/1.5.7 libidn2/2.3.7 nghttp2/1.63.0 ngtcp2/1.20.0 nghttp3/1.15.0`; `ldd` zeigt nur libc/libpthread, die Bibliotheken sind also statisch eingebunden). Das Wheel liefert **nur** die MIT-Lizenz von curl_cffi mit, keine Texte der eingebetteten Komponenten. Lizenzangaben unten stammen aus dem Upstream-Repository (GitHub-License-API bzw. libidn2-README, Stand Hauptzweig, nicht versionsgenau) und sind deshalb **UNSICHER**, bis die Texte der konkreten Versionen im Paket bzw. in den Notices belegt sind:

| Komponente | Version (Laufzeit) | Upstream-Lizenz (UNSICHER) | Quelle |
|---|---|---|---|
| curl-impersonate (lexiforest) | Basis curl 8.21.0 | MIT (GitHub-API) | github.com/lexiforest/curl-impersonate |
| libcurl | 8.21.0-IMPERSONATE | curl-Lizenz (GitHub-API: NOASSERTION, Datei `COPYING`) | github.com/curl/curl |
| BoringSSL | ohne Versionsangabe im String | Apache-2.0 laut GitHub-API für den Hauptzweig; ältere Stände OpenSSL/ISC; eingebetteter Stand **UNSICHER** | github.com/google/boringssl |
| nghttp2 | 1.63.0 | NOASSERTION (GitHub-API), Datei `LICENSE` | github.com/nghttp2/nghttp2 |
| ngtcp2 | 1.20.0 | MIT | github.com/ngtcp2/ngtcp2 |
| nghttp3 | 1.15.0 | MIT | github.com/ngtcp2/nghttp3 |
| brotli | 1.2.0 | MIT | github.com/google/brotli |
| zstd | 1.5.7 | NOASSERTION (GitHub-API; Upstream dual BSD/GPLv2) | github.com/facebook/zstd |
| zlib | 1.3.1 | **UNSICHER** (GitHub-API ohne Antwort) | github.com/madler/zlib |
| libidn2 | 2.3.7 | GPL-2.0-or-later **oder** LGPL-3.0-or-later (README) | gitlab.com/libidn/libidn2 |

**Befund:** libidn2 ist Copyleft (GPLv2+/LGPLv3+) und im Linux-Wheel statisch gelinkt. Für eine Weitergabe sind LGPL-Pflichten (Lizenztext, Quellzugang, Relinking-Möglichkeit) zu prüfen. Windows/macOS-Wheels wurden hier nicht untersucht (**UNSICHER**). Advisory-Abgleich der Native: `docs/security/CURL_NATIVE_PRELIMINARY_AUDIT_2026-10-17.json` (Status OFFEN).

**Befund:** `ddgs` (`requirements-runtime.txt:17`, `ddgs>=9.0,<10`) und dessen nativer HTTP-Client `primp` werden über `ALLOWED_COLLECT_ALL_PACKAGES` gepackt (`packaging/kk_content_policy.py:79`), sind aber **nicht** in `constraints-runtime.txt` gepinnt. Im venv: ddgs 9.16.0 (MIT), primp 2.0.1 (MIT). Welche Version das Release ausliefert, ist **UNSICHER**; deshalb kein hashgebundener Eintrag.

`DISTRIBUTION_LICENSE_EVIDENCE_2026-10-16.json` bleibt unverändert: Er belegt python-jobspy 1.1.82 im damaligen Linux-Artefakt 12042181192 und ist ein historischer Prüfbericht.

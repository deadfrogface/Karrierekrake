# JobSpy-Transport: tls_client vs. curl_cffi – Entscheidung und Inventar (PR144, Data Engine)

Stand: 18.10.2026, Basis `adc297cf27039f806066597e02b4da21a7ff8926`. Nachweisort: VM, nicht i3; **kein CI-Lauf**.
Betrifft T06.05.07.05.04.02/.03/.04 und T07.06. Nichts hiervon ist FERTIG; Abnahme nur durch den Kritiker.

## Ergebnis

**tls_client wird NICHT in die Runtime-Requirements aufgenommen.** Keine neue Netzwerk-/Native-Abhängigkeit,
daher ist kein Neuaufnahme-Inventar nötig. Die geprüfte Alternative ist bereits umgesetzt: JobSpy 1.3.0 + curl_cffi.

## Prüfung gegen den JobSpy-Quellcode (python_jobspy-1.3.0-py3-none-any.whl von PyPI)

- `Requires-Dist`: beautifulsoup4>=4.12.2, curl_cffi>=0.16.2, markdownify>=1.1.0, pandas>=2.1.2, pydantic>=2.3.0, requests>=2.31.0. **Kein tls_client.**
- `grep tls_client` im gesamten Paket: **0 Treffer**. Einziger Transportimport: `jobspy/util.py: from curl_cffi import CurlOpt, requests as curl_requests`.
- `jobspy/indeed/__init__.py`: `create_session(..., is_tls=False)` → `requests.Session` (POST `https://apis.indeed.com/graphql`).
- `jobspy/linkedin/__init__.py`: `create_session(..., is_tls=False, clear_cookies=True)` → `requests.Session` (GET `https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search`).
- curl_cffi muss trotzdem gebündelt und ladbar sein, weil `jobspy.util` es beim Import lädt (ImportError/OSError bricht jede Quelle).

## Einordnung des Vorbefunds (main accb5cb4)

Auf `accb5cb4` gilt: `constraints-runtime.txt` pinnt `python-jobspy==1.1.82` und `tls-client==1.0.1`, und
`search/indeed.py` importiert in `health_check()`/`search()` **selbst** `tls_client`. Wird dort JobSpy 1.3.0
installiert (requirements `>=1.1.0`, ohne Constraints), fehlt tls_client und Karrierekrakes **eigener** Import
lässt Indeed und LinkedIn (Unterklasse) scheitern. Ursache ist der Adapter-Import, nicht JobSpy 1.3.0.
Auf dem PR144-Head ist dieser Import entfernt; Packager und Frozen-Verifier weisen tls_client aktiv ab
(`packaging/kk_content_policy.py`, `core/security/jobspy_runtime.py`). Für main bleibt der Befund gültig, bis PR144 eingeht.

## Advisory-Abfragen (wörtlich, 18.10.2026 ca. 01:57 MESZ)

OSV `POST https://api.osv.dev/v1/query` (Ecosystem PyPI):

```
curl-cffi==0.16.3: {}
python-jobspy==1.3.0: {}
markdownify==1.2.3: {}
qh3==2.0.3: {}
tls-client==1.0.1: {}
requests==2.34.2: {}
urllib3==2.8.0: {}
```

pip-audit 2.10.1 (`--no-deps --disable-pip -r` mit python-jobspy==1.3.0, curl_cffi==0.16.3, markdownify==1.2.3, qh3==2.0.3), Quelle OSV und PyPI:

```
No known vulnerabilities found
```

Hinweis: Diese Python-Paketabfragen decken **nicht** die eingebetteten nativen Komponenten ab
(libcurl-impersonate 8.21.0, BoringSSL, nghttp2/ngtcp2/nghttp3, zlib/brotli/zstd/libidn2 in curl_cffi;
qh3-Rust/C-Teile). Für tls-client 1.0.1 dokumentiert `EMBEDDED_GO_TRANSPORT_AUDIT_2026-10-17.json` ein
eingebettetes Go-1.20-Binary mit 178 Advisory-IDs (inkl. Aliase) – ein weiterer Grund gegen die Wiederaufnahme.
T06.05.07.05.04.04 bleibt **OFFEN**.

Lokal geladene native Version (Linux x86_64, curl_cffi-Wheel):
`libcurl/8.21.0-IMPERSONATE BoringSSL zlib/1.3.1 brotli/1.2.0 zstd/1.5.7 libidn2/2.3.7 nghttp2/1.63.0 ngtcp2/1.20.0 nghttp3/1.15.0`.
Hash/Lizenz/Herkunft je Plattform für dieses native Artefakt: **UNSICHER** (nicht in diesem Patch erhoben).

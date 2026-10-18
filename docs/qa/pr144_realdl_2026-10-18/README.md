# PR #176 – echte Proxy-Download-Läufe (18.10.2026, Box, nicht Zielhardware)

Echter Download von `Qwen3.5-4B-Q2_K_XL.gguf` (1.940.825.248 Bytes, SHA-256 `b7d9ec51…cb5a`) über huggingface.co. Der einzige Eingriff ist ein CONNECT-Tunnel, der genau einen CDN-Tunnel auf TCP-Ebene nach N = 472.695.563 Bytes trennt. Kein eigenes CA-Zertifikat, kein `verify=False`, kein geändertes CA-Bundle. Primärbelege sind die App-Logs (`runN_app.log`), die Harness-Beobachtungen in `runN_evidence.json` sind Sekundärbelege. Die Datei wurde nach jedem Lauf gelöscht (`cleanup` im Evidence-JSON).

| Lauf | Commit | Harness | Ergebnis | Bedeutung |
|---|---|---|---|---|
| 1 | `856768c` | `harness_run1_pre_cutfix.py` | **FAIL** | Harness-Fehler: Der Schnitt wurde auf einem Tunnel verbraucht, den das Box-Netz schon nach 5.378 Bytes getrennt hatte. Zusätzlich zeigt das App-Log das alte Budgetproblem: Versuch 1 brach vor dem ersten Byte ab, Versuch 2 sicherte 663.388.644 Bytes, Versuch 3 setzte korrekt mit `Range: bytes=663388644-` und 206 fort und brach dann ab. Danach gab die App nach 3 Versuchen mit `connection_interrupted` auf, obwohl Versuch 2 Fortschritt gebracht hatte. |
| 2 | `856768c` | `harness_run2_run3.py` | PASS | Vorher-Beleg: Harness repariert, Range-Start gleich `.part`-Größe. Kam nur durch, weil der dritte und letzte Versuch durchlief. Zählt laut Kritiker nicht für T03. |
| 3 | `0da7d9c` | `harness_run2_run3.py` | PASS | Gültiger Lauf für den Budget-Fix: 4 Versuche, davon 1 gezählt (`counted: True`, weniger als 1 MiB neu). Der alte Code hätte nach Versuch 3 aufgegeben. |

Grenzen: Gemessen wurde auf der Linux-Box und nicht auf dem i3-Zielrechner. Die Netzabbrüche außer dem Schnitt kamen vom Box-Netz und sind nicht reproduzierbar. Schwärzungen: keine nötig (kein Hostname, keine Tokens oder signierten URLs gefunden). Prüfen mit `sha256sum -c SHA256SUMS`.

Nachtrag (nach den Läufen, nur Stil): In beiden Harness-Skripten wurden die ruff-Funde behoben (Ausführbar-Bit, Import-Reihenfolge in `child_main`, `check=False` beim Kind-`subprocess.run`); kein Verhalten geändert. Die Läufe nutzten den vorherigen Stand (Commit `e712a5f`) mit diesen SHA-256-Werten: `harness_run1_pre_cutfix.py` `da06f89c5ed4b0eb878e4835a3d7aecb4a2a3b34af12d50200f8eb69ca7438a7`, `harness_run2_run3.py` `28839e3f4f3f470f64cd0eb8c3c895b49fbb7a43c80e9f28f2d91098625e4e24`. Prüfen mit `git show e712a5f:docs/qa/pr144_realdl_2026-10-18/<datei> | sha256sum`. `SHA256SUMS` enthält den aktuellen Stand.

# PR #144 – Paket-/Commitidentitäten für die Beta-Ergebnisvorlage (T15.03)

> **Herkunft der Hashes (Teamlead/Kritiker 19.10.2026).** Alle Hashes in diesem Dokument und in `docs/beta/sessions/PR144_2470ca16_*.json` sind **gebaut aus `e0f9c3839c0b0b9bdd78ff71fbc28dca6787855c`** (CI-Merge-Build: PR-Head `2470ca1610c039e235f5597601016b7ab8b228d4` gemergt in `main` `6db9c47f36407bba539034b3186564eba212aaa8`). PR-CI baut nie den Head-Commit selbst. Head-Evidenz über **gleichen Tree**: `git rev-parse e0f9c383^{tree} 2470ca16^{tree}` ergibt beide Male `29eed340b374796e61e2d19379dad309042aa57d` (geprüft 19.10.2026). Inhaltlich gleich (gleicher Tree), nicht byte-identisch belegt, da das Paket die Commit-SHA einbettet. Eingebettet ist sie bei Linux in `_internal/native-current.json` (auf der Box geprüft) und bei Windows in `build_metadata.txt` im ZIP (auf der Box geprüft). Bei macOS wird `native-current.json` laut `packaging/kk_content_policy.py` gebündelt, und die laufende App meldete `e0f9c383`; die DMGs habe ich auf der Box nicht geöffnet. Ob die Windows-Onefile-EXE selbst die SHA enthält, ist **UNSICHER**. Session-Felder: `build_kind = "merge_build"`, `tree`, `head_evidence = true`, `head_evidence_basis = "same_tree"`, `built_from` je Hash.

> **Neuer Head (Rebase auf `96df5fca`, 19.10.2026):** Für den neuen PR-Head (Tree ≠ `29eed340`) sind diese Paket-Identitäten **UNSICHER**, bis ein Build genau dieses Heads existiert; die obigen Hashes bleiben gebaut aus `e0f9c383` (Tree `29eed340` = Tree von `2470ca16`).

Stand: 19.10.2026, Personaler (HR-Reviewer). Alle Zeiten in MESZ (UTC+2), Ablaufdaten im November in MEZ (UTC+1).
Nur geprüfte Werte. Was nicht geprüft werden konnte, steht als **läuft/UNSICHER**. Kein Testerergebnis wird behauptet: alle B01–B10/X01–X12 bleiben `not_tested`.

## Commit-Identität

| Feld | Wert | Quelle |
|---|---|---|
| PR-Head (Branch `cursor/roadmap-execution-20261012-d85b`) | `2470ca1610c039e235f5597601016b7ab8b228d4` | GitHub-API `pulls/144` |
| Basis `main` | `6db9c47f36407bba539034b3186564eba212aaa8` | GitHub-API `pulls/144`, `branches/main` |
| **Im Paket eingebettete App-Commit-Identität** | `e0f9c3839c0b0b9bdd78ff71fbc28dca6787855c` | `native-current.json`, `gui-startup.json`, `upgrade.json` im Artefakt; CI-Checkout „HEAD is now at e0f9c38 Merge 2470ca16… into 6db9c47f…“ |
| Version | `1.0.0-alpha.1` („Alpha 1.0“), Sequenz `39200083290` | `native-current.json` |

**Wichtig:** Die Workflows laufen mit dem Ereignis `pull_request`. Deshalb baut CI den Merge-Commit `e0f9c383` (Eltern `6db9c47f` und `2470ca16`), nicht `2470ca16` selbst. Testpersonen sehen in der App `e0f9c383`. Für das Feld `commit` der Vorlage gilt diese eingebettete Identität. Den PR-Head enthält zusätzlich `package_identity.pr_head_commit`. Ändert sich `main` oder der PR-Head, ist das Paket nicht mehr aktuell.

## CI-Läufe für Head `2470ca16` (alle `pull_request`, Versuch 1, gestartet 19.10.2026 06:33:39 MESZ)

| Lauf | Workflow | Stand bei Erhebung |
|---|---|---|
| 39200083290 | Desktop Platforms | `completed`/`success` um 06:59:56 (alle 3 Build-Jobs `success`) |
| 39200083236 | Windows Smoke | `completed`/`success` um 07:02:23 (`qt-smoke` und `exe-smoke-worker` `success`) |
| 39200083213 | CI | **completed, `success`** (alle 15 Jobs `success`; `cv-regression` grün um 07:18:59 MESZ). PR-Head `2470ca16`: 21/21 Checks grün |

## Pakete

| Plattform | Job (ID) | Ergebnis | Zeit (MESZ) | Artefakt (ID) | Artefakt-ZIP | Paketdatei | Paket-SHA256 | Executable-SHA256 |
|---|---|---|---|---|---|---|---|---|
| Linux x86-64 | build ubuntu-22.04 (117891044917) | success | 06:33:41–06:47:48 | `Karrierekrake-linux-x86_64` (12163653246), läuft ab 02.11.2026 05:47 MEZ | 244 699 244 B, sha256 `a83fe270e4a811ca71c678508e977833d70a57497fec27b8b4141dff86b34429` (gebaut aus `e0f9c383`; Tree `29eed340…` = Tree von PR-Head `2470ca16`) | `Karrierekrake-Alpha-1.0-Linux-x86_64.tar.gz`, 241 019 370 B | `6165086420f2491070ab7cec8ae755a055425c6ac70e6831a5eef834be76fe82` (gebaut aus `e0f9c383`; Tree `29eed340…` = Tree von PR-Head `2470ca16`) | `d6b35d8a5bdefe20a8bb2f014055ac2d33720e1698b1f262884fbc71a474e147` (gebaut aus `e0f9c383`; Tree `29eed340…` = Tree von PR-Head `2470ca16`) |
| macOS Apple Silicon | build macos-14 (117891044684) | success | 06:33:46–06:44:33 | `Karrierekrake-macos-arm64` (12163787087), läuft ab 02.11.2026 05:44 MEZ | 192 450 640 B, sha256 `71b1bd6516be34f9dcbb2d35924eec66fdda031a136fd26c456d4f793097a95e` (gebaut aus `e0f9c383`; Tree `29eed340…` = Tree von PR-Head `2470ca16`) | `Karrierekrake-Alpha-1.0-macOS-AppleSilicon.dmg`, 190 424 712 B | `7f0c80df3ccd4cd689d057c31bf4e0fb95445ec9fb98937bfd81e1dcdf438daf` (gebaut aus `e0f9c383`; Tree `29eed340…` = Tree von PR-Head `2470ca16`) | `6edd87a59c810204da6c72e89bb1e2f0b8344ed9f7bed183d819ca554299ae11` (gebaut aus `e0f9c383`; Tree `29eed340…` = Tree von PR-Head `2470ca16`) |
| macOS Intel | build macos-15-intel (117891044938) | success | 06:33:45–06:59:55 | `Karrierekrake-macos-x86_64` (12164450880), läuft ab 02.11.2026 05:59 MEZ | 212 127 824 B, sha256 `caf5960ba79a1e92d1818ad454990d7d86b45bfd0c373aac386b59f4791ce6eb` (gebaut aus `e0f9c383`; Tree `29eed340…` = Tree von PR-Head `2470ca16`) | `Karrierekrake-Alpha-1.0-macOS-Intel.dmg`, 210 091 731 B | `9ad1fe5fe8480fed28b37100f38d4b2676fb76fe651a086bd72856c550886479` (gebaut aus `e0f9c383`; Tree `29eed340…` = Tree von PR-Head `2470ca16`) | `2f0b44782c74ef954c2c3e40797fc4cfd0beb3183fec7ae1ac5462f860ff4ac5` (gebaut aus `e0f9c383`; Tree `29eed340…` = Tree von PR-Head `2470ca16`) |
| Windows x86-64 | Windows Smoke `exe-smoke-worker` (117891044582); Onefile-Smoke-Paket, kein Release-Build (`build-windows.yml` startet nur per `workflow_dispatch`/`v*`-Tag und lief nicht) | success | 06:33:41–07:02:18 | `Karrierekrake-Windows-Smoke` (12164316649), Lauf 39200083236, läuft ab 02.11.2026 06:02 MEZ | 172 749 599 B, sha256 `303ee4caf2cb88f4cb2d9b4f03f1835f92301f9160385490ec1206e8d608a626` (gebaut aus `e0f9c383`; Tree `29eed340…` = Tree von PR-Head `2470ca16`) | `Karrierekrake-Windows.zip`, 170 279 300 B | `e171ffcb5c5d083470cc5817b338e506032f5dc71167c7e1bdaa9ed170318dbf` (gebaut aus `e0f9c383`; Tree `29eed340…` = Tree von PR-Head `2470ca16`) | `6ed77fb4c8318f2658a1eb68f17134020f24cc87126615f816f6fa639d2d56d9` (gebaut aus `e0f9c383`; Tree `29eed340…` = Tree von PR-Head `2470ca16`) (= `build_metadata.txt`) |

Wie die Hashes geprüft wurden: Alle vier Artefakte wurden am 19.10.2026 auf der Box über die GitHub-API geladen und lokal mit `sha256sum` gehasht. Der ZIP-Hash stimmt mit dem Digest der Artefakt-API überein, bei Linux und macOS arm64 zusätzlich mit dem Digest im Upload-Log. Die Upload-Logs von macOS Intel und Windows habe ich nicht gelesen. Der Paket-Hash stimmt bei Linux/macOS mit `archive_sha256` in `upgrade.json` überein. Bei Windows stimmt der Hash der entpackten `Karrierekrake.exe` mit `build_metadata.txt` und `backup-restore.json` überein (für das ZIP selbst veröffentlicht CI keinen Hash). Bei Linux stimmt außerdem der Hash der entpackten Programmdatei mit `executable_sha256` aus `gui-startup.json`, `backup-restore.json` und `upgrade.json` überein.

CI-Belege im Artefakt (Build-Host, keine Geräteabnahme): Smoke, Offline-Import DE_01/EN_01, Suche ohne Netzwerk (Linux im netns), Backup/Restore/Neustart, GUI-Start ohne Tray, Upgrade von Baseline-Lauf 39194636153 (Commit `02f900cc`) mit erhaltenem synthetischem Marker – jeweils `ok: true` (Linux, macOS arm64, macOS Intel; macOS Intel mit `--require-avx2`). Windows: Smoke, Offline-Import DE/EN, Profil übernehmen und Neustart, Anschreiben-Erzeugung (Modus `CI_Python_using_verified_install_sidecar_not_packaged_writer_UI`, also nicht über die Paket-UI; keine HR-Qualitätsprüfung), Backup/Restore, Suche-Selbsttest: jeweils `ok: true`. Beobachtung: Windows `peak_job_memory_used_bytes` 3 520 630 784 B beim Import liegt über dem 3,3-GB-Wert aus `docs/devops/i3-8gb-peak-rss-gate.md`. Ob dieses Gate für einen 2-Kern-CI-Runner gilt, ist **UNSICHER**. Die Datei meldet `release_blocked: false`.

## Ausgefüllte Vorlage

- `docs/beta/sessions/PR144_2470ca16_linux-x86_64.json`
- `docs/beta/sessions/PR144_2470ca16_macos-arm64.json`
- `docs/beta/sessions/PR144_2470ca16_macos-x86_64.json`
- `docs/beta/sessions/PR144_2470ca16_windows-x86_64.json`

Alle vier sind mit `python scripts/beta_acceptance_report.py <datei>` geprüft. Ergebnis: gültig, `not_tested` 22, `approved: false`. `os_version`/`device_alias` beschreiben den CI-Build-Host und kein Testgerät. Für einen echten (synthetischen) Testlauf legt jede Testperson eine eigene Session mit ihrem Gerät an und übernimmt `commit` und `package_sha256` von hier.

## Grenzen

- Ein CI-Build ist keine Plattformfreigabe. Die Zielmatrix aus `PR144_EXTENDED_ACCEPTANCE.md` (Linux mit grafischer Sitzung und Keyring, Windows, macOS Intel und Apple Silicon auf echten Geräten) ist offen.
- Signatur/Notarisierung der Pakete: **UNSICHER**, auf der Box nicht geprüft. Es ist kein Release und kein Tag.
- T15.03 bleibt `IMPLEMENTIERT – PRÜFUNG OFFEN`. FERTIG setzt nur der Kritiker.

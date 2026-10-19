# Sicherung Data Engine, 19.10.2026 (Teamlead-Anweisung). Nicht mergen.

Basis: #144-Head `7d5243d02a2e7c066bd035e6e8dbd32fa057b868` (cursor/roadmap-execution-20261012-d85b).
Quelle: die lokalen Data-Engine-Repos und -Worktrees (ohne den defekten Worktree main144).
Nur Commits/Änderungen, die auf keinem Remote-Branch liegen. `git cherry` gegen den #144-Head: + = nicht in #144.

| Datei | Original-Commit | Branch (lokal) | Inhalt | Warum nicht als Cherry-Pick |
|---|---|---|---|---|
| `m9-fix-v1/0001-…` | `a8d98278e782a2c750df67589efd41f091ca42e5` | `backup/m9-fix-v1` | fix(classify): Absage eines bestehenden Termins durch den Arbeitgeber -> interview_cancelled (T01.10 Punkt 3) | Konflikt mit dem #144-Head |
| `m9-fix-v1/0002-…` | `741d1afcd12d44004225b891e912c3f5298fd925` | `backup/m9-fix-v1` | feat(calendar): CANCELLED-Update eines bestehenden Termins vorschlagen, Export erst nach Freigabe (T01.10 Punkt 6) | Konflikt in `tests/test_t0110_synthetic_mail_calendar.py` |
| `stash0-on-466eb40.patch` | Stash `f64e2c5` („WIP on data-engine/main144: 466eb40“, 18.10.2026 22:48 MESZ) | – | Entfernt `_formal_salutation` in `integrations/reply_draft.py` und zugehörige Tests (−104/+9). Ist eine Rücknahme, keine neue Arbeit. **UNSICHER**, wozu der Stash diente | – |
| `pr144-sectionN/0001-…` | `91908f42177471a73ef59b4c1201f6fd59e3cb7c` | `cursor/roadmap-execution-20261012-d85b` (lokal, ahead 3 auf `45dcf057`) | docs(pr144): Abschnitt N.0–N.3 curl_cffi-Native-Inventar, Lizenzen, Advisories (T06.05.07.05.04.04) | Nur lokal, noch nicht gepusht; Basis `45dcf057` |
| `pr144-sectionN/0002-…` | `9534f184d826f8914017a55a334382950a8959c0` | dito | docs(pr144): Abschnitt N.4 Datenfluss je Host gegen den Paketcode (T07.06) | dito |
| `pr144-sectionN/0003-…` | `bfd4cb6705999948e169efd33457581d2e497d91` | dito | docs(pr144): Work-Items-Belege für T06.05.07.05.04.04 und T07.06 (Abschnitt N) | dito |
| `pr144-sectionN-on-f4451b2d/0001-…` | `17370f38251a7b8fed19a3f57cd14db4c0ba3c99` (Cherry-Pick von `91908f42`) | `de-sectionN-on-f4451b2d` (lokal, ahead 3 auf `f4451b2d`) | wie `pr144-sectionN/0001-…` | Nur lokal, nicht nach #144 gepusht; Basis `f4451b2d` (CI zum Zeitpunkt noch laufend) |
| `pr144-sectionN-on-f4451b2d/0002-…` | `762416018b78c6ab85633fc588de145eb7dcd385` (Cherry-Pick von `9534f184`) | dito | wie `pr144-sectionN/0002-…` | dito |
| `pr144-sectionN-on-f4451b2d/0003-…` | `56ea142064dec0825ad26d1d239e50f9a5716cb9` (Cherry-Pick von `bfd4cb67`, Commit-Verweise in `PR144_WORK_ITEMS.json` auf `17370f38`/`76241601` aktualisiert) | dito | wie `pr144-sectionN/0003-…` | dito |
| `pr144-sectionN-on-f4451b2d/0004-…` | `d9f91204848be160190a959ff5e96a853084ff05` (neu, auf `56ea1420`) | dito (ahead 4 auf `f4451b2d`) | docs(pr144): Kritiker-Fixes Abschnitt N – Scope-Minimalität UNSICHER (unbelegt), Pins bis `f4451b2d` per `git diff` belegt, neues Work-Item T07.10 (BRouter-JAR ohne Hash-Prüfung, OFFEN) | dito |
| `pr144-sectionN-on-56f0c41a/0001-…` | `454b1f63ae24d146f3f8f9455a3315470ec2c378` (Cherry-Pick von `17370f38`) | `de-sectionN-on-56f0c41a` (lokal, ahead 4 auf `56f0c41a`) | wie `pr144-sectionN/0001-…` | Nur lokal, nicht nach #144 gepusht; Basis `56f0c41a` (Designer, CI zum Zeitpunkt noch laufend) |
| `pr144-sectionN-on-56f0c41a/0002-…` | `dbea073f8407c5c70371ebba29f41a5959c6f058` (Cherry-Pick von `76241601`) | dito | wie `pr144-sectionN/0002-…` | dito |
| `pr144-sectionN-on-56f0c41a/0003-…` | `c46b70dcaf29b6d0a3a51614102c86db5f193146` (Cherry-Pick von `56ea1420`, Commit-Verweise in `PR144_WORK_ITEMS.json` auf `454b1f63`/`dbea073f` aktualisiert) | dito | wie `pr144-sectionN/0003-…` | dito |
| `pr144-sectionN-on-56f0c41a/0004-…` | `d8fd119d6ad26c934d0aacc32c78e8c3415d91a6` (Cherry-Pick von `d9f91204`, Verweis T07.10 auf `dbea073f` aktualisiert) | dito | wie `pr144-sectionN-on-f4451b2d/0004-…` | dito |
| `pr144-sectionN-pushed-d8fd119d/0001-…0004-…` | `454b1f63`, `dbea073f`, `c46b70dc`, `d8fd119d` | `cursor/roadmap-execution-20261012-d85b` (#144, Head `d8fd119d6ad26c934d0aacc32c78e8c3415d91a6`) | wie `pr144-sectionN-on-56f0c41a/` | Am 19.10.2026 ~19:25 MESZ ohne Force nach #144 gepusht (Basis `56f0c41a`, 21/21 Checks grün); Sicherung des gepushten Stands, From-Zeile `data-engine@invalid` |

Wiederherstellen: `git am <datei>` (für `pr144-sectionN/` auf `45dcf057af024a3cd98ba06034af2d0a97ff6513`) (format-patch) bzw. `git apply stash0-on-466eb40.patch`.

Bei der Datenschutzprüfung weggelassen (Kritiker 13:55): `jobspy-inventory/0001-…` (Original-Commit `968df07917e5577c395877c5ef582e0f4df273b0`, Branch `data-engine/pr144-jobspy-inventory`, nur Coverage-Doku). Der Patch enthielt einen Box-Pfad, den Klarnamen des Nutzers und einen Host-Namen. Die 3 Vorgänger-Commits des Branches sind patch-gleich in #144; der Commit selbst bleibt nur lokal.

Nicht enthalten, weil schon auf einem Remote-Branch bzw. patch-gleich in #144:
- `data-engine/pr144-t0110-synthetic-mail-calendar` (3 Commits, alle patch-gleich in #144).
- `data-engine/main144` (in #144 enthalten).
- Alle übrigen lokalen Branches (vollständig auf Remote-Branches).
- Uncommittete Änderungen in den Worktrees: keine.

Nachtrag 19.10.2026 14:35 MESZ: `pr144-sectionN/` (`git format-patch 45dcf057..bfd4cb67`, nur Doku: `docs/project/PR144_COVERAGE_AND_GATES.md`, `docs/project/PR144_WORK_ITEMS.json`). Datenschutzprüfung der 3 Patches: keine Box-Pfade, kein Klarname, kein Benutzer-/Host-Name, keine escaped Pfade (`\u005c`, `%5C`, `%2F`, `\u002f`); nichts geschwärzt.

Nachtrag 19.10.2026 15:50 MESZ: `pr144-sectionN-on-f4451b2d/` (`git format-patch f4451b2d..56ea1420`, Wiederherstellen mit `git am` auf `f4451b2d0a2cd8c1a9ec02cf1a92a849f4ddd2b6`). Cherry-Pick ohne Konflikte. Datenschutzprüfung der 3 Patches wie oben: keine Treffer; nichts geschwärzt.

Nachtrag 19.10.2026 15:54 MESZ: `pr144-sectionN-on-f4451b2d/0004-…` (aus `git format-patch f4451b2d..d9f91204`, nur Doku). Datenschutzprüfung wie oben: keine Treffer; nichts geschwärzt. Zusätzlich in `quicksave-20261019/threshold-1c641a0/0001-…` die verbliebene `@users.noreply.github.com`-Adresse der From-Zeile durch `<redacted>` ersetzt.

Nachtrag 19.10.2026 16:18 MESZ: `pr144-sectionN-on-56f0c41a/` (`git format-patch 56f0c41a..d8fd119d`, nur Doku, Wiederherstellen mit `git am` auf `56f0c41a683b4e4e8d7250416ce0c1cacf124f3b`). Cherry-Pick ohne Konflikte; nur die Commit-Verweise in `PR144_WORK_ITEMS.json` (T06.05.07.05.04.04, T07.06, T07.10) auf die neuen SHAs umgestellt, `status_counts` passen weiter (233). Datenschutzprüfung der 4 Patches wie oben: keine Treffer; nichts geschwärzt.


## Quicksave 19.10.2026 (Nachtrag, MESZ)

Zielordner: `quicksave-20261019/<source>/`. Nur noch lokal Vorhandenes, das zuvor fehlte oder (jobspy-inventory) aus Datenschutzgründen weggelassen war. Section-N-Commits `91908f42`/`9534f184`/`bfd4cb67` nicht erneut gesichert (liegen schon unter `pr144-sectionN/`).

| Datei | Original-Commit / Basis | Quelle (relativer Name) | Inhalt | Anmerkung |
|---|---|---|---|---|
| `quicksave-20261019/jobspy-inventory/0001-…` | `968df07917e5577c395877c5ef582e0f4df273b0` auf Basis `966cbccfb2a28ecf70babbbd4b4c25d55bcdb112` | `kk-144-data-inventory` (Branch `data-engine/pr144-jobspy-inventory`) | Coverage-Doku JobSpy-Lizenznachweis + T07.06 Host-Register | Zuvor weggelassen (Kritiker). Kopie **geschwärzt**: Klarname, Box-Host, `/workspace/…`-Venv-Pfad → `[REDACTED…]`. Vorgänger `e460d92`/`55f7ecb`/`966cbcc` patch-gleich in #144 |
| `quicksave-20261019/kk-144-wip/wip-combined.diff` (plus tracked/untracked-Teile) | WIP auf `b992856f1653df9ed146cb8eff48358ec5903a38` | `kk-144` (Branch `data-engine/pr144-jobspy-package-dataflow`) | Uncommittet: Model-Setup-UX (`desktop/i18n.py`, `theme.py`, `model_setup_panel.py`, `wizard/__init__.py`, Tests) + untracked `desktop/widgets/model_fit.py`, `tests/test_model_setup_ux.py` | Kopie geschwärzt: Klarname, synthetischer `C:\Users\…\token=`-Teststring |
| `quicksave-20261019/threshold-1c641a0/0001-…` | `1c641a0137d6a0c9cd9886463db892863d4e02e6` auf Basis `adc297cf27039f806066597e02b4da21a7ff8926` | `kk-panel-fits` (lokaler Branch `backup/threshold-pre-rebase-1c641a0` / stale tip) | fix(setup): Setup-Modell nach Gesamt-RAM klassifizieren (8-GB-Geräte) | SHA lokal-only (`git cherry` + gegen #144 und gegen `origin/perf/pr144-setup-thresholds`); From-Zeile geschwärzt |

Übersprungen (patch-gleich auf Remote bzw. schon gesichert):
- `data-engine/pr144-jobspy-package-dataflow` lokale SHAs `11def97`/`c79e9a6`/`b992856` — patch-gleich auf `origin/data-engine/pr144-jobspy-package-dataflow` (`a2513ba`).
- `data-engine/pr144-t0110-synthetic-mail-calendar` — patch-gleich in #144.
- `pr144-sectionN/`, `m9-fix-v1/`, `stash0-on-466eb40.patch` — bereits im Backup.
- Verzeichnisse designer/personaler/po/kritiker und defekter Worktree `kk-144-data-main144` nicht durchsucht; `kk-144-data-main144-r` nur Section N (skip).

Datenschutzprüfung Quicksave: `rg` auf `/workspace`, `/home/`, `/Users/`, Damiano, Sümegi/sumegi/suemegi, Box-VM/Host, `\u005c`, `%5C`, `%2F`, `\u002f`, Laufwerkspfade, `token=` — nach Schwärzung **keine Treffer** in `quicksave-20261019/`.

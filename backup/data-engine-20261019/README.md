# Sicherung Data Engine, 19.10.2026 (Teamlead-Anweisung). Nicht mergen.

Basis: #144-Head `7d5243d02a2e7c066bd035e6e8dbd32fa057b868` (cursor/roadmap-execution-20261012-d85b).
Quelle: die lokalen Data-Engine-Repos und -Worktrees (ohne den defekten Worktree main144).
Nur Commits/Änderungen, die auf keinem Remote-Branch liegen. `git cherry` gegen den #144-Head: + = nicht in #144.

| Datei | Original-Commit | Branch (lokal) | Inhalt | Warum nicht als Cherry-Pick |
|---|---|---|---|---|
| `m9-fix-v1/0001-…` | `a8d98278e782a2c750df67589efd41f091ca42e5` | `backup/m9-fix-v1` | fix(classify): Absage eines bestehenden Termins durch den Arbeitgeber -> interview_cancelled (T01.10 Punkt 3) | Konflikt mit dem #144-Head |
| `m9-fix-v1/0002-…` | `741d1afcd12d44004225b891e912c3f5298fd925` | `backup/m9-fix-v1` | feat(calendar): CANCELLED-Update eines bestehenden Termins vorschlagen, Export erst nach Freigabe (T01.10 Punkt 6) | Konflikt in `tests/test_t0110_synthetic_mail_calendar.py` |
| `stash0-on-466eb40.patch` | Stash `f64e2c5` („WIP on data-engine/main144: 466eb40“, 18.10.2026 22:48 MESZ) | – | Entfernt `_formal_salutation` in `integrations/reply_draft.py` und zugehörige Tests (−104/+9). Ist eine Rücknahme, keine neue Arbeit. **UNSICHER**, wozu der Stash diente | – |

Wiederherstellen: `git am <datei>` (format-patch) bzw. `git apply stash0-on-466eb40.patch`.

Bei der Datenschutzprüfung weggelassen (Kritiker 13:55): `jobspy-inventory/0001-…` (Original-Commit `968df07917e5577c395877c5ef582e0f4df273b0`, Branch `data-engine/pr144-jobspy-inventory`, nur Coverage-Doku). Der Patch enthielt einen Box-Pfad, den Klarnamen des Nutzers und einen Host-Namen. Die 3 Vorgänger-Commits des Branches sind patch-gleich in #144; der Commit selbst bleibt nur lokal.

Nicht enthalten, weil schon auf einem Remote-Branch bzw. patch-gleich in #144:
- `data-engine/pr144-t0110-synthetic-mail-calendar` (3 Commits, alle patch-gleich in #144).
- `data-engine/main144` (in #144 enthalten).
- Alle übrigen lokalen Branches (vollständig auf Remote-Branches).
- Uncommittete Änderungen in den Worktrees: keine.

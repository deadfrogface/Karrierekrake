# Anschreiben-Lauf letters_full (2026-10-18) — Beleg-Ordner

Nur synthetische Daten (Repo-Fixtures `tests/fixtures/anschreiben_gold/`, 16 Gold-Fälle mit `expected_outcome=interview`).

- Lauf: 2026-10-18 18:38:49–20:23:36 MESZ (UTC+2), Code-Stand `ffa483c34bfc212a86c40ff9392960ed74195ecf`, Box-VM, **VM, nicht i3**.
- Modelle: `q4_k_m/` = unsloth Qwen3.5-4B Q4_K_M (sha256 `00fe7986ff5f6b46…`), `q2_k_xl_4b_gsq/` = ISTA-DASLab Qwen3.5-4B GSQ Q2_K_XL (sha256 `b7d9ec51fb4d726d…`).
- Writer: `core.cover_quality.rewrite_cover_letter`, 2 Versuche je Fall, T=0.2. Treiber: `tools/run_all.sh`.
- Inhalt: `RUN.log` (Zeiten, Exit-Codes, Peak RSS), `SUMMARY.md` (Fakten je Fall), `FACTS.json` (`tools/facts.py`), `GUARD_REPLAY.json` (`tools/replay_guard.py`, deterministischer Guard ohne LLM auf die aufgezeichneten Rohantworten), `CLAIMS_SCAN_<modell>.txt` (`tools/claims_scan.py`), je Fall ein JSON pro Modell, `logs/` (stdout- und Watchdog-Logs je Fall).
- Vollständig übernommen: Gesamtgröße ca. 688 KB (< 5 MB), daher wurden **keine** Logs weggelassen. Alle Dateien sind byte-identisch mit dem Original-Ordner der QA-Box.
- HR-Urteil zu diesem Lauf: `docs/personaler/BLIND_REVIEW_BERICHT.md` (Abschnitt 7) und `docs/qa/PR144_MODEL_COMPARE_GSQ4B_Q4KM_2026-10-18.md` (Abschnitt 4).

## Redaktion

Vor dem Commit erneut geprüft (rg über alle Dateien dieses Ordners): `ghp_|github_pat_|hf_[A-Za-z0-9]|GITHUB_TOKEN|HF_TOKEN|/home/` sowie der Box-Hostname. Ergebnis: **keine Treffer** außer der Beschreibung dieser Suche selbst in `SUMMARY.md` (Abschnitt „Redaction“). Nichts geschwärzt. Nur vermerkt, nicht geschwärzt: temporäres HOME `/tmp/kk-letters-home.m6f9` in `RUN.log` und `/workspace/...`-Pfade (Modelle, Repo) in JSONs, Logs und Skripten.

## Integrität

`SHA256SUMS` deckt alle Dateien dieses Ordners außer `SHA256SUMS` selbst ab (inkl. dieser `README.md`). Prüfung: `cd docs/qa/pr144_model_compare_2026-10-18/letters_full && sha256sum -c SHA256SUMS`.

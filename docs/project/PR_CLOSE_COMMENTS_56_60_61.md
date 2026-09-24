# Vorbereitete Close-Kommentare für Spike-PRs

**Status Agent (2026-09-24):** Close erneut versucht — weiterhin **403**
(`gh pr close` / `gh pr comment` / `ManagePullRequest set_pr_status`).
**#63** wurde per Merge-API erfolgreich auf main gebracht; #62 bleibt offen.

Maintainer kann die drei PRs mit den Texten unten schließen.

---

## PR #56 — Phi-Extraktion ≥99% Sollwerte

```
Schließen: überholt.

PHI_EXTRACT wurde aus dem produktiven Pfad entfernt. Der aktuelle
Integrationsversuch ist Docpick+Qwen auf PR #62 (DET-frei auf dem
Feature-Branch). Kein Merge dieses Spikes.
```

## PR #60 — Phi vs DET begrenzter Vergleich

```
Schließen: überholt.

Phi-Extract ist entfernt; der produktive Ersatzversuch läuft über
Docpick+Qwen (PR #62). DET bleibt nur auf main, bis #62 mergefähig ist.
```

## PR #61 — OSS Docling+SmartResume Prototyp

```
Schließen: überholt durch Docpick/#62.

SmartResume-/Docling-Spike nicht weiterverfolgen; neuer Importpfad ist
Docpick+Qwen3.5-4B ohne DET-Fallback (Branch cursor/docpick-qwen35-cv-replace-d85b).
```

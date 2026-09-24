# Phase 2 – Desktop- und CV-Performance

Messdaten: `artifacts/perf_phase2/BASELINE.json` (offscreen, gleiche Hardware wie Agent-VM).

## Vorher (bekannter Engpass)

- CV-Import-Dialog rief `import_cv` **synchron im Konstruktor** auf → UI-Freeze ≈ **90–110 s** (Round2 Ø **87,8 s/CV**).
- Docling wurde bei jedem Folgeimport der gleichen Datei erneut ausgeführt.

## Nachher (gemessen)

| Ablauf | Vorher | Nachher |
|--------|--------|---------|
| App-Start (QApp+Config+MainWindow) | — | **3,28 s** (MainWindow 1,93 s), Peak RSS **206 MB** |
| Seitennavigation | — | **≤ 3 ms**/Seite |
| CV-Dialog öffnen (ctor) | ≈ 90–110 s blockiert | **0,002 s**, OK deaktiviert bis Extract fertig |
| Docling DE_01 (kalt) | Teil von ~88–111 s | **25,9 s** (inkl. OCR-Modell-Kaltstart) |
| Docling DE_01 (Folge, SHA-256-Cache) | erneut Docling | **0,0 s** |
| LLM Qwen3.5-4B (CPU, :8765) | dominant | **101–118 s**/Call |
| Full Docpick-Import (Folge) | — | **106 s** (LLM-dominant), Peak RSS **2453 MB** |

## Änderungen mit messbarem Nutzen

1. **Async CV-Import** (`CvImportWorker` + Progress/Abbrechen) — UI bleibt bedienbar; größter UX-Gewinn.
2. **Docling-Text-Cache** (SHA-256 der PDF-Bytes + Docling-Version) — Folge-PDF-Text **25,9 s → 0 s**.
3. **Schema-JSON-Cache** — vermeidet wiederholtes `model_json_schema()`-Serialisieren.

## Weiterhin langsam

- **LLM-Inferenz auf CPU** (~100 s/CV) bleibt der Bottleneck; kein Qualitäts-Trade-off in Phase 2 erzwungen.
- Kaltstart Docling + RapidOCR (~2,2 GB RSS-Delta) beim ersten PDF im Prozess.

## Nicht behauptet

- Keine pauschale „App ist schneller“-Aussage jenseits der Tabelle.
- Docpick ist auf **main** weiterhin nicht produktiv (DET aktiv), solange #62 nicht gemerged ist.

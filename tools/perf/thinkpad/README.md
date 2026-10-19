# Karrierekrake – ThinkPad-Speedtest **CV-Import** (Vorbereitung, NICHT auf dem ThinkPad gelaufen)

Stand 2026-10-19 (Europe/Berlin), Box. Eingebetteter Repo-Snapshot: **`47e8f83b08a1925579891abbc861b68a284a66a8`**
(= Commit der Q4_K_M-Referenz-Extrakte des Personalers; Merge „Kritiker-Doku 0c68c205 in #144“, 144 Commits nach
dem vorher verwendeten `8fca79b5`). Der Box-Checkout `kk-t0208` steht unverändert auf 8fca79b5; der Snapshot wird per
`git archive 47e8f83b` erzeugt (kein Checkout). Nichts wurde auf dem ThinkPad oder einem anderen Nutzerrechner
ausgeführt. Keine Pushes, keine PRs.

## Entscheidungen (Teamlead/Kritiker, 18.10.)
1. **Gemessen wird der Produktpfad CV-Import** (`core/cv_llm_runtime.py`, in-process): tok/s (Prompt + Generierung),
   Zeit pro CV, TTFT, Spitzen-RAM auf den **10 synthetischen CVs** von `tests/fixtures/cv_corpus/expected_results.json`
   (DE_01…DE_05, EN_01…EN_05; dieselben 10 PDFs wie `scripts/run_cv_corpus.py`).
2. **Baseline und jede Variante laufen auf llama-cpp-python==0.3.35** (constraints-runtime.txt), in-process wie das
   Produkt, **nicht llama-server**. Die alte 0.3.36-Baseline (docs/qa/pr144_thinkpad_speed_2026-10-18) zählt nicht;
   die Baseline wird in derselben Sitzung neu gemessen (Matrix-Skript misst sie zusätzlich am Ende noch einmal).
3. **Brief-Harness ist aus dem Speedtest gestrichen** (Parent-Update). `thinkpad_speed_bench.py`, `build_kk_prompts.py`,
   `prompts/`, `smoke/`, `gguf_*`, `tokenizer_compare.txt`, `llama-b10453-linux/` liegen **unverändert** im Ordner
   (alte Bündelversion: `kk-speed-bundle-v1-letters.zip`), sind aber **nicht** Teil des neuen Bundles und werden nicht
   weiter gepflegt. Falls je wieder verwendet: „nicht verdrahteter Pfad, Produktbezug UNSICHER“ (Brief im Produkt =
   Template `core/cover_letter.py`; `suggest_writing`/`plan_draft` ruft die App nicht auf).

## Neues Bundle `kk-speed-bundle.zip`
| Datei | Zweck |
|---|---|
| `thinkpad_cv_bench.py` | Harness (`run`, `diff`, `spec-check`, `summarize`, `sysinfo`), Python 3.12, braucht Repo-Snapshot + psutil + llama-cpp-python 0.3.35 |
| `thinkpad_peak_raw.py` | getrennter Schritt P: ruft `scripts/run_i3_peak_job_benchmark.py` des Repos auf, **nur Roh-Peak**, Label „ThinkPad, speed/peak raw data, not i3 evidence“ |
| `kk-repo-47e8f83b.zip` | `git archive` des Repos @ 47e8f83b (core, guenther, desktop, devops, contracts, config, cv_corpus, run_cv_corpus.py, run_i3_peak_job_benchmark.py, constraints/requirements-runtime) + `REPO_COMMIT` |
| `run_cv_matrix.ps1` | Pre-flight + Variantenmatrix A–H (+ `-With8B` I–L), `-Preset short` (A,B,D,E,F,G; mit `-With8B` + J,L), danach `summarize` + `diff` gegen Baseline + `spec-check` L↔J; `-PeakRaw` = nur Schritt P |
| `tests/test_thinkpad_cv_bench.py` | 12 Unit-Tests (diff, Normalisierung, Pre-flight, 2× spec-check, 6× Energiezustand inkl. „ändert nie den Energieplan“) |
| `models.json`, `fetch_models.py` | gepinnte URLs/Größen/SHA-256 für GGUFs **und das Windows-Wheel** (`python_wheels`) |
| `smoke_cv/` | Box-Smoke (Xeon-VM, geteilt mit anderen Prozessen) – **keine Zielzahlen** |
| `README.md` | diese Datei |

## Wie die Harness den Produktpfad aufruft
`run --mode import` (Standard) ruft pro CV **`core.cv_docpick_import.import_cv_docpick(pfad)`** auf – dieselbe Funktion,
die das Import-Kind ausführt (`desktop/cv_import_child.py:354` → `core/cv_parser.py:3067` → `core/cv_intelligence.py:206`).
Darin: PDF-Text (`extract_cv_text`, :1200) → Prompt (`_extraction_messages`, :1247) → `_llm_extract` (:1280) →
`chat_completion_inprocess` (cv_llm_runtime.py:1069) → ggf. **zweiter fokussierter LLM-Aufruf**
(`_complete_explicit_lists`, :1424, eigener Model-Load) → Nachbearbeitung. „Zeit pro CV“ = Wandzeit dieses Aufrufs.
`--mode llm` misst nur den ersten Extraktionsaufruf (ohne Retry/Nachbearbeitung).

Ladeparameter = Produkt, unverändert (cv_llm_runtime.py:1133-1141, 856-874, 1254-1262): `n_ctx` 4096
(`resolve_cv_llm_n_ctx`), `n_threads`/`n_threads_batch` aus `resolve_cv_llm_thread_plan` (ThinkPad 6C/12T, SMT → reserve 0
→ **6/12**), `n_batch` 512, `use_mmap` True, `use_mlock` False, `verbose` False; Chat-Template aus dem GGUF mit
`{% set enable_thinking = false %}` (`core/local_chat_template.py`), `/no_think` im System-Prompt; Prefill in 512er-Blöcken
(`_prefill_prompt_blocks`), dann `create_chat_completion(stream=True, temperature=0.0, max_tokens=min(4096, n_ctx−prompt−8),
response_format={"type":"json_object"})` → JSON-Grammatik; Seed = llama-cpp-python-Default (bei greedy irrelevant).
Die Harness setzt nur die **produkteigenen** Env-Schalter (`KARRIEREKRAKE_CV_LLM_MODEL`, `…_N_THREADS[_BATCH]`,
`…_MAX_TOKENS`, `…_IMPORT_TIMEOUT_S`=7200, `KARRIEREKRAKE_MODELS_DIR`/`_DATA_DIR` = Sandbox im Ergebnisordner, damit
App-AppData/Lock unberührt bleiben), löscht andere `KARRIEREKRAKE_*` (protokolliert) und erzwingt den In-process-Transport
(`http_llm_available` → False). Beobachtungs-Hooks (nur Zeitstempel): `chat_completion_inprocess`, `completion_token_budget`,
`_prefill_prompt_blocks`, `_llama_cls` → `BenchLlama(Llama)`.

### Pro Lauf (1 Warm-up ungezählt + 3 Läufe pro CV pro Variante)
`wall_s` (Zeit pro CV), `ttft_s` (Aufrufbeginn inkl. Model-Load → erster Stream-Chunk) und `ttft_from_loaded_s`,
`load_s_total`, `pp_tok_s`/`tg_tok_s` (llama_perf_context – dieselbe Quelle wie `llm_step` des Produkts),
**`tg_tok_s_wall`** (Tokens / Wandzeit erster→letzter Chunk; enthält Grammatik-/Sampling-Zeit, die llama_perf nicht zählt),
`gen_tokens`, `n_prompt`, `max_tokens_budget`, `peak_rss_bytes` + `peak_private_bytes` (psutil-Poll 25 ms dieses Prozesses;
Windows: private = PagefileUsage, Linux: RssAnon), `peak_wset_lifetime_bytes`, Produkt-Zähler
`product_private_commit_high_water_bytes` und (Windows) `product_peak_job_memory_used_bytes` (Job-Lebensdauer!),
`cpu_cores_effective`, SHA-256 von Messages/Prompt-Token-IDs/Rohantwort, Korpus-Bewertung (`evaluate_doc` aus
`scripts/run_cv_corpus.py`, PASS/FAIL je Sektion).
### Pro Sitzung (`session.json`)
`repo_commit` (+ Quelle, Dirty-Liste, SHA-256 der Schlüsseldateien), System (CPU, Kerne/Threads, RAM, OS, Akku/AC,
`powercfg /getactivescheme`, Top-Prozesse CPU/RSS), llama-cpp-python-Version, **vendored llama.cpp-Commit**
(`ggml_commit()` aus ggml-base; erwartet `4df29be`), `llama_print_system_info()`, SHA-256 der DLLs, Paketversionen,
Modell-SHA-256, Sampling/Seed, exakte Kommandozeile + argv, alle Hooks, Env.

### Ausgabe-Layout (Vergleich durch den Personaler)
```
<out>/<label>/session.json
<out>/<label>/extracts/<CV-Stem>/{warmup1,run1,run2,run3}.parsed.json          # komplettes Extrakt, kanonisches JSON
<out>/<label>/extracts/<CV-Stem>/<tag>.call<k>.<primary_extract|focused_retry>.raw.txt   # LLM-Rohantwort byte-genau
<out>/<label>/extracts/<CV-Stem>/<tag>.error.json                              # nur bei Fehlschlag (Code, Detail)
<out>/<label>/extracts/<CV-Stem>/_messages.<sha16>.json                        # exakter Prompt (Messages)
```
`parsed.json` = Rückgabe von `import_cv_docpick`, `sort_keys`, UTF-8, LF; **normalisiert**: `source_path` → Dateiname,
`peak_rss_mb_at_end` entfernt (steht in `session.json` unter `volatile`). **Referenz-Extrakte** = Variante A
(`4b-q4km-baseline`, Q4_K_M, 0.3.35, Commit 47e8f83b) aus derselben Sitzung; die Personaler-Referenz (Q4_K_M, 0.3.35,
47e8f83b) lässt sich direkt als `<ref-dir>` angeben, wenn sie im selben Layout vorliegt; jede textverändernde Variante speichert alle
10 CVs × alle Läufe.
```
py thinkpad_cv_bench.py diff <ref-dir> <variant-dir> [--a-tag run1] [-v] [--json-out diff.json]
```
vergleicht pro CV/Lauf `parsed.json` byte-genau und bei Abweichung strukturell (JSON-Pfade), Rohantworten byte-genau
(erster Unterschied mit Kontext), warnt bei unterschiedlichem Repo-Commit / llama-cpp-python / Prompt-Messages.
Exit 0 = alles identisch. `--a-tag run1` = Referenzlauf 1 gegen jeden Lauf der Variante.

### Byte-Identitäts-Pflicht für Speculative (Kritiker, bindend)
```
py thinkpad_cv_bench.py run ... --seed 4294967295 --spec prompt-lookup --spec-baseline <8b-baseline-dir>   # automatisch am Ende
py thinkpad_cv_bench.py spec-check <8b-baseline-dir> <8b-spec-dir>                                        # nachträglich, Exit 4 bei Abweichung
```
Die 8B-Prompt-Lookup-Variante L läuft auf **allen 10 CVs**, Temperatur 0 (Produkt), **derselbe Seed wie die 8B-Baseline J**
(beide explizit `--seed 4294967295` = `LLAMA_DEFAULT_SEED`, d. h. Produktverhalten; `--seed` wird an `Llama(seed=…)` übergeben).
Geprüft wird pro CV und Lauf: `parsed.json` **und** jede Roh-LLM-Ausgabe (`callN.*.raw.txt`) byte-identisch zu J, dieselbe
Menge an LLM-Aufrufen, Temperatur 0 in allen Aufrufen beider Sitzungen, effektiver Seed gleich und eindeutig, gleicher
Commit/Modell-SHA/llama-cpp-python/max_tokens/Thinking; fehlende oder abgebrochene Spec-Läufe zählen als Abweichung.
Jede Abweichung → `session.json.spec_identity_check` und `diff`-Ausgabe tragen **„KV-rollback defect, not a speed gain, goes to
Personaler“**, `speed_gain_counted=false`; `summarize` meldet die Variante mit `!!` und schreibt in `summary.csv` die Spalten
`speed_gain_counted` und `spec_identity_cv` (`DEVIATION`/`identical`/`unchecked`). Ohne Prüfung gilt `unchecked` – auch
dann nicht als Geschwindigkeitsgewinn zählen. Box-Nachweis der Mechanik: 0.6B Baseline vs. Lookup (beide `--seed`),
`spec identity OK`; 4B-Lookup-Sitzungen der Box sind als Defekt markiert (Abbruch).

## Varianten auf 0.3.35 – was geht, was nicht
| ID | Variante | Schalter | Auf 0.3.35 möglich? |
|---|---|---|---|
| A | Baseline Q4_K_M, Threads-Plan (6/12) | – | ja, = Produkt |
| B | 6 physische Threads (6/6) | `--threads 6 --threads-batch 6` | ja, über Produkt-Env `KARRIEREKRAKE_CV_LLM_N_THREADS[_BATCH]` |
| C | Speculative | `--spec prompt-lookup` | **Draft-Modell (zweites GGUF, z. B. 0.8B/0.6B): NEIN.** 0.3.35 hat nur die abstrakte Schnittstelle `LlamaDraftModel` und als einzige Implementierung `LlamaPromptLookupDecoding` (n-gram aus Prompt/Kontext); `Llama(draft_model=…)` nimmt nur solche Objekte. Eine Zweitmodell-Speculation gibt es nur in llama-server (`-md`), nicht in llama-cpp-python. **Prompt-Lookup auf Qwen3.5-4B: läuft NICHT.** Box-Smoke: (1) ohne explizites `logits_all=True` → `ValueError` im 2. Prefill-Block (0.3.35-Bug: `draft_model` setzt intern `_logits_all=True`, `scores` wird aber nach dem Argument mit nur `n_batch` Zeilen angelegt, llama.py:351/484) – betrifft jeden Prompt > 512 Tokens, also jeden CV; (2) mit `logits_all=True` (Harness-Default) → `llama_decode returned -1` nach dem 3. Draft (Qwen3.5 ist hybrid/rekurrent; verworfene Draft-Tokens erfordern partielles `kv_cache_seq_rm`, das der rekurrente Teil nicht kann). Auf dem **nicht-hybriden Qwen3** (Box: Qwen3-0.6B) funktioniert es, Ausgabe byte-identisch, aber **langsamer** (Wand 50,3 s statt 36,1 s; Prefill 98 statt 277 tok/s wegen `logits_all`-Kopien; Peak-RSS 3,45 statt 1,45 GB). Logits-Puffer `n_ctx × n_vocab × 4 B` (4B: 4096 × 248320 → 4,07 GB virtuell; 8B: 4096 × 151936 → 2,49 GB). In der Matrix daher C nur als 1-Lauf-Check auf DE_01, L = 8B Q4_K_M mit Prompt-Lookup. |
| D | Prompt-/Prefix-Cache | `--prefix-cache ram` | ja, nur **in-process** `LlamaRAMCache` (Zustand am Ende von „## Document Text\n“ = Template+System+Schema, 1347 Tokens, `llama_state_size` 96,9 MB). Disk-Cache (`LlamaDiskCache`) verboten (`core/security/diskcache_guard.py`). Box: TTFT 29–30 s → 7,4–10,6 s, Restore 1,2 s, Extrakte byte-identisch zur Baseline (DE_01, EN_05). Kosten: Private Bytes stiegen über 4 Läufe 2,63 → 4,06 GB (Baseline 2,0 GB) – Ursache UNSICHER (`LlamaState` kopiert u. a. `scores` n_batch × n_vocab × 4 B ≈ 0,5 GB; mögliches Festhalten alter Zustände). Produktbezug UNSICHER: App startet pro Import ein neues Kind und lädt das Modell pro LLM-Aufruf → Cache wirkt nur mit langlebigem Worker (gibt es nicht). Retry-Aufruf hat anderen System-Prompt → kein Treffer. `pp_tok_s` (llama_perf) zählt hier nur die Tokens nach dem Restore → `pp_tok_s_wall` verwenden. |
| E | Modelltausch Q4_0 | `--model …Q4_0.gguf` | ja |
| F | Produkt-4B GSQ Q2_K_XL | `--model …Q2_K_XL.gguf` | ja (Katalog `qwen3.5-4b-gsq`) |
| G | max_tokens-Deckel 1024 | `--max-tokens 1024` | ja (Produkt-Env). Kein Geschwindigkeitshebel, solange die Antwort kürzer ist (Stopp bei EOS); längere Antwort → `llm_output_truncated` (wie Produkt, als Fehlschlag gezählt). |
| H | Thinking an (Vergleich) | `--thinking on` | technisch ja (`enable_thinking=true`; `/no_think` bleibt in den Messages), **aber wirkungslos**: Produkt hat Thinking schon aus, und die JSON-Grammatik (`response_format=json_object`) erzwingt ab dem ersten Token `{` – es entsteht kein `<think>`-Block. Box: Prompt 1761 statt 1763 Tokens, 656 statt 655 Gen-Tokens, Extrakt identisch, Rohtext minimal anders. |
| I–K | 8B GSQ Q3_K_M / Q4_K_M / Q4_0 | `-With8B` | ja (Qwen3-Template hat `enable_thinking`) |
| L | 8B Q4_K_M + Prompt-Lookup | `-With8B` (auch in `-Preset short`) | ja (nicht-hybrid); alle 10 CVs, gleicher Seed wie J, `--spec-baseline` J → Byte-Identitätsprüfung (Extrakte + Rohausgaben); Abweichung = „KV-rollback defect, not a speed gain, goes to Personaler“ |

Textverändernd (Extrakte immer gegen A diffen): C, D, E, F, G (bei Abbruch), H, I–L; B kann durch andere
Reduktionsreihenfolge minimal abweichen. `diff` beendet mit 0 nur, wenn alle gemeinsamen `parsed.json` byte-identisch sind;
Rohtext-Abweichungen werden angezeigt (`raw [≠]`), CVs ohne Gegenstück nur als Warnung.

## Windows-Installation (Python 3.12, llama-cpp-python==0.3.35)
Geprüft gegen `scripts/build_native_llama.py`: das Skript baut nur macOS/Linux aus dem sdist
(`SOURCE_SHA256 1139dbb5…de12`); sein Docstring sagt „Windows continues using its pinned wheel“, und
`constraints-runtime.txt` nennt genau dieses Wheel für die Windows-EXE.
* Wheel: `https://github.com/abetlen/llama-cpp-python/releases/download/v0.3.35/llama_cpp_python-0.3.35-py3-none-win_amd64.whl`
  — 7 086 788 B, **SHA-256 `31590ea000d5aff6f05f1e428048e72318a83709288159a5bd4dabec530080bb`**
  (GitHub-Asset-Digest, auf der Box nachgerechnet). Index: `https://abetlen.github.io/llama-cpp-python/whl/cpu`.
  Vendored llama.cpp `4df29be4f4c3673f428170fda944a5b19f743bb8`. `py3-none` → passt zu Python 3.12.
```
$K="$env:USERPROFILE\kk-speedtest"
Expand-Archive .\kk-speed-bundle.zip -DestinationPath $K            # -> $K\cvbench\...
Expand-Archive $K\cvbench\kk-repo-47e8f83b.zip -DestinationPath $K\repo-47e8f83b
py -3.12 -m venv $K\venv-cv035
$PY="$K\venv-cv035\Scripts\python.exe"
& $PY -m pip install --upgrade pip
& $PY $K\cvbench\fetch_models.py --dest $K\wheels --ids llama-cpp-python-0.3.35-win_amd64     # prüft Größe+SHA-256
& $PY -m pip install --no-deps $K\wheels\llama_cpp_python-0.3.35-py3-none-win_amd64.whl
& $PY -m pip install -c $K\repo-47e8f83b\constraints-runtime.txt numpy diskcache jinja2 MarkupSafe psutil pypdf python-docx httpx pydantic docpick==0.1.3
& $PY -c "import llama_cpp; print(llama_cpp.__version__, llama_cpp.llama_print_system_info())"
& $PY $K\cvbench\fetch_models.py --dest $K\models --ids 4b-Q4_K_M,4b-Q4_0,4b-product-Q2_K_XL   # + 8b-product-Q3_K_M,8b-Q4_K_M,8b-Q4_0 für -With8B
& $PY $K\cvbench\thinkpad_cv_bench.py sysinfo
# Pre-flight (macht run_cv_matrix.ps1 vor jeder Variante selbst; hier zur Kontrolle von Hand):
Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^(python|pythonw|py|llama-server|llama-cli|llama-bench|Karrierekrake)' } | Select ProcessId,Name,CommandLine
#   -> muss LEER sein (läuft noch ein Brief-Lauf, erst beenden lassen). Die Harness prüft zusätzlich selbst
#      (thinkpad_cv_bench.py --preflight auto = auf Windows aktiv, Abbruch mit Liste der Prozesse).
# Energiezustand (nur lesen; das Skript ändert den Energieplan NIE). Erwartet für diese Sitzung: Netzteil an,
# Schema 381b4222-f694-41f0-9685-ff5bb260df2e 'Ausbalanciert' (Stand 19.10.). Vorher selbst prüfen:
powercfg /getactivescheme
& $PY $K\cvbench\thinkpad_cv_bench.py power-snapshot --out $env:TEMP\power_now.json    # Exit 5 = kein Netzteil / Schema unlesbar
powershell -ExecutionPolicy Bypass -File $K\cvbench\run_cv_matrix.ps1 -K $K -Preset short          # Kurzmatrix A,B,D,E,F,G
powershell -ExecutionPolicy Bypass -File $K\cvbench\run_cv_matrix.ps1 -K $K -Preset short -With8B  # + J (8B Q4_K_M) + L (8B Lookup)
powershell -ExecutionPolicy Bypass -File $K\cvbench\run_cv_matrix.ps1 -K $K                 # volle Matrix A–H (+ -With8B)
powershell -ExecutionPolicy Bypass -File $K\cvbench\run_cv_matrix.ps1 -K $K -PeakRaw         # Schritt P (getrennt)
```
Minimal-Paketsatz auf der Box geprüft (frisches venv, Python 3.12, manylinux-Wheel 0.3.35 + obige Pakete mit
Constraints): `import_cv_docpick` läuft durch, Prompt-SHA-256 für DE_01 identisch zum Dev-venv
(`2a3b9ace…fdce`). Alternative mit exakt dem EXE-Paketbaum:
`pip install -c constraints-runtime.txt -r requirements-runtime.txt` (größer; PySide6, Playwright-Paket).
`docpick` ist in `constraints-runtime.txt` **nicht** gepinnt → hier `==0.1.3` (neueste PyPI-Version, = Box). Die Harness
speichert Messages-/Prompt-SHA-256; `diff` warnt bei abweichendem Prompt.
**Fallback nur wenn das Wheel nicht installierbar ist** (nicht produktgleich, Zahlen getrennt kennzeichnen):
VS 2022 Build Tools (C++), CMake ≥ 3.21, dann sdist (`fetch_models.py --ids llama-cpp-python-0.3.35-sdist`,
SHA-256 `1139dbb5…de12`) mit `set CMAKE_ARGS=-DGGML_NATIVE=OFF -DGGML_AVX2=ON -DGGML_CPU_ALL_VARIANTS=OFF -DGGML_BACKEND_DL=OFF`
und `pip install --no-binary llama-cpp-python <sdist>`.

## Laufzeit-Schätzung ThinkPad
Box-Baseline DE_01: ≈ 1 763 Prompt-Tokens, ≈ 655 Gen-Tokens, ≈ 2,4 min/CV. Auf dem Ryzen 5 PRO 4650U grob 1,5–3 min/CV →
pro Variante 10 CVs × 4 Läufe ≈ **60–120 min**; Matrix A–H + Baseline-Ende ≈ 9–18 h. Kürzen: `-Runs 2`, `-Cvs DE_01,EN_05`,
`-Only A,B,C,D,E`. Netzbetrieb, Energiesparmodus aus, andere Apps zu (wird protokolliert).

### Kurzmatrix `-Preset short` (je 10 CVs × (1 Warm-up + 3 Läufe) = 40 Imports pro Variante, kein Baseline-Ende)
Grundlage: Box DE_01 Q4_K_M ≈ 2,0–2,1 min/CV (8 vCPU Xeon, 7 Threads, geteilt). Für den Ryzen 5 PRO 4650U (6C/12T,
DDR4) gibt es **keine eigene Messung** – die Spannen sind Schätzungen, nicht Messungen:
| Variante | min/CV (Schätzung) | pro Variante |
|---|---|---|
| A Baseline 4B Q4_K_M | 1,5–3 | 60–120 min |
| B Threads 6/6 | 1,5–3 (±10 % zu A) | 60–130 min |
| D Prompt-Cache RAM | 1,2–2,6 (Box: −15 %) | 50–105 min |
| E Q4_0 | 1,4–3 | 55–120 min |
| F Q2_K_XL (Produkt-GSQ) | 1,8–3,6 (Box: +15 %, langsames Prefill) | 70–145 min |
| G Thinking aus + max_tokens 1024 | wie A (Ausgaben ≈ 570–660 Tokens < 1024) | 60–120 min |
| **Summe 4B (A,B,D,E,F,G)** | | **≈ 6–12 h** |
| J 8B Q4_K_M | 3–6 (≈ 2× 4B, bandbreitenlimitiert) | 120–240 min |
| L 8B Q4_K_M + Prompt-Lookup | 3–8 (Box 0.6B: +40–65 % langsamer wegen `logits_all`; auf 8B unbekannt) | 120–320 min |
| **Summe mit `-With8B`** | | **≈ 10–21 h** |
Ehrliche Einordnung: die untere Grenze setzt voraus, dass der Ryzen pro Thread etwa Box-Niveau erreicht und nicht
thermisch drosselt; wenn das Notebook drosselt oder im Akku-/Ausgewogen-Profil läuft, eher obere Grenze oder darüber.
Pragmatisch auf zwei Nächte aufteilen: Nacht 1 `-Preset short`, Nacht 2 `-Only J,L -With8B`. Schneller Plausibilitäts-
Lauf vorab: `-Only A -Cvs DE_01 -Runs 1` (≈ 5 min) und die Zeit pro CV mit der Tabelle oben hochrechnen.

## Schritt P – Roh-Peak über `scripts/run_i3_peak_job_benchmark.py` (getrennt, **nicht i3-Nachweis**)
Label überall: **„ThinkPad, speed/peak raw data, not i3 evidence“**. `thinkpad_peak_raw.py` ruft pro CV
`python scripts/run_i3_peak_job_benchmark.py --cv <CV> --timeout 3600 --json-out <out>` im Repo-Snapshot auf
(volle Job-Kette: Windows Job Object → `python -m desktop.cv_import_child` → `import_cv` → `import_cv_docpick`,
`PeakJobMemoryUsed`). Produkt-`n_ctx` (4096) und Produkt-Thread-Plan (keine `N_CTX`/`N_THREADS`/`MAX_TOKENS`/
`IMPORT_TIMEOUT`-Env), llama-cpp-python 0.3.35 (geprüft), Q4_K_M (SHA-256 geprüft).
**Nie** `--attest-physical-i3`, **nie** `--enforce-limit`; `KARRIEREKRAKE_PHYSICAL_I3_8GB` wird aus der Umgebung entfernt;
das Skript schreibt nur in `--out` (kein `PEAK_ATTESTATION`-Eintrag). **Achtung, neu in 47e8f83b:** `guenther/setup_models.py` enthält jetzt
`PEAK_ATTESTATION` (alle Modelle `None`), das Format eines Eintrags verweist auf `--attest-physical-i3`. Schritt P liest
diese Datei nicht und schreibt sie nie; Wächter: SHA-256 von `guenther/setup_models.py` vor dem ersten und nach jedem CV,
jede Änderung bricht ab (`peak_raw_session.json.peak_attestation_file`). Rohwerte dieses Schritts dürfen nie in
`PEAK_ATTESTATION` übernommen werden (ThinkPad ≠ physischer i3, kein `ship_evidence`).
und verwirft die Ausgabe, falls das Repo-Skript `ship_evidence=true` meldet. `hard_fail`/`limit_bytes` werden nur als
`…_reference_only` übernommen; Exit-Code 2 des Repo-Skripts heißt nur „über 3,3 GB“, nicht „i3 fällt durch“.
Ergebnis: `results-peak-raw-not-i3-evidence\peak_raw_session.json` (`max_peak_bytes`, pro CV `peak_bytes`, `method`,
`llm_step`, System/llama-Info, Commit) + Original-Report des Repo-Skripts je CV.
```
powershell -ExecutionPolicy Bypass -File $K\cvbench\run_cv_matrix.ps1 -K $K -PeakRaw
#  = & $PY $K\cvbench\thinkpad_peak_raw.py --repo $K\repo-47e8f83b --repo-commit 47e8f83b08a1925579891abbc861b68a284a66a8 `
#        --model $K\models\Qwen3.5-4B-Q4_K_M.gguf --expect-model-sha256 00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4 `
#        --out $K\results-peak-raw-not-i3-evidence        [--cvs DE_01]
```
Box-Smoke (Linux-Scaffold `process_group_vmrss`, enthält mmap-Seiten, daher nicht mit Windows `PeakJobMemoryUsed`
vergleichbar): DE_01 import ok, Peak 4 775 641 088 B, `ship_evidence=false`, 126 s, Threads 7 (Box-Plan).

## Commit 8fca79b5 → 47e8f83b: Unterschiede im CV-Import-Pfad
144 Commits, 194 geänderte Dateien; im Snapshot-Umfang geändert: `core/cover_guard.py`, `core/cover_quality.py`,
`core/security/jobspy_runtime.py`, `desktop/{app,i18n,theme}.py`, `desktop/widgets/{apply_preview_dialog,model_fit,
model_setup_panel}.py`, `desktop/wizard/__init__.py`, `guenther/{device_check,model_budgets,setup_models}.py`.
**Byte-identisch** (SHA-256 verglichen): `core/cv_llm_runtime.py`, `core/cv_docpick_import.py`, `core/cv_parser.py`,
`core/cv_intelligence.py`, `core/local_chat_template.py`, `desktop/cv_import_child.py`, `guenther/runtime/llama_cpp_provider.py`,
`guenther/model_manager.py`, `guenther/validation.py`, `core/security/diskcache_guard.py`, `core/hardware_peak_gate.py`,
`devops/peak_rss_harness.py`, `devops/win_job_object.py`, `scripts/run_i3_peak_job_benchmark.py`, `scripts/run_cv_corpus.py`,
`constraints-runtime.txt`, `requirements-runtime.txt`, `tests/fixtures/cv_corpus/expected_results.json`.
Einzige Berührung: `resolve_cv_model_path()` importiert `guenther.setup_models.selected_model_id/selected_model_path`
(Datei geändert: Katalog nutzt `model_budgets`, neu `PEAK_ATTESTATION`/`peak_unverified`). Erreicht wird das nur, wenn
`KARRIEREKRAKE_CV_LLM_MODEL` fehlt oder auf keine Datei zeigt – Harness und Schritt P setzen es immer auf das GGUF, also
nicht im Messpfad. Box-Smoke DE_01 @ 47e8f83b: Messages-SHA `2a3b9ace…`, Prompt-IDs-SHA `a1806d3b…`, 1763 Prompt-Tokens,
655 Gen-Tokens, Roh-SHA `6371aa99…`, `parsed.json` `e2ba56bd…` – **alle gleich wie @ 8fca79b5**, `diff` Warm-up + Lauf
IDENTICAL, raw `=` (nur Warnung „repo commits differ“).

## Box-Smoke (Xeon-VM, 8 vCPU, geteilt mit anderen Agenten-Prozessen – **keine Zielzahlen**), 4B Q4_K_M, 0.3.35
Neu @ 47e8f83b (19.10.): Schritt P aus dem entpackten Bundle (`box-peak-raw-47e8f83b-not-i3-evidence`, DE_01): Peak 4 774 830 080 B, import ok, `ship_evidence=false`, `setup_models.py`-SHA vorher = nachher. `box-4b-q4km-baseline-47e8f83b` DE_01 1 WU + 1: 125,8 / 127,3 s, TTFT 32,8 / 32,0 s, pp 59,3–59,7,
tg 10,0–10,5 (Wand 6,9–7,1) tok/s, Peak RSS 4,47 GB / Private 2,03 GB, Korpus PASS, Extrakt/Roh byte-gleich zu 8fca79b5
(≈ 6 % langsamer = Box-Rauschen, geteilte VM). `box-qwen3-0.6b-seed-{base,spec}-47e8f83b`: `--seed` + `--spec-baseline`
Ende-zu-Ende, spec identity OK, Lookup 65,8 s vs. 39,4 s ohne.
Die Tabelle unten stammt von Commit 8fca79b5 (CV-Pfad byte-identisch, s. o.):
| Variante | CVs × Läufe | Wand/CV (Median) | TTFT | pp tok/s | tg tok/s (perf / Wand) | Peak RSS / Private | Extrakt vs. Baseline |
|---|---|---|---|---|---|---|---|
| Baseline (Plan 7/7) | DE_01, EN_05 × (1 WU + 1) | 111,9 s (DE_01 120,5 / EN_05 103,4) | 29,0 s | 62,7 | 11,0 / 7,4 | 4,81 / 2,04 GB | Referenz; WU = Lauf byte-gleich; Korpus PASS |
| Prefix-Cache RAM | DE_01, EN_05 × (1 WU + 1) | 94,3 s | 9,1 s | 261 (Wand, inkl. Restore) | 10,6 / 7,2 | 6,74 / 4,06 GB | identisch (2/2) |
| Threads 4/4 | DE_01 × 1 | 191,6 s | 49,6 s | 37,8 | 5,8 / 4,6 | 4,77 / 2,00 GB | identisch |
| Prompt-Lookup | DE_01 × 1 | Abbruch 43,8 s | – | – | – | 6,95 / 4,61 GB | `llama_decode returned -1` |
| Prompt-Lookup ohne logits_all | DE_01 × 1 | Abbruch 27,2 s | – | – | – | 6,06 / 3,29 GB | `ValueError` (0.3.35-Bug) |
| max_tokens 300 | DE_01 × 1 | Abbruch 72 s | 31,5 s | – | – | – | `llm_output_truncated` (wie Produkt) |
| Thinking an | DE_01 × 1 | 123,3 s | 31,2 s | 61,7 | 10,5 | 4,44 GB RSS | identisch (Rohtext ≠) |
| Q2_K_XL (GSQ) | DE_01 × 1 | 139,3 s | 54,2 s | 33,1 | 11,9 / 7,8 | 2,61 / 0,65 GB | identisch (Rohtext ≠) |
| Qwen3-0.6B Baseline / + Prompt-Lookup (Mechanik-Test, nicht-hybrid) | DE_01 × 1 | 36,1 / 50,3 s | 7,4 / 9,9 s | 277 / 98 | Wand 19,0 / 13,5 | 1,45 / 3,45 GB RSS | byte-identisch |
Wichtig für die Auswertung: llama_perf-tg (`tg_tok_s`) enthält **keine** Grammatik-/Sampling-Zeit; die Wandrate
(`tg_tok_s_wall`, Tokens / erster→letzter Chunk) lag auf der Box ≈ 30 % darunter – beide Werte berichten.
Alle Smoke-Sitzungen: `smoke_cv/<label>/session.json`, Extrakte, `diff_vs_*.txt/json`, `summary.txt/csv`.

## Energiezustand pro Sitzung (Kritiker, bindend)
Aufgezeichnet werden **aktives Energieschema (GUID + Name, `powercfg /getactivescheme`, OEM-Codepage; dazu Win-11-Energiemodus
`powercfg /getactiveoverlayscheme` als `overlay_guid`)** und
**Netzteil/Akku (`GetSystemPowerStatus`: ACLineStatus, Akku-%)**:
* Sitzungsstart: `run_cv_matrix.ps1` → `thinkpad_cv_bench.py power-snapshot --out results-cv\power_ref.json`
  (Referenz). Kein Netzteil oder Schema unlesbar → Abbruch vor der ersten Variante (Exit 5).
* Vor und nach jeder Variante: `power-check --ref power_ref.json --log power_log.jsonl --where "before/after <label>"`.
* In der Harness (`run --power-ref power_ref.json`): Stichprobe bei Variantenstart, **vor jedem CV** und bei
  Variantenende; alles in `session.json.power.samples`.
Verglichen werden Schema-GUID, Schema-Name und AC-Status mit dem Sitzungsstart; zusätzlich muss AC = verbunden sein.
Akku-% allein wird nur protokolliert (darf am Netzteil schwanken). Bei jeder Abweichung: `power_state_consistent=false`
in `session.json` (+ `aborted`), restliche CVs der Variante werden nicht mehr gemessen, Harness-Exit 5, das Matrix-Skript
bricht alle weiteren Varianten ab, schreibt `results-cv\SESSION_INVALID.txt` („SESSION DOES NOT COUNT …“), erstellt
trotzdem `summary.txt/csv` (zur Diagnose) und endet mit Exit 5. `summarize` meldet `!! <label>: power_state_consistent=False`
und schreibt die Spalten `power_state_consistent`, `power_scheme`, `power_ac_online`; liegt `SESSION_INVALID.txt` im
Ergebnisordner oder unterscheidet sich die Referenz (GUID/Name/AC) zwischen den zusammengefassten Sitzungen, steht
überall `False`. Danach Ausgangszustand von Hand wiederherstellen und eine **neue** Sitzung starten (alter Ordner
`results-cv` umbenennen). `--power-check auto` = auf Windows erzwungen, auf Linux nur protokolliert (Box: kein
Energieschema/Akku → `power_state_consistent=null`). Schritt P protokolliert Start/Ende ebenso
(`results-peak-raw-not-i3-evidence\power_ref.json`, `power_log.jsonl`).

## Offene Punkte (UNSICHER)
* Energiezustand: `powercfg`-Parsing (DE/EN getestet per Unit-Test, echte Ausgabe auf dem ThinkPad nicht gesehen) und
  `GetSystemPowerStatus` sind Windows-seitig ungetestet. Ein Wechsel zwischen zwei Stichproben (z. B. während eines CVs
  kurz Akku, dann wieder Netz) wird nicht erkannt; Stichprobe ist pro CV, nicht kontinuierlich. Der Windows-11-
  „Energiemodus“-Schieber wird über `powercfg /getactiveoverlayscheme` mitgeprüft (`overlay_guid`; auf Builds ohne diesen
  Schalter `null`, dann unerkannt). Herstellerprofile (Lenovo Vantage „Intelligent Cooling“/Leistungsmodus) werden nicht
  erfasst – vor dem Start von Hand festhalten.
* Windows-Pfad der Harness nicht ausgeführt (Box = Linux): `psutil` private/peak_wset, `powercfg`, Win32_Battery-Abfrage,
  Job-Object-Zähler und `ggml_commit()` per ctypes aus `ggml-base.dll` sind Windows-seitig ungetestet.
* Box-llama-cpp-python ist ein lokaler Build (`ggml_commit` = `4df29be-dirty`), nicht das Windows-Wheel; Box-Zahlen sind
  daher auch build-seitig nicht übertragbar.
* `docpick` ist in `constraints-runtime.txt` nicht gepinnt (hier `==0.1.3`); welche Version die EXE bündelt, ist nicht geprüft.
  Absicherung: Messages-/Prompt-SHA-256 je Aufruf (DE_01: `2a3b9ace…`), `diff` warnt bei Abweichung.
* In-process-Messung ≠ App-Import-Kind: Prozessstart/Imports des Kinds nicht in `wall_s` (Schritt P misst das Kind).
* Prefix-Cache: steigende Private Bytes (2,6 → 4,1 GB über 4 Läufe), Ursache offen; Produktbezug nur mit langlebigem Worker.
* Speculative auf 8B (L) nur auf der Box mit 0.6B mechanisch geprüft; ob es auf dem Ryzen schneller ist, offen (Box: langsamer).
* Ob Prompt-Lookup auf Qwen3.5 mit einem anderen llama-cpp-python (> 0.3.35) liefe, nicht geprüft (Pin verbietet es).
* Windows PowerShell 5.1: Matrix-Skript nutzt `$ErrorActionPreference="Continue"`, Exit-Codes der Läufe werden nicht
  ausgewertet (Fehlschläge stehen in `session.json`).
* Laufzeit auf dem ThinkPad nur geschätzt (≈ 60–120 min/Variante; Kurzmatrix 6–12 h, mit 8B 10–21 h).
* Personaler-Referenz @ 47e8f83b: Layout/Venv/Wheel der Personaler-Extrakte nicht gesehen; `diff` prüft Commit und
  llama-Version nur, wenn dort eine `session.json` liegt – sonst manuell sicherstellen (0.3.35-Wheel, gleicher Commit,
  gleiches Q4_K_M `00fe7986…`, Normalisierung `source_path`/`peak_rss_mb_at_end` wie hier).
* Die Smoke-Tabelle (8fca79b5) wurde nicht auf 47e8f83b wiederholt; nur Baseline DE_01 + 0.6B-Mechanik. CV-Pfad-Dateien
  sind byte-identisch, Abhängigkeit über `guenther.setup_models` nur außerhalb des Messpfads.
* Byte-Identität bei Prompt-Lookup auf 8B ist nicht garantiert: Verifikations-Batches rechnen mit anderer Batchgröße
  als Einzeltoken-Decoding; numerisch abweichende Logits können bei knappen Greedy-Entscheidungen andere Tokens geben
  (dann wird es korrekt als Defekt markiert, auch wenn die Ursache Rechenreihenfolge statt KV-Rollback ist).

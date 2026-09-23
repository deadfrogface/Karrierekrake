# OSS CV-Parser Replacement — Requirements & Candidate Audit

**Branch:** `cursor/cv-parser-oss-replace-d85b`  
**Base:** `cursor/cv-parser-smartresume-de-en` @ `28e459a` (DET productive)  
**Scope:** DE/EN document language only. Other languages as *skills* in CV OK.

## 1. Karrierekrake import fields (actual)

From productive `import_cv` / Scorer V2 `SCHEMA_MAPPING`:

| Field group | Required keys |
|-------------|---------------|
| Personal | `first_name`, `last_name`, `date_of_birth` |
| Contact | `emails[0]`, `phones[0]` |
| Address | `street`, `house_number`, `postal_code`, `city`, `country` |
| Languages | list of `{language, level}` pairs |
| Licenses | driving licence classes |
| Education | `institution`, `qualification`, `start_date`, `end_date` |
| Employment | `company`/`title`, dates, optional duties |
| Skills / Software / Certificates | string lists |
| Target role | optional (class B) |

## 2. Operating constraints

| Constraint | Source | Value |
|------------|--------|-------|
| Offline / no CV cloud API | product + prior audit | mandatory |
| Hardware | PHASE0 baseline | 15 GiB RAM, no CUDA |
| License | redistribution | Apache-2.0 / MIT / BSD-compatible; **no GPL-3 viral** |
| Latency SLA | project docs | **not specified** (measure & report) |
| Quality gate (pre-declared) | prior smoke + this run | F1 ≥ 0.90, hallu ≤ 0.03, invented emp/edu = 0, 100% process success |

## 3. Candidate table (code/license inspected; README ≠ test)

| Candidate | License | Fields vs need | Code locus | Prior / new blockers | Decision |
|-----------|---------|----------------|------------|----------------------|----------|
| **SmartResume** | Apache-2.0 code + Qwen3-0.6B Apache-2.0 | basic_info / work / education (+ spike schema covers most) | `smartresume/`, HF `Alibaba-EI/SmartResume` | Smoke FAIL section-acc **0.7284** (≠ F1); Chinese-centric prompts; ~87 s/CV | **Supplement** (LLM extract) behind Docling — retry only with Docling text as concrete layout fix |
| **Docling** | MIT (+ model pkgs) | layout/OCR text only — **no CV schema** | `docling` PyPI | Was blocked: `AutoImageProcessor` via **torch/torchvision ABI mismatch** (`torchvision::nms`). **Fix verified:** reinstall matching torchvision → convert works | **Main frontend** |
| **oksomu/resume-ner** | Apache-2.0 | NER labels: NAME…LANGUAGE — **no address split, no DOB, no licence**; **EN-only** | HF model | `token_type_ids` TypeError on DistilBERT. **Fix verified:** drop `token_type_ids` before forward. DE spans garbled | **Not primary** (EN-only); optional EN NER note only |
| **somus/resume-extract** | MIT (README/package; no LICENSE file in clone) | structured personal/experience/education/skills via oksomu | TypeScript/Bun + ONNX | Depends on EN-only NER; Node/Bun stack | Reject as primary (lang + stack) |
| **Tanya Resume-Parser** | MIT | training/eval reference | repo | Small set / overfit risk (prior audit) | Reference only |
| **pyresparser** | **GPL-3.0** | name/email/skills/degree — incomplete schema; EN spaCy | `pyresparser/` | GPL incompatible with proprietary ship without viral copyleft | **Reject (license)** |
| **brijkpatel ResumeParser** | MIT (`pyproject.toml`; no LICENSE file) | 19 fields incl. languages | `src/framework/` | Default strategies use **Gemini cloud** (`GEMINI_API_KEY`) for work/edu/languages — forbidden for CV-PII offline | **Reject (cloud LLM dependency)** |

## 4. Chosen architecture (one main + ≤2 supplements)

1. **Main:** Docling PDF → markdown/text (local, offline)  
2. **Supplement A:** SmartResume Qwen3-0.6B local extract → full schema JSON  
3. **Own code:** adapter + evidence filter + Scorer-V2 mapping only (no new DET rule farm)

oksomu not wired into this prototype (EN-only; schema gaps). Documented as available after `token_type_ids` fix if a future EN-only path is needed.

## 5. Pre-locked evaluation sample

Reuse `SMOKE_DE_EN_10_V1` (5 DE + 5 EN fixtures) — locked before this scoring run.  
Scorer: `holdout_scorer_v2.py` **unchanged**. GT: `tests/fixtures/cv_corpus/expected_results.json` **unchanged**.

**Note:** Fixture GT uses `education_count`/`work_count` rather than full entry lists for some docs; Scorer V2 still evaluates available evidenced fields. This is a **known-corpus** gate, not an independent blind proof.

## 6. Success / failure rule

- Gate pass → integrate, archive DET, remove productive DET path, request new blind DE/EN set for 0.99.  
- Gate fail → **„DET-Ersatz noch nicht erreicht; DET läuft vorübergehend weiter.“** Max one correction round after first full test.

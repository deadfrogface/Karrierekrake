"""Build the fixed synthetic cover-letter prompts for the ThinkPad speed test.

Runs on the box (Linux) against a Karrierekrake checkout. It only imports repo
code and the gold fixtures; it loads no model weights (the chat template is read
from the GGUF header). Output is a self-contained bundle that the Windows
harness reads; the harness never imports repo code.

Prompt = exactly what guenther.service.GuentherService._generate_validated +
guenther.runtime.llama_cpp_provider.LlamaCppProvider.generate would send for the
"writing" pipeline:
  stage draft_legacy : quality_loop mode "old"   (one call, max_tokens 900)
  stage plan         : first call of default mode "plan_draft" (max_tokens 768)
The DRAFT-after-PLAN call depends on the plan output and is therefore NOT a
fixed prompt; it is not generated here.

NOTE: on this branch the product cover letter is the template
(core/cover_letter.py compose_cover_letter); suggest_writing is not called by
the app. These prompts measure the LLM writing pipeline that exists in guenther/.

Usage (box):
  cd <repo> && HOME=/tmp/kkh XDG_CONFIG_HOME=/tmp/kkh/.config QT_QPA_PLATFORM=offscreen \
    <KK_VENV>/bin/python <KK_SPEED_PREP_DIR>/build_kk_prompts.py \
      --repo . --out <KK_SPEED_PREP_DIR>/prompts \
      --template qwen35=<MODELS_DIR>/Qwen3.5-4B-Q2_K_XL.gguf \
      --template qwen3=https://huggingface.co/ISTA-DASLab/Qwen3-8B-GGUF-GSQ/resolve/5605b36840bc26d62b34a6adb518109f55c412d2/qwen3-8b-Q3_K_M.gguf
  Options: --cases cl-01,cl-14 (default: all fixtures) --cache-set cl-01:cl-01,cl-14,cl-20
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from gguf_vocab_check import meta  # noqa: E402  (stdlib GGUF header reader)

TOKEN_BUDGET = {"writing": 900, "writing_plan": 768}   # guenther/service.py:182-194
TEMPERATURE = 0.2                                        # guenther/service.py:640


def sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def load_gold(repo: Path):
    path = repo / "tests" / "test_cover_letter_gold.py"
    spec = importlib.util.spec_from_file_location("kk_gold", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def job_text_of(job: dict) -> str:
    # Benchmark convention (no product caller exists): title, company, ad text.
    return f"{job.get('title') or ''}\n{job.get('company') or ''}\n{job.get('description') or ''}"


def provider_messages(system: str, trusted: str, untrusted: str) -> list[dict]:
    # guenther/runtime/llama_cpp_provider.py:173-182
    return [
        {"role": "system", "content": (system or "").rstrip() + "\n/no_think"},
        {"role": "user", "content": f"{trusted}\n\n{untrusted}\n\nAntworte nur mit einem JSON-Objekt. /no_think"},
    ]


def stage_messages(stage: str, profile_text: str, job_text: str, company: str | None):
    from guenther.prompts import SCHEMA_HINTS, SYSTEM_WRITE, build_layers
    from guenther.intelligence.evidence import build_evidence_store
    from guenther.intelligence.quality_loop import state_machine as sm

    lang = sm.infer_letter_language(profile_text=profile_text, job_text=job_text)
    if stage == "draft_legacy":          # state_machine.py:191-199
        schema, task = "writing", sm._draft_task_legacy(lang)
        trusted = sm._legacy_trusted(profile_text, "", company, None)
        untrusted = f"JOB:\n{job_text[:8000]}"
    elif stage == "plan":                # state_machine.py:237-244
        schema, task = "writing_plan", sm._plan_task()
        store = build_evidence_store(profile_text=profile_text, existing_evidence=[])
        trusted = sm._plan_trusted(profile_text, store, company, None, "", None)
        untrusted = f"JOB:\n{job_text[:8000]}"
    else:
        raise ValueError(stage)
    system, tb, ub = build_layers(task=task, schema_hint=SCHEMA_HINTS.get(schema, "{}"),
                                  trusted=trusted, untrusted=untrusted, system_core=SYSTEM_WRITE)
    return schema, lang, provider_messages(system, tb, ub)


def render(template: str, eos_text: str, bos_text: str, messages: list[dict], thinking: bool) -> str:
    # Same as core/local_chat_template.py:configure_non_thinking_chat + llama-cpp-python
    # Jinja2ChatFormatter (add_generation_prompt=True). thinking=True sets the switch
    # to true explicitly (Qwen3.5's template only thinks when it is defined and true).
    from llama_cpp.llama_chat_format import Jinja2ChatFormatter
    tpl = "{% set enable_thinking = " + ("true" if thinking else "false") + " %}" + template
    fmt = Jinja2ChatFormatter(template=tpl, eos_token=eos_text, bos_token=bos_text)
    return fmt(messages=messages).prompt


def template_info(src: str) -> dict:
    kv = meta(src)
    toks = kv.get("tokenizer.ggml.tokens") or []
    eos = kv.get("tokenizer.ggml.eos_token_id")
    bos = kv.get("tokenizer.ggml.bos_token_id")
    tpl = kv.get("tokenizer.chat_template") or ""
    return {"src": src, "template": tpl, "template_sha256": sha(tpl),
            "eos_text": toks[eos] if eos is not None else "",
            "bos_text": toks[bos] if bos is not None else "",
            "has_enable_thinking": "enable_thinking" in tpl}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--template", action="append", default=[], help="family=gguf path or URL")
    ap.add_argument("--cases", default="")
    ap.add_argument("--stages", default="draft_legacy,plan")
    ap.add_argument("--cache-set", default="cl-01:cl-01,cl-14,cl-20",
                    help="PROFILE_CASE:JOB_CASE,JOB_CASE,... -> letters sharing one CV")
    a = ap.parse_args()
    repo = Path(a.repo).resolve()
    sys.path.insert(0, str(repo))
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    gold = load_gold(repo)
    from core.cover_guard import confirmed_profile_text

    cases = {c["id"]: c for c in gold._load_cases()}
    def pick(prefix):
        hits = [k for k in cases if k == prefix or k.startswith(prefix + "-")]
        if len(hits) != 1: raise SystemExit(f"case {prefix!r}: {hits}")
        return cases[hits[0]]
    wanted = [pick(p) for p in a.cases.split(",") if p] if a.cases else [cases[k] for k in sorted(cases)]
    templates = {}
    for spec in a.template:
        fam, src = spec.split("=", 1)
        templates[fam] = template_info(src)
        (out / f"chat_template.{fam}.jinja").write_text(templates[fam]["template"], encoding="utf-8")

    def emit(name: str, profile_case: dict, job_case: dict, stage: str) -> dict:
        cfg = gold._config_from_case(profile_case)
        profile_text = confirmed_profile_text(cfg)
        job = job_case["job"]
        jt = job_text_of(job)
        schema, lang, msgs = stage_messages(stage, profile_text, jt, job.get("company"))
        rec = {"name": name, "stage": stage, "schema": schema, "lang": lang,
               "profile_case": profile_case["id"], "job_case": job_case["id"],
               "expected_outcome": job_case.get("expected_outcome"),
               "max_tokens": TOKEN_BUDGET[schema], "temperature": TEMPERATURE,
               "messages": msgs, "messages_sha256": sha(json.dumps(msgs, ensure_ascii=False)),
               "rendered": {}}
        for fam, ti in templates.items():
            for mode, thinking in (("nothink", False), ("think", True)):
                text = render(ti["template"], ti["eos_text"], ti["bos_text"], msgs, thinking)
                fn = f"{name}.{fam}.{mode}.prompt.txt"
                (out / fn).write_bytes(text.encode("utf-8"))
                rec["rendered"][f"{fam}.{mode}"] = {"file": fn, "sha256": sha(text), "chars": len(text)}
        (out / f"{name}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
        return {k: rec[k] for k in ("name", "stage", "lang", "profile_case", "job_case",
                                     "expected_outcome", "max_tokens", "messages_sha256", "rendered")}

    index = []
    for stage in [s for s in a.stages.split(",") if s]:
        for case in wanted:
            index.append(emit(f"{case['id'][:5]}.{stage}", case, case, stage))
    cache_sets = []
    if a.cache_set:
        pc, jobs = a.cache_set.split(":")
        prof = pick(pc)
        names = []
        for jc in jobs.split(","):
            name = f"cache.{prof['id'][:5]}x{jc}.draft_legacy"
            index.append(emit(name, prof, pick(jc), "draft_legacy")); names.append(name)
        cache_sets.append({"profile_case": prof["id"], "letters": names})
    manifest = {"repo_commit": commit, "repo": "<KK_REPO>", "templates": {k: {kk: v for kk, v in t.items() if kk != "template"} for k, t in templates.items()},
                "sampling_product": {"temperature": TEMPERATURE, "top_p": 0.95, "top_k": 40, "min_p": 0.05,
                                      "repeat_penalty": 1.0, "seed": "llama-cpp-python default (0xFFFFFFFF, re-seeded per call)",
                                      "response_format": "json_object -> llama_cpp.llama_grammar.JSON_GBNF"},
                "prompts": index, "cache_sets": cache_sets}
    try:
        from llama_cpp.llama_grammar import JSON_GBNF
        (out / "json_object.gbnf").write_text(JSON_GBNF, encoding="utf-8")
        manifest["json_grammar_file"] = "json_object.gbnf"; manifest["json_grammar_sha256"] = sha(JSON_GBNF)
    except Exception as e:  # noqa: BLE001
        manifest["json_grammar_error"] = repr(e)
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(index)} prompts -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

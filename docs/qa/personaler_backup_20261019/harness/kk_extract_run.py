"""QA driver (not repo code): Q4_K_M CV extracts of SMOKE_DE_EN_10 via the app CV-import child.
Sequential, one fresh process per CV.  usage: python kk_extract_run.py
"""
import datetime, hashlib, json, os, platform, socket, subprocess, sys, time
from importlib import metadata
from pathlib import Path
import psutil
ROOT = Path(r"%USERPROFILE%\kk_extracts_2026-10-18"); OUT = ROOT / "q4_k_m"; LOGS = OUT / "logs"
SRC = ROOT / "src_47e8f83b"; PY = Path(sys.executable)
CHILD = ROOT / "_harness" / "kk_extract_child.py"
COMMIT = "47e8f83b08a1925579891abbc861b68a284a66a8"
MODEL = Path(r"%USERPROFILE%\kk_letters_2026-10-18\_models\Qwen3.5-4B-Q4_K_M.gguf")
PIN = "00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4"
SEED = "42"; TIMEOUT = 2400
LOGS.mkdir(parents=True, exist_ok=True)
HOST = socket.gethostname()
red = lambda s: s.replace(HOST, "<HOST>")
now = lambda: datetime.datetime.now().astimezone().isoformat(timespec="seconds")
rl = open(ROOT / "RUN.log", "a", encoding="utf-8")
def log(s): print(s, flush=True); rl.write(s + "\n"); rl.flush()
def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""): h.update(b)
    return h.hexdigest()
llver = metadata.version("llama_cpp_python")
if llver != "0.3.35":
    log(f"ABORT llama-cpp-python {llver} != 0.3.35"); sys.exit(2)
msha = sha256(MODEL)
log(f"MODEL_SHA {msha} pinned={PIN} match={msha == PIN}")
if msha != PIN: sys.exit(3)
env = {k: v for k, v in os.environ.items() if not k.startswith("KARRIEREKRAKE_")}
env_set = {"KARRIEREKRAKE_CV_LLM_MODEL": str(MODEL), "KARRIEREKRAKE_DATA_DIR": str(ROOT / "_appdata"),
           "KARRIEREKRAKE_MODELS_DIR": str(ROOT / "_appdata" / "models-empty"), "KK_QA_SEED": SEED,
           "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
env.update(env_set)
sys.path.insert(0, str(SRC)); os.environ.update(env_set)
import core.cv_llm_runtime as rt
plan = rt.resolve_cv_llm_thread_plan()
import llama_cpp
manifest = json.loads((SRC / "artifacts/cv_parser_replacement/SMOKE_DE_EN_10_MANIFEST.json").read_text(encoding="utf-8"))
meta = dict(product_commit=COMMIT, product_src=str(SRC) + " (git archive of PR #144 head 47e8f83b)",
            code_path="python kk_extract_child.py -> desktop.cv_import_child.run (app CV-import child) -> core.cv_parser.import_cv -> core.cv_intelligence.import_cv_canonical -> core.cv_docpick_import (Docpick schema extract) -> core.cv_llm_runtime.chat_completion_inprocess (llama-cpp-python in-process, temperature=0.0, response_format=json_object, enable_thinking=false)",
            llama_cpp_python_version=llver, llama_cpp_python_file=llama_cpp.__file__,
            llama_cpp_commit="UNSICHER (not exposed by the llama-cpp-python wheel)",
            llama_system_info=llama_cpp.llama_print_system_info().decode(errors="replace"),
            model_path=str(MODEL), model_sha256=msha, model_sha256_pinned=PIN,
            model_source="https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/resolve/main/Qwen3.5-4B-Q4_K_M.gguf (guenther/model_manager.py MODEL_CATALOG)",
            seed=int(SEED), seed_note="explicit Llama(seed=42) via wrapper; product default would be LLAMA_DEFAULT_SEED (random); temperature=0.0 -> greedy, seed does not affect output",
            temperature=0.0, llama_init=dict(n_ctx=rt.resolve_cv_llm_n_ctx(), n_threads=plan[0], n_threads_batch=plan[1], physical=plan[2], logical=plan[3], reserve=plan[4], n_batch=512, use_mmap=True, use_mlock=False, draft_model=None, prompt_cache=None),
            env_set=env_set, python=platform.python_version(), python_exe=str(PY), manifest_id=manifest.get("manifest_id"), created=now())
(OUT / "run_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
log(f"EXTRACT_START {now()} commit={COMMIT[:8]} llama-cpp-python={llver} threads={plan[0]}/{plan[1]}")
for d in manifest["documents"]:
    did = d["id"]; pdf = SRC / d["path"]; stem = Path(d["path"]).stem
    out_json = OUT / f"{stem}.json"
    if out_json.is_file(): log(f"SKIP {stem}"); continue
    child_out = OUT / f"{stem}.child_raw.json"
    cmd = [str(PY), str(CHILD), str(SRC), "--cv", str(pdf), "--out", str(child_out)]
    t0 = time.time(); peak = 0; minav = 10**13; killed = ""
    with open(LOGS / f"{stem}.stderr.raw", "w", encoding="utf-8") as se:
        p = subprocess.Popen(cmd, stdout=se, stderr=se, env=env, cwd=str(SRC)); pp = psutil.Process(p.pid)
        while p.poll() is None:
            try: peak = max(peak, sum(x.memory_info().rss for x in [pp] + pp.children(recursive=True)))
            except Exception: pass
            av = psutil.virtual_memory().available; minav = min(minav, av)
            if av < 1024**3: killed = "low_memory"
            if time.time() - t0 > TIMEOUT: killed = "timeout"
            if killed:
                for x in pp.children(recursive=True) + [pp]:
                    try: x.kill()
                    except Exception: pass
                break
            time.sleep(1)
        rc = p.wait()
    wall = round(time.time() - t0, 1)
    raw = LOGS / f"{stem}.stderr.raw"; (LOGS / f"{stem}.log").write_text(red(raw.read_text(encoding="utf-8", errors="replace")), encoding="utf-8"); raw.unlink()
    child = json.loads(child_out.read_text(encoding="utf-8")) if child_out.is_file() else None
    step = (child or {}).get("llm_step") or {}
    rec = dict(cv=stem, manifest_id=did, ok=bool(child and child.get("ok")), kind=(child or {}).get("kind", killed or f"exit_{rc}"),
               extract=(child or {}).get("parsed"), child_output=child, wall_s=wall, process_exit_code=rc, killed=killed or None,
               prompt_tokens=step.get("prompt_tokens"), gen_tokens=step.get("gen_tokens"),
               prompt_tok_per_s=step.get("prompt_tok_per_s"), gen_tok_per_s=step.get("gen_tok_per_s"),
               peak_tree_rss_mib=round(peak / 2**20), min_mem_available_mib=round(minav / 2**20),
               exact_command_line=" ".join(f'"{x}"' if " " in x else x for x in cmd), env_set=env_set,
               seed=int(SEED), product_commit=COMMIT, llama_cpp_python_version=llver, model_sha256=msha, finished=now())
    out_json.write_text(json.dumps(rec, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    log(f"CV {stem} ok={rec['ok']} kind={rec['kind']} wall_s={wall} prompt_tok={rec['prompt_tokens']} gen_tok={rec['gen_tokens']} pp_tok_s={rec['prompt_tok_per_s']} tg_tok_s={rec['gen_tok_per_s']} peak_rss_mib={rec['peak_tree_rss_mib']} rc={rc}")
log(f"EXTRACT_END {now()}")

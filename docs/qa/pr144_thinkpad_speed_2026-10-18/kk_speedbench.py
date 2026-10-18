"""ThinkPad speed test (T02.08): tokens/s only. Not i3 evidence."""
import json, platform, sys, time, os
import psutil
from llama_cpp import Llama

model = sys.argv[1]
out = sys.argv[2]
runs = int(sys.argv[3]) if len(sys.argv) > 3 else 3
threads = psutil.cpu_count(logical=False)
prompt = ("Fasse den folgenden Lebenslauf in drei Sätzen zusammen. " +
          "Max Mustermann, Speditionskaufmann, 8 Jahre Erfahrung in Disposition, SAP TM, "
          "Zollabwicklung, Teamleitung von 6 Personen, Englisch C1. " * 8)
proc = psutil.Process()
t0 = time.perf_counter()
llm = Llama(model_path=model, n_ctx=2048, n_threads=threads, verbose=False, seed=1)
load_s = time.perf_counter() - t0
results = []
for i in range(runs):
    llm.reset()
    try:
        from llama_cpp import llama_cpp as C
        C.llama_perf_context_reset(llm._ctx.ctx)
    except Exception:
        C = None
    t = time.perf_counter()
    r = llm.create_completion(prompt, max_tokens=128, temperature=0.0, seed=1)
    dt = time.perf_counter() - t
    u = r["usage"]
    results.append({"run": i, "prompt_tokens": u["prompt_tokens"],
                    "completion_tokens": u["completion_tokens"], "wall_s": round(dt, 3)})
    if C is not None:
        p = C.llama_perf_context(llm._ctx.ctx)
        results[-1].update({
            "prompt_eval_ms": round(p.t_p_eval_ms, 1), "n_p_eval": p.n_p_eval,
            "eval_ms": round(p.t_eval_ms, 1), "n_eval": p.n_eval,
            "prompt_tok_s": round(p.n_p_eval / (p.t_p_eval_ms / 1000), 2) if p.t_p_eval_ms else None,
            "gen_tok_s": round(p.n_eval / (p.t_eval_ms / 1000), 2) if p.t_eval_ms else None})
timings = None
try:
    from llama_cpp import llama_cpp as C
    p = C.llama_perf_context(llm._ctx.ctx)
    timings = {"prompt_eval_ms": p.t_p_eval_ms, "n_p_eval": p.n_p_eval,
               "eval_ms": p.t_eval_ms, "n_eval": p.n_eval}
except Exception as e:
    timings = {"error": type(e).__name__}
vm = psutil.virtual_memory()
rec = {
    "note": "ThinkPad speed test only; NOT i3 evidence (Damiano 2026-10-18 18:58)",
    "device": platform.node(), "cpu": platform.processor(),
    "physical_cores": threads, "logical_cores": psutil.cpu_count(),
    "ram_total_bytes": vm.total, "ram_available_bytes_end": vm.available,
    "model": os.path.basename(model), "model_bytes": os.path.getsize(model),
    "n_threads": threads, "load_s": round(load_s, 3), "runs": results,
    "last_run_perf": timings, "peak_rss_bytes": getattr(proc.memory_info(), "peak_wset", None),
    "llama_cpp": __import__("llama_cpp").__version__, "python": platform.python_version(),
}
json.dump(rec, open(out, "w"), indent=2)
print(json.dumps(rec, indent=2))

"""Result files of the ThinkPad benches must not carry home, repo or model directories.

Both benches are driven through their real `main(["run", ...])` code path. Only the parts that need a
model / llama-server / the product are replaced by small fakes; every path-bearing field the scripts
record (argv, cmdline, cwd, sys.executable, llama_cpp.__file__, repo path, model/draft/prompt/grammar
paths, power reference, server version error, /props, logs, sha cache) is fed sentinel paths.
"""
import json
import os
import sys
import types
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

WIN_HOME = "C:\\Users\\Max Müller"          # profile name with space + umlaut
WIN_URL = "file:///C:/Users/Max%20M%C3%BCller/kk-speedtest/models/" + "Qwen3.5-4B-Q4_K_M.gguf"
MODEL_NAME = "Qwen3.5-4B-Q4_K_M.gguf"


def _forms(p: str) -> set[str]:
    """plain, JSON-escaped (double backslash, ensure_ascii on/off), forward-slash, \\u005c and URL (%5C/%20)."""
    from urllib.parse import quote
    out = {p, p.replace("\\", "\\\\"), p.replace("\\", "/"), json.dumps(p)[1:-1],
           json.dumps(p, ensure_ascii=False)[1:-1], p.replace("\\", "\\u005c"),
           json.dumps(p)[1:-1].replace("\\\\", "\\u005c")}
    out |= {quote(p, safe=":"), quote(p.replace("\\", "/"), safe=":/")}
    return out


NAME_TOKENS = ("müller", "m\\u00fcller", "m%c3%bcller", "max%20m", "sentinel")


def _assert_clean(root: Path, sentinels: list[str]) -> list[str]:
    texts = []
    for f in sorted(root.rglob("*")):
        if f.is_file():
            t = f.read_bytes().decode("utf-8", "replace")
            texts.append(t)
            for s in sentinels:
                for form in _forms(s):
                    assert form.lower() not in t.lower(), f"{form!r} found in {f.relative_to(root)}"
            for tok in NAME_TOKENS:
                assert tok not in t.lower(), f"{tok!r} found in {f.relative_to(root)}"
    return texts


@pytest.fixture()
def fake_home(tmp_path, monkeypatch):
    home = tmp_path / "SENTINEL HOME" / "Max Müller"
    k = home / "kk-speedtest"
    (k / "models").mkdir(parents=True)
    (k / "models" / MODEL_NAME).write_bytes(b"GGUF-fake-model")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", WIN_HOME)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(os.path, "expanduser", lambda p: str(p).replace("~", str(home), 1))
    monkeypatch.setattr(sys, "executable", WIN_HOME + r"\kk-speedtest\venv-cv035\Scripts\python.exe")
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.chdir(k)
    env0 = dict(os.environ)
    yield home, k
    os.environ.clear()
    os.environ.update(env0)


def test_cv_bench_session_has_no_home_repo_or_model_dirs(fake_home, monkeypatch):
    import llama_cpp  # pinned wheel is installed in the test venv; no model is loaded

    import thinkpad_cv_bench as h

    home, k = fake_home
    repo = k / "repo-47e8f83b"
    (repo / "core").mkdir(parents=True)
    (repo / "core" / "cv_llm_runtime.py").write_text("# fake\n", encoding="utf-8")
    model = k / "models" / MODEL_NAME
    pref = k / "results" / "power_ref.json"
    pref.parent.mkdir(parents=True)
    pref.write_text(json.dumps({"reference": {"scheme_guid": None, "ac_online": None}}), encoding="utf-8")

    rt = types.ModuleType("core.cv_llm_runtime")
    rt.resolve_cv_llm_thread_plan = lambda: (4, 4, 4, 8, 0)
    core = types.ModuleType("core")
    core.cv_llm_runtime = rt
    monkeypatch.setitem(sys.modules, "core", core)
    monkeypatch.setitem(sys.modules, "core.cv_llm_runtime", rt)
    monkeypatch.setattr(llama_cpp, "__file__", str(k / "venv-cv035" / "Lib" / "site-packages" / "llama_cpp" / "__init__.py"))
    monkeypatch.setattr(h.psutil, "cpu_percent", lambda *a, **kw: 0.0)
    monkeypatch.setattr(h, "install_hooks", lambda B: {"observe": [], "variant": []})
    monkeypatch.setattr(h, "corpus_documents", lambda r: [("DE_01_Klassisch.pdf", {})])
    monkeypatch.setattr(h, "load_corpus_evaluator", lambda r: None)

    def fake_run_one(B, a, repo_, cv_name, tag, sampler, out, evaluate_doc, expected):
        src = repo_ / "tests" / "fixtures" / "cv_corpus" / cv_name
        return {"cv": cv_name, "tag": tag, "kind": "measured", "ok": True, "error": None, "wall_s": 1.0,
                "n_llm_calls": 1, "ttft_s": 0.5, "pp_tok_s": 10.0, "tg_tok_s": 5.0, "gen_tokens": 3,
                "peak_rss_bytes": 1 << 20, "volatile": {"source_path": str(src)}, "files": {},
                "llm_calls": [{"index": 1, "ok": True, "n_prompt": 7,
                               "llama_kwargs": {"model_path": str(Path(a.model).resolve())},
                               "note": f"model at {str(Path(a.model).resolve()).replace(os.sep, chr(92))}",
                               "model_url": WIN_URL,
                               "win_model": WIN_HOME + "\\kk-speedtest\\models\\" + MODEL_NAME}]}

    monkeypatch.setattr(h, "run_one", fake_run_one)
    argv = ["run", "--repo", str(repo), "--repo-commit", "c" * 40, "--model", str(model),
            "--out", str(k / "results"), "--label", "t", "--warmup", "0", "--runs", "1", "--cooldown", "0",
            "--preflight", "off", "--power-check", "record", "--power-ref", str(pref), "--allow-dirty"]
    monkeypatch.setattr(sys, "argv", [WIN_HOME + r"\kk-speedtest\cvbench\thinkpad_cv_bench.py", *argv])
    assert h.main(argv) == 0

    _assert_clean(k / "results" / "t", [str(home), WIN_HOME, str(repo), str(model.parent)])
    _assert_clean(k / "results", [str(home), WIN_HOME])
    s = json.loads((k / "results" / "t" / "session.json").read_text(encoding="utf-8"))
    assert s["repo"]["path"] == "<KK_REPO>"
    assert s["model"]["path"].endswith(MODEL_NAME) and s["model"]["path"].startswith("<MODELS_DIR>")
    assert s["cwd"].startswith("<HOME>")
    assert s["system"]["python_executable"].startswith("<HOME>")
    assert s["llama"]["module"].startswith("<HOME>")
    assert s["runs"][0]["llm_calls"][0]["llama_kwargs"]["model_path"].endswith(MODEL_NAME)
    assert s["model"]["sha256"] and s["runs"][0]["wall_s"] == 1.0   # measured values untouched


def test_speed_bench_results_have_no_home_or_model_dirs(fake_home, monkeypatch):
    import thinkpad_speed_bench as sb

    home, k = fake_home
    model = k / "models" / MODEL_NAME
    draft = k / "models" / "Qwen3.5-0.8B-Q8_0.gguf"
    draft.write_bytes(b"GGUF-fake-draft")
    prompt = k / "cvbench" / "prompts" / "cl-01.plan.qwen35.nothink.prompt.txt"
    prompt.parent.mkdir(parents=True)
    prompt.write_text("<|im_start|>user\nhi<|im_end|>\n", encoding="utf-8")
    grammar = k / "cvbench" / "prompts" / "json_object.gbnf"
    grammar.write_text('root ::= "{}"\n', encoding="utf-8")
    server = WIN_HOME + r"\kk-speedtest\llama-b10453-win\llama-server.exe"

    class FakeServer:
        def __init__(self, cmd, port, log_path):
            self.cmd, self.port, self.log_path = cmd, port, log_path
            Path(log_path).write_text(f"llama_model_loader: loaded meta data from {model}\n"
                                      f"main: server binary {server}\n", encoding="utf-8")
            self.p = types.SimpleNamespace(pid=os.getpid())

        def wait_ready(self, timeout_s):
            return 1.0

        def http(self, method, path, body=None, timeout=3600):
            return 200, {"model_path": str(model), "model_url": WIN_URL, "build_info": "b10453",
                         "win_model_path": WIN_HOME + "\\kk-speedtest\\models\\" + MODEL_NAME}

        def stop(self):
            pass

    def fake_one_request(srv, sampler, a, prompt_text):
        return {"ttft_s": 0.1, "wall_s": 1.0, "pp_tok_s": 100.0, "tg_tok_s": 9.0, "gen_tokens": 4,
                "peak_rss_bytes": 1 << 20, "prompt_tokens": 5, "cache_n": 0}, "out"

    monkeypatch.setattr(sb, "Server", FakeServer)
    monkeypatch.setattr(sb, "one_request", fake_one_request)
    monkeypatch.setattr(sb.psutil, "cpu_percent", lambda *a, **kw: 0.0)
    argv = ["run", "--server", server, "--model", str(model), "--draft-model", str(draft),
            "--prompt", str(prompt), "--grammar", str(grammar), "--out", str(k / "results-speed"),
            "--label", "t", "--warmup", "0", "--runs", "1", "--cooldown", "0", "--port", "18080"]
    monkeypatch.setattr(sys, "argv", [WIN_HOME + r"\kk-speedtest\thinkpad_speed_bench.py", *argv])
    assert sb.main(argv) == 0

    _assert_clean(k / "results-speed", [str(home), WIN_HOME, str(model.parent)])
    r = json.loads((k / "results-speed" / "t" / "results.json").read_text(encoding="utf-8"))
    assert r["files"]["model"]["path"].endswith(MODEL_NAME)
    assert r["files"]["draft_model"]["path"].endswith("Qwen3.5-0.8B-Q8_0.gguf")
    assert r["files"]["prompts"][0]["path"].endswith("cl-01.plan.qwen35.nothink.prompt.txt")
    assert r["files"]["grammar"]["path"].endswith("json_object.gbnf")
    assert r["runs"][0]["tg_tok_s"] == 9.0   # measured values untouched

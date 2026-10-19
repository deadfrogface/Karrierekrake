"""Console output of the benches (what run_cv_matrix.ps1 tees into *.console.log) must not carry paths,
including output that native code writes straight to fd 1/2 (llama.cpp via C stdio / write(2)), output
that bypasses sys.stdout, and the interpreter's own SystemExit message / traceback.

Every case runs a real bench entrypoint in a subprocess with stdout+stderr merged into one log file,
exactly like `& $PY $H run ... 2>&1 | Tee-Object -FilePath ...console.log`.
"""
import ctypes.util
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_bench_result_privacy import NAME_TOKENS, WIN_HOME, _forms  # noqa: E402

HAVE_LIBC = bool(ctypes.util.find_library("c")) and os.name != "nt"

# Fake llama_cpp: writes the sentinel paths natively at import time and inside llama_print_system_info().
# printf/fputs are deliberately NOT flushed: C stdio buffers them when fd 1 is a pipe, so they only come
# out at fflush/exit - the capture has to flush C stdio before it restores the fds.
FAKE_LLAMA = textwrap.dedent('''
    import ctypes, os
    __version__ = "0.3.35"
    WIN = os.environ["KK_TEST_WIN_HOME"] + "\\\\kk-speedtest\\\\models\\\\Qwen3.5-4B-Q4_K_M.gguf"
    LIN = os.environ["HOME"] + "/kk-speedtest/models/Qwen3.5-4B-Q4_K_M.gguf"

    def _native(tag):
        os.write(1, f"NATIVE-MARK {tag} fd1 llama_model_loader: loaded meta data from {WIN}\\n".encode())
        os.write(2, f"NATIVE-MARK {tag} fd2 llama_model_load: {LIN}\\n".encode())
        if os.environ.get("KK_TEST_LIBC") == "1":
            libc = ctypes.CDLL(None)
            libc.printf(b"NATIVE-MARK %s printf %s\\n", tag.encode(), WIN.encode())
            err = ctypes.c_void_p.in_dll(libc, "stderr")
            libc.fputs(f"NATIVE-MARK {tag} fputs {LIN}\\n".encode(), err)
            out = ctypes.c_void_p.in_dll(libc, "stdout")
            libc.fputs(f"NATIVE-MARK {tag} fputs-partial-no-newline {WIN}".encode(), out)

    _native("import")

    def llama_print_system_info():
        _native("sysinfo")
        return b"AVX2 = 1"
''')


@pytest.fixture()
def env_home(tmp_path):
    home = tmp_path / "SENTINEL HOME" / "Max Müller"
    (home / "kk-speedtest" / "models").mkdir(parents=True)
    fake = home / "kk-speedtest" / "fake-site" / "llama_cpp"
    fake.mkdir(parents=True)
    (fake / "__init__.py").write_text(FAKE_LLAMA, encoding="utf-8")
    env = dict(os.environ)
    env.update(HOME=str(home), USERPROFILE=WIN_HOME, KK_TEST_WIN_HOME=WIN_HOME, PYTHONIOENCODING="utf-8",
               PYTHONPATH=str(fake.parent), KK_TEST_LIBC="1" if HAVE_LIBC else "0", QT_QPA_PLATFORM="offscreen")
    return home, env


def _run_to_log(cmd, env, cwd, log: Path) -> str:
    with open(log, "wb") as fh:                                   # 2>&1 | Tee-Object -FilePath <log>
        subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT, env=env, cwd=cwd, timeout=120)
    return log.read_bytes().decode("utf-8", "replace")


def _assert_log_clean(text: str, home: Path, must_contain: list[str]):
    for s in (str(home), WIN_HOME):
        for form in _forms(s):
            assert form.lower() not in text.lower(), f"{form!r} in console log:\n{text}"
    for tok in NAME_TOKENS:
        assert tok not in text.lower(), f"{tok!r} in console log:\n{text}"
    for m in must_contain:                                        # output is scrubbed, not swallowed
        assert m in text, f"{m!r} missing from console log:\n{text}"


def test_cv_bench_sysinfo_native_output_is_scrubbed(env_home, tmp_path):
    home, env = env_home
    text = _run_to_log([sys.executable, str(HERE / "thinkpad_cv_bench.py"), "sysinfo"], env, home,
                       tmp_path / "sysinfo.console.log")
    need = ["NATIVE-MARK import fd1", "NATIVE-MARK import fd2", "NATIVE-MARK sysinfo fd1", "<HOME>"]
    if HAVE_LIBC:
        need += ["NATIVE-MARK sysinfo printf", "NATIVE-MARK sysinfo fputs", "fputs-partial-no-newline"]
    _assert_log_clean(text, home, need)


def test_peak_raw_native_output_systemexit_and_traceback_are_scrubbed(env_home, tmp_path):
    home, env = env_home
    repo = home / "kk-speedtest" / "repo-47e8f83b"
    (repo / "scripts").mkdir(parents=True)
    (repo / "scripts" / "run_i3_peak_job_benchmark.py").write_text("# fake\n", encoding="utf-8")
    (repo / "REPO_COMMIT").write_text("c" * 40 + "\n", encoding="utf-8")
    missing_model = home / "kk-speedtest" / "models" / "missing-Qwen3.5-4B-Q4_K_M.gguf"
    text = _run_to_log([sys.executable, str(HERE / "thinkpad_peak_raw.py"), "--repo", str(repo),
                        "--model", str(missing_model), "--out", str(home / "kk-speedtest" / "results-peak"),
                        "--allow-concurrent"], env, home, tmp_path / "peak.console.log")
    # model is missing -> uncaught FileNotFoundError (traceback carries the model + script paths)
    _assert_log_clean(text, home, ["NATIVE-MARK import fd1", "NATIVE-MARK import fd2", "FileNotFoundError",
                                   "missing-Qwen3.5-4B-Q4_K_M.gguf"])
    # missing repo script -> SystemExit("<path> missing") printed by the interpreter
    text = _run_to_log([sys.executable, str(HERE / "thinkpad_peak_raw.py"), "--repo", str(home / "nope"),
                        "--model", str(missing_model), "--out", str(home / "x")], env, home,
                       tmp_path / "peak2.console.log")
    _assert_log_clean(text, home, ["run_i3_peak_job_benchmark.py missing"])


def test_speed_bench_native_output_is_scrubbed(env_home, tmp_path):
    home, env = env_home
    driver = textwrap.dedent(f'''
        import sys
        sys.path.insert(0, {str(HERE)!r})
        import thinkpad_speed_bench as sb

        def fake_diff(a):                     # stands in for a subcommand; native output happens inside main()
            import llama_cpp                  # fake: native writes at import
            llama_cpp.llama_print_system_info()
            return 0

        sb.cmd_diff = fake_diff
        raise SystemExit(sb.main(["diff", "a", "b"]))
    ''')
    text = _run_to_log([sys.executable, "-c", driver], env, home, tmp_path / "speed.console.log")
    need = ["NATIVE-MARK import fd1", "NATIVE-MARK sysinfo fd2"]
    if HAVE_LIBC:
        need += ["NATIVE-MARK sysinfo printf", "fputs-partial-no-newline"]
    _assert_log_clean(text, home, need)

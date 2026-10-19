"""Native console scrubbing must not depend on how output is chunked: a path written in two halves
(C printf + fflush after each half, os.write halves), a final line without newline at process exit, and a
path straddling the reader's 64 KiB forced-flush boundary must all come out scrubbed."""
import os
import sys
import textwrap
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_bench_native_output_privacy import HAVE_LIBC, _assert_log_clean, _run_to_log  # noqa: E402
from test_bench_result_privacy import WIN_HOME  # noqa: E402

DRIVER = textwrap.dedent('''
    import ctypes, os, sys
    sys.path.insert(0, {here!r})
    import thinkpad_speed_bench as sb
    WIN = os.environ["KK_TEST_WIN_HOME"] + "\\\\kk-speedtest\\\\models\\\\Qwen3.5-4B-Q4_K_M.gguf"
    LIN = os.environ["HOME"] + "/kk-speedtest/models/Qwen3.5-4B-Q4_K_M.gguf"
    CASE = {case!r}

    def halves(p):                                   # split inside the profile name: "...Max M" | "üller..."
        cut = p.index("Max M") + len("Max M")
        return p[:cut], p[cut:]

    def fake(a):
        if CASE == "halves":
            if os.environ.get("KK_TEST_LIBC") == "1":
                libc = ctypes.CDLL(None)
                h1, h2 = halves(WIN)
                libc.printf(b"HALF-PRINTF %s", h1.encode()); libc.fflush(None)
                libc.printf(b"%s\\n", h2.encode()); libc.fflush(None)
            h1, h2 = halves(LIN)
            os.write(2, ("HALF-WRITE " + h1).encode()); os.write(2, (h2 + "\\n").encode())
            b = ("FINAL-MARK " + WIN).encode()       # last line: no newline, two raw writes, then exit
            os.write(1, b[:len(b) // 2]); os.write(1, b[len(b) // 2:])
        else:                                        # path straddles the 64 KiB forced flush (no newline before)
            os.write(1, b"S" * (65536 - 20) + ("STRADDLE " + WIN + " tail").encode() + b"\\n")
            os.write(1, b"T" * (65536 - 7) + ("STRADDLE2 " + LIN).encode())   # no newline at all, then exit
        return 0

    sb.cmd_diff = fake
    raise SystemExit(sb.main(["diff", "a", "b"]))
''')


@pytest.fixture()
def env_home(tmp_path):
    home = tmp_path / "SENTINEL HOME" / "Max Müller"
    (home / "kk-speedtest" / "models").mkdir(parents=True)
    env = dict(os.environ)
    env.update(HOME=str(home), USERPROFILE=WIN_HOME, KK_TEST_WIN_HOME=WIN_HOME, PYTHONIOENCODING="utf-8",
               KK_TEST_LIBC="1" if HAVE_LIBC else "0")
    env.pop("KK_BENCH_NATIVE_SCRUB", None)
    return home, env


@pytest.mark.parametrize("case", ["halves", "straddle"])
def test_native_output_chunking_never_leaks(case, env_home, tmp_path):
    home, env = env_home
    text = _run_to_log([sys.executable, "-c", DRIVER.format(here=str(HERE), case=case)], env, home,
                       tmp_path / f"{case}.console.log")
    if case == "halves":
        need = ["HALF-WRITE <HOME>", "FINAL-MARK <HOME>"] + (["HALF-PRINTF <HOME>"] if HAVE_LIBC else [])
        assert text.endswith("Qwen3.5-4B-Q4_K_M.gguf")          # final marker line present, unterminated
    else:
        need = ["STRADDLE <HOME>", " tail", "STRADDLE2 <HOME>"]
        assert text.count("S") >= 65536 - 20 and text.count("T") >= 65536 - 7   # nothing swallowed
    _assert_log_clean(text, home, need)

"""Download + verify benchmark files listed in models.json (stdlib only, resumable).

  python fetch_models.py --dest %USERPROFILE%\\kk-speedtest\\models --ids 4b-Q4_K_M,draft-0.8b-Q8_0
  python fetch_models.py --dest ... --ids all          (~23 GB for everything)
  python fetch_models.py --dest ... --verify-only
  python fetch_models.py --dest ...\wheels --ids llama-cpp-python-0.3.35-win_amd64   (pinned wheel)

A file is accepted only if size AND sha256 match models.json. Never touches the app's model store.
"""
import argparse, hashlib, http.client, json, sys, urllib.request
from pathlib import Path

def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(8 << 20), b""): h.update(b)
    return h.hexdigest()

def download(url, dst, size, attempts=30):
    """Resumable. A connection that closes early is resumed with a Range request;
    the .part file is renamed only when its size equals the expected size."""
    part = dst.with_suffix(dst.suffix + ".part")
    for attempt in range(attempts):
        have = part.stat().st_size if part.exists() else 0
        if have >= size:
            break
        try:
            req = urllib.request.Request(url, headers={"Range": f"bytes={have}-"} if have else {})
            with urllib.request.urlopen(req, timeout=120) as r, open(part, "ab" if have else "wb") as f:
                if have and r.status != 206: raise RuntimeError("server ignored Range; delete .part and retry")
                done = have
                while True:
                    b = r.read(8 << 20)
                    if not b: break
                    f.write(b); done += len(b)
                    print(f"\r  {dst.name}: {done/2**30:.2f}/{size/2**30:.2f} GiB", end="", flush=True)
            print()
        except (OSError, http.client.HTTPException) as e:
            print(f"\n  attempt {attempt + 1}: {e!r}; resuming")
    if not part.exists() or part.stat().st_size != size:
        raise RuntimeError(f"{dst.name}: incomplete download ({part.stat().st_size if part.exists() else 0}/{size} B); rerun to resume")
    part.replace(dst)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dest", required=True)
    ap.add_argument("--ids", default=""); ap.add_argument("--verify-only", action="store_true")
    a = ap.parse_args()
    m = json.loads((Path(__file__).parent / "models.json").read_text())
    items = m["models"] + m["llama_cpp"] + m.get("python_wheels", [])
    if a.ids and a.ids != "all":
        want = set(a.ids.split(",")); items = [x for x in items if x["id"] in want]
    dest = Path(a.dest); dest.mkdir(parents=True, exist_ok=True); bad = 0
    for x in items:
        dst = dest / x["url"].rsplit("/", 1)[1]
        if not dst.exists() and not a.verify_only:
            print(f"download {x['id']} <- {x['url']}"); download(x["url"], dst, x["bytes"])
        if not dst.exists(): print(f"MISSING {x['id']}"); bad += 1; continue
        ok = dst.stat().st_size == x["bytes"] and sha256(dst) == x["sha256"]
        print(f"{'OK ' if ok else 'BAD'} {x['id']} {dst}"); bad += (not ok)
    return 1 if bad else 0

if __name__ == "__main__": sys.exit(main())

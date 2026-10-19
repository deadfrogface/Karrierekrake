"""Read GGUF tokenizer metadata from a file prefix (local file or HTTP range) and
compare target vs draft the way llama.cpp's common_speculative_are_compatible does
(vocab type, add_bos/add_eos, bos/eos ids, |n_vocab diff| <= 128, token text equal
from id 5 up). Stdlib only."""
import hashlib, io, json, struct, sys, urllib.request

T = {0:"<B",1:"<b",2:"<H",3:"<h",4:"<I",5:"<i",6:"<f",7:"?",10:"<Q",11:"<q",12:"<d"}
class Short(Exception): pass

def rd(f, n):
    b = f.read(n)
    if len(b) < n: raise Short()
    return b
def rstr(f):
    (n,) = struct.unpack("<Q", rd(f, 8)); return rd(f, n).decode("utf-8", "replace")
def rval(f, t):
    if t in T:
        fmt = T[t]; return struct.unpack(fmt, rd(f, struct.calcsize(fmt)))[0]
    if t == 8: return rstr(f)
    if t == 9:
        (et,) = struct.unpack("<I", rd(f, 4)); (n,) = struct.unpack("<Q", rd(f, 8))
        return [rval(f, et) for _ in range(n)]
    raise ValueError(t)

def read_meta(blob):
    f = io.BytesIO(blob)
    assert rd(f, 4) == b"GGUF"
    ver, = struct.unpack("<I", rd(f, 4)); nt, nkv = struct.unpack("<QQ", rd(f, 16))
    kv = {}
    for _ in range(nkv):
        k = rstr(f); (t,) = struct.unpack("<I", rd(f, 4)); kv[k] = rval(f, t)
    return kv

def fetch(src, nbytes):
    if src.startswith("http"):
        import subprocess, time
        for attempt in range(5):
            r = subprocess.run(["curl", "-sfL", "--max-time", "300", "-r", f"0-{nbytes-1}", src], capture_output=True)
            if r.returncode == 0 and r.stdout: return r.stdout[:nbytes]
            time.sleep(3 * (attempt + 1))
        raise RuntimeError(f"fetch failed {src} rc={r.returncode}")
    with open(src, "rb") as fh: return fh.read(nbytes)

def meta(src):
    n = 16 << 20
    while True:
        try: return read_meta(fetch(src, n))
        except Short: n *= 2
        if n > (256 << 20): raise RuntimeError("header too large")

def h(o): return hashlib.sha256(json.dumps(o, ensure_ascii=False).encode()).hexdigest()[:16]

def summary(kv):
    g = lambda k: kv.get("tokenizer.ggml." + k)
    toks = g("tokens") or []
    return {"arch": kv.get("general.architecture"), "name": kv.get("general.name"),
            "file_type": kv.get("general.file_type"),
            "model": g("model"), "pre": g("pre"), "n_vocab": len(toks),
            "tokens_h": h(toks), "tokens_from5_h": h(toks[5:]), "token_type_h": h(g("token_type")),
            "merges_n": len(g("merges") or []), "merges_h": h(g("merges")),
            "bos": g("bos_token_id"), "eos": g("eos_token_id"), "pad": g("padding_token_id"),
            "add_bos": g("add_bos_token"), "add_eos": g("add_eos_token"),
            "chat_template_sha256": hashlib.sha256((kv.get("tokenizer.chat_template") or "").encode()).hexdigest()[:16],
            "chat_template_has_enable_thinking": "enable_thinking" in (kv.get("tokenizer.chat_template") or ""),
            }, toks

def compat(a, ta, b, tb):
    res = {"vocab_type": a["model"] == b["model"], "add_bos": a["add_bos"] == b["add_bos"],
           "add_eos": a["add_eos"] == b["add_eos"], "bos": a["bos"] == b["bos"], "eos": a["eos"] == b["eos"],
           "n_vocab_diff<=128": abs(a["n_vocab"] - b["n_vocab"]) <= 128}
    m = min(len(ta), len(tb)); bad = [i for i in range(5, m) if ta[i] != tb[i]]
    res["token_text_equal_from_5"] = not bad; res["first_mismatch_ids"] = bad[:5]
    res["llama_cpp_compatible"] = all(v for k, v in res.items() if k != "first_mismatch_ids")
    return res

if __name__ == "__main__":
    spec = json.load(open(sys.argv[1]))  # {"targets":{name:src}, "drafts":{name:src}, "pairs":[[t,d],...]}
    S = {}
    for name, src in {**spec["targets"], **spec["drafts"]}.items():
        S[name] = summary(meta(src)); print(name, json.dumps(S[name][0]), flush=True)
    out = {"files": {k: v[0] for k, v in S.items()}, "pairs": []}
    for t, d in spec["pairs"]:
        r = compat(S[t][0], S[t][1], S[d][0], S[d][1]); out["pairs"].append({"target": t, "draft": d, **r})
        print("PAIR", t, "<-", d, json.dumps(r))
    json.dump(out, open(sys.argv[2], "w"), indent=1)

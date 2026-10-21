"""QA fact helper (not repo code, no verdicts): per case & model -> mechanical facts for final letter and each raw attempt body.
Checks: company/title presence, must_mention missing, must_not_contain hits, years/numbers not in profile, capitalized tokens not in profile/job,
repeated sentences, word count. Usage: facts.py <out_root>  -> FACTS.json + printout."""
import json, re, sys, glob
from pathlib import Path
G = Path("/workspace/km_main/tests/fixtures/anschreiben_gold")
root = Path(sys.argv[1]); res = {}
def N(s): return re.sub(r"\s+", " ", str(s).casefold())
def strip_g(t): return re.sub(r"\s*\((m/w/d|w/m/d|m/f/d|d/m/w)\)", "", t).strip()
def body_of(raw):
    try: return json.loads(raw).get("body", "")
    except Exception:
        m = re.search(r'"body"\s*:\s*"((?:[^"\\]|\\.)*)"', raw or "", re.S)
        return json.loads('"'+m.group(1)+'"') if m else (raw or "")
def facts(text, case):
    prof = json.dumps(case["profile"], ensure_ascii=False); job = case["job"]
    pn, jn = N(prof), N(job["title"]+" "+job["company"]+" "+job["description"])
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 20]
    seen = {}; rep = []
    for s in sents:
        k = N(s)
        if k in seen: rep.append(s)
        seen[k] = 1
    # 6-word ngram verbatim repetition
    w = re.findall(r"\w+", N(text)); ng = {}
    for i in range(len(w)-5): ng.setdefault(" ".join(w[i:i+6]), 0); ng[" ".join(w[i:i+6])] += 1
    years = sorted(set(re.findall(r"\b(?:19|20)\d\d\b", text)))
    caps = sorted({t for t in re.findall(r"\b[A-ZÄÖÜ][\wÄÖÜäöüß\-]{2,}", text) if N(t) not in pn and N(t) not in jn})
    return dict(words=len(w), chars=len(text),
        company_in_text=N(job["company"]) in N(text) if job["company"] else None,
        title_in_text=N(strip_g(job["title"])) in N(text),
        must_mention_missing=[m for m in case.get("must_mention", []) if N(m) not in N(text)],
        must_not_contain_hits=[m for m in case.get("must_not_contain", []) if N(m) in N(text)],
        years=years, years_not_in_profile=[y for y in years if y not in prof],
        cap_tokens_not_in_profile_or_job=caps,
        repeated_sentences=rep, repeated_6grams=sorted(k for k, v in ng.items() if v > 1))
for md in sorted(p for p in root.iterdir() if p.is_dir() and p.name != "tools"):
    for f in sorted(md.glob("cl-*.json")):
        r = json.loads(f.read_text()); case = json.load(open(G / f.name))
        e = {"ok": r.get("ok"), "reason": r.get("reason"), "issues": r.get("issues"), "outcome": r.get("outcome"),
             "elapsed_s": r.get("elapsed_s"), "n_attempts": len(r.get("attempts_raw", [])),
             "final": facts(r["text"], case) if r.get("text") else None,
             "attempts": [facts(body_of(a.get("raw_reply", "")), case) if "raw_reply" in a else a for a in r.get("attempts_raw", [])]}
        res.setdefault(md.name, {})[r["case"]] = e
(root / "FACTS.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
for m, d in res.items():
    for c, e in d.items():
        print(m, c, e["ok"], e["reason"], e["issues"], e["elapsed_s"], "final" if e["final"] else "no-letter")

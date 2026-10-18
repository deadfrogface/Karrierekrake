"""QA claim scanner (not repo code): for each final letter and raw attempt, list sentences with credential/employer/date/degree/language/number
keywords, and org names (GmbH/AG/KG) not in profile. Output for manual reading; no verdicts. Usage: claims_scan.py <model_dir>"""
import json, re, sys
from pathlib import Path
G = Path("/workspace/km_main/tests/fixtures/anschreiben_gold")
KW = r"schein|zertifi|lizenz|führerschein|klasse|studium|abschluss|ausbildung|bachelor|master|ihk|jahre|jahren|seit|muttersprach|\b[abc][12]\b|niveau|fließend|verhandlungssicher|stapler|gefahrgut|adr|weiterbild|schulung|\d"
md = Path(sys.argv[1])
for f in sorted(md.glob("cl-*.json")):
    r = json.loads(f.read_text()); case = json.load(open(G / f.name)); prof = json.dumps(case["profile"], ensure_ascii=False).casefold()
    texts = [("FINAL", r["text"])] if r.get("text") else []
    for i, a in enumerate(r.get("attempts_raw", [])):
        try: b = json.loads(a["raw_reply"])["body"]
        except Exception: b = a.get("raw_reply", "") or str(a)
        texts.append((f"att{i}", b))
    print("=====", r["case"], "ok=", r["ok"])
    for tag, t in texts:
        orgs = [o for o in re.findall(r"[A-ZÄÖÜ][\wÄÖÜäöüß\- ]{1,40}?(?:GmbH|AG|KG)\b", t) if o.casefold().strip() not in prof and o.casefold().strip() not in case["job"]["company"].casefold()]
        hits = [s for s in re.split(r"(?<=[.!?])\s+|\n", t) if re.search(KW, s, re.I)]
        print(f" [{tag}] orgs_not_in_profile_or_job={orgs}")
        for s in hits: print("    -", s.strip()[:260])

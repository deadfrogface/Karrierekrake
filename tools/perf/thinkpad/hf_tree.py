import json, sys, urllib.request
def tree(repo, rev="main"):
    url = f"https://huggingface.co/api/models/{repo}/tree/{rev}?recursive=1"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.load(r)
    except Exception as e:
        return {"error": str(e)}
def info(repo):
    try:
        with urllib.request.urlopen(f"https://huggingface.co/api/models/{repo}", timeout=30) as r:
            return json.load(r)
    except Exception as e:
        return {"error": str(e)}
for repo in sys.argv[1:]:
    i = info(repo)
    print("==", repo, "sha=", i.get("sha"), "err=", i.get("error"), "base=", (i.get("cardData") or {}).get("base_model"))
    t = tree(repo)
    if isinstance(t, dict):
        print("  tree err", t); continue
    for f in t:
        p = f.get("path"); lfs = f.get("lfs") or {}
        if p.endswith(".gguf") or p.endswith(".json"):
            print("  ", p, f.get("size"), lfs.get("oid", "") if lfs else "(git oid " + str(f.get("oid")) + ")")

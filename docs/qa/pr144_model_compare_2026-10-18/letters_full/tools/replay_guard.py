"""QA replay (not repo code, no LLM): re-run the deterministic checks of rewrite_cover_letter on recorded raw replies to see which violations fired."""
import importlib.util, json, os, sys
from copy import deepcopy
from pathlib import Path
ROOT=Path("/workspace/km_main"); sys.path.insert(0,str(ROOT)); os.chdir(ROOT)
R=Path("/workspace/qa-findings/pr144-model-compare/letters_full_2026-10-18")
spec=importlib.util.spec_from_file_location("gold",ROOT/"tests/test_cover_letter_gold.py"); gold=importlib.util.module_from_spec(spec); spec.loader.exec_module(gold)
from core.cv_employment_evidence import with_source_duties
from core.cover_guard import confirmed_profile_text, prepare_cover_check, screen_prepared_letter
from core.cover_letter import compose_cover_letter,_cover_bundle,_resolve_writer_claims,cover_letter_reference_hits,normalize_cover_text
from guenther.contracts import WritingSuggestion
from guenther.validation import parse_contract
from guenther.intelligence.writing_validate import validate_writing_grounded
from guenther.intelligence.quality_loop.critic import deterministic_ready_as_is_hint
cases={c["id"]:c for c in gold._load_cases()}
out={}
for m in sys.argv[1:]:
    for f in sorted((R/m).glob("cl-*.json")):
        r=json.loads(f.read_text()); c=cases[r["case"]]
        job=gold._job_from_case(c); config=deepcopy(gold._config_from_case(c))
        config.profile.qualifications.work_experience=with_source_duties(config.profile.qualifications.work_experience or [],config.application.cv_source_text,cv_import=getattr(config.profile.extract_review,"source","")=="cv")
        seed=compose_cover_letter(job,config)
        bundle=_cover_bundle(job,config,"",description=seed.description_used)
        profile=confirmed_profile_text(config); claims=_resolve_writer_claims(config,None)
        prepared=prepare_cover_check(config,seed.description_used,f"{job.title} {job.company}")
        res=[]
        for i,a in enumerate(r.get("attempts_raw",[])):
            if "raw_reply" not in a: res.append({"att":i,"exception":a.get("exception"),"code":a.get("code")}); continue
            e={"att":i}
            try:
                s=parse_contract("writing",a["raw_reply"])
                if not isinstance(s,WritingSuggestion): e["contract"]="invalid"; res.append(e); continue
                s2,rep=validate_writing_grounded(s,profile_text=profile,job_text=seed.description_used,target_company=job.company,target_role=job.title,contact_claims=claims,applicant_name=config.application.full_name)
                body=normalize_cover_text(s2.body)
                refs=cover_letter_reference_hits(body,job,config,facts=list(bundle.facts))
                q=deterministic_ready_as_is_hint(body=body,target_company=job.company,safety_ok=rep.ok) and 100<=len(body.split())<=350 and len(body.split("\n\n"))>=4
                sc=screen_prepared_letter(body,prepared)
                e.update(report_errors=[(x.code,x.severity,str(getattr(x,"message",""))[:200]) for x in rep.errors],
                         refs_accepted=refs.accepted, refs_missing=list(refs.missing), quality=q, words=len(body.split()), paras=len(body.split("\n\n")),
                         screen_ok=sc.ok, violations=[str(v) for v in sc.violations], invented_flag=s.invented_flag, body_changed_by_validator=(s2.body!=s.body))
            except Exception as ex: e["replay_error"]=f"{type(ex).__name__}: {ex}"[:300]
            res.append(e)
        out.setdefault(m,{})[r["case"]]=res
Path("/workspace/qa_tmp/guard_replay.json").write_text(json.dumps(out,ensure_ascii=False,indent=1))
for m,d in out.items():
    for c,res in d.items():
        for e in res: print(m,c,json.dumps(e,ensure_ascii=False))

# Günther — Capabilities matrix (Phases 8–14)

| Capability | Module | Deterministic primary | Günther role | Safety |
|------------|--------|----------------------|--------------|--------|
| CV | `suggest_cv_extract` | `core/cv_parser.py` | Assist messy CVs | Drop ungrounded skills; manual wins |
| Job | `suggest_job_analysis` | matcher keywords | Structured requirements | Must appear in JD text |
| Evidence | `suggest_evidence_assist` | `core/matcher.py` | Narrative assist | Never NOT_SUPPORTED→DIRECT without profile |
| Email | `suggest_email_class` + case_pipeline advisory | `email_classify.py` | Second opinion | False-rejection guard wins |
| Association | `suggest_association` | `email_associate.py` | Second opinion | Ambiguous → no HIGH silent link |
| Writing | `suggest_writing` | cover_letter / reply_draft templates | Constrained rewrite | Invented-fact flag |
| Interview | `suggest_interview_prep` | `interview_prep.py` | Questions from evidence | Anchors validated |

**Günther may think. Karrierekrake decides. User authorizes consequential actions.**

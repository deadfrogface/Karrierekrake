#!/bin/bash
# QA driver (not repo code): sequential per-case runs, Q4_K_M first, then Q2_K_XL. Reuses ../tools/{env.sh,guarded_run.sh,letters.py} unchanged.
set -u
T=/workspace/qa-findings/pr144-model-compare/tools
OUT=/workspace/qa-findings/pr144-model-compare/letters_full_2026-10-18
PY=/workspace/km_venv/bin/python
CASES="cl-01-dispatch-hafenlogistik cl-05-source-fixture cl-07-adr-schein-trap cl-09-named-contact cl-10-english-ad cl-11-long-ad-requirements-end cl-12-html-remnants cl-14-two-stations cl-15-station-and-skill cl-18-sap-business-one-covers-sap cl-20-nordmole-dispatcher cl-24-two-requirements-in-title cl-27-gender-title cl-28-titled-contact cl-29-two-contacts cl-30-html-contact"
source $T/env.sh
TMPH=$(mktemp -d /tmp/kk-letters-home.XXXX); export HOME=$TMPH XDG_CONFIG_HOME=$TMPH/.config; mkdir -p $XDG_CONFIG_HOME
echo "RUN_START $(date -Is) home=$TMPH commit=$(git -C /workspace/km_main rev-parse HEAD)"
for M in "q4_k_m:/workspace/models/Qwen3.5-4B-Q4_K_M.gguf" "q2_k_xl_4b_gsq:/workspace/models/Qwen3.5-4B-Q2_K_XL.gguf"; do
  D=$OUT/${M%%:*}; MP=${M#*:}; mkdir -p $D/logs
  echo "MODEL_START ${M%%:*} $(date -Is) sha=$(sha256sum $MP | cut -c1-16)"
  for C in $CASES; do
    KARRIEREKRAKE_CV_LLM_MODEL=$MP bash $T/guarded_run.sh $D/logs/$C $PY $T/letters.py $D $C
    echo "CASE ${M%%:*} $C $(tail -1 $D/logs/$C.watchdog.log) | $(tail -1 $D/logs/$C.stdout.log)"
  done
  echo "MODEL_END ${M%%:*} $(date -Is)"
done
echo "RUN_END $(date -Is)"

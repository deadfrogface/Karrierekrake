#!/bin/bash
# Rebuilds kk-speed-bundle.zip (CV-import speed test). Box only.
set -euo pipefail
HERE="${KK_SPEED_PREP_DIR:-$(cd "$(dirname "$0")" && pwd)}"; REPO="${KK_REPO:?set KK_REPO to a clean Karrierekrake checkout}"
PY="${KK_PY:-python3}"
# Embedded snapshot = commit of the Personaler Q4_K_M reference extracts (override: KK_COMMIT=<sha>)
COMMIT=$(git -C $REPO rev-parse "${KK_COMMIT:-47e8f83b08a1925579891abbc861b68a284a66a8}^{commit}"); SHORT=${COMMIT:0:8}
test -z "$(git -C $REPO status --porcelain)" || { echo "repo dirty"; exit 1; }
W=$(mktemp -d); B=$W/cvbench; mkdir -p $B
zipdir() { $PY - "$1" "$2" <<'PYEOF'
import sys, zipfile, os
src, dst = sys.argv[1], sys.argv[2]
files = sorted(os.path.relpath(os.path.join(r, f), src) for r, _, fs in os.walk(src) for f in fs)
with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
    for f in files:
        zi = zipfile.ZipInfo(f.replace(os.sep, "/"), date_time=(2026, 10, 18, 0, 0, 0))
        zi.compress_type = zipfile.ZIP_DEFLATED; zi.external_attr = 0o644 << 16
        z.writestr(zi, open(os.path.join(src, f), "rb").read())
PYEOF
}
S=$W/snap; mkdir -p $S
git -C $REPO archive $COMMIT core guenther desktop devops contracts config tests/fixtures/cv_corpus scripts/run_cv_corpus.py scripts/run_i3_peak_job_benchmark.py \
    constraints-runtime.txt requirements-runtime.txt | tar -x -C $S
echo "$COMMIT" > $S/REPO_COMMIT
zipdir $S $B/kk-repo-$SHORT.zip
cp $HERE/thinkpad_cv_bench.py $HERE/thinkpad_peak_raw.py $HERE/run_cv_matrix.ps1 $HERE/models.json $HERE/fetch_models.py $HERE/README.md $B/
mkdir -p $B/tests && cp $HERE/tests/test_thinkpad_cv_bench.py $B/tests/
(cd $HERE && find smoke_cv -path '*/_sandbox' -prune -o -type f -print | while read f; do mkdir -p "$B/$(dirname "$f")"; cp "$f" "$B/$f"; done)
(cd $B && find . -type f ! -name SHA256SUMS | LC_ALL=C sort | xargs sha256sum > SHA256SUMS)
mkdir -p $W/top && mv $B $W/top/
rm -f $HERE/kk-speed-bundle.zip
zipdir $W/top $HERE/kk-speed-bundle.zip
sha256sum $HERE/kk-speed-bundle.zip
rm -rf $W

"""QA wrapper (not repo code) around the app's own CV-import child entry
desktop.cv_import_child.run (same function the desktop dialog spawns; it calls
core.cv_parser.import_cv -> Docpick + in-process Qwen, temperature=0.0).
Only change: llama_cpp.Llama gets an explicit seed (KK_QA_SEED, default 42),
because the product leaves the seed at LLAMA_DEFAULT_SEED (random). With
temperature=0.0 (greedy) the seed does not influence sampling.
stderr is kept (the app's main() would discard it) so diagnostic lines are logged.
usage: python kk_extract_child.py <src_root> --cv <pdf> --out <json>
"""
import logging, os, sys
SRC = sys.argv[1]; sys.path.insert(0, SRC); os.chdir(SRC)
logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(asctime)s %(name)s %(levelname)s %(message)s")
SEED = int(os.environ.get("KK_QA_SEED", "42"))
import core.cv_llm_runtime as rt
def _seeded_llama_cls():
    from llama_cpp import Llama
    class SeededLlama(Llama):
        def __init__(self, *a, **kw):
            kw.setdefault("seed", SEED)
            super().__init__(*a, **kw)
    return SeededLlama
rt._llama_cls = _seeded_llama_cls
from desktop.cv_import_child import run
sys.exit(run(sys.argv[2:]))

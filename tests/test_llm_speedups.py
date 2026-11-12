"""Fast JSON check and stored fixed prompt part: same result, less waiting."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from core import cv_llm_runtime as rt
from core import llm_prompt_cache as cache


@pytest.fixture(autouse=True)
def _no_phase_files(monkeypatch):
    from core import cv_phase_events

    monkeypatch.setattr(cv_phase_events, "append_phase_event", lambda event: None)
    monkeypatch.setattr(cv_phase_events, "emit_diag", lambda line: None)


class _Llm:
    n_batch = 4

    def __init__(self):
        self.blocks: list[list[int]] = []

    def eval(self, tokens):
        self.blocks.append(list(tokens))


def test_prefill_evaluates_every_token_once_in_batches():
    llm = _Llm()
    assert rt._prefill_prompt_blocks(llm, list(range(10)), origin={"t": None})
    assert llm.blocks == [[0, 1, 2, 3], [4, 5, 6, 7], [8, 9]]


def test_prefill_stops_a_block_at_the_fixed_part_and_stores_it_there():
    llm = _Llm()
    stored: list[int] = []
    rt._prefill_prompt_blocks(llm, list(range(10)), origin={"t": None}, split_at=6,
                              after_split=lambda: stored.append(sum(len(b) for b in llm.blocks)))
    assert llm.blocks == [[0, 1, 2, 3], [4, 5], [6, 7, 8, 9]]
    assert stored == [6]


def test_prefill_after_a_restored_fixed_part_reads_only_the_document():
    llm = _Llm()
    called: list[int] = []
    rt._prefill_prompt_blocks(llm, list(range(10)), origin={"t": None}, start=6, split_at=6,
                              after_split=lambda: called.append(1))
    assert llm.blocks == [[6, 7, 8, 9]]
    assert called == []


def test_fixed_part_is_what_two_other_documents_share(monkeypatch):
    prompts = {"0": [1, 2, 3, 9, 4], "#": [1, 2, 3, 8, 4]}
    monkeypatch.setattr(rt, "_prompt_ids_for_prefill", lambda llm, messages: prompts[messages])
    assert rt._fixed_prompt_part(object(), [1, 2, 3, 7, 7, 4], lambda text: text) == ([1, 2, 3], 3)
    # A prompt that changes the instructions (correction attempt) shares only their start.
    assert rt._fixed_prompt_part(object(), [1, 2, 5, 7], lambda text: text) == ([1, 2, 3], 2)


def test_json_output_uses_the_built_in_grammar_for_doubles_and_for_sampling():
    kwargs, fast = rt._json_output_kwargs(object(), 0.0)
    assert kwargs == {"response_format": {"type": "json_object"}} and fast is None
    kwargs, fast = rt._json_output_kwargs(object(), 0.2)
    assert kwargs == {"response_format": {"type": "json_object"}} and fast is None


def test_cache_file_depends_on_model_prompt_and_context(tmp_path: Path):
    model = tmp_path / "models" / "m" / "model.gguf"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"x")
    pytest.importorskip("llama_cpp")
    first = cache.cache_file(model, [1, 2, 3], 4096)
    assert first is not None and first.parent == tmp_path / "models" / cache.CACHE_DIRNAME
    assert cache.cache_file(model, [1, 2, 3], 4096) == first
    assert cache.cache_file(model, [1, 2, 4], 4096) != first
    assert cache.cache_file(model, [1, 2, 3], 2048) != first


def test_restore_without_a_file_or_with_a_broken_one_reads_the_whole_prompt(tmp_path: Path):
    assert cache.restore(object(), None, [1, 2, 3]) == 0
    assert cache.restore(object(), tmp_path / "missing.state", [1, 2, 3]) == 0
    broken = tmp_path / "broken.state"
    broken.write_bytes(b"not a state")
    assert cache.restore(object(), broken, list(range(500))) == 0
    assert not broken.exists()  # a file that cannot be used is removed


def test_save_refuses_a_short_prefix(tmp_path: Path):
    assert cache.save(object(), tmp_path / "a.state", [1, 2, 3]) is False
    assert not (tmp_path / "a.state").exists()


def test_fast_json_checks_one_token_and_falls_back_to_the_full_pass():
    from core.llm_fast_json import FastJsonGrammar

    class OnlyEvenTokens(FastJsonGrammar):
        def __init__(self):
            self.full_passes = self.tokens = 0
            self.temperature, self._rng = 0.0, None
            self.accepted: list[int] = []

        def _is_valid(self, token, logit):
            return token % 2 == 0

        def _rule_out_invalid(self, scores):
            scores[1::2] = float("-inf")

        def _accept(self, token):
            self.accepted.append(token)

    fast = OnlyEvenTokens()
    out = fast(None, np.array([0.1, 0.2, 5.0, 0.3], dtype=np.single))  # favourite 2 is valid
    assert int(np.argmax(out)) == 2 and fast.full_passes == 0
    out = fast(None, np.array([0.1, 9.0, 5.0, 7.0], dtype=np.single))  # favourite 1 is not: best valid is 2
    assert int(np.argmax(out)) == 2 and fast.full_passes == 1
    assert fast.accepted == [2, 2] and fast.tokens == 2


def test_sampling_draws_only_from_the_likely_tokens_and_hands_over_one_token():
    from core.llm_fast_json import FastJsonGrammar, draw_token

    rng = np.random.default_rng(1)
    scores = np.full(100, -20.0, dtype=np.single)
    scores[[7, 8]] = [5.0, 4.5]
    assert {draw_token(scores, 0.2, rng) for _ in range(200)} <= {7, 8}
    assert draw_token(scores, 0.0, rng) == 7

    class AnyToken(FastJsonGrammar):
        def __init__(self):
            self.full_passes = self.tokens = 0
            self.temperature, self._rng = 0.2, rng

        def _is_valid(self, token, logit):
            return True

        def _accept(self, token):
            self.picked = token

    fast = AnyToken()
    out = fast(None, scores.copy())
    assert np.isfinite(out).sum() == 1 and int(np.argmax(out)) == fast.picked


def test_a_repeated_list_entry_is_recognised_as_a_stuck_answer():
    letter = '{"body": "Sehr geehrte Damen und Herren, ich bewerbe mich. ", "anchors_used": ['
    assert not rt.output_is_looping(letter + '"Teamkoordinatorin", "seit 2022", "Kundenanfragen"]}')
    assert rt.output_is_looping(letter + '"Teamkoordinatorin Kundenservice", ' * 9)
    assert rt.output_is_looping(letter + " \n" * 130)
    assert not rt.output_is_looping("x" * 1000)
    assert not rt.output_is_looping('{"skills": ["Excel", "Excel", "Excel"]}')


def test_a_finished_letter_survives_a_stuck_evidence_list():
    import json

    from core.cover_quality import _finished_body_of_cut_off_answer
    from core.cv_docpick_import import CvImportError

    cut = CvImportError("llm_output_truncated", "llm_output_truncated")
    cut.partial = '{\n  "body": "Sehr geehrte Damen und Herren,\\n\\nText.",\n  "anchors_used": ["A", "A", "A'
    assert json.loads(_finished_body_of_cut_off_answer(cut))["body"] == "Sehr geehrte Damen und Herren,\n\nText."
    cut.partial = '{"body": "Sehr geehrte Damen und Herren, mitten im Sa'
    assert _finished_body_of_cut_off_answer(cut) == ""
    assert _finished_body_of_cut_off_answer(ValueError("x")) == ""


def test_fast_json_matches_the_real_grammar_token_by_token():
    """Against llama.cpp's own JSON grammar, without a model: a tiny vocabulary file is enough."""
    llama_cpp = pytest.importorskip("llama_cpp")
    from core.llm_fast_json import _TOKEN_DATA

    assert _TOKEN_DATA.itemsize == __import__("ctypes").sizeof(llama_cpp.llama_token_data)
    assert [_TOKEN_DATA.fields[name][1] for name in ("id", "logit", "p")] == [
        getattr(llama_cpp.llama_token_data, name).offset for name in ("id", "logit", "p")]

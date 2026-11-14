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


def _grammar_double(temperature, valid, draw=None):
    from core.llm_fast_json import FastJsonGrammar

    class Double(FastJsonGrammar):
        def __init__(self):
            self.full_passes = self.tokens = 0
            self.temperature = temperature
            self.accepted: list[int] = []
            self.checked: list[list[int]] = []
            self.draw_saw = None

        def _valid_mask(self, tokens):
            self.checked.append(sorted(int(t) for t in tokens))
            return np.array([valid(int(t)) for t in tokens])

        def _rule_out_invalid(self, scores):
            for token in range(len(scores)):
                if not valid(token):
                    scores[token] = float("-inf")

        def _draw(self, scores):
            self.draw_saw = scores.copy()
            return draw(scores)

        def _accept(self, token):
            self.accepted.append(token)

    return Double()


def test_fast_json_checks_one_token_and_falls_back_to_the_full_pass():
    fast = _grammar_double(0.0, valid=lambda token: token % 2 == 0)
    out = fast(None, np.array([0.1, 0.2, 5.0, 0.3], dtype=np.single))  # favourite 2 is valid
    assert int(np.argmax(out)) == 2 and fast.full_passes == 0 and fast.checked == [[2]]
    out = fast(None, np.array([0.1, 9.0, 5.0, 7.0], dtype=np.single))  # favourite 1 is not: best valid is 2
    assert int(np.argmax(out)) == 2 and fast.full_passes == 1
    assert fast.accepted == [2, 2] and fast.tokens == 2


def test_sampling_gives_the_sampler_the_candidates_the_grammar_would_have_left():
    scores = np.arange(100, dtype=np.single)          # top 40 are tokens 60..99
    fast = _grammar_double(0.2, valid=lambda token: True, draw=lambda s: 97)
    out = fast(None, scores.copy())
    assert fast.checked == [list(range(60, 100))] and fast.full_passes == 0
    assert np.array_equal(fast.draw_saw, scores)       # nothing removed: the sampler sees every token
    assert np.isfinite(out).sum() == 1 and int(np.argmax(out)) == 97 and fast.accepted == [97]

    # One of the top tokens is not valid JSON: it is removed, the next valid ones move up, no pass over everything.
    fast = _grammar_double(0.2, valid=lambda token: token != 99, draw=lambda s: int(np.argmax(s)))
    out = fast(None, scores.copy())
    assert fast.full_passes == 0 and fast.draw_saw[99] == float("-inf")
    assert np.isfinite(fast.draw_saw).sum() == 99
    assert int(np.argmax(out)) == 98 and fast.accepted == [98]

    # Fewer than 40 valid tokens near the top: the grammar runs over everything, as the built-in path does.
    fast = _grammar_double(0.2, valid=lambda token: token < 10, draw=lambda s: int(np.argmax(s)))
    out = fast(None, scores.copy())
    assert fast.full_passes == 1 and int(np.argmax(out)) == 9 and fast.accepted == [9]


def test_token_layout_matches_llama_cpp():
    """The numpy record used for the grammar and sampler calls must be llama.cpp's ``llama_token_data``."""
    import ctypes

    llama_cpp = pytest.importorskip("llama_cpp")
    from core.llm_fast_json import _TOKEN_DATA

    assert _TOKEN_DATA.itemsize == ctypes.sizeof(llama_cpp.llama_token_data)
    assert [_TOKEN_DATA.fields[name][1] for name in ("id", "logit", "p")] == [
        getattr(llama_cpp.llama_token_data, name).offset for name in ("id", "logit", "p")]


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


def test_the_writer_stops_when_the_letter_text_is_complete():
    from core.cover_quality import _letter_text_is_complete

    answer = '{\n  "body": "Sehr geehrte Damen und Herren,\\n\\nich nenne \\"SAP Business One\\" hier.'
    grown = ""
    for piece in answer:                      # never before the closing quote of the letter text
        grown += piece
        assert not _letter_text_is_complete(grown), grown
    assert _letter_text_is_complete(answer + '"')
    assert not _letter_text_is_complete('{"anchors_used": ["A"')
    assert not _letter_text_is_complete('{"body": ""')

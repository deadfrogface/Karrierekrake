"""Verified look-ahead: the answer stays the model's own, token for token."""
from __future__ import annotations

import json
import re

from core.llm_lookahead import answer_start, leaf_values, lookahead_tokens, scaffold_guess

ANSWER = json.dumps({
    "name": {"first_name": "Mara", "last_name": "Beispiel"},
    "email": None,
    "skills": ["Disposition", "Zoll", "Logistik"],
    "employment": [
        {"company": "Nordlicht Logistik GmbH", "position": "Disponentin", "start_date": "02.2024", "end_date": "heute"},
        {"company": "Beispiel KG", "position": "Sachbearbeiterin", "start_date": "06.2021", "end_date": "01.2024"},
        {"company": "Muster \"Handel\" GmbH", "position": "Aushilfe", "start_date": "2019", "end_date": None},
    ],
    "years": 7,
}, ensure_ascii=False, indent=2).encode("utf-8")
END = -1


def _tokens(text: bytes) -> list[bytes]:
    """Split like a tokenizer would: words, whitespace runs and single punctuation marks."""
    return re.findall(rb"\s+|\w+|[^\w\s]", text)


class _Model:
    """Knows the whole answer; logits are just 'the position in the answer' (or garbage after a wrong token)."""

    def __init__(self, text: bytes = ANSWER):
        self.pieces = _tokens(text)
        self.vocab = {piece: number for number, piece in enumerate(dict.fromkeys(self.pieces))}
        self.words = {number: piece for piece, number in self.vocab.items()}
        self.truth = [self.vocab[piece] for piece in self.pieces]
        self.kept = 0            # tokens in the model's memory
        self.decoded = 0         # tokens evaluated in total
        self.batches: list[int] = []

    def pick(self, logits):
        assert logits != "garbage", "a choice was read behind a token that was never verified"
        return self.truth[logits] if logits < len(self.truth) else END

    def decode(self, tokens):
        base = self.kept
        self.kept += len(tokens)
        self.decoded += len(tokens)
        self.batches.append(len(tokens))

        def after(index):
            fed = tokens[:index + 1]
            return base + index + 1 if fed == self.truth[base:base + index + 1] else "garbage"
        return after

    def forget(self, count):
        self.kept -= count

    def run(self, max_tokens=10_000, given=0):
        """``given``: so many tokens of the answer are in the model's memory already (its fixed start)."""
        stats: dict = {}
        self.kept = given
        out = b"".join(chunk for _token, chunk in lookahead_tokens(
            given, pick=self.pick, decode=self.decode, forget=self.forget, piece=self.words.__getitem__,
            is_end=lambda token: token == END, max_tokens=max_tokens, stats=stats,
            given=self.truth[:given] or None))
        return out, stats


def test_values_are_found_with_their_field_and_unfinished_ones_are_left_out():
    leaves = leaf_values(ANSWER)
    texts = [ANSWER[start:end] for _field, start, end in leaves]
    assert texts[:4] == [b'Mara"', b'Beispiel"', b"null", b'Disposition"']
    fields = [field for field, _s, _e in leaves]
    assert fields[0] == (b"name", 2, b"first_name") and fields[2] == (b"", 1, b"email")
    assert fields[3] == fields[4] == (b"skills", 2, b"#")                      # list elements share one field
    companies = [i for i, f in enumerate(fields) if f == (b"employment", 3, b"company")]
    assert len(companies) == 3                                                   # one per record, same field
    assert ANSWER[leaves[companies[2]][1]:leaves[companies[2]][2]] == b'Muster \\"Handel\\" GmbH"'
    cut = ANSWER[:ANSWER.index(b"Sachbearbeiterin") + 5]
    assert leaf_values(cut)[-1][0] == (b"employment", 3, b"company")           # the position is not finished


def test_guess_is_what_followed_the_same_field_in_the_previous_record():
    model = _Model()
    ends, total = [], 0
    for piece in model.pieces:
        total += len(piece)
        ends.append(total)
    upto = model.pieces.index(b"Sachbearbeiterin") + 2       # ... "position": "Sachbearbeiterin"
    text = b"".join(model.pieces[:upto])
    guess = scaffold_guess(text, model.truth[:upto], ends[:upto])
    assert b"".join(model.words[token] for token in guess) == b',\n      "start_date": "'
    assert scaffold_guess(text[:-3], model.truth[:upto - 1], ends[:upto - 1]) == []   # inside a value
    first = model.pieces.index(b"Disponentin") + 2
    assert scaffold_guess(b"".join(model.pieces[:first]), model.truth[:first], ends[:first]) == []  # first record


def test_the_answer_is_the_models_own_and_scaffolding_runs_in_batches():
    model = _Model()
    out, stats = model.run()
    assert out == ANSWER and stats["finish"] == "stop"
    assert stats["tokens"] == len(model.truth)
    assert stats["accepted"] > 20                               # scaffolding of the second and third record
    assert stats["batches"] < stats["tokens"] - 20              # fewer model calls than tokens
    assert model.kept == len(model.truth)                       # nothing rejected stays in the model's memory
    assert max(model.batches) > 4


def test_a_wrong_guess_costs_only_the_discarded_tokens():
    # The third record has another key order: guesses from the second record fail and are taken back.
    text = ANSWER.replace(b'"position": "Aushilfe",\n      "start_date": "2019"',
                          b'"start_date": "2019",\n      "position": "Aushilfe"')
    model = _Model(text)
    out, stats = model.run()
    assert out == text
    assert stats["guessed"] > stats["accepted"] > 0
    assert model.kept == len(model.truth)
    assert model.decoded - model.kept == stats["guessed"] - stats["accepted"]


def test_the_token_limit_ends_the_answer_as_before():
    model = _Model()
    out, stats = model.run(max_tokens=40)
    assert stats["finish"] == "length" and stats["tokens"] == 40
    assert out == b"".join(model.pieces[:40])


def test_the_fixed_start_of_an_answer_ends_before_its_first_value():
    one_line = json.dumps({"name": {"first_name": "x", "last_name": "x"}, "email": "x"})
    assert answer_start(one_line) == '{"name": {"first_name":'          # text or null stays the model's choice
    assert answer_start(json.dumps({"years": 7, "name": "x"})) == '{"years":'
    assert answer_start(json.dumps({"skills": ["x"], "name": "x"})) == '{"skills": ['
    assert answer_start("{}") == ""


def test_a_given_start_is_not_written_again_and_the_rest_is_the_models_own():
    text = json.dumps(json.loads(ANSWER), ensure_ascii=False).encode("utf-8")      # the same answer on one line
    model = _Model(text)
    start = answer_start(text.decode("utf-8")).encode("utf-8")
    given = next(count for count in range(1, len(model.pieces)) if b"".join(model.pieces[:count]) == start)
    out, stats = model.run(given=given)
    assert start + out == text
    assert stats["tokens"] == len(model.truth) - given
    assert model.kept == len(model.truth)
    assert stats["accepted"] > 20                               # look-ahead works on the one-line layout too
    limited, stats = _Model(text).run(max_tokens=30, given=given)
    assert stats["finish"] == "length" and stats["tokens"] == 30   # the given start does not count


def test_the_one_line_grammar_is_a_grammar_llama_cpp_accepts():
    import pytest

    llama_cpp = pytest.importorskip("llama_cpp")
    from core.llm_fast_json import COMPACT_JSON_GBNF

    assert "\\n" not in COMPACT_JSON_GBNF.split("string ::=")[0]             # no line break between the parts
    assert llama_cpp.LlamaGrammar.from_string(COMPACT_JSON_GBNF, verbose=False) is not None

"""JSON-only output at full generation speed, with the same text as the built-in grammar.

llama-cpp-python's ``response_format={"type": "json_object"}`` runs the JSON grammar over the whole vocabulary
for every generated token. With a 250k-token vocabulary that costs more than the model step itself on a laptop
CPU. This processor asks the grammar only about the tokens that can be picked at all; the full pass runs only
when one of them is not valid JSON.

The picked token is the one the built-in path picks:

* ``temperature == 0``: the best token; if it is not valid JSON, the best valid one.
* ``temperature > 0``: llama-cpp-python's own sampler chain (top-k 40, top-p 0.95, min-p 0.05, temperature,
  seeded draw) on the same candidates. When all top-k tokens are valid JSON the grammar would not have removed
  any of them, so the chain sees what it saw before; otherwise the grammar runs over everything first, as before.
  One draw per token from the same seed gives the same letter as the built-in path.
"""
from __future__ import annotations

import ctypes
from typing import Any

import numpy as np

_NEG_INF = float("-inf")
_TOKEN_DATA = np.dtype([("id", np.intc), ("logit", np.single), ("p", np.single)], align=True)
TOP_K, TOP_P, MIN_P, TYPICAL_P = 40, 0.95, 0.05, 1.0  # create_chat_completion defaults
WIDE = 512  # tokens looked at before the grammar has to run over the whole vocabulary


class FastJsonGrammar:
    """Logits processor for ``create_chat_completion(..., logits_processor=[...])`` with the same temperature."""

    def __init__(self, llm: Any, temperature: float = 0.0) -> None:
        import llama_cpp
        from llama_cpp import llama_grammar

        self._api = llama_cpp
        self._chain = None
        self._sampler = llama_cpp.llama_sampler_init_grammar(
            llm._model.vocab, llama_grammar.JSON_GBNF.encode("utf-8"), b"root")
        if not self._sampler:
            raise RuntimeError("json_grammar_unavailable")
        self.full_passes = 0
        self.tokens = 0
        self.temperature = float(temperature)
        self._llm = llm

    def _sampler_chain(self) -> Any:
        """The same samplers, in the same order and with the same seed, as ``Llama._init_sampler`` builds.

        Built at the first token, not in ``__init__``: llama-cpp-python sets the seed of a completion when the
        completion starts (derived from the model's seed, so every run draws the same numbers).
        """
        if self._chain is None:
            api = self._api
            chain = api.llama_sampler_chain_init(api.llama_sampler_chain_default_params())
            for part in (
                api.llama_sampler_init_top_k(TOP_K),
                api.llama_sampler_init_typical(TYPICAL_P, 1),
                api.llama_sampler_init_top_p(TOP_P, 1),
                api.llama_sampler_init_min_p(MIN_P, 1),
                api.llama_sampler_init_temp(self.temperature),
                api.llama_sampler_init_dist(self._llm._seed),
            ):
                api.llama_sampler_chain_add(chain, part)
            self._chain = chain
        return self._chain

    def __call__(self, _input_ids: Any, scores: Any) -> Any:
        if self.temperature <= 0.0:
            best = int(np.argmax(scores))
            if not self._all_valid(np.array([best])):
                self.full_passes += 1
                self._rule_out_invalid(scores)
                best = int(np.argmax(scores))
        else:
            k = min(TOP_K, len(scores))
            if not self._all_valid(np.argpartition(scores, -k)[-k:]):
                # Some top tokens are not valid JSON. Remove the invalid ones among the best WIDE tokens; if
                # at least k valid ones remain there, they are exactly the grammar's top k. Otherwise the
                # grammar runs over everything.
                wide = min(WIDE, len(scores))
                near = np.argpartition(scores, -wide)[-wide:]
                invalid = near[~self._valid_mask(near)]
                if wide - len(invalid) >= k:
                    scores[invalid] = _NEG_INF
                else:
                    self.full_passes += 1
                    self._rule_out_invalid(scores)
            best = self._draw(scores)
            # The sampler after this processor must take exactly the token that was drawn and accepted.
            logit = scores[best]
            scores[:] = _NEG_INF
            scores[best] = logit
        self._accept(best)
        self.tokens += 1
        return scores

    def pick(self, scores: Any) -> int:
        """The token the built-in path takes at temperature 0 for these logits; the grammar moves on to it."""
        best = int(np.argmax(scores))
        if not self._all_valid(np.array([best])):
            self.full_passes += 1
            self._rule_out_invalid(scores)
            best = int(np.argmax(scores))
        self._accept(best)
        self.tokens += 1
        return best

    def _array(self, data: np.ndarray) -> Any:
        api = self._api
        return api.llama_token_data_array(
            data=data.ctypes.data_as(api.llama_token_data_p), size=len(data), selected=-1, sorted=False)

    def _valid_mask(self, tokens: Any) -> np.ndarray:
        """For each of ``tokens``: does the grammar accept it as the next token?"""
        some = np.zeros(len(tokens), dtype=_TOKEN_DATA)
        some["id"] = tokens
        self._api.llama_sampler_apply(self._sampler, ctypes.byref(self._array(some)))
        return some["logit"] != _NEG_INF

    def _all_valid(self, tokens: Any) -> bool:
        return bool(np.all(self._valid_mask(tokens)))

    def _every_token(self, scores: Any) -> np.ndarray:
        every = np.zeros(len(scores), dtype=_TOKEN_DATA)
        every["id"] = np.arange(len(scores), dtype=np.intc)
        every["logit"] = scores
        return every

    def _rule_out_invalid(self, scores: Any) -> None:
        every = self._every_token(scores)
        self._api.llama_sampler_apply(self._sampler, ctypes.byref(self._array(every)))
        scores[:] = every["logit"]

    def _draw(self, scores: Any) -> int:
        every = self._every_token(scores)
        array = self._array(every)
        self._api.llama_sampler_apply(self._sampler_chain(), ctypes.byref(array))
        return int(array.data[array.selected].id)

    def _accept(self, token: int) -> None:
        self._api.llama_sampler_accept(self._sampler, token)

    def close(self) -> None:
        for name in ("_sampler", "_chain"):
            handle = getattr(self, name, None)
            if handle:
                self._api.llama_sampler_free(handle)
                setattr(self, name, None)

"""JSON-only output at full generation speed.

llama-cpp-python's ``response_format={"type": "json_object"}`` runs the JSON grammar over the whole vocabulary
for every generated token. With a 250k-token vocabulary that costs more than the model step itself on a laptop
CPU. This processor checks only the token the model is about to pick; the full pass runs only when that token
is not valid JSON. With ``temperature=0`` the generated text is the same as with the built-in grammar.

With sampling (``temperature > 0``) the token is drawn here with llama-cpp-python's default chain (top-k 40,
top-p 0.95, min-p 0.05, temperature); if the draw is not valid JSON it is repeated among the valid tokens. This
is llama.cpp's own order for grammars (sample first, check, resample).
"""
from __future__ import annotations

import ctypes
from typing import Any

import numpy as np

_NEG_INF = float("-inf")
_TOKEN_DATA = np.dtype([("id", np.intc), ("logit", np.single), ("p", np.single)], align=True)


TOP_K, TOP_P, MIN_P = 40, 0.95, 0.05


def draw_token(scores: Any, temperature: float, rng: Any) -> int:
    """One token from ``scores``: the best one at temperature 0, otherwise top-k, top-p, min-p, temperature."""
    if temperature <= 0.0:
        return int(np.argmax(scores))
    k = min(TOP_K, len(scores))
    top = np.argpartition(scores, -k)[-k:]
    top = top[np.argsort(scores[top])[::-1]]
    logits = scores[top].astype(np.float64)
    top, logits = top[np.isfinite(logits)], logits[np.isfinite(logits)]
    if len(top) == 0:
        return int(np.argmax(scores))
    probs = np.exp(logits - logits[0])
    probs /= probs.sum()
    keep = int(np.searchsorted(np.cumsum(probs), TOP_P) + 1)
    keep = min(keep, int((probs >= MIN_P * probs[0]).sum()))
    top, logits = top[:keep], logits[:keep]
    probs = np.exp((logits - logits[0]) / temperature)
    probs /= probs.sum()
    return int(top[rng.choice(len(top), p=probs)])


class FastJsonGrammar:
    """Logits processor for ``create_chat_completion(..., logits_processor=[...])`` with the same temperature."""

    def __init__(self, llm: Any, temperature: float = 0.0) -> None:
        import llama_cpp
        from llama_cpp import llama_grammar

        self._api = llama_cpp
        self._sampler = llama_cpp.llama_sampler_init_grammar(
            llm._model.vocab, llama_grammar.JSON_GBNF.encode("utf-8"), b"root")
        if not self._sampler:
            raise RuntimeError("json_grammar_unavailable")
        self.full_passes = 0
        self.tokens = 0
        self.temperature = float(temperature)
        self._rng = np.random.default_rng()

    def __call__(self, _input_ids: Any, scores: Any) -> Any:
        best = draw_token(scores, self.temperature, self._rng)
        if not self._is_valid(best, float(scores[best])):
            # The pick is not valid JSON here: let the grammar rule out every invalid token and pick again.
            self.full_passes += 1
            self._rule_out_invalid(scores)
            best = draw_token(scores, self.temperature, self._rng)
        self._accept(best)
        self.tokens += 1
        if self.temperature > 0.0:
            # The sampler after this processor must take exactly the token that was checked and accepted.
            logit = scores[best]
            scores[:] = _NEG_INF
            scores[best] = logit
        return scores

    def _apply(self, data: np.ndarray) -> None:
        api = self._api
        array = api.llama_token_data_array(
            data=data.ctypes.data_as(api.llama_token_data_p), size=len(data), selected=-1, sorted=False)
        api.llama_sampler_apply(self._sampler, ctypes.byref(array))

    def _is_valid(self, token: int, logit: float) -> bool:
        one = np.zeros(1, dtype=_TOKEN_DATA)
        one["id"], one["logit"] = token, logit
        self._apply(one)
        return float(one["logit"][0]) != _NEG_INF

    def _rule_out_invalid(self, scores: Any) -> None:
        every = np.zeros(len(scores), dtype=_TOKEN_DATA)
        every["id"] = np.arange(len(scores), dtype=np.intc)
        every["logit"] = scores
        self._apply(every)
        scores[:] = every["logit"]

    def _accept(self, token: int) -> None:
        self._api.llama_sampler_accept(self._sampler, token)

    def close(self) -> None:
        if self._sampler:
            self._api.llama_sampler_free(self._sampler)
            self._sampler = None

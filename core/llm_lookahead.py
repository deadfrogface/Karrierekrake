"""The same JSON answer in less time: evaluate the predictable scaffolding in one batch.

More than half of an extraction answer is JSON scaffolding (key names, brackets, indentation), and in a list
of records it repeats from record to record. One token at a time is the slowest way to run a model on a CPU:
the same tokens in one batch take about a third of the time.

After a value ends, this generator looks up what followed the same field in the previous record, feeds those
tokens to the model in one batch together with the token just chosen, and then checks every one of them: the
model's own choice at each position must be exactly the token that was guessed. The first position where it
is not ends the run, the model's choice is used there, and the tokens evaluated after it are taken back out of
the model's memory. So the answer is token for token the one the model writes on its own; a wrong guess only
costs the time of the tokens thrown away.

Greedy choice only (temperature 0), which is how documents are read.
"""
from __future__ import annotations

import bisect
from typing import Any, Callable, Iterator

GUESS_LIMIT = 24   # tokens per run; scaffolding between two values is rarely longer
_LITERAL = frozenset(b"-+.0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
_LITERAL_START = frozenset(b"-0123456789tfn")
_QUOTE, _BACKSLASH = ord('"'), ord("\\")


def leaf_values(text: bytes) -> list[tuple[tuple, int, int]]:
    """Finished values that are not containers, as ``(field, start, end)`` in reading order.

    ``field`` names the place of the value without its position in a list: the list or object it sits in, the
    nesting depth and its key (``#`` for a list element). ``start`` is the first content byte (after the opening
    quote of a string) and ``end`` one past the value (after the closing quote). An unfinished value at the end
    of ``text`` is not reported.
    """
    leaves: list[tuple[tuple, int, int]] = []
    stack: list[tuple[int, bytes]] = []   # (kind, name): kind is ord("{") or ord("["), name the key it sits under
    key: bytes | None = None
    expect_key = False
    i, n = 0, len(text)

    def field() -> tuple:
        if not stack:
            return (b"", 0, b"")
        kind, name = stack[-1]
        return (name, len(stack), (key or b"") if kind == 0x7B else b"#")

    while i < n:
        c = text[i]
        if c == _QUOTE:
            j = i + 1
            while j < n and text[j] != _QUOTE:
                j += 2 if text[j] == _BACKSLASH else 1
            if j >= n:
                break
            if stack and stack[-1][0] == 0x7B and expect_key:
                key, expect_key = text[i + 1:j], False
            else:
                leaves.append((field(), i + 1, j + 1))
            i = j + 1
        elif c in (0x7B, 0x5B):   # { [
            name = (key or b"") if (stack and stack[-1][0] == 0x7B) else (stack[-1][1] if stack else b"")
            stack.append((c, name))
            key, expect_key = None, c == 0x7B
            i += 1
        elif c in (0x7D, 0x5D):   # } ]
            if stack:
                stack.pop()
            key, expect_key = None, False
            i += 1
        elif c == 0x2C:           # ,
            expect_key = bool(stack) and stack[-1][0] == 0x7B
            i += 1
        elif c in _LITERAL_START:
            j = i
            while j < n and text[j] in _LITERAL:
                j += 1
            if j >= n:
                break
            leaves.append((field(), i, j))
            i = j
        else:
            i += 1
    return leaves


def scaffold_guess(text: bytes, ids: list[int], ends: list[int], limit: int = GUESS_LIMIT,
                   careful: bool = False) -> list[int]:
    """Tokens that followed the same field the last time, up to the start of the next value.

    ``ids`` are the answer's tokens and ``ends[i]`` the length of ``text`` after token ``i``. Returns ``[]``
    when the answer is not right behind a value, the field has not occurred before, or the earlier scaffolding
    does not continue what has been written since the value ended.

    ``careful`` leaves out every place where the model decides something: whether a list goes on or ends,
    and whether the next value is a text or ``null``. What remains is the next key inside a record and the
    closing bracket of a record. For models where taking a wrong guess back is expensive.
    """
    leaves = leaf_values(text)
    if len(leaves) < 2:
        return []
    field, _start, end = leaves[-1]
    if careful and field[2] == b"#":
        return []   # after a list element the list goes on or ends
    tail = text[end:]
    for index in range(len(leaves) - 2, -1, -1):
        earlier, _s, earlier_end = leaves[index]
        if earlier != field:
            continue
        stop = leaves[index + 1][1]
        scaffold = text[earlier_end:stop]
        if len(scaffold) <= len(tail) or not scaffold.startswith(tail):
            return []
        if careful:
            if text[stop - 1] == _QUOTE:
                stop -= 1                               # text or null is the model's decision
            for mark in (b"}", b"]"):
                closing = text.find(mark, earlier_end + len(tail), stop)
                if closing >= 0:
                    stop = closing + 1                  # what follows a closing bracket is a decision too
        target = earlier_end + len(tail)
        first = bisect.bisect_left(ends, target)
        if first >= len(ends) or ends[first] != target:
            return []   # the earlier text is not split into tokens at this point
        out: list[int] = []
        k = first + 1
        while k < len(ids) and ends[k] <= stop and len(out) < limit:
            out.append(ids[k])
            k += 1
        return out if len(out) > 1 or not careful else []   # one token is not worth a state copy
    return []


def answer_skeleton(model: Any) -> str:
    """An answer of this pydantic model with every field present and one entry per list, laid out like the
    model's own answers. It is only a source for guesses about the scaffolding: every guess is checked."""
    import json
    import types
    import typing

    def shape(annotation: Any) -> Any:
        origin = typing.get_origin(annotation)
        if origin in (typing.Union, types.UnionType):
            inner = [arg for arg in typing.get_args(annotation) if arg is not type(None)]
            return shape(inner[0]) if inner else "x"
        if origin in (list, tuple, set):
            return [shape((typing.get_args(annotation) or (str,))[0])]
        fields = getattr(annotation, "model_fields", None)
        if isinstance(fields, dict):
            return {name: shape(field.annotation) for name, field in fields.items()}
        return "x"

    return json.dumps(shape(model), ensure_ascii=False, indent=2)


def lookahead_tokens(
    first_logits: Any,
    *,
    pick: Callable[[Any], int],
    decode: Callable[[list[int]], Callable[[int], Any]],
    forget: Callable[[int], None],
    piece: Callable[[int], bytes],
    is_end: Callable[[int], bool],
    max_tokens: int,
    stats: dict[str, int] | None = None,
    skeleton: tuple[bytes, list[int], list[int]] | None = None,
    careful: bool = False,
) -> Iterator[tuple[int, bytes]]:
    """Greedy generation with verified look-ahead; yields ``(token, its bytes)``.

    ``pick(logits)`` chooses the next token from the logits after the text so far. ``decode(tokens)`` evaluates
    tokens after everything kept so far and returns ``logits_after(i)`` for each of them. ``forget(k)`` takes
    the last ``k`` evaluated tokens back out of the model's memory. Ends before an end token and after
    ``max_tokens`` tokens (``stats["finish"]`` is then ``"length"``). ``skeleton`` is an earlier text of the
    same shape as ``(text, its tokens, text length after each token)``: guesses for the first record of a list
    and for the fields outside lists come from it.
    """
    stats = stats if stats is not None else {}
    stats.update(tokens=0, guessed=0, accepted=0, batches=0, taken_back=0, finish="stop")
    text, ids, ends = (skeleton[0], list(skeleton[1]), list(skeleton[2])) if skeleton else (b"", [], [])
    before = len(ids)
    max_tokens += before
    current = pick(first_logits)
    while True:
        if is_end(current):
            return
        if len(ids) >= max_tokens:
            stats["finish"] = "length"
            return
        chunk = piece(current)
        text += chunk
        ids.append(current)
        ends.append(len(text))
        stats["tokens"] += 1
        yield current, chunk
        guess = scaffold_guess(text, ids, ends, min(GUESS_LIMIT, max_tokens - len(ids)), careful)
        logits_after = decode([current] + guess)
        stats["batches"] += 1
        stats["guessed"] += len(guess)
        kept = 0
        following = pick(logits_after(0))
        while kept < len(guess) and following == guess[kept]:
            chunk = piece(following)
            text += chunk
            ids.append(following)
            ends.append(len(text))
            stats["tokens"] += 1
            stats["accepted"] += 1
            kept += 1
            yield following, chunk
            following = pick(logits_after(kept))
        if kept < len(guess):
            stats["taken_back"] += 1
            forget(len(guess) - kept)
        current = following


def _tokenized(llm: Any, text: str) -> tuple[bytes, list[int], list[int]] | None:
    data = text.encode("utf-8")
    ids = [int(token) for token in llm.tokenize(data, add_bos=False, special=False)]
    ends, total = [], 0
    for token in ids:
        total += len(llm.detokenize([token]))
        ends.append(total)
    return (data, ids, ends) if total == len(data) else None


def lookahead_chat_chunks(llm: Any, fast_json: Any, max_tokens: int, stats: dict[str, int],
                          skeleton: str = "") -> Iterator[dict]:
    """Chat-completion stream chunks for a prompt that ``llm`` has already evaluated in full."""
    import codecs
    import ctypes

    import llama_cpp
    import numpy as np

    context = llm._ctx
    vocab = llm._model.vocab
    n_vocab = llm.n_vocab()
    state = {"n_past": int(llm.n_tokens)}

    def logits_at(index: int) -> Any:
        pointer = llama_cpp.llama_get_logits_ith(context.ctx, index)
        return np.ctypeslib.as_array(pointer, shape=(n_vocab,)).copy()   # pick may write into it

    # Some models (Qwen3.5) keep a running state next to the attention cache, and evaluated tokens cannot be
    # removed from it. For those the running state is copied before a batch with guesses (about 50 MB, 40 ms)
    # and put back when a guess was wrong.
    removable = bool(llama_cpp.llama_memory_can_shift(context.memory))
    partial = llama_cpp.LLAMA_STATE_SEQ_FLAGS_PARTIAL_ONLY

    def run(tokens: list[int]) -> None:
        llm._batch.set_batch(batch=tokens, n_past=state["n_past"], logits_all=True)
        context.decode(llm._batch)
        state["n_past"] += len(tokens)

    def decode(tokens: list[int]) -> Callable[[int], Any]:
        if not removable and len(tokens) > 1:
            size = llama_cpp.llama_state_seq_get_size_ext(context.ctx, 0, partial)
            copy = (ctypes.c_uint8 * size)()
            if llama_cpp.llama_state_seq_get_data_ext(context.ctx, copy, size, 0, partial) != size:
                raise RuntimeError("lookahead_state_copy_failed")
            state["copy"] = (copy, size, state["n_past"], list(tokens))
        run(tokens)
        return logits_at

    def forget(count: int) -> None:
        if removable:
            state["n_past"] -= count
            if not context.kv_cache_seq_rm(-1, state["n_past"], -1):
                raise RuntimeError("lookahead_rollback_failed")
            return
        copy, size, position, tokens = state["copy"]
        if llama_cpp.llama_state_seq_set_data_ext(context.ctx, copy, size, 0, partial) != size:
            raise RuntimeError("lookahead_state_restore_failed")
        if not context.kv_cache_seq_rm(-1, position, -1):
            raise RuntimeError("lookahead_rollback_failed")
        state["n_past"] = position
        run(tokens[:len(tokens) - count])   # the token chosen by the model and the guesses that were right

    decoder = codecs.getincrementaldecoder("utf-8")(errors="ignore")
    first = logits_at(-1)   # after the last prompt token, from the evaluation that just ended
    for _token, chunk in lookahead_tokens(
        first, pick=fast_json.pick, decode=decode, forget=forget,
        piece=lambda token: llm.detokenize([token]),
        is_end=lambda token: bool(llama_cpp.llama_vocab_is_eog(vocab, token)),
        max_tokens=max_tokens, stats=stats, skeleton=_tokenized(llm, skeleton) if skeleton else None,
        careful=not removable,
    ):
        yield {"choices": [{"delta": {"content": decoder.decode(chunk)}, "finish_reason": None}]}
    yield {"choices": [{"delta": {}, "finish_reason": stats["finish"]}]}

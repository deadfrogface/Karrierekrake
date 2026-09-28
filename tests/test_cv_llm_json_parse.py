"""CV LLM JSON parse must tolerate Qwen think-blocks."""

from __future__ import annotations

import json

import pytest

from core.cv_docpick_import import _parse_extraction_json


def _docpick_parse(text: str) -> dict:
    from docpick.llm.prompt import parse_llm_json

    return parse_llm_json(text)


def test_parse_strips_think_blocks_before_json():
    raw = (
        "<think>planning the extraction...</think>\n"
        '{"name":{"first_name":"Mara","last_name":"König"},'
        '"email":"mara.koenig@example.com","employment":[]}'
    )
    data = _parse_extraction_json(raw, parse_llm_json=_docpick_parse)
    assert data["name"]["first_name"] == "Mara"
    assert data["email"] == "mara.koenig@example.com"


def test_parse_falls_back_when_docpick_parser_rejects_think_prefix():
    def boom(_text: str) -> dict:
        raise json.JSONDecodeError("nope", _text, 0)

    raw = (
        "<think>ignore</think>\n"
        '{"name":{"first_name":"Mara","last_name":"König"},"email":"a@b.c"}'
    )
    data = _parse_extraction_json(raw, parse_llm_json=boom)
    assert data["name"]["last_name"] == "König"


def test_parse_raises_when_no_json():
    with pytest.raises(json.JSONDecodeError):
        _parse_extraction_json("<think>only thoughts</think>", parse_llm_json=_docpick_parse)

"""Unit tests for BaseApplier fill helpers (no real browser)."""

from __future__ import annotations

from apply.base import BaseApplier
from core.config import ApplicationProfile


class _DummyApplier(BaseApplier):
    def _do_apply(self, job, resume_pdf_path, cover_letter_text, profile):
        raise NotImplementedError


class _FakeEl:
    def __init__(self, *, visible: bool = True, value: str = "") -> None:
        self._visible = visible
        self._value = value
        self.filled: str | None = None

    def is_visible(self) -> bool:
        return self._visible

    def input_value(self) -> str:
        return self._value

    def fill(self, text: str) -> None:
        self.filled = text
        self._value = text


class _FakePage:
    def __init__(self, elements: dict[str, _FakeEl]) -> None:
        self._elements = elements

    def query_selector(self, selector: str):
        return self._elements.get(selector)

    def query_selector_all(self, selector: str):
        return []

    def wait_for_selector(self, *args, **kwargs):
        return None


def test_fill_cover_letter_fills_first_visible_empty_textarea():
    ta = _FakeEl(value="")
    page = _FakePage({"textarea[name*='cover']": ta})
    applier = _DummyApplier(page, dry_run=True, submit=False)
    assert applier._fill_cover_letter("Hallo", ["textarea[name*='cover']"]) is True
    assert ta.filled == "Hallo"


def test_fill_cover_letter_skips_when_already_filled():
    ta = _FakeEl(value="already")
    page = _FakePage({"textarea": ta})
    applier = _DummyApplier(page, dry_run=True, submit=False)
    assert applier._fill_cover_letter("Neu", ["textarea"]) is False
    assert ta.filled is None


def test_fill_identity_fields_writes_name_email_phone():
    first = _FakeEl()
    last = _FakeEl()
    email = _FakeEl()
    phone = _FakeEl()
    page = _FakePage(
        {
            "input[name*='first']": first,
            "input[name*='last']": last,
            "input[type='email']": email,
            "input[type='tel']": phone,
        }
    )
    # _safe_fill uses human_type path which needs input_value empty after fill attempt;
    # FakeEl.fill works via exception path when input_value check fails differently.
    # Force fill by making human_type path fall through: empty value then fill.
    applier = _DummyApplier(page, dry_run=True, submit=False)

    def _noop_pause(*_a, **_k):
        return None

    applier._random_pause = _noop_pause  # type: ignore[method-assign]
    applier._human_type = lambda el, value: el.fill(value)  # type: ignore[method-assign]

    profile = ApplicationProfile(
        first_name="Ada",
        last_name="Lovelace",
        email="ada@example.com",
        phone="+491234",
    )
    assert (
        applier._fill_identity_fields(
            profile,
            first_name="input[name*='first']",
            last_name="input[name*='last']",
            email="input[type='email']",
            phone="input[type='tel']",
        )
        is True
    )
    assert first.filled == "Ada"
    assert last.filled == "Lovelace"
    assert email.filled == "ada@example.com"
    assert phone.filled == "+491234"


def test_consent_auto_check_skips_bare_required_checkbox():
    """Only privacy/consent-named boxes are auto-checked — not every required checkbox."""
    import inspect

    from apply import base as base_mod

    src = inspect.getsource(base_mod.BaseApplier._fill_german_profile_fields)
    assert "privacy" in src
    assert "consent" in src or "datenschutz" in src
    assert "input[type='checkbox'][required]" not in src


def test_fast_fill_has_no_character_delay(monkeypatch):
    from unittest.mock import Mock
    element = _FakeEl()
    applier = _DummyApplier(_FakePage({}))
    monkeypatch.setattr('apply.base.time.sleep', Mock(side_effect=AssertionError('artificial delay')))
    applier._human_type(element, 'A long application field ' * 30)
    assert element.filled == 'A long application field ' * 30

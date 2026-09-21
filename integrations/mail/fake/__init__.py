"""Fake in-process mail package."""

from integrations.mail.fake.adapter import FakeInProcessMailAdapter, fake_providers_allowed

__all__ = ["FakeInProcessMailAdapter", "fake_providers_allowed"]

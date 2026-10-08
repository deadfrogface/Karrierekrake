import pytest

from core.ai_chat_bridge import (
    BEGIN, END, CHAT_URLS, build_chat_prompt, extract_chat_letter, provider_chat_url,
)
from core.ai_provider_contract import AiProvider, AiProviderChoice, provider_requires_api_key


@pytest.mark.parametrize("provider", list(CHAT_URLS))
def test_chat_bridge_roundtrip(provider):
    prompt = build_chat_prompt(
        verified_profile="Erfahrung in Kundenservice",
        job_description="Kundendienstleitung gesucht",
        provider=provider,
    )
    assert "Erfahrung in Kundenservice" in prompt
    assert "Kundendienstleitung gesucht" in prompt
    assert provider_chat_url(provider).startswith("https://")
    assert extract_chat_letter(f"Vorbemerkung\n{BEGIN}\nSehr geehrte Damen und Herren,\n...\n{END}") == (
        "Sehr geehrte Damen und Herren,\n..."
    )


def test_chat_bridge_rejects_unmarked_or_empty_answer():
    with pytest.raises(ValueError):
        extract_chat_letter("Hier ist Ihr Anschreiben")
    with pytest.raises(ValueError):
        extract_chat_letter(f"{BEGIN} {END}")


def test_remote_provider_requires_explicit_upload_consent():
    assert not provider_requires_api_key(AiProvider.LOCAL_QWEN)
    assert provider_requires_api_key(AiProvider.OPENAI)
    with pytest.raises(PermissionError):
        AiProviderChoice(provider=AiProvider.OPENAI).validate()
    AiProviderChoice(
        provider=AiProvider.OPENAI,
        allow_remote_processing=True,
        user_confirmed_personal_data_upload=True,
    ).validate()

from core.security.redaction import scrub_mapping


def test_nested_list_secrets_are_scrubbed():
    payload = {"entries": [
        {"access_token": "secret-value", "note": "Bearer secret-value"},
        {"details": {"refresh_token": "refresh-value"}},
    ]}
    result = scrub_mapping(payload)
    assert result["entries"][0]["access_token"] == "[REDACTED]"
    assert result["entries"][1]["details"]["refresh_token"] == "[REDACTED]"
    assert "secret-value" not in str(result)


def test_nested_input_is_not_modified():
    payload = {"entries": [{"access_token": "abc"}]}
    scrub_mapping(payload)
    assert payload["entries"][0]["access_token"] == "abc"

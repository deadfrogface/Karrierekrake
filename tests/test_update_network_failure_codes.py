import requests
from core.app_updates import failure_code


def test_tls_error_is_distinct_from_generic_connectivity():
    assert failure_code(requests.exceptions.SSLError("private data")) == "tls_failed"


def test_interrupted_http_stream_is_distinct():
    assert failure_code(requests.exceptions.ChunkedEncodingError("truncated")) == "connection_interrupted"


def test_timeout_remains_classified():
    assert failure_code(requests.Timeout("timeout")) == "connection_timeout"

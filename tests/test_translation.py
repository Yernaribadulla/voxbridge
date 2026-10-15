import json
import pytest
import requests
from app.translation.lmstudio import LMStudioProvider, TranslationError


class Response:
    def __init__(self, data=None, status=200, raw=None):
        self.status_code = status
        self.raw = json.dumps(data).encode() if raw is None else raw

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def iter_content(self, size):
        for start in range(0, len(self.raw), size):
            yield self.raw[start : start + size]


class Session:
    def __init__(self, response, calls):
        self.response, self.calls = response, calls
        self.trust_env = True

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def request(self, *args, **kwargs):
        self.calls.append((self.trust_env, args, kwargs))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def setup(monkeypatch, response):
    calls = []
    monkeypatch.setattr(
        "app.translation.lmstudio.requests.Session", lambda: Session(response, calls)
    )
    return LMStudioProvider(model="local-model"), calls


def test_translation_contract_no_proxy_no_redirect_and_timeout(monkeypatch):
    provider, calls = setup(
        monkeypatch, Response({"choices": [{"message": {"content": " Привет "}}]})
    )
    assert provider.translate("Hello", "en_ru") == "Привет"
    proxy, args, kwargs = calls[0]
    assert proxy is False
    assert kwargs["allow_redirects"] is False
    assert kwargs["timeout"] == (3, 8)
    assert kwargs["json"]["model"] == "local-model"
    assert kwargs["json"]["messages"][1]["content"] == "Hello"


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"choices": []},
        {"choices": [{"message": {"content": None}}]},
        {"choices": [{"message": {"content": "  "}}]},
    ],
)
def test_invalid_completion_contracts(monkeypatch, data):
    provider, calls = setup(monkeypatch, Response(data))
    with pytest.raises(TranslationError):
        provider.translate("text", "en_ru")


@pytest.mark.parametrize(
    "response",
    [
        Response(raw=b"{broken"),
        Response(raw=b"x" * 524289),
        Response({}, 500),
        Response({}, 307),
        requests.Timeout("secret transcript"),
        requests.ConnectionError("secret transcript"),
    ],
)
def test_service_errors_are_bounded_and_do_not_echo_payload(monkeypatch, response):
    provider, calls = setup(monkeypatch, response)
    with pytest.raises(TranslationError) as error:
        provider.translate("private text", "ru_en")
    assert "private text" not in str(error.value) and "secret transcript" not in str(
        error.value
    )


def test_model_list_and_empty_input(monkeypatch):
    provider, calls = setup(
        monkeypatch, Response({"data": [{"id": "local"}, {"id": None}, "bad"]})
    )
    assert provider.test_connection() == ["local"]
    assert provider.translate("  ", "en_ru") == ""
    assert len(calls) == 1


def test_missing_model_and_unknown_direction_fail_before_network(monkeypatch):
    provider, calls = setup(monkeypatch, Response({}))
    provider.model = ""
    with pytest.raises(TranslationError):
        provider.translate("text", "en_ru")
    with pytest.raises(ValueError):
        provider.translate("text", "unsupported")
    assert calls == []

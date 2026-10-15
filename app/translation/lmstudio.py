"""Bounded LM Studio client. No credentials, cloud fallback or transcript logging."""

import json
import requests
from app.config import validate_endpoint

PROMPTS = {
    "en_ru": "Translate the source text into natural Russian. Preserve meaning, names, gaming terms, slang, tone, and conversational intent. Return only the translation. Do not answer, explain, summarize, or invent context.",
    "ru_en": "Translate the source text into natural conversational English. Preserve intended meaning and tone. Return only the translation. Do not answer, explain, summarize, or invent context.",
}


class TranslationError(RuntimeError):
    pass


class LMStudioProvider:
    def __init__(self, base_url="http://localhost:1234/v1", model="", timeout=8):
        self.base_url = validate_endpoint(base_url)
        self.model = model
        self.timeout = timeout

    def _request(self, route, payload=None):
        try:
            with requests.Session() as session:
                # An environment proxy must not silently receive transcript text.
                session.trust_env = False
                with session.request(
                    "GET" if payload is None else "POST",
                    self.base_url + route,
                    json=payload,
                    timeout=(3, self.timeout),
                    stream=True,
                    allow_redirects=False,
                ) as response:
                    if not 200 <= response.status_code < 300:
                        raise TranslationError(
                            f"LM Studio: HTTP {response.status_code}. Проверьте endpoint и модель."
                        )
                    parts, size = [], 0
                    for chunk in response.iter_content(8192):
                        size += len(chunk)
                        if size > 524288:
                            raise TranslationError(
                                "Ответ LM Studio превышает допустимый размер."
                            )
                        parts.append(chunk)
                    data = json.loads(b"".join(parts))
                    if not isinstance(data, dict):
                        raise ValueError
                    return data
        except requests.Timeout:
            raise TranslationError(
                "LM Studio не ответила вовремя. Проверьте нагрузку и модель."
            ) from None
        except requests.RequestException:
            raise TranslationError(
                "LM Studio недоступна. Проверьте локальный сервер."
            ) from None
        except (ValueError, UnicodeDecodeError):
            raise TranslationError("LM Studio вернула некорректный JSON.") from None

    def translate(self, text, direction):
        if not text.strip():
            return ""
        if direction not in PROMPTS:
            raise ValueError("Unknown translation direction.")
        if not self.model.strip():
            raise TranslationError("Укажите ID модели LM Studio в настройках.")
        data = self._request(
            "/chat/completions",
            {
                "model": self.model,
                "temperature": 0.1,
                "max_tokens": 512,
                "messages": [
                    {"role": "system", "content": PROMPTS[direction]},
                    {"role": "user", "content": text},
                ],
            },
        )
        try:
            content = data["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ValueError
            return content.strip()
        except (KeyError, IndexError, TypeError, ValueError):
            raise TranslationError(
                "LM Studio вернула пустой или неподдерживаемый перевод."
            ) from None

    def test_connection(self):
        data = self._request("/models")
        models = data.get("data")
        if not isinstance(models, list):
            raise TranslationError("Сервер не вернул список моделей LM Studio.")
        return [
            item["id"]
            for item in models
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        ]

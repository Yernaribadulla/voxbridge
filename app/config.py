"""Validated, atomic per-user settings; audio and transcripts are never persisted."""

import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from urllib.parse import urlsplit


def validate_endpoint(value):
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError
        parsed.port
    except (ValueError, TypeError, AttributeError):
        raise ValueError(
            "Укажите HTTP(S) API endpoint без пароля, query или fragment."
        ) from None
    return value.rstrip("/")


@dataclass
class Settings:
    translation_url: str = "http://localhost:1234/v1"
    translation_model: str = ""
    mic_device: str = ""
    system_device: str = ""
    partner_model: str = (
        "base"  # Legacy field; one user_model is shared by both routes.
    )
    user_model: str = "base"
    compute_device: str = "cpu"
    compute_type: str = "int8"
    opacity: float = 0.94
    font_size: int = 22
    history_length: int = 20  # Legacy metadata; persistent history is not implemented.
    persistent_history: bool = False
    ptt_button: str = "x2"


def path():
    return (
        Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
        / "VoxBridge"
        / "settings.json"
    )


def normalize(data):
    result = Settings()
    if not isinstance(data, dict):
        return result
    for item in fields(result):
        value = data.get(item.name, getattr(result, item.name))
        if type(value) is type(getattr(result, item.name)):
            setattr(result, item.name, value)
    try:
        result.translation_url = validate_endpoint(result.translation_url)
    except ValueError:
        result.translation_url = Settings.translation_url
    if result.user_model not in ("base", "small"):
        result.user_model = "base"
    result.partner_model = result.user_model
    if result.compute_device not in ("cpu", "cuda"):
        result.compute_device = "cpu"
    if (
        result.compute_type not in ("int8", "float16", "int8_float16")
        or result.compute_device == "cpu"
    ):
        result.compute_type = "int8"
    if result.ptt_button not in ("x1", "x2"):
        result.ptt_button = "x2"
    result.opacity = (
        max(0.35, min(1.0, result.opacity)) if math.isfinite(result.opacity) else 0.94
    )
    result.font_size = max(14, min(28, result.font_size))
    result.persistent_history = False
    return result


def load(settings_path=None, env=None):
    target = Path(settings_path) if settings_path else path()
    try:
        data = json.loads(target.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        data = {}
    settings = normalize(data)
    environment = os.environ if env is None else env
    if "VOXBRIDGE_TRANSLATION_URL" in environment:
        settings.translation_url = validate_endpoint(
            environment["VOXBRIDGE_TRANSLATION_URL"]
        )
    if "VOXBRIDGE_TRANSLATION_MODEL" in environment:
        settings.translation_model = environment["VOXBRIDGE_TRANSLATION_MODEL"]
    return settings


def save(settings, settings_path=None):
    target = Path(settings_path) if settings_path else path()
    validate_endpoint(settings.translation_url)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix="settings-", suffix=".tmp", dir=target.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(
                asdict(normalize(asdict(settings))),
                stream,
                ensure_ascii=False,
                indent=2,
            )
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

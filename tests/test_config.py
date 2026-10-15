import json
import pytest
from app.config import Settings, load, save, normalize, validate_endpoint


def test_missing_or_corrupt_configuration_uses_defaults(tmp_path):
    target = tmp_path / "settings.json"
    assert load(target, env={}).user_model == "base"
    for text in ("{broken", "[]", "null"):
        target.write_text(text)
        assert load(target, env={}).compute_device == "cpu"


def test_unknown_or_invalid_field_does_not_erase_valid_settings(tmp_path):
    target = tmp_path / "settings.json"
    target.write_text(
        json.dumps(
            {
                "translation_model": "local-model",
                "future_option": True,
                "opacity": float("nan"),
                "font_size": "bad",
                "ptt_button": "unknown",
            }
        )
    )
    result = load(target, env={})
    assert result.translation_model == "local-model"
    assert result.opacity == 0.94 and result.ptt_button == "x2"


def test_roundtrip_and_environment_overrides(tmp_path):
    target = tmp_path / "settings.json"
    settings = Settings(translation_model="модель", mic_device="device", font_size=24)
    save(settings, target)
    result = load(target, env={"VOXBRIDGE_TRANSLATION_MODEL": "override"})
    assert result.translation_model == "override"
    assert result.mic_device == "device" and result.font_size == 24
    assert not result.persistent_history


def test_atomic_save_preserves_previous_file_on_replace_failure(tmp_path, monkeypatch):
    target = tmp_path / "settings.json"
    save(Settings(translation_model="original"), target)

    def fail(*args):
        raise OSError("disk unavailable")

    monkeypatch.setattr("app.config.os.replace", fail)
    with pytest.raises(OSError):
        save(Settings(translation_model="replacement"), target)
    assert load(target, env={}).translation_model == "original"
    assert list(tmp_path.glob("*.tmp")) == []


@pytest.mark.parametrize(
    "endpoint",
    [
        "file:///secret",
        "http://user:pass@localhost/v1",
        "http://[",
        "http://localhost:invalid",
        "ftp://localhost",
        "http://localhost/v1?token=x",
    ],
)
def test_invalid_endpoints_rejected(endpoint):
    with pytest.raises(ValueError):
        validate_endpoint(endpoint)


def test_compute_and_shared_model_normalization():
    result = normalize(
        {
            "compute_device": "cpu",
            "compute_type": "float16",
            "user_model": "tiny.en",
            "persistent_history": True,
        }
    )
    assert result.compute_type == "int8"
    assert result.user_model == result.partner_model == "base"
    assert not result.persistent_history

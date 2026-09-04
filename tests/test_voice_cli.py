from nexus.config import (
    disable_voice_settings,
    load_voice_settings,
    update_voice_settings,
)


def test_voice_settings_default_to_disabled(tmp_path):
    settings = load_voice_settings(env={}, path=tmp_path / "config.local.json")
    assert settings.enabled is False
    assert settings.transcription_provider == "faster_whisper"
    assert settings.transcription_model == "small"
    assert settings.synthesis_provider == "system"
    assert settings.max_record_seconds == 30
    assert settings.max_audio_bytes == 25 * 1024 * 1024


def test_voice_settings_persist_and_disable_transactionally(tmp_path):
    path = tmp_path / "config.local.json"
    saved, returned_path = update_voice_settings(
        enabled=True,
        transcription_model="base",
        language="zh",
        voice="Microsoft Huihui Desktop",
        max_record_seconds=12,
        play_audio=False,
        path=path,
    )
    assert returned_path == path
    assert saved.enabled is True
    assert load_voice_settings(env={}, path=path).language == "zh"
    disabled, _ = disable_voice_settings(path=path)
    assert disabled.enabled is False
    assert disabled.transcription_model == "base"

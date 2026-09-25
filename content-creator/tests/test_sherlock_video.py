import json
from types import SimpleNamespace

from sherlock import gather, models


def fake_run_ok(info):
    def run(cmd, **kwargs):
        return SimpleNamespace(returncode=0, stdout=json.dumps(info), stderr="")
    return run


def test_gather_video_builds_text_from_metadata():
    info = {"title": "3 hábitos", "description": "Descrição do vídeo", "uploader": "Ana",
            "view_count": 1200, "like_count": 90, "comment_count": 5, "tags": ["saúde", "rotina"]}
    result = gather.gather_video("https://www.tiktok.com/@a/video/1", run=fake_run_ok(info))
    assert isinstance(result, models.GatherResult)
    assert result.method == "yt-dlp"
    assert "3 hábitos" in result.text and "Descrição do vídeo" in result.text
    assert "1200" in result.text and "saúde" in result.text


def test_gather_video_appends_transcript_when_available():
    info = {"title": "T", "description": "D"}
    result = gather.gather_video("https://youtu.be/x", run=fake_run_ok(info), transcribe=lambda url: "olá a todos")
    assert result.method == "yt-dlp+whisper"
    assert "olá a todos" in result.text


def test_gather_video_returns_needs_upload_when_ytdlp_fails():
    def run(cmd, **kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="ERROR: bloqueado")

    result = gather.gather_video("https://www.tiktok.com/@a", run=run)
    assert isinstance(result, models.NeedsUpload)
    assert "bloqueado" in result.reason


def test_gather_video_returns_needs_upload_when_ytdlp_missing():
    def run(cmd, **kwargs):
        raise FileNotFoundError("yt-dlp")

    result = gather.gather_video("https://youtu.be/x", run=run)
    assert isinstance(result, models.NeedsUpload)


def test_whisper_transcribe_returns_none_when_whisper_not_installed(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "whisper":
            raise ImportError("no whisper")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert gather.whisper_transcribe("https://youtu.be/x") is None


def test_gather_video_uses_utf8_and_keeps_accents():
    seen = {}

    def run(cmd, **kwargs):
        seen.update(kwargs)
        return SimpleNamespace(returncode=0, stdout=json.dumps({"title": "3 hábitos"}), stderr="")

    result = gather.gather_video("https://youtu.be/x", run=run)
    assert seen["encoding"] == "utf-8" and seen["errors"] == "replace"
    assert "3 hábitos" in result.text


def test_gather_video_returns_needs_upload_on_bad_json():
    for out in ("não é json", None):
        def run(cmd, out=out, **kwargs):
            return SimpleNamespace(returncode=0, stdout=out, stderr="")

        assert isinstance(gather.gather_video("https://youtu.be/x", run=run), models.NeedsUpload)


def test_gather_video_null_fields_do_not_render_none():
    info = {"title": None, "uploader": None, "description": None}
    result = gather.gather_video("https://youtu.be/x", run=fake_run_ok(info))
    assert "None" not in result.text

import json
import subprocess
from types import SimpleNamespace

import pytest

from sherlock import gather, models


@pytest.fixture(autouse=True)
def _reset_transcribe_worker_state():
    """whisper_transcribe tracks its last worker thread in module state (finding A)
    so overlapping transcriptions bail out. Reset it around every test so a slow
    fake model left running by one test can't make the next test see a "worker
    still alive" false positive."""
    gather._transcribe_state["worker"] = None
    yield
    gather._transcribe_state["worker"] = None


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
        return SimpleNamespace(returncode=1, stdout="", stderr="ERROR: bloqueado https://secret.example/token=abc")

    result = gather.gather_video("https://www.tiktok.com/@a", run=run)
    assert isinstance(result, models.NeedsUpload)
    assert "bloqueado" not in result.reason
    assert result.reason == gather.VIDEO_FAIL_REASON


def test_gather_video_argv_has_separator_before_url_and_playlist_guards():
    seen = {}

    def run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen.update(kwargs)
        return SimpleNamespace(returncode=0, stdout=json.dumps({"title": "T"}), stderr="")

    url = "https://youtu.be/x"
    gather.gather_video(url, run=run)
    assert seen["cmd"][-2:] == ["--", url]
    assert "--no-playlist" in seen["cmd"]
    assert "--playlist-items" in seen["cmd"]
    assert seen["timeout"] == gather.METADATA_TIMEOUT


def test_gather_video_rejects_a_non_http_scheme():
    def run(cmd, **kwargs):
        raise AssertionError("yt-dlp must not be invoked for a blocked scheme")

    result = gather.gather_video("file:///etc/passwd", run=run)
    assert isinstance(result, models.NeedsUpload)
    assert result.reason == gather.VIDEO_BAD_SOURCE_REASON


def test_gather_video_accepts_scheme_less_links_by_normalizing_first():
    seen = {}

    def run(cmd, **kwargs):
        seen["cmd"] = cmd
        return SimpleNamespace(returncode=0, stdout=json.dumps({"title": "T"}), stderr="")

    cases = [
        ("youtu.be/x", "https://youtu.be/x"),
        ("www.youtube.com/watch?v=x", "https://www.youtube.com/watch?v=x"),
        ("tiktok.com/@a/video/1", "https://tiktok.com/@a/video/1"),
    ]
    for raw, normalized in cases:
        result = gather.gather_video(raw, run=run)
        assert isinstance(result, models.GatherResult), f"{raw!r} should be accepted"
        assert seen["cmd"][-2:] == ["--", normalized]
        assert result.source == raw


def test_gather_video_returns_needs_upload_on_timeout():
    def run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout"))

    result = gather.gather_video("https://youtu.be/x", run=run)
    assert isinstance(result, models.NeedsUpload)
    assert result.reason == gather.VIDEO_TIMEOUT_REASON


def test_gather_video_returns_needs_upload_when_json_is_not_an_object():
    for out in ("[]", "null", "5"):
        def run(cmd, out=out, **kwargs):
            return SimpleNamespace(returncode=0, stdout=out, stderr="")

        assert isinstance(gather.gather_video("https://youtu.be/x", run=run), models.NeedsUpload)


def test_gather_video_returns_needs_upload_when_ytdlp_missing():
    def run(cmd, **kwargs):
        raise FileNotFoundError("yt-dlp")

    result = gather.gather_video("https://youtu.be/x", run=run)
    assert isinstance(result, models.NeedsUpload)
    assert "yt-dlp" not in result.reason.lower()


def test_gather_video_reasons_never_mention_yt_dlp():
    # yt-dlp is jargon in user-facing text (brief principle 3): every NeedsUpload
    # reason gather_video can produce must stay tool-name-free.
    scenarios = [
        (lambda cmd, **kw: SimpleNamespace(returncode=1, stdout="", stderr="ERROR: x")),
        (lambda cmd, **kw: (_ for _ in ()).throw(FileNotFoundError("yt-dlp"))),
        (lambda cmd, **kw: SimpleNamespace(returncode=0, stdout="not json", stderr="")),
        (lambda cmd, **kw: SimpleNamespace(returncode=0, stdout="[]", stderr="")),
    ]
    for run in scenarios:
        result = gather.gather_video("https://youtu.be/x", run=run)
        assert isinstance(result, models.NeedsUpload)
        assert "yt-dlp" not in result.reason.lower()


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


def test_whisper_transcribe_success_path(monkeypatch):
    import sys

    class FakeModel:
        def transcribe(self, path):
            return {"text": "  olá mundo  "}

    fake_whisper = SimpleNamespace(load_model=lambda name: FakeModel())
    monkeypatch.setitem(sys.modules, "whisper", fake_whisper)

    def run(cmd, **kwargs):
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    assert gather.whisper_transcribe("https://youtu.be/x", run=run) == "olá mundo"


def test_whisper_transcribe_returns_none_when_download_fails(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "whisper", SimpleNamespace(load_model=lambda name: None))

    def run(cmd, **kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="x")

    assert gather.whisper_transcribe("https://youtu.be/x", run=run) is None


def test_whisper_transcribe_argv_has_separator_before_url_and_playlist_guards(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "whisper", SimpleNamespace(load_model=lambda name: None))
    seen = {}

    def run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen.update(kwargs)
        return SimpleNamespace(returncode=1, stdout="", stderr="")

    url = "https://youtu.be/x"
    gather.whisper_transcribe(url, run=run)
    assert seen["cmd"][-2:] == ["--", url]
    assert "--no-playlist" in seen["cmd"]
    assert seen["timeout"] == gather.AUDIO_TIMEOUT


def test_whisper_transcribe_returns_none_on_timeout(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "whisper", SimpleNamespace(load_model=lambda name: None))

    def run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout"))

    assert gather.whisper_transcribe("https://youtu.be/x", run=run) is None


def test_whisper_transcribe_returns_none_when_transcription_times_out(monkeypatch):
    import sys
    import time

    monkeypatch.setattr(gather, "TRANSCRIBE_TIMEOUT", 0.05)

    class SlowModel:
        def transcribe(self, path):
            time.sleep(1)
            return {"text": "nunca chega"}

    monkeypatch.setitem(sys.modules, "whisper", SimpleNamespace(load_model=lambda name: SlowModel()))

    def run(cmd, **kwargs):
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    assert gather.whisper_transcribe("https://youtu.be/x", run=run) is None


def test_whisper_transcribe_worker_exception_does_not_reach_excepthook(monkeypatch):
    import sys
    import threading

    excepthook_calls = []
    monkeypatch.setattr(threading, "excepthook", lambda args: excepthook_calls.append(args))

    class BoomModel:
        def transcribe(self, path):
            raise RuntimeError("o modelo rebentou")

    monkeypatch.setitem(sys.modules, "whisper", SimpleNamespace(load_model=lambda name: BoomModel()))

    def run(cmd, **kwargs):
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    assert gather.whisper_transcribe("https://youtu.be/x", run=run) is None
    assert excepthook_calls == []


def test_whisper_transcribe_returns_none_immediately_if_a_previous_worker_is_still_alive(monkeypatch):
    import sys
    import threading
    import time

    monkeypatch.setattr(gather, "TRANSCRIBE_TIMEOUT", 0.05)
    started = threading.Event()

    class SlowModel:
        def transcribe(self, path):
            started.set()
            time.sleep(0.3)  # still running well after TRANSCRIBE_TIMEOUT elapses
            return {"text": "nunca chega"}

    monkeypatch.setitem(sys.modules, "whisper", SimpleNamespace(load_model=lambda name: SlowModel()))

    calls = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    # First call times out, but its worker thread is still running in the background.
    assert gather.whisper_transcribe("https://youtu.be/x", run=run) is None
    assert started.wait(1), "the worker never started"

    calls_before = len(calls)
    # Second call must see the still-alive worker and bail out without running yt-dlp again.
    assert gather.whisper_transcribe("https://youtu.be/x", run=run) is None
    assert len(calls) == calls_before

    gather._transcribe_state["worker"].join(2)  # let the slow worker finish before the test ends


def test_whisper_transcribe_survives_tempdir_cleanup_errors(monkeypatch):
    import sys

    class FakeModel:
        def transcribe(self, path):
            return {"text": "transcrição boa"}

    monkeypatch.setitem(sys.modules, "whisper", SimpleNamespace(load_model=lambda name: FakeModel()))

    class FakeTempDir:
        def __init__(self, ignore_cleanup_errors=False):
            self.ignore_cleanup_errors = ignore_cleanup_errors

        def __enter__(self):
            return "tmp"

        def __exit__(self, *a):
            if not self.ignore_cleanup_errors:
                raise PermissionError("ficheiro em uso pelo ffmpeg")
            return False

    monkeypatch.setattr(gather.tempfile, "TemporaryDirectory", FakeTempDir)

    def run(cmd, **kwargs):
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    assert gather.whisper_transcribe("https://youtu.be/x", run=run) == "transcrição boa"


def test_gather_video_treats_raising_transcribe_as_no_transcript():
    def boom(url):
        raise RuntimeError("whisper rebentou")

    result = gather.gather_video("https://youtu.be/x", run=fake_run_ok({"title": "T"}), transcribe=boom)
    assert isinstance(result, models.GatherResult)
    assert result.method == "yt-dlp"
    assert "Título: T" in result.text


def test_gather_video_truncation_keeps_metadata_and_cuts_transcript():
    info = {"title": "T", "description": "D", "tags": ["a", "b"]}
    result = gather.gather_video("https://youtu.be/x", run=fake_run_ok(info), transcribe=lambda url: "x" * 50000)
    assert len(result.text) <= gather.MAX_CHARS
    assert result.text.startswith(gather._video_text(info))
    assert "Transcrição:" in result.text


def test_gather_video_drops_transcript_when_metadata_fills_the_limit(monkeypatch):
    monkeypatch.setattr(gather, "MAX_CHARS", 50)
    info = {"title": "T" * 100, "description": "D"}
    result = gather.gather_video("https://youtu.be/x", run=fake_run_ok(info), transcribe=lambda url: "transcrição")
    assert result.method == "yt-dlp"
    assert "Transcrição:" not in result.text
    assert len(result.text) <= 50
    assert result.text == gather._video_text(info)[:50]


def test_gather_video_runs_ytdlp_through_the_current_python():
    # "yt-dlp" is only on PATH when the venv is activated; running it as a module of
    # the interpreter the app already uses works regardless.
    import sys

    seen = []

    def run(cmd, **kwargs):
        seen.append(cmd)
        return SimpleNamespace(returncode=0, stdout=json.dumps({"title": "t" * 300}), stderr="")

    gather.gather_video("https://youtu.be/x", run=run)
    assert seen[0][:3] == [sys.executable, "-m", "yt_dlp"]

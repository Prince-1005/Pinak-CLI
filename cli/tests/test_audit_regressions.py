"""Regression evidence for the audit's security and state-preservation contracts."""

from __future__ import annotations

import json
import os
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

import pinak.config as settings
import pinak.downloader as downloads
import pinak.history as history
from pinak.commands.run import run_single
from pinak.media.core.input_parser import KeyEvent
from pinak.media.decoders.image_loader import ImageLoader
from pinak.media.ipc.client import MediaIPCClient
from pinak.media.ipc.server import MediaIPCServer
from pinak.media.picker.tui_picker import TUIMediaPicker
from pinak.media.player.coordinator import MediaSession
from pinak.media.player.playlist import PlaylistManager
from pinak.media.player.transport import TransportController


def test_environment_overrides_are_temporary(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text('{"quality":"720p"}')
    monkeypatch.setattr(settings, "CONFIG_FILE", str(path))
    monkeypatch.setattr(settings, "config", settings.PinakSettings.model_construct().model_dump())
    monkeypatch.setenv("PINAK_QUALITY", "360p")
    assert settings.init_config()["quality"] == "360p"
    assert settings.save_config({"retry_count": 7})
    assert json.loads(path.read_text())["quality"] == "720p"
    assert settings.config["quality"] == "360p"


def test_two_processes_merge_configuration_changes(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{}")
    code = """
import pathlib, sys, time
import pinak.config as c
c.CONFIG_FILE = sys.argv[1]
c.init_config()
root = pathlib.Path(sys.argv[1]).parent
(root / sys.argv[2]).touch()
deadline = time.monotonic() + 10
while not (root / 'a').exists() or not (root / 'b').exists():
    if time.monotonic() > deadline: raise RuntimeError('barrier timeout')
    time.sleep(.01)
assert c.save_config({sys.argv[3]: sys.argv[4]})
"""
    env = {k: v for k, v in os.environ.items() if not k.startswith("PINAK_")}
    processes = [
        subprocess.Popen([sys.executable, "-c", code, str(path), *args], env=env)
        for args in (("a", "quality", "720p"), ("b", "retry_count", "7"))
    ]
    try:
        assert all(p.wait(timeout=15) == 0 for p in processes)
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.wait()
    result = json.loads(path.read_text())
    assert result["quality"] == "720p" and result["retry_count"] == 7


def test_failed_history_mutations_report_failure(monkeypatch):
    monkeypatch.setattr(
        history, "get_db_connection", MagicMock(side_effect=sqlite3.OperationalError("disk full"))
    )
    assert history.clear_all_history() is False
    assert history.delete_history_by_ids([1]) is False


def test_endpoint_discovery_ignores_stale_and_requires_selection(tmp_path, monkeypatch):
    from pinak.media.ipc import endpoint

    monkeypatch.setattr(endpoint, "endpoint_directory", lambda: tmp_path)
    monkeypatch.delenv("PINAK_IPC_PORT", raising=False)
    monkeypatch.setattr(endpoint, "_process_alive", lambda pid: pid == os.getpid())
    (tmp_path / "session-1.json").write_text('{"pid":0,"port":1,"token":"stale"}')
    first = endpoint.publish_endpoint(23450, "first")
    assert endpoint.discover_endpoint() == (23450, "first")
    second = endpoint.publish_endpoint(23451, "second")
    with pytest.raises(ConnectionError):
        endpoint.discover_endpoint()
    monkeypatch.setenv("PINAK_IPC_PORT", "23451")
    assert endpoint.discover_endpoint() == (23451, "second")
    first.unlink()
    second.unlink()


def test_ipc_oversized_frame_and_shutdown(tmp_path, monkeypatch):
    from pinak.media.ipc import endpoint

    monkeypatch.setattr(endpoint, "endpoint_directory", lambda: tmp_path)
    session = SimpleNamespace(transport=TransportController(), audio_backend=None)
    server = MediaIPCServer(session, port=0)
    port = server.start()
    client = socket.create_connection(("127.0.0.1", port), timeout=2)
    try:
        client.sendall(b"x" * (server.max_message_bytes + 1))
        assert client.recv(4096) == b""  # close oversized frames before parsing
    finally:
        client.close()
        started = time.monotonic()
        server.stop()
        assert time.monotonic() - started < 3


def test_audio_driver_failure_falls_back_and_marks_eof(tmp_path, monkeypatch):
    from pinak.media.decoders.audio_backend import AudioPlayerBackend

    path = tmp_path / "short.wav"
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(48000)
        wav.writeframes(b"\x00\x00" * 20)
    calls = []
    backend = AudioPlayerBackend(path, driver="broken")
    monkeypatch.setattr(backend, "available_drivers", lambda: ["broken", "working"])
    original = backend._stream

    def stream(driver, start, generation, cancelled):
        calls.append(driver)
        if driver == "broken":
            raise OSError("device unavailable")
        backend._driver = driver
        backend._eos = True

    monkeypatch.setattr(backend, "_stream", stream)
    backend.play()
    backend._worker.join(timeout=2)
    assert calls == ["broken", "working"]
    assert backend.is_eos and backend.error is None
    backend.stop()
    monkeypatch.setattr(backend, "_stream", original)


def test_unknown_duration_uses_output_eof(tmp_path):
    path = tmp_path / "music.wav"
    path.touch()
    session = MediaSession([path], enable_consent_prompt=False)
    session.transport.duration_sec = 0
    session.audio_backend = MagicMock(error=None, is_eos=True)
    session.master_clock = MagicMock(get_time=lambda: 0.2)
    session._render_media_tui(80, 24, 0.01)
    assert session.transport.is_playing is False


def test_queued_controls_are_cancelled_on_teardown(tmp_path):
    path = tmp_path / "music.wav"
    path.touch()
    session = MediaSession([path], enable_consent_prompt=False)
    ready = threading.Event()
    result = {}
    session._ipc_requests.put((session._control_generation, "{}", ready, result))
    session._teardown_media_components()
    assert ready.is_set() and result["error"] == "media session changed"


def test_future_video_frame_waits_for_the_clock(tmp_path):
    from pinak.media.decoders.video_decoder import DecodedVideoFrame

    path = tmp_path / "movie.mp4"
    path.touch()
    session = MediaSession([path], enable_consent_prompt=False)
    frame = DecodedVideoFrame(1.0, 16, 16, b"\x00" * 768)
    session.video_decoder = MagicMock(error=None, eof=False, target_fps=30)
    session.video_decoder.read_frame.return_value = frame
    session.master_clock = MagicMock(get_time=lambda: 0.9)
    session._render_media_tui(80, 24, 0.01)
    assert session._last_video_img is None and session._holding_future_frame
    session.master_clock.get_time = lambda: 1.0
    session._render_media_tui(80, 24, 0.01)
    assert session._last_video_img is not None and not session._holding_future_frame


def test_short_audio_does_not_end_a_longer_video(tmp_path):
    from pinak.media.decoders.audio_backend import AudioPlayerBackend
    from pinak.media.sync.clock import MasterAudioClock

    path = tmp_path / "movie.mp4"
    path.touch()
    session = MediaSession([path], enable_consent_prompt=False)
    session.transport.duration_sec = 5
    backend = AudioPlayerBackend(path, driver="mock")
    backend._elapsed_offset = 1
    backend._eos = True
    session.audio_backend = backend
    session.master_clock = MasterAudioClock(backend)
    session.video_decoder = MagicMock(error=None, eof=False, target_fps=30)
    session.video_decoder.read_frame.return_value = None
    session._render_media_tui(80, 24, 0.01)
    assert session.master_clock.audio_backend is None
    assert session.transport.is_playing and session.transport.current_pts >= 1


def test_video_eof_waits_for_the_last_frame_interval(tmp_path):
    from pinak.media.decoders.video_decoder import DecodedVideoFrame

    path = tmp_path / "movie.mp4"
    path.touch()
    session = MediaSession([path], enable_consent_prompt=False)
    session.video_decoder = MagicMock(error=None, eof=True, target_fps=30, _frame_queue=[])
    session.video_decoder.read_frame.return_value = None
    session._buffered_video_frame = DecodedVideoFrame(1, 16, 16, b"\x00" * 768)
    session._last_frame_pts = 1
    session.master_clock = MagicMock(get_time=lambda: 1.01)
    session._render_media_tui(80, 24, 0.01)
    assert session.transport.is_playing


def test_probe_tolerates_missing_numeric_fields_and_cover_art(tmp_path, monkeypatch):
    from pinak.media.decoders import probe

    binary = tmp_path / "ffprobe"
    binary.touch()
    monkeypatch.setattr(probe, "ensure_ffprobe", lambda: str(binary))
    output = {
        "streams": [
            {"codec_type": "video", "disposition": {"attached_pic": 1}, "width": "N/A"},
            {"codec_type": "audio", "sample_rate": "N/A", "channels": None},
        ],
        "format": {"duration": "NaN", "tags": {"title": "track"}},
    }
    monkeypatch.setattr(
        probe.subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(returncode=0, stdout=json.dumps(output)),
    )
    meta = probe.MediaProbe._probe_with_ffprobe(tmp_path / "song.mp3", 100)
    assert meta.media_type == "audio" and meta.duration_seconds == 0
    assert meta.channels == 0 and meta.sample_rate == 0 and meta.title == "track"


def test_probe_reads_video_stream_duration_without_format_duration(tmp_path, monkeypatch):
    from pinak.media.decoders import probe

    binary = tmp_path / "ffprobe"
    binary.touch()
    monkeypatch.setattr(probe, "ensure_ffprobe", lambda: str(binary))
    output = {
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "duration": "12.5",
                "width": "1920",
                "height": "1080",
                "nb_frames": "N/A",
                "avg_frame_rate": "N/A",
                "r_frame_rate": "30000/1001",
            },
            {"codec_type": "audio", "sample_rate": "48000", "channels": "2"},
        ],
        "format": {
            "duration": "N/A",
            "tags": {"title": "movie", "artist": "artist", "album": "album"},
        },
    }
    monkeypatch.setattr(
        probe.subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(returncode=0, stdout=json.dumps(output)),
    )
    meta = probe.MediaProbe._probe_with_ffprobe(tmp_path / "movie.mp4", 100)
    assert meta.media_type == "video" and meta.duration_seconds == 12.5
    assert (meta.width, meta.height, meta.channels, meta.sample_rate) == (1920, 1080, 2, 48000)
    assert meta.fps == pytest.approx(29.97003)


@pytest.mark.parametrize(
    "payload", ["[]", '{"streams":null}', '{"streams":[null],"format":null}', "invalid"]
)
def test_malformed_probe_output_is_safe(tmp_path, monkeypatch, payload):
    from pinak.media.decoders import probe

    binary = tmp_path / "ffprobe"
    binary.touch()
    monkeypatch.setattr(probe, "ensure_ffprobe", lambda: str(binary))
    monkeypatch.setattr(
        probe.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=0, stdout=payload)
    )
    result = probe.MediaProbe._probe_with_ffprobe(tmp_path / "movie.mp4", 100)
    assert result is None or result.duration_seconds == 0


def test_port_collision_discovery_uses_the_actual_listener(tmp_path, monkeypatch):
    from pinak.media.ipc import endpoint

    monkeypatch.setattr(endpoint, "endpoint_directory", lambda: tmp_path)
    monkeypatch.delenv("PINAK_IPC_PORT", raising=False)
    blocker = socket.socket()
    blocker.bind(("127.0.0.1", 0))
    blocker.listen()
    server = MediaIPCServer(
        SimpleNamespace(transport=TransportController(), audio_backend=None),
        port=blocker.getsockname()[1],
    )
    try:
        assert server.start() != blocker.getsockname()[1]
        client = MediaIPCClient()
        assert client.send_command("get_property", "duration") == {
            "error": "success",
            "data": 0,
        }
    finally:
        server.stop()
        blocker.close()


def test_metadata_is_not_a_successful_download(tmp_path, monkeypatch):
    fake = MagicMock()
    fake.extract_info.return_value = {"title": "no file"}
    fake.prepare_filename.return_value = str(tmp_path / "absent.mp4")
    fake.__enter__.return_value = fake
    monkeypatch.setattr(downloads.yt_dlp, "YoutubeDL", lambda _: fake)
    monkeypatch.setattr(downloads, "ffmpeg_available", lambda: False)
    result = downloads.download_media_content("https://example.com/media", str(tmp_path))
    assert result["success"] is False
    assert result["files"] == []


def test_partials_and_directories_are_never_media(tmp_path):
    partial = tmp_path / "clip.mp4.part"
    partial.write_bytes(b"unfinished")
    sidecar = tmp_path / "clip.info.json"
    sidecar.write_text("{}")
    valid, rejected = downloads.verify_files([str(partial), str(sidecar), str(tmp_path)])
    assert valid == []
    assert len(rejected) == 3


def test_busy_database_is_not_quarantined(tmp_path, monkeypatch):
    database = tmp_path / "history.db"
    database.write_bytes(b"original")
    monkeypatch.setattr(history, "DB_FILE", str(database))
    monkeypatch.setattr(
        history.sqlite3, "connect", MagicMock(side_effect=sqlite3.OperationalError("locked"))
    )
    with pytest.raises(sqlite3.OperationalError):
        history.get_db_connection()
    assert database.read_bytes() == b"original"
    assert not list(tmp_path.glob("*.corrupt.*"))


def test_dry_run_does_not_save_or_mutate_overrides(tmp_path, capsys):
    before = settings.config.copy()
    with patch.object(settings, "save_config") as save:
        assert (
            run_single(
                "https://example.com/video",
                str(tmp_path),
                False,
                False,
                None,
                False,
                False,
                True,
                True,
            )
            == 0
        )
    assert settings.config == before
    save.assert_not_called()
    assert json.loads(capsys.readouterr().out)["dry_run"]


def test_json_download_separates_human_output(monkeypatch, capsys):
    def fake_download(*args, **kwargs):
        print("human progress")
        return {"success": False, "files": [], "errors": ["unavailable"]}

    monkeypatch.setattr("pinak.commands.run.handle_download", fake_download)
    assert (
        run_single("https://example.com/video", None, False, False, None, False, False, False, True)
        == 1
    )
    captured = capsys.readouterr()
    assert json.loads(captured.out)["success"] is False
    assert "human progress" in captured.err


def test_generated_ipc_token_is_required_and_shutdown_closes_idle_clients(tmp_path, monkeypatch):
    monkeypatch.setattr("pinak.media.ipc.endpoint.endpoint_directory", lambda: tmp_path)
    session = SimpleNamespace(
        transport=TransportController(), audio_backend=None, video_decoder=None, stop=MagicMock()
    )
    server = MediaIPCServer(session, port=0)
    port = server.start()
    idle = socket.create_connection(("127.0.0.1", port), timeout=1)
    try:
        unauthorized = MediaIPCClient(port=port).send_command("quit")
        assert "unauthorized" in unauthorized["error"]
        session.stop.assert_not_called()
        authenticated = MediaIPCClient(port=port, auth_token=server.auth_token)
        assert authenticated.send_command("quit")["error"] == "success"
        session.stop.assert_called_once()
        assert server.dispatch_command("[]")["error"] == "request must be an object"
    finally:
        server.stop()
    assert idle.recv(1) == b""
    idle.close()
    assert not list(tmp_path.glob("session-*.json"))


@pytest.mark.parametrize("percent", [0, 1, 1.5, 2, 50, 150])
def test_ipc_volume_has_consistent_percentage_units(percent):
    transport = TransportController()
    server = MediaIPCServer(SimpleNamespace(transport=transport, audio_backend=None), port=0)
    response = server.dispatch_command(json.dumps({"command": ["set_property", "volume", percent]}))
    assert response["error"] == "success"
    assert transport.volume == percent / 100


def test_gif_frames_survive_orientation_preparation(tmp_path):
    path = tmp_path / "animation.gif"
    first = Image.new("RGB", (12, 12), "red")
    second = Image.new("RGB", (12, 12), "blue")
    first.save(path, save_all=True, append_images=[second], duration=[100, 200], loop=0)
    loaded = ImageLoader.load(path)
    assert loaded.is_animated
    assert len(loaded.frames) == 2
    assert loaded.frames[0].getpixel((0, 0)) != loaded.frames[1].getpixel((0, 0))


def test_shuffle_keeps_the_playing_track_identity(tmp_path):
    paths = [tmp_path / f"{i}.mp3" for i in range(4)]
    for path in paths:
        path.touch()
    playlist = PlaylistManager(paths, initial_index=2)
    current = playlist.get_current()
    with patch("pinak.media.player.playlist.random.randint", return_value=0):
        playlist.toggle_shuffle()
    assert playlist.get_current() == current
    playlist.toggle_shuffle()
    assert playlist.get_current() == current


def test_picker_spaces_are_text(tmp_path):
    picker = TUIMediaPicker(tmp_path)
    picker.is_inputting_path = True
    for key in ("a", "space", "b"):
        picker.handle_input(KeyEvent(key))
    assert picker.path_input == "a b"


def test_media_initialization_failure_releases_every_acquisition(tmp_path):
    path = tmp_path / "file.mp4"
    path.touch()
    session = MediaSession([path], enable_consent_prompt=False)
    with (
        patch(
            "pinak.media.player.coordinator.MediaProbe.probe",
            return_value=MagicMock(width=640, media_type="video"),
        ),
        patch("pinak.media.player.coordinator.TerminalSessionContext"),
        patch.object(session.ipc_server, "start"),
        patch.object(session.ipc_server, "stop") as stop,
        patch.object(session, "_init_media_components", side_effect=RuntimeError("failed")),
        patch.object(session, "_teardown_media_components") as teardown,
        pytest.raises(RuntimeError, match="failed"),
    ):
        session.start()
    teardown.assert_called_once()
    stop.assert_called_once()
    from pinak.media.lifecycle.session_coordinator import MediaSessionCoordinator

    assert MediaSessionCoordinator._active_session is None


def test_picture_mode_key_is_dispatched_once(tmp_path):
    path = tmp_path / "file.png"
    Image.new("RGB", (12, 12), "red").save(path)
    session = MediaSession([path], enable_consent_prompt=False)
    viewer = MagicMock()
    viewer.current_index = 0
    session.picture_viewer = viewer
    session._handle_action_key("m", 80, 24)
    viewer.handle_input.assert_called_once_with(KeyEvent("m"))
    assert session.playlist_manager.repeat_mode == "none"


def test_thumbnail_does_not_count_as_downloaded_audio(tmp_path, monkeypatch):
    fake = MagicMock()
    fake.__enter__.return_value = fake

    def metadata(*args, **kwargs):
        (tmp_path / "song.jpg").write_bytes(b"only a thumbnail")
        return {"title": "song", "_filename": str(tmp_path / "song.mp3")}

    fake.extract_info.side_effect = metadata
    fake.prepare_filename.return_value = str(tmp_path / "song.mp3")
    monkeypatch.setattr(downloads.yt_dlp, "YoutubeDL", lambda _: fake)
    monkeypatch.setattr(downloads, "ffmpeg_available", lambda: False)
    result = downloads.download_media_content(
        "https://example.com/audio", str(tmp_path), extract_audio=True
    )
    assert result["success"] is False and result["files"] == []


def test_failed_remux_retains_original_audio_bytes(tmp_path, monkeypatch):
    import subprocess

    fake = MagicMock()
    fake.__enter__.return_value = fake
    original = b"the original audio data"

    def extract(*args, **kwargs):
        (tmp_path / "song.mp3").write_bytes(original)
        (tmp_path / "song.jpg").write_bytes(b"cover")
        return {"title": "song"}

    fake.extract_info.side_effect = extract
    fake.prepare_filename.return_value = str(tmp_path / "song.webm")
    monkeypatch.setattr(downloads.yt_dlp, "YoutubeDL", lambda _: fake)
    monkeypatch.setattr(downloads, "ffmpeg_available", lambda: True)

    def failed_remux(cmd, **kwargs):
        Path(cmd[-1]).write_bytes(b"")
        return subprocess.CompletedProcess(cmd, 1, "", "failed")

    monkeypatch.setattr("pinak.subproc.run_cmd", failed_remux)
    result = downloads.download_media_content(
        "https://example.com/audio", str(tmp_path), extract_audio=True
    )
    assert (tmp_path / "song.mp3").read_bytes() == original
    assert result["success"] is True  # Optional cover repair failed; audio was preserved.


def test_software_retry_does_not_redetect_failed_hardware(tmp_path, monkeypatch):
    from pinak.media.decoders.video_decoder import VideoDecoder

    decoder = VideoDecoder(tmp_path / "clip.mp4")
    monkeypatch.setattr(decoder, "find_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(decoder, "detect_hw_accel", lambda: "cuda")
    calls = []

    def fail_spawn(cmd, **kwargs):
        calls.append(cmd)
        raise OSError("cannot spawn")

    monkeypatch.setattr("pinak.media.decoders.video_decoder.subprocess.Popen", fail_spawn)
    decoder.start()
    assert len(calls) == 2
    assert "-hwaccel" in calls[0] and "-hwaccel" not in calls[1]
    assert decoder.error is not None


def test_partial_unicode_and_escape_sequences_are_buffered(monkeypatch):
    from pinak.media.core.input_parser import InputParser

    parser = InputParser()
    chunks = iter([b"\x1b", b"[A", b"\xe2\x82", b"\xac"])
    monkeypatch.setattr(parser, "_read_nonblocking", lambda _: next(chunks))
    assert parser.poll_events() == []
    assert parser.poll_events() == [KeyEvent("up")]
    assert parser.poll_events() == []
    assert parser.poll_events() == [KeyEvent("€")]


def test_untrusted_working_directory_binary_is_never_discovered(tmp_path, monkeypatch):
    from pinak import utils

    malicious = tmp_path / "ffmpeg.exe"
    malicious.write_bytes(b"not executed")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setattr(utils, "_ensure_static_ffmpeg_paths", lambda: None)
    monkeypatch.setattr(utils, "_get_platform_candidate_dirs", lambda: [])
    assert utils.trusted_which("ffmpeg.exe") is None
    assert utils._resolve_binary(("ffmpeg.exe",)) != str(malicious)

"""Unit tests for the Subtitle engine (model, parser, renderer)."""

from pathlib import Path
import sys

import pytest

from PIL import Image

from pinak.media.subtitles.model import SubtitleCue, SubtitleTrack
from pinak.media.subtitles import parser as subtitle_parser
from pinak.media.subtitles.parser import SubtitleParser
from pinak.media.subtitles.renderer import SubtitleRenderer


def test_subtitle_cue_is_active():
    cue = SubtitleCue(index=1, start_sec=10.0, end_sec=15.0, text="Hello world")
    assert cue.is_active(9.9) is False
    assert cue.is_active(10.0) is True
    assert cue.is_active(12.5) is True
    assert cue.is_active(15.0) is True
    assert cue.is_active(15.1) is False


def test_subtitle_track_get_active_cues():
    cue1 = SubtitleCue(index=1, start_sec=2.0, end_sec=5.0, text="First Line")
    cue2 = SubtitleCue(index=2, start_sec=5.0, end_sec=9.0, text="Second Line")
    cue3 = SubtitleCue(index=3, start_sec=12.0, end_sec=16.0, text="Third Line")

    track = SubtitleTrack(track_id=1, title="English", language="en", cues=[cue3, cue1, cue2])
    # Post-init should sort cues by start_sec
    assert [c.index for c in track.cues] == [1, 2, 3]

    assert track.get_active_text(1.0) == ""
    assert track.get_active_text(3.5) == "First Line"
    assert track.get_active_text(5.0) == "First Line\nSecond Line"
    assert track.get_active_text(14.0) == "Third Line"


def test_long_subtitle_remains_visible_after_many_short_overlaps():
    long = SubtitleCue(index=1, start_sec=0, end_sec=100, text="Long caption")
    short = [
        SubtitleCue(index=i + 2, start_sec=i + 1, end_sec=i + 1.1, text="Short")
        for i in range(13)
    ]
    track = SubtitleTrack(track_id=1, cues=[long, *short])
    assert track.get_active_text(30) == "Long caption"


def test_subtitle_input_and_process_output_have_byte_limits(tmp_path, monkeypatch):
    monkeypatch.setattr(subtitle_parser, "MAX_SUBTITLE_BYTES", 32)
    oversized = tmp_path / "movie.srt"
    oversized.write_bytes(b"x" * 33)
    assert SubtitleParser.parse_file(oversized) is None

    with pytest.raises(ValueError, match="byte limit"):
        subtitle_parser._run_bounded_stdout(
            [sys.executable, "-c", "print('x' * 2048)"], timeout=3, max_bytes=100
        )


def test_subtitle_parser_timestamps():
    assert SubtitleParser.timestamp_to_seconds("00:01:23,456") == 83.456
    assert SubtitleParser.timestamp_to_seconds("01:23.456") == 83.456
    assert SubtitleParser.timestamp_to_seconds("10.5") == 10.5
    assert SubtitleParser.timestamp_to_seconds("invalid") == 0.0


def test_subtitle_parser_parse_srt():
    sample_srt = """
1
00:00:01,000 --> 00:00:04,500
Hello <i>world</i>!

2
00:00:05,200 --> 00:00:08,000
<b>Welcome to Pinak Media</b>
Enjoy the playback.
"""
    cues = SubtitleParser.parse_srt(sample_srt)
    assert len(cues) == 2
    assert cues[0].start_sec == 1.0
    assert cues[0].end_sec == 4.5
    assert cues[0].text == "Hello world!"
    assert cues[1].start_sec == 5.2
    assert cues[1].end_sec == 8.0
    assert "Welcome to Pinak Media\nEnjoy the playback." in cues[1].text


def test_subtitle_parser_parse_vtt():
    sample_vtt = """WEBVTT - Sample File

00:02.000 --> 00:06.000
Testing WebVTT parsing.
"""
    cues = SubtitleParser.parse_vtt(sample_vtt)
    assert len(cues) == 1
    assert cues[0].start_sec == 2.0
    assert cues[0].end_sec == 6.0
    assert cues[0].text == "Testing WebVTT parsing."


def test_subtitle_parser_file_and_sibling_discovery(tmp_path: Path):
    media_file = tmp_path / "movie.mp4"
    media_file.write_bytes(b"dummy")

    sub_en = tmp_path / "movie.en.srt"
    sub_en.write_text(
        "1\n00:00:01,000 --> 00:00:03,000\nHello English\n",
        encoding="utf-8",
    )

    sub_es = tmp_path / "movie_es.vtt"
    sub_es.write_text(
        "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nHola Espanol\n",
        encoding="utf-8",
    )

    tracks = SubtitleParser.discover_sibling_subtitles(media_file)
    assert len(tracks) == 2
    assert any("en" in t.title.lower() for t in tracks)
    assert any("es" in t.title.lower() for t in tracks)
    assert {t.language for t in tracks} == {"en", "es"}


def test_subtitle_renderer_frame_overlay():
    frame = Image.new("RGB", (640, 360), color=(100, 150, 200))
    result = SubtitleRenderer.render_overlay_on_frame(frame, "Hello Pinak Subtitle")
    assert result.size == (640, 360)
    assert result.mode == "RGB"

    # Empty text returns identical copy
    empty_result = SubtitleRenderer.render_overlay_on_frame(frame, "")
    assert empty_result.size == (640, 360)


def test_subtitle_renderer_tui_formatting():
    tui_text = SubtitleRenderer.format_tui_subtitles("Pinak TUI Subtitle", max_cols=80)
    assert "Pinak TUI Subtitle" in tui_text
    assert "\x1b[" in tui_text

    empty_tui = SubtitleRenderer.format_tui_subtitles("", max_cols=80)
    assert empty_tui == ""


def test_extract_embedded_subtitles_continue_on_failure(monkeypatch, tmp_path):
    """Verifies that extract_embedded_subtitles continues searching when stream 0 fails (FALLBACK-04)."""
    import subprocess

    monkeypatch.setattr("pinak.media.subtitles.parser.ensure_ffmpeg", lambda: "/usr/bin/ffmpeg")

    calls = []

    def fake_run(cmd, **kwargs):
        # cmd: [ffmpeg_bin, "-v", "quiet", "-i", media, "-map", "0:s:N", "-f", "srt", "pipe:1"]
        # Find the -map arg
        map_idx = cmd.index("-map")
        stream_spec = cmd[map_idx + 1]
        calls.append(stream_spec)
        if stream_spec == "0:s:0":
            # Stream 0 is an unsupported bitmap subtitle
            raise RuntimeError("Bitmap subtitle decoder not found")
        elif stream_spec == "0:s:1":
            # Stream 1 is valid SRT
            srt_content = b"1\n00:00:01,000 --> 00:00:03,000\nValid Subtitle\n"
            return subprocess.CompletedProcess(cmd, 0, stdout=srt_content, stderr=b"")
        return subprocess.CompletedProcess(cmd, 1, stdout=b"", stderr=b"")

    monkeypatch.setattr("pinak.media.subtitles.parser._run_bounded_stdout", fake_run)
    media_file = tmp_path / "video.mkv"
    media_file.write_bytes(b"dummy")

    tracks = SubtitleParser.extract_embedded_subtitles(media_file)
    assert len(tracks) == 1
    assert tracks[0].title == "Embedded #2"
    assert tracks[0].cues[0].text == "Valid Subtitle"
    # Ensure stream 0 was attempted, failed, and stream 1 was evaluated
    assert "0:s:0" in calls
    assert "0:s:1" in calls


def test_embedded_tracks_use_language_metadata(monkeypatch, tmp_path):
    import json
    import subprocess

    media = tmp_path / "video.mp4"
    media.write_bytes(b"dummy")
    monkeypatch.setattr("pinak.media.subtitles.parser.ensure_ffmpeg", lambda: "ffmpeg")

    def run(cmd, **kwargs):
        if "-show_entries" in cmd:
            metadata = {"streams": [{"tags": {"language": "hin"}}, {"tags": {"language": "eng"}}]}
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(metadata).encode())
        if int(cmd[cmd.index("-map") + 1].rsplit(":", 1)[1]) >= 2:
            return subprocess.CompletedProcess(cmd, 1, stdout=b"")
        return subprocess.CompletedProcess(
            cmd, 0, stdout=b"1\n00:00:00,000 --> 00:00:02,000\nCaption\n"
        )

    monkeypatch.setattr("pinak.media.subtitles.parser._run_bounded_stdout", run)
    tracks = SubtitleParser.extract_embedded_subtitles(media)
    assert [track.label for track in tracks] == ["Hindi", "English"]
    assert [track.language for track in tracks] == ["hin", "eng"]


def test_real_multilanguage_container_and_player_cycle(tmp_path, monkeypatch):
    import subprocess

    import pytest

    from pinak.media.player.coordinator import MediaSession
    from pinak.utils import get_ffmpeg_path, get_ffprobe_path

    ffmpeg, ffprobe = get_ffmpeg_path(), get_ffprobe_path()
    if not Path(ffmpeg).is_file() or not Path(ffprobe).is_file():
        pytest.skip("Local FFmpeg and FFprobe are required for the container smoke test")
    inputs = []
    languages = ["en", "hi", "es"]
    container_codes = ["eng", "hin", "spa"]
    for code in languages:
        path = tmp_path / f"source-{code}.srt"
        path.write_text(f"1\n00:00:00,000 --> 00:00:01,000\nCaption {code}\n", encoding="utf-8")
        inputs.extend(["-i", str(path)])
    media = tmp_path / "three-languages.mkv"
    stream_options = ["-map", "0:v:0"]
    for idx, code in enumerate(container_codes):
        stream_options.extend(["-map", f"{idx + 1}:0", f"-metadata:s:s:{idx}", f"language={code}"])
    subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=s=160x90:r=10:d=1",
            *inputs,
            *stream_options,
            "-c:v",
            "mpeg4",
            "-c:s",
            "srt",
            str(media),
        ],
        check=True,
        capture_output=True,
        timeout=20,
    )
    monkeypatch.setattr("pinak.media.subtitles.parser.ensure_ffmpeg", lambda: ffmpeg)
    monkeypatch.setattr("pinak.media.subtitles.parser.get_ffprobe_path", lambda: ffprobe)
    tracks = SubtitleParser.extract_embedded_subtitles(media)
    assert [track.label for track in tracks] == [
        "English",
        "Hindi",
        "Spanish",
    ]
    session = MediaSession([media], enable_consent_prompt=False)
    monkeypatch.setattr(session._subtitle_loader, "poll", lambda: tracks)
    session._poll_subtitles()
    assert session.active_sub_idx == -1
    for code in languages:
        session._handle_action_key("c", 80, 24)
        assert (
            session.subtitle_tracks[session.active_sub_idx].get_active_text(0.5)
            == f"Caption {code}"
        )
    session._handle_action_key("c", 80, 24)
    assert session.active_sub_idx == -1
    session._handle_action_key("c", 80, 24)
    assert session.active_sub_idx == 0


def test_subtitle_metadata_ansi_and_osc_sanitized():
    malicious_title = "\x1b[2J\x1b]0;evil\x07Malicious Track"
    track = SubtitleTrack(track_id=1, title=malicious_title)
    assert "\x1b" not in track.label
    assert "\x07" not in track.label
    assert track.label == "Malicious Track"


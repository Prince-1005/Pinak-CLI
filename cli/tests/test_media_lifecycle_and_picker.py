import math
from pathlib import Path
from unittest.mock import patch

from pinak.media.core.input_parser import KeyEvent
from pinak.media.decoders.probe import MediaMetadata
from pinak.media.diagnostics.capacity_scorer import CapacityScorer
from pinak.media.diagnostics.preflight_modal import PreflightConsentModal
from pinak.media.diagnostics.telemetry_probe import DeviceTelemetry
from pinak.media.lifecycle.close_affordances import CloseAffordanceManager
from pinak.media.lifecycle.session_coordinator import MediaSessionCoordinator
from pinak.media.picker.fuzzy_search import FuzzyMediaFilter
from pinak.media.picker.scanner import MediaScanner
from pinak.media.picker.sibling_seeder import SiblingPlaylistSeeder
from pinak.media.picker.tui_picker import TUIMediaPicker


def test_session_coordinator_locking():
    assert MediaSessionCoordinator.is_media_active() is False

    mock_sess = type("MockSession", (), {"is_running": True, "stop": lambda self: None})()
    MediaSessionCoordinator.acquire_session(mock_sess)
    assert MediaSessionCoordinator.is_media_active() is True

    # Check banner generation
    susp_banner = MediaSessionCoordinator.format_suspended_cli_banner()
    assert "Media is Playing in TUI" in susp_banner

    # Release
    MediaSessionCoordinator.release_session()
    assert MediaSessionCoordinator.is_media_active() is False


def test_close_affordances_hit_test():
    closed = []
    mgr = CloseAffordanceManager(on_close=lambda: closed.append(True))
    mgr.update_layout(total_cols=80, total_rows=24)

    # Only the rendered footer has a close action.
    assert mgr.handle_click(78, 1) is False
    hit = mgr.handle_click(78, 22)
    assert hit is True
    assert len(closed) == 1

    # Click in dead space
    hit_dead = mgr.handle_click(10, 10)
    assert hit_dead is False


def test_diagnostics_and_capacity_scorer():
    telem = DeviceTelemetry(
        cpu_cores_logical=8,
        cpu_cores_physical=4,
        cpu_usage_pct=20.0,
        ram_total_mb=16384.0,
        ram_available_mb=8192.0,
        ram_usage_pct=50.0,
        gpu_acceleration="dxva2",
        is_on_battery=False,
        battery_pct=100,
        terminal_type="xterm-256color",
        has_truecolor=True,
    )

    prof = CapacityScorer.evaluate(telem, media_type="video")
    assert prof.tier == "high"
    assert prof.capacity_score >= 75.0

    # Test modal rendering
    modal_text = PreflightConsentModal.render_modal_text(telem, prof, "test.mp4", "1080p @ 60 FPS")
    assert "HARDWARE ASSESSMENT" in modal_text
    assert "Yes, Start Playback" in modal_text


def test_media_scanner_and_fuzzy_search(tmp_path: Path):
    sub = tmp_path / "music"
    sub.mkdir()
    (sub / "song1.mp3").write_bytes(b"dummy")
    (sub / "video1.mp4").write_bytes(b"dummy")
    (sub / "doc.txt").write_bytes(b"dummy")  # Not media

    items = MediaScanner.scan_directory(sub)
    item_names = [it.name for it in items if not it.is_dir]
    assert "song1.mp3" in item_names
    assert "video1.mp4" in item_names
    assert "doc.txt" in item_names
    assert next(item for item in items if item.name == "doc.txt").media_type is None

    # Fuzzy filter
    filtered = FuzzyMediaFilter.filter_items(items, "song")
    filtered_names = [it.name for it in filtered if not it.is_dir]
    assert "song1.mp3" in filtered_names
    assert "video1.mp4" not in filtered_names


def test_sibling_seeder_and_tui_picker(tmp_path: Path):
    d = tmp_path / "album"
    d.mkdir()
    f1 = d / "01.mp3"
    f2 = d / "02.mp3"
    f1.write_bytes(b"dummy")
    f2.write_bytes(b"dummy")

    siblings, idx = SiblingPlaylistSeeder.seed_from_file(f2)
    assert len(siblings) == 2
    assert idx == 1

    # TUI Picker navigation
    picker = TUIMediaPicker(start_dir=d)
    tui = picker.render_tui(cols=80, rows=24)
    assert "PINAK MEDIA PICKER" in tui

    picker.handle_input(KeyEvent(key="down"))
    assert picker.cursor_idx >= 0


def test_tui_picker_custom_path_entry(tmp_path: Path):
    """Verifies that pressing 'p' allows entering a custom directory or file path."""
    sub_dir = tmp_path / "custom_music"
    sub_dir.mkdir()
    song = sub_dir / "mysong.flac"
    song.write_bytes(b"dummy")

    picker = TUIMediaPicker(start_dir=tmp_path)
    assert picker.current_dir == tmp_path.resolve()

    # Press 'p' to open path input mode
    re_render, confirmed = picker.handle_input(KeyEvent(key="p"))
    assert re_render is True
    assert confirmed is None
    assert picker.is_inputting_path is True

    # Type directory path
    for ch in str(sub_dir):
        picker.handle_input(KeyEvent(key=ch))
    assert picker.path_input == str(sub_dir)

    # Press Enter to open directory
    re_render, confirmed = picker.handle_input(KeyEvent(key="enter"))
    assert re_render is True
    assert confirmed is None
    assert picker.is_inputting_path is False
    assert picker.current_dir == sub_dir.resolve()
    assert any(it.name == "mysong.flac" for it in picker.visible_items)

    # Type direct file path
    picker.handle_input(KeyEvent(key="p"))
    for ch in str(song):
        picker.handle_input(KeyEvent(key=ch))
    re_render, confirmed = picker.handle_input(KeyEvent(key="enter"))
    assert re_render is True
    assert confirmed == song.resolve()


def test_preflight_consent_critical_evaluation(tmp_path: Path):
    """Verifies that preflight consent prompt is only activated during critical resource conditions."""
    sample_file = tmp_path / "test.mp3"
    sample_file.write_bytes(b"dummy")
    meta = MediaMetadata(
        media_type="audio",
        file_path=sample_file,
        file_size_bytes=1000,
        duration_seconds=120.0,
    )

    # 1. Healthy system -> not critical
    healthy_telem = DeviceTelemetry(
        cpu_cores_logical=16,
        cpu_cores_physical=8,
        cpu_usage_pct=25.0,
        ram_total_mb=16384.0,
        ram_available_mb=8192.0,
        ram_usage_pct=50.0,
        gpu_acceleration="dxva2",
        is_on_battery=False,
        battery_pct=100,
        terminal_type="xterm-256color",
        has_truecolor=True,
    )
    prof = CapacityScorer.evaluate(healthy_telem, media_type="audio")
    is_crit, reason = PreflightConsentModal.is_critical_situation(healthy_telem, prof, meta)
    assert is_crit is False
    assert reason == ""

    # prompt_user on healthy system returns True immediately without prompting
    with patch(
        "pinak.media.diagnostics.preflight_modal.DeviceDiagnosticsProbe.inspect",
        return_value=healthy_telem,
    ):
        assert PreflightConsentModal.prompt_user(meta) is True

    # 2. Low battery (< 20% on battery) -> critical
    low_bat_telem = DeviceTelemetry(
        cpu_cores_logical=16,
        cpu_cores_physical=8,
        cpu_usage_pct=25.0,
        ram_total_mb=16384.0,
        ram_available_mb=8192.0,
        ram_usage_pct=50.0,
        gpu_acceleration="dxva2",
        is_on_battery=True,
        battery_pct=14,
        terminal_type="xterm-256color",
        has_truecolor=True,
    )
    is_crit, reason = PreflightConsentModal.is_critical_situation(low_bat_telem, prof, meta)
    assert is_crit is True
    assert "Low battery" in reason

    # 3. Low RAM (< 512MB available) -> critical
    low_ram_telem = DeviceTelemetry(
        cpu_cores_logical=16,
        cpu_cores_physical=8,
        cpu_usage_pct=25.0,
        ram_total_mb=8192.0,
        ram_available_mb=320.0,
        ram_usage_pct=96.0,
        gpu_acceleration=None,
        is_on_battery=False,
        battery_pct=100,
        terminal_type="xterm-256color",
        has_truecolor=True,
    )
    is_crit, reason = PreflightConsentModal.is_critical_situation(low_ram_telem, prof, meta)
    assert is_crit is True
    assert "Low RAM" in reason

    # 4. Transient CPU usage alone should not interrupt playback.
    high_cpu_telem = DeviceTelemetry(
        cpu_cores_logical=16,
        cpu_cores_physical=8,
        cpu_usage_pct=92.0,
        ram_total_mb=8192.0,
        ram_available_mb=4096.0,
        ram_usage_pct=50.0,
        gpu_acceleration=None,
        is_on_battery=False,
        battery_pct=100,
        terminal_type="xterm-256color",
        has_truecolor=True,
    )
    is_crit, reason = PreflightConsentModal.is_critical_situation(high_cpu_telem, prof, meta)
    assert is_crit is False
    assert reason == ""


def test_spectrum_bars_resampling_and_full_axis_fit():
    """Verifies that spectrum bars cover the entire width of the frequency axis and all lines align."""
    from pinak.media.visualizer.spectrum_bars import SpectrumBarsRenderer, _visible_len

    bands = [0.1 + (i % 8) * 0.1 for i in range(32)]
    peaks = [b + 0.05 for b in bands]
    pcm = [0.0] * 1024

    # Test resampling
    resampled = SpectrumBarsRenderer.resample_bands(bands, 46)
    assert len(resampled) == 46

    # Test symmetric axis generation
    axis_46 = SpectrumBarsRenderer.build_symmetric_axis(46)
    assert len(axis_46) == 46
    assert axis_46 == "TREBLE ── MID ── BASS ── BASS ── MID ── TREBLE"

    # Test panel rendering across multiple column sizes
    for test_cols in (50, 54, 60, 75):
        panel = SpectrumBarsRenderer.render_panel(
            bands, peaks, pcm, max_cols=test_cols, max_rows=14
        )
        assert len(panel) == 14
        # Every single row MUST have exact visible length equal to test_cols
        for row_idx, line in enumerate(panel):
            vl = _visible_len(line)
            assert vl == test_cols, f"Row {row_idx} visible length {vl} != expected {test_cols}"


def test_audio_decoder_pts_synchronization_offset(tmp_path: Path):
    """Verifies AudioDecoder get_visualizer_samples synchronizes against _buffer_start_pts."""
    from pinak.media.decoders.audio_decoder import AudioDecoder

    dummy = tmp_path / "sync_test.mp3"
    dummy.write_bytes(b"ID3" + b"\x00" * 100)

    decoder = AudioDecoder(dummy)
    decoder.start(start_time_sec=20.0)
    assert decoder._buffer_start_pts == 20.0

    # Populate buffer with dummy samples representing 1 second of audio
    with decoder._lock:
        decoder._pcm_buffer.extend([int(math.sin(i * 0.1) * 10000) for i in range(48000)])

    # Query at pts=20.5 (0.5s after start)
    samples = decoder.get_visualizer_samples(count=128, pts=20.5)
    assert len(samples) == 128
    assert any(abs(s) > 0.01 for s in samples)
    decoder.close()


def test_cli_banners_clean_rich_markup():
    """Verifies that CLI banners use Rich markup without raw ANSI and preserve escaped [x]."""
    susp = MediaSessionCoordinator.format_suspended_cli_banner()
    assert "\x1b[33;1m" not in susp
    assert "[bold yellow]" in susp
    assert r"\[x]" in susp

    ret = MediaSessionCoordinator.format_return_cli_banner()
    assert "\x1b[32;1m" not in ret
    assert "[bold green]" in ret


def test_recursive_media_counter(tmp_path: Path):
    """Verifies recursive counting of media files inside nested subdirectories."""
    parent_dir = tmp_path / "top_folder"
    parent_dir.mkdir()
    sub1 = parent_dir / "sub1"
    sub1.mkdir()
    sub2 = parent_dir / "sub2" / "deep"
    sub2.mkdir(parents=True)

    # 1 root media file, 1 in sub1, 2 in deep sub2
    (parent_dir / "root.mp3").write_bytes(b"dummy")
    (sub1 / "clip.mp4").write_bytes(b"dummy")
    (sub2 / "pic.png").write_bytes(b"dummy")
    (sub2 / "song.flac").write_bytes(b"dummy")
    (sub2 / "readme.txt").write_bytes(b"not media")

    count = MediaScanner.count_media_in_dir(parent_dir)
    assert count == 4

    items = MediaScanner.scan_directory(tmp_path)
    parent_item = next(it for it in items if it.name == "top_folder")
    assert parent_item.is_dir is True
    assert parent_item.child_media_count == 4


def test_tui_picker_search_and_paste_with_blank_cursor(tmp_path: Path):
    """Verifies that '/' opens search with blank space + cursor and supports pasting."""
    (tmp_path / "song_holiday.mp3").write_bytes(b"dummy")
    (tmp_path / "video_nature.mp4").write_bytes(b"dummy")
    (tmp_path / "unrelated.webm").write_bytes(b"dummy")

    picker = TUIMediaPicker(start_dir=tmp_path)

    # Trigger search by file name
    re_render, _ = picker.handle_input(KeyEvent(key="/"))
    assert re_render is True
    assert picker.is_searching is True

    # Check that TUI renders blank space with cursor
    tui = picker.render_tui(cols=80, rows=24)
    assert "SEARCH FILE NAME" in tui
    assert "█" in tui

    # Paste text into search
    picker.handle_input(KeyEvent(key="holiday"))
    assert picker.search_query == "holiday"
    matched_media = [it for it in picker.visible_items if not it.name.startswith("..")]
    assert len(matched_media) == 1
    assert matched_media[0].name == "song_holiday.mp3"

    # Press enter to complete typing search
    picker.handle_input(KeyEvent(key="enter"))
    assert picker.is_searching is False
    assert any(it.name == "song_holiday.mp3" for it in picker.visible_items)

    # Press esc to clear search
    picker.handle_input(KeyEvent(key="esc"))
    assert picker.search_query == ""
    assert any(it.name == "video_nature.mp4" for it in picker.visible_items)


def test_tui_picker_path_paste_and_cursor(tmp_path: Path):
    """Verifies path entry 'p' displays cursor and accepts pasted multi-char paths."""
    sub = tmp_path / "nested_audio"
    sub.mkdir()
    (sub / "track.ogg").write_bytes(b"dummy")

    picker = TUIMediaPicker(start_dir=tmp_path)
    picker.handle_input(KeyEvent(key="p"))
    assert picker.is_inputting_path is True

    tui = picker.render_tui(cols=80, rows=24)
    assert "GOTO PATH" in tui
    assert "█" in tui

    # Paste full path directly
    picker.handle_input(KeyEvent(key=str(sub)))
    assert picker.path_input == str(sub)

    picker.handle_input(KeyEvent(key="enter"))
    assert picker.is_inputting_path is False
    assert picker.current_dir == sub.resolve()


def test_tui_fullscreen_removed():
    """Verifies fullscreen [f] option is removed from picker and coordinator footers."""
    picker = TUIMediaPicker(start_dir=".")
    for cols in (65, 80, 100, 130):
        tui = picker.render_tui(cols=cols, rows=24)
        assert "[f] Fullscreen" not in tui
        assert "[f] Full" not in tui
        assert "[f]" not in tui


def test_tui_vertical_line_and_inspector_box_integrity(tmp_path: Path):
    """Verifies that the vertical line separator │ never cracks and has identical column position across all rows."""
    from pinak.media.visualizer.spectrum_bars import _visible_len

    # Create mixed directory and media files
    d1 = tmp_path / "A_Directory_With_Long_Name"
    d1.mkdir()
    (d1 / "a.mp3").write_bytes(b"dummy")
    (tmp_path / "short.mp4").write_bytes(b"dummy")
    (tmp_path / "A_Very_Long_Filename_For_Testing_Alignment_Wrap.webm").write_bytes(b"dummy")

    picker = TUIMediaPicker(start_dir=tmp_path)
    for test_cols in (70, 80, 100, 120):
        tui = picker.render_tui(cols=test_cols, rows=20)
        lines = tui.split("\n")
        body_lines = lines[1:-1]
        divider_positions = []
        for line in body_lines:
            assert "│" in line, f"Divider missing in line: {line}"
            left_part = line.split("│")[0]
            vl = _visible_len(left_part)
            divider_positions.append(vl)

        # Every row must have the EXACT same visible divider column position
        message = f"Divider cracked across rows at cols={test_cols}: {divider_positions}"
        assert len(set(divider_positions)) == 1, message
        # And the total visible width of every line must exactly equal test_cols
        for row_idx, line in enumerate(lines):
            line_vl = _visible_len(line)
            assert line_vl == test_cols, f"Row {row_idx} visible width {line_vl} != {test_cols}"


def test_video_player_default_max_resolution_and_no_visualizer(tmp_path: Path):
    """Verifies default max video resolution and visualizer command removal during video playback."""
    from unittest.mock import MagicMock

    from pinak.media.decoders.probe import MediaMetadata
    from pinak.media.decoders.video_decoder import DecodedVideoFrame
    from pinak.media.player.coordinator import MediaSession

    vid_file = tmp_path / "movie.mp4"
    vid_file.write_bytes(b"dummy")

    session = MediaSession([vid_file], enable_consent_prompt=False)
    session._current_meta = MediaMetadata(
        media_type="video",
        file_path=vid_file,
        file_size_bytes=10000,
        duration_seconds=60.0,
        width=1920,
        height=1080,
    )
    # Check default resolution profile is native
    assert session.quality_manager.current_profile.id == "native"

    # Compute target dimensions: must be max of original video resolution (1920, 1080)
    w, h = session.quality_manager.get_target_dimensions(
        term_cols=80,
        term_rows=24,
        native_w=session._current_meta.width,
        native_h=session._current_meta.height,
        is_video=True,
    )
    assert w == 1920
    assert h == 1080

    # Mock video decoder to simulate active video playback
    session.video_decoder = MagicMock()
    session.video_decoder.read_frame.return_value = DecodedVideoFrame(
        pts=1.0, rgb_data=b"\x00" * (1920 * 1080 * 3), width=1920, height=1080
    )

    # 1. Visualizer command MUST be removed from footer during video playback across all column widths
    for test_cols in (70, 85, 100, 130):
        footer = session._build_responsive_footer(cols=test_cols)
        assert "[v] Visualizer" not in footer
        assert "[v] Vis" not in footer
        assert "[v]" not in footer

    # 2. Pressing 'v' during video playback does not cycle visualizer theme
    initial_theme = session.current_vis_theme
    session._on_tick(0.016, [KeyEvent(key="v")])
    assert session.current_vis_theme == initial_theme

    # 3. Audio mode: visualizer is present in footer and cycles with 'v'
    session.video_decoder = None
    session.turntable = MagicMock()
    footer_audio = session._build_responsive_footer(cols=125)
    assert "[v] Visualizer" in footer_audio
    session._on_tick(0.016, [KeyEvent(key="v")])
    assert session.current_vis_theme != initial_theme

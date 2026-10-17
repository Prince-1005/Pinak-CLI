"""End-to-end integration tests for Pinak TUI media subsystem."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from pinak.cli import app
from pinak.commands.media import handle_media_command, handle_play_command, handle_view_command
from pinak.media.decoders.probe import MediaMetadata
from pinak.media.diagnostics.preflight_modal import PreflightConsentModal
from pinak.media.lifecycle.session_coordinator import MediaSessionCoordinator
from pinak.media.player.coordinator import MediaSession


@pytest.fixture
def dummy_media_dir(tmp_path: Path) -> Path:
    """Creates a temporary directory with dummy media files."""
    from PIL import Image

    media_dir = tmp_path / "media_test"
    media_dir.mkdir()

    # Create dummy real image
    img = media_dir / "sample.jpg"
    im = Image.new("RGB", (100, 100), (255, 0, 0))
    im.save(img, format="JPEG")

    # Create dummy audio
    aud = media_dir / "sample.mp3"
    aud.write_bytes(b"ID3" + b"\x00" * 100)

    # Create dummy video
    vid = media_dir / "sample.mp4"
    vid.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 100)

    return media_dir


def test_preflight_consent_modal_rejection(dummy_media_dir: Path):
    """Verifies that rejecting the pre-flight capacity prompt cleanly cancels playback."""
    sample_mp4 = dummy_media_dir / "sample.mp4"

    with patch.object(PreflightConsentModal, "prompt_user", return_value=False):
        session = MediaSession(
            playlist=[sample_mp4],
            enable_consent_prompt=True,
        )
        session.start()

        # Session should not have acquired lock or started running
        assert not MediaSessionCoordinator.is_media_active()
        assert not session.is_running


def test_preflight_consent_modal_acceptance(dummy_media_dir: Path):
    """Verifies that accepting the pre-flight capacity prompt proceeds to run the session."""
    sample_jpg = dummy_media_dir / "sample.jpg"

    meta = MediaMetadata(
        media_type="picture",
        file_path=sample_jpg,
        file_size_bytes=1000,
        duration_seconds=0.0,
        width=800,
        height=600,
    )

    # Mock event loop to stop immediately on first tick
    def fake_run(callback):
        assert MediaSessionCoordinator.is_media_active()
        callback(0.016, [])
        session.stop()

    with (
        patch("pinak.media.player.coordinator.MediaProbe.probe", return_value=meta),
        patch.object(PreflightConsentModal, "prompt_user", return_value=True),
        patch("pinak.media.player.coordinator.PrecisionEventLoop.run", side_effect=fake_run),
        patch("pinak.media.player.coordinator.TerminalSessionContext"),
    ):
        session = MediaSession(
            playlist=[sample_jpg],
            enable_consent_prompt=True,
        )
        session.start()

        # After exit, coordinator should release session
        assert not MediaSessionCoordinator.is_media_active()


def test_media_session_mutual_exclusion(dummy_media_dir: Path):
    """Verifies that MediaSessionCoordinator enforces CLI prompt suspension and auto-closing on new command."""
    mock_session = MagicMock()
    mock_session.is_running = True

    MediaSessionCoordinator.acquire_session(mock_session)
    assert MediaSessionCoordinator.is_media_active()

    # Incoming new command requests close
    MediaSessionCoordinator.request_close_active_session(reason="test_new_command")
    mock_session.stop.assert_called_once()
    assert not MediaSessionCoordinator.is_media_active()


def test_handle_play_command_file_launch(dummy_media_dir: Path):
    """Verifies /play <file> initializes session with sibling seeding."""
    sample_mp3 = dummy_media_dir / "sample.mp3"

    with patch("pinak.commands.media.MediaSession") as mock_session_cls:
        instance = mock_session_cls.return_value
        handle_play_command([str(sample_mp3)])

        mock_session_cls.assert_called_once()
        instance.start.assert_called_once()


def test_handle_media_command_directory_picker(dummy_media_dir: Path):
    """Verifies /media <dir> launches interactive TUI picker and plays selection."""
    sample_mp4 = dummy_media_dir / "sample.mp4"

    with (
        patch("pinak.commands.media._run_picker_loop", return_value=sample_mp4),
        patch("pinak.commands.media.MediaSession") as mock_session_cls,
    ):
        handle_media_command([str(dummy_media_dir)])

        mock_session_cls.assert_called_once()
        mock_session_cls.return_value.start.assert_called_once()


def test_cli_direct_invocation_play_and_media(dummy_media_dir: Path):
    """Verifies pinak play <file> and pinak media invoke corresponding handlers."""
    runner = CliRunner()
    sample_jpg = dummy_media_dir / "sample.jpg"

    with patch("pinak.commands.media.handle_play_command") as mock_play:
        result = runner.invoke(app, ["play", str(sample_jpg)])
        assert result.exit_code == 0
        mock_play.assert_called_once_with([str(sample_jpg)])

    with patch("pinak.commands.media.handle_media_command") as mock_media:
        result = runner.invoke(app, ["media", str(dummy_media_dir)])
        assert result.exit_code == 0
        mock_media.assert_called_once_with([str(dummy_media_dir)])


def test_handle_view_command_inline_launch(dummy_media_dir: Path):
    """Verifies /view <file> launches MediaSession directly inline without opening a new tab/window."""
    sample_jpg = dummy_media_dir / "sample.jpg"

    with (
        patch("pinak.commands.media.launch_standalone_media_window") as mock_standalone,
        patch("pinak.commands.media.MediaSession") as mock_session_cls,
    ):
        instance = mock_session_cls.return_value
        handle_view_command([str(sample_jpg)], standalone=False)

        # Standalone external window MUST NOT be launched
        mock_standalone.assert_not_called()
        # Direct inline TUI MediaSession MUST be launched
        mock_session_cls.assert_called_once()
        instance.start.assert_called_once()


def test_handle_view_command_explicit_standalone(dummy_media_dir: Path):
    """Verifies /view <file> --standalone respects explicit user flag to open separate window."""
    sample_jpg = dummy_media_dir / "sample.jpg"

    with (
        patch("pinak.commands.media.launch_standalone_media_window") as mock_standalone,
        patch("pinak.commands.media.MediaSession") as mock_session_cls,
    ):
        handle_view_command([str(sample_jpg), "--standalone"])
        mock_standalone.assert_called_once()
        mock_session_cls.assert_not_called()


def test_cli_direct_invocation_view(dummy_media_dir: Path):
    """Verifies pinak view <file> invokes handle_view_command."""
    runner = CliRunner()
    sample_jpg = dummy_media_dir / "sample.jpg"

    with patch("pinak.commands.media.handle_view_command") as mock_view:
        result = runner.invoke(app, ["view", str(sample_jpg)])
        assert result.exit_code == 0
        mock_view.assert_called_once_with([str(sample_jpg)])

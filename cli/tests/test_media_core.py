"""Unit tests for pinak.media.core modules."""

from unittest.mock import patch

from pinak.media.core.event_loop import PrecisionEventLoop
from pinak.media.core.input_parser import InputParser, KeyEvent, MouseEvent
from pinak.media.core.lifecycle import TerminalSessionContext
from pinak.media.core.terminal_caps import TerminalCapabilities, TerminalProber


def test_terminal_capabilities_defaults():
    caps = TerminalCapabilities()
    assert caps.cols == 80
    assert caps.rows == 24
    assert caps.cell_aspect_ratio == 2.0
    assert caps.primary_graphics_mode == "ascii"


def test_terminal_capabilities_modes():
    caps_kitty = TerminalCapabilities(has_kitty=True)
    assert caps_kitty.primary_graphics_mode == "kitty"

    caps_sixel = TerminalCapabilities(has_sixel=True)
    assert caps_sixel.primary_graphics_mode == "sixel"

    caps_iterm = TerminalCapabilities(has_iterm2=True)
    assert caps_iterm.primary_graphics_mode == "iterm2"

    caps_tc = TerminalCapabilities(has_truecolor=True)
    assert caps_tc.primary_graphics_mode == "halfblock"


def test_terminal_prober_env():
    with patch.dict("os.environ", {"COLORTERM": "truecolor", "TERM": "xterm-kitty"}):
        caps = TerminalProber.probe(skip_active_interrogation=True)
        assert caps.has_truecolor is True
        assert caps.has_kitty is True


def test_terminal_auto_elevation_kitty_and_sixel():
    from pinak.media.sync.fallback_manager import FallbackManager

    # Auto-elevation to Kitty via KITTY_WINDOW_ID
    with patch.dict("os.environ", {"KITTY_WINDOW_ID": "42", "TERM": "xterm-256color"}):
        caps = TerminalProber.probe(skip_active_interrogation=True)
        assert caps.has_kitty is True
        renderer = FallbackManager.get_best_renderer(caps)
        assert renderer.mode_name == "kitty"

    # Auto-elevation to Sixel via xterm-sixel
    with patch.dict("os.environ", {"TERM": "xterm-sixel", "KITTY_WINDOW_ID": ""}):
        caps = TerminalProber.probe(skip_active_interrogation=True)
        assert caps.has_sixel is True
        renderer = FallbackManager.get_best_renderer(caps)
        assert renderer.mode_name == "sixel"


def test_input_parser_keys():
    parser = InputParser()

    # Arrow keys
    ev, consumed = parser._parse_next_event(b"\x1b[A")
    assert isinstance(ev, KeyEvent) and ev.key == "up" and consumed == 3

    ev, consumed = parser._parse_next_event(b"\x1b[B")
    assert isinstance(ev, KeyEvent) and ev.key == "down" and consumed == 3

    # Characters
    ev, consumed = parser._parse_next_event(b"q")
    assert isinstance(ev, KeyEvent) and ev.key == "q" and consumed == 1

    ev, consumed = parser._parse_next_event(b" ")
    assert isinstance(ev, KeyEvent) and ev.key == "space" and consumed == 1

    # Ctrl+C
    ev, consumed = parser._parse_next_event(b"\x03")
    assert isinstance(ev, KeyEvent) and ev.key == "c" and ev.ctrl is True


def test_input_parser_mouse_sgr():
    parser = InputParser()
    # Left click press at col 45, row 12: \x1b[<0;45;12M
    ev, consumed = parser._parse_next_event(b"\x1b[<0;45;12M")
    assert isinstance(ev, MouseEvent)
    assert ev.button == 0
    assert ev.col == 45
    assert ev.row == 12
    assert ev.is_pressed is True


def test_input_parser_without_file_descriptor(monkeypatch):
    import io

    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setattr("sys.stdin", io.StringIO())
    parser = InputParser()
    parser._buffer.extend(b"q")
    assert parser.poll_events() == [KeyEvent("q")]


def test_input_parser_closed_descriptor(monkeypatch):
    from unittest.mock import Mock

    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setattr("sys.stdin", Mock(fileno=Mock(return_value=-1)))
    assert InputParser().poll_events() == []


def test_terminal_lifecycle_restore():
    ctx = TerminalSessionContext(enable_mouse=True)
    with patch("sys.stdout.write") as mock_write, patch("sys.stdout.flush"):
        ctx.activate()
        assert mock_write.called
        assert ctx._is_active is True

        ctx.restore()
        assert ctx._is_active is False


def test_event_loop_single_tick():
    loop = PrecisionEventLoop(target_fps=60.0, enable_sync_updates=True)
    ticks = []

    def on_tick(dt, events):
        ticks.append(dt)
        loop.stop()
        return "TEST_FRAME"

    with patch("sys.stdout.write"), patch("sys.stdout.flush"):
        loop.run(on_tick)

    assert len(ticks) == 1
    assert ticks[0] > 0


def test_launch_standalone_media_window_darwin(monkeypatch):
    import sys

    from pinak.commands.media import launch_standalone_media_window

    monkeypatch.setattr(sys, "platform", "darwin")
    popen_args = []

    class FakeProc:
        def wait(self):
            pass

    monkeypatch.setattr(
        "subprocess.Popen", lambda cmd, **kwargs: (popen_args.append(cmd), FakeProc())[1]
    )

    dangerous_arg = 'sample"; do shell script "evil"; --.mp4'
    success = launch_standalone_media_window([dangerous_arg], wait=False)

    assert success is True
    assert len(popen_args) == 1
    script = popen_args[0][2]
    assert 'tell application "Terminal" to do script' in script
    # The double quote in dangerous_arg must be safely escaped in AppleScript string
    assert '\\"' in script

"""Unit tests for the mpv-compatible JSON-IPC server and client."""

from pathlib import Path
from unittest.mock import MagicMock

from pinak.media.ipc.client import MediaIPCClient
from pinak.media.ipc.server import MediaIPCServer


def test_ipc_server_dispatch_command():
    fake_session = MagicMock()
    fake_session.transport.is_playing = True
    fake_session.transport.current_pts = 42.0
    fake_session.transport.duration_sec = 180.0
    fake_session.transport.volume = 0.8
    fake_session.transport.is_muted = False
    fake_session.playlist_manager.get_current.return_value = Path("sample.mp4")

    server = MediaIPCServer(session=fake_session, port=0)

    # 1. get_property playback-time
    resp = server.dispatch_command(
        '{"command": ["get_property", "playback-time"], "request_id": 1}'
    )
    assert resp["error"] == "success"
    assert resp["data"] == 42.0
    assert resp["request_id"] == 1

    # 2. get_property duration
    resp = server.dispatch_command('{"command": ["get_property", "duration"]}')
    assert resp["error"] == "success"
    assert resp["data"] == 180.0

    # 3. set_property volume
    resp = server.dispatch_command('{"command": ["set_property", "volume", 50]}')
    assert resp["error"] == "success"
    assert fake_session.transport.volume == 0.5

    # 4. seek
    fake_session.transport.seek_relative.return_value = 52.0
    resp = server.dispatch_command('{"command": ["seek", 10, "relative"]}')
    assert resp["error"] == "success"
    assert resp["data"] == 52.0
    fake_session.transport.seek_relative.assert_called_with(10.0)

    # 4b. seek absolute
    fake_session.transport.seek_to.return_value = 95.0
    resp = server.dispatch_command('{"command": ["seek", 95, "absolute"]}')
    assert resp["error"] == "success"
    assert resp["data"] == 95.0
    fake_session.transport.seek_to.assert_called_with(95.0)

    # 5. cycle pause
    resp = server.dispatch_command('{"command": ["cycle", "pause"]}')
    assert resp["error"] == "success"
    fake_session.transport.toggle_play_pause.assert_called()

    # 6. Invalid command
    resp = server.dispatch_command('{"command": ["unknown_cmd"]}')
    assert "not implemented" in resp["error"]


def test_ipc_server_client_roundtrip():
    fake_session = MagicMock()
    fake_session.transport.is_playing = True
    fake_session.transport.current_pts = 15.5
    fake_session.transport.duration_sec = 60.0
    fake_session.transport.volume = 1.0

    server = MediaIPCServer(session=fake_session, port=0)
    port = server.start()

    try:
        client = MediaIPCClient(port=port, auth_token=server.auth_token)
        pts = client.get_playback_time()
        assert pts == 15.5

        client.set_volume(80)
        assert fake_session.transport.volume == 0.8

        client.toggle_pause()
        fake_session.transport.toggle_play_pause.assert_called()

        client.quit()
        fake_session.stop.assert_called()
    finally:
        server.stop()


def test_transport_seek_absolute():
    from pinak.media.player.transport import TransportController

    tc = TransportController(duration_sec=120.0)
    tc.seek_to(30.0)
    assert tc.current_pts == 30.0

    tc.seek_absolute(75.0)
    assert tc.current_pts == 75.0

    # Bounds check
    tc.seek_absolute(999.0)
    assert tc.current_pts == 120.0


def test_ipc_auth_token_protection():
    """Verifies that MediaIPCServer rejects unauthenticated requests when auth_token is set (SEC-02)."""
    fake_session = MagicMock()
    fake_session.transport.current_pts = 22.0

    server = MediaIPCServer(session=fake_session, port=0, auth_token="secret-token-123")
    port = server.start()

    try:
        # 1. Unauthenticated client should be rejected
        unauth_client = MediaIPCClient(port=port)
        res = unauth_client.send_command("get_property", "playback-time")
        assert "unauthorized" in res.get("error", "").lower()

        # 2. Authenticated client should succeed
        auth_client = MediaIPCClient(port=port, auth_token="secret-token-123")
        pts = auth_client.get_playback_time()
        assert pts == 22.0
    finally:
        server.stop()

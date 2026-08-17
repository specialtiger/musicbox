from __future__ import annotations

import json
import socket
import threading
import time
import urllib.request
import pytest

from NEMbox.web import MusicboxWebHandler, _HTML_PAGE
import http.server


@pytest.fixture
def test_web_server(monkeypatch):
    # Mock send_request for tests
    def mock_send_request(method, params=None):
        if method == "player.status":
            return {
                "ok": True,
                "data": {
                    "state": "playing",
                    "song": {
                        "id": 123456,
                        "name": "Test Song",
                        "artist": "Test Artist",
                        "album": "Test Album",
                        "duration": 200,
                    },
                    "position": 45.0,
                    "length": 200,
                    "volume": 60,
                    "mode": "ordered",
                    "backend": "mpv",
                },
            }
        elif method == "queue.list":
            return {
                "ok": True,
                "data": {
                    "items": [
                        {"song_id": 123456, "name": "Test Song", "artist": "Test Artist"}
                    ],
                    "index": 0,
                    "size": 1,
                },
            }
        elif method == "player.lyrics":
            return {
                "ok": True,
                "data": {
                    "song_id": 123456,
                    "name": "Test Song",
                    "lyric": ["[00:10.00]Hello world"],
                    "tlyric": ["[00:10.00]你好世界"],
                },
            }
        elif method == "player.toggle":
            return {"ok": True, "data": {"state": "paused"}}
        return {"ok": True, "data": {}}

    monkeypatch.setattr("NEMbox.web.send_request", mock_send_request)

    # Start ephemeral test server
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), MusicboxWebHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield f"http://127.0.0.1:{port}"

    server.shutdown()
    server.server_close()


def test_web_index_page(test_web_server):
    with urllib.request.urlopen(f"{test_web_server}/") as resp:
        assert resp.status == 200
        content = resp.read().decode("utf-8")
        assert "MusicBox" in content
        assert "progress-bar-fill" in content


def test_web_api_status(test_web_server):
    with urllib.request.urlopen(f"{test_web_server}/api/status") as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["ok"] is True
        assert data["data"]["song"]["name"] == "Test Song"


def test_web_api_queue(test_web_server):
    with urllib.request.urlopen(f"{test_web_server}/api/queue") as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["ok"] is True
        assert len(data["data"]["items"]) == 1


def test_web_api_control(test_web_server):
    req = urllib.request.Request(
        f"{test_web_server}/api/control",
        data=json.dumps({"action": "toggle", "params": {}}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["ok"] is True
        assert data["data"]["state"] == "paused"

"""Regression: POST chime preferences/preview must never demand a query 'request'."""
from __future__ import annotations
import importlib.util
import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI

ROOT = Path(__file__).resolve().parents[1] / "historia-clinica" / "app"
spec = importlib.util.spec_from_file_location("queue_arrival_chime_test_http", ROOT / "queue_arrival_chime.py")
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

with tempfile.TemporaryDirectory() as root:
    app = FastAPI()
    monitor = mod.install(app, lambda: None, Path(root), lambda row: False)
    for path in ("/api/queue/chime", "/api/queue/chime/test"):
        route = next(r for r in app.routes
                     if getattr(r, "path", "") == path and "POST" in getattr(r, "methods", set()))
        assert not route.dependant.query_params, (path, route.dependant.query_params)
        assert not route.dependant.body_params, (path, route.dependant.body_params)

    def request(method, path, payload=None, authorized=True):
        # Native ASGI HTTP simulation; avoids httpx or any network dependency.
        raw = json.dumps(payload if payload is not None else {}).encode()
        hdr = [(b"content-type", b"application/json")]
        if authorized:
            hdr.append((b"x-historia-queue-chime", b"1"))
        scope = {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
            "method": method, "scheme": "http", "path": path,
            "raw_path": path.encode(), "query_string": b"",
            "root_path": "", "headers": hdr, "client": ("127.0.0.1", 6000),
            "server": ("127.0.0.1", 80),
        }
        calls = 0
        messages = []
        async def receive():
            nonlocal calls
            calls += 1
            if calls == 1:
                return {"type":"http.request", "body":raw, "more_body":False}
            return {"type":"http.disconnect"}
        async def send(message):
            messages.append(message)
        asyncio.run(app(scope, receive, send))
        status = next(m["status"] for m in messages if m["type"]=="http.response.start")
        body = b"".join(m["body"] for m in messages if m["type"]=="http.response.body")
        return status, json.loads(body)

    # Former bug: 422 with loc=["query","request"] before reaching the sound.
    status, body = request("POST", "/api/queue/chime",
                           {"enabled":True, "volume":70, "sound":"soft"})
    assert status == 200, (status, body)
    assert body["volume"] == 70 and monitor.settings["sound"]=="soft"
    with patch.object(mod, "_play_native_diagnostic",
                      return_value={"ok":True, "method":"wav",
                                    "message":"Prueba reproducida"}) as playback:
        status, body = request("POST", "/api/queue/chime/test")
        assert status == 200 and body["ok"] is True, (status, body)
        assert body["method"] == "wav"
        playback.assert_called_once_with(70, "soft")

    with patch.object(mod, "_play_native_diagnostic",
                      return_value={"ok":False, "method":"",
                                    "message":"Dispositivo de audio no disponible"}):
        status, body = request("POST", "/api/queue/chime/test")
        assert status == 503 and "Dispositivo de audio" in body["message"], (status, body)
        assert status != 422

    status, body = request("POST", "/api/queue/chime", {"enabled":False},
                           authorized=False)
    assert status == 403, (status, body)
    status, body = request("POST", "/api/queue/chime/test", authorized=False)
    assert status == 403, (status, body)
    status, body = request("POST", "/api/queue/chime",
                           {"enabled":True, "volume":1000})
    assert status == 400, (status, body)

print("HISTORIA_CHIME_HTTP_1461_REQUIRED_REQUEST_FIELD_FIXED_OK")

"""Regression: POST chime preferences/preview must never demand a query 'request'."""
from __future__ import annotations
import importlib.util
import tempfile
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

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

    headers = {"X-Historia-Queue-Chime": "1"}
    client = TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 6000))

    # This was formerly 422 "Field required" because Request was unresolved
    # under postponed annotations imported only inside install().
    res = client.post("/api/queue/chime", headers=headers,
                      json={"enabled": True, "volume": 70, "sound": "soft"})
    assert res.status_code == 200, (res.status_code, res.text)
    assert res.json()["volume"] == 70, res.json()
    assert monitor.settings["sound"] == "soft"

    with patch.object(mod, "_play_native_diagnostic",
                      return_value={"ok": True, "method": "wav",
                                    "message": "Prueba reproducida"}) as playback:
        res = client.post("/api/queue/chime/test", headers=headers, json={})
        assert res.status_code == 200, (res.status_code, res.text)
        assert res.json()["ok"] is True
        assert res.json()["method"] == "wav"
        playback.assert_called_once_with(70, "soft")

    with patch.object(mod, "_play_native_diagnostic",
                      return_value={"ok": False, "method": "",
                                    "message": "Dispositivo de audio no disponible"}):
        res = client.post("/api/queue/chime/test", headers=headers, json={})
        assert res.status_code == 503, (res.status_code, res.text)
        assert "Dispositivo de audio" in res.json()["message"]
        assert res.status_code != 422

    res = client.post("/api/queue/chime", json={"enabled": False}, headers={})
    assert res.status_code == 403, (res.status_code, res.text)
    res = client.post("/api/queue/chime/test", json={}, headers={})
    assert res.status_code == 403, (res.status_code, res.text)
    res = client.post("/api/queue/chime", headers=headers,
                      json={"enabled": True, "volume": 1000})
    assert res.status_code == 400, (res.status_code, res.text)

print("HISTORIA_CHIME_HTTP_1461_REQUIRED_REQUEST_FIELD_FIXED_OK")

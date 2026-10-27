"""Pruebas de avisos sonoros locales: consultas/revisiones sí, procedimientos no."""
from __future__ import annotations
import importlib.util
import io
import sqlite3
import tempfile
import wave
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "historia-clinica" / "app"
spec = importlib.util.spec_from_file_location("queue_arrival_chime", ROOT / "queue_arrival_chime.py")
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def is_procedure(row):
    norm = mod._kind(row["attention_type"])
    return norm not in {"", "CONSULTA", "N", "NUEVO", "S", "SUBSECUENTE",
                        "REVISION DE EXAMENES"}

with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    data = root / "queue.db"
    conn = sqlite3.connect(data)
    conn.execute("""CREATE TABLE waiting_queue (
        id TEXT PRIMARY KEY, status TEXT, attention_type TEXT,
        queued_at TEXT, deleted_at TEXT)""")
    conn.commit()
    conn.close()
    def db():
        c = sqlite3.connect(data)
        c.row_factory = sqlite3.Row
        return c
    def add(id, kind="Consulta", status="waiting"):
        with db() as c:
            c.execute("INSERT INTO waiting_queue VALUES (?,?,?,?,NULL)",
                      (id,status,kind,datetime.now().isoformat(timespec="seconds")))
            c.commit()
    count = []
    def sound():
        count.append("chime")
    add("old_consult")
    add("old_review", "Revisión de exámenes")
    monitor = mod.QueueArrivalChime(db, root, is_procedure, player=sound)
    assert monitor.settings == {"enabled":True,"volume":40,"sound":"soft"}
    assert not monitor.check_once(), "Al arrancar no suenan pacientes antiguos"
    assert not count
    add("procedure", "Ecografía")
    assert not monitor.check_once() and not count, "Procedimiento debe ser silencioso"
    add("procedure_named", "Procedimiento · Curación")
    assert not monitor.check_once() and not count
    add("consult", "Consulta")
    assert monitor.check_once() and len(count)==1
    assert not monitor.check_once() and len(count)==1, "No repetir por cada sondeo"
    add("review", "REVISION DE EXAMENES")
    assert monitor.check_once() and len(count)==2
    add("review_accents","REVISIÓN DE EXÁMENES")
    assert monitor.check_once() and len(count)==3
    add("group_a","Consulta")
    add("group_b","Subsecuente")
    assert monitor.check_once() and len(count)==4, "Un sonido por grupo de llegadas"
    with db() as c:
        c.execute("UPDATE waiting_queue SET status='in_consultation' WHERE id='consult'")
        c.commit()
    assert not monitor.check_once() and len(count)==4, "Cambio de estado no reproduce"
    monitor.set_settings(False, 60, "short")
    add("muted","Consulta")
    assert not monitor.check_once() and len(count)==4
    assert monitor.settings=={"enabled":False,"volume":60,"sound":"short"}
    assert monitor.preview() and len(count)==5, "Prueba manual independiente del silencio"
    again=mod.QueueArrivalChime(db,root,is_procedure,player=sound)
    assert again.settings=={"enabled":False,"volume":60,"sound":"short"}
    assert not again.check_once(), "Reabrir Historia no reproduce los existentes"
    again.set_enabled(True)
    assert again.check_once() is False, "Activar sonido no reproduce acumulados"
    add("new_after_restart","Consulta")
    assert again.check_once() and len(count)==6
    try:
        again.set_settings(True, 150, "soft")
        raise AssertionError("Volumen inválido permitido")
    except ValueError:
        pass
    try:
        again.set_settings(True, 25, "unknown")
        raise AssertionError("Tipo inválido permitido")
    except ValueError:
        pass
    for kind in ("soft","short"):
        with wave.open(io.BytesIO(mod._gentle_chime(40,kind)), "rb") as wave_file:
            assert wave_file.getnchannels()==1 and wave_file.getframerate()==22050
            assert wave_file.getnframes()>0
    assert mod._gentle_chime(0)!=mod._gentle_chime(80)
    assert "select" not in (root/"data"/"queue_arrival_chime.json").read_text().lower()

# Simulación de Windows: si falla WAV en memoria, probar WAV por archivo.
import os
import sys
import types
from unittest.mock import patch
calls = []
fake_winsound = types.SimpleNamespace(SND_MEMORY=4, SND_FILENAME=2, SND_NODEFAULT=8)
def fake_play(sound, flags):
    calls.append((type(sound).__name__, flags))
    if isinstance(sound, bytes):
        raise RuntimeError("SND_MEMORY denied")
    assert Path(sound).is_file()
    with wave.open(sound, "rb") as w:
        assert w.getnchannels()==1 and w.getnframes()>0
fake_winsound.PlaySound = fake_play
fake_os = types.SimpleNamespace(name="nt", fdopen=os.fdopen, unlink=os.unlink)
with patch.object(mod, "os", fake_os), patch.dict(sys.modules, {"winsound": fake_winsound}):
    result = mod._play_native_diagnostic(40, "soft")
    assert result["ok"] is True and result["method"]=="wav", result
    assert [name for name,flags in calls]==["bytes","str"]
    zero = mod._play_native_diagnostic(0, "soft")
    assert zero["ok"] is False and "0%" in zero["message"]
    def reject_all(sound, flags):
        raise RuntimeError("no output available")
    fake_winsound.PlaySound=reject_all
    result=mod._play_native_diagnostic(40,"short")
    assert result["ok"] is False
    assert "Windows no pudo reproducir" in result["message"]
    assert "no output available" in result["message"]

app=(ROOT/"app.py").read_text(encoding="utf-8")
docs=(ROOT/"documentos_clinicos.py").read_text(encoding="utf-8")
css=(ROOT/"static"/"style.css").read_text(encoding="utf-8")
module=(ROOT/"queue_arrival_chime.py").read_text(encoding="utf-8")
assert "queue_arrival_chime.install(app, db, ROOT, _queue_is_procedure)" in app
assert "@app.on_event(\"startup\")" in module and "monitor.start()" in module
assert "@app.on_event(\"shutdown\")" in module and "monitor.stop()" in module
assert "FROM waiting_queue" in module and "WHERE status IN ('waiting','in_consultation')" in module
assert "/api/queue/chime/test" in module
assert "get_sync_status" not in module and "neon" not in module.lower()
assert "hc-b-chime-toggle" in app and "loadChime()" in app
for key in ("cfg-chime-volume", "cfg-chime-sound", "cfg-chime-test",
            "cfg-chime-enabled", "cfgSaveChime", "cfgLoadChime"):
    assert key in docs, key
assert "Avisos sonoros" in docs and "Campanilla suave" in docs
assert "Historia v1.4.59" in css
assert "_play_native_diagnostic" in module and "winsound.SND_FILENAME" in module
assert "monitor.preview_result()" in module
assert not module.startswith("from __future__ import annotations"), "Aplazamiento convertía Request en query HTTP 422"
assert "from fastapi import HTTPException, Request" in module
assert "cfgChimeReadResponse" in docs
assert "cfgChimeErrorText" in docs
assert "Si no lo escucha" in docs
assert "cfgChimeStatus.textContent=message" in docs

print("HISTORIA_QUEUE_ARRIVAL_CHIME_1459_OK")

"""Regresión 4.8.124: guardado local ágil y reintento LAN acotado y seguro."""
from pathlib import Path
import ast
from datetime import datetime, timedelta
import json

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "recepcion/app"
identity = (APP / "reception_history_identity_consolidated.py").read_text(encoding="utf-8")
transport = (APP / "historia_lan_transport.py").read_text(encoding="utf-8")
app = (APP / "app.py").read_text(encoding="utf-8")
version = json.loads((APP / "recepcion-version.json").read_text(encoding="utf-8"))["version"]
manifest = json.loads((APP / "update_manifest.json").read_text(encoding="utf-8"))

assert tuple(map(int, version.split("."))) >= (4, 8, 124)
assert all(manifest[k] == version for k in ("version", "app_version", "runtime_version"))

# La pantalla no repite un POST de prepare a Neon si ya dispone de estado
# verificado y reciente del MISMO paciente (hasta cinco minutos).
assert "const cached=statusCache.get(pid);" in identity
assert "const recentlyVerified=!!(" in identity
assert "Date.now()-cached.at<300000" in identity
assert "checked?.linked===true" in identity
assert "checked?.clinical_patient?.verified" in identity
assert "if(!recentlyVerified){" in identity
assert "try{pre=await prepare(pid,true)}" in identity
assert "if(pre?.ok!==false&&pre?.reachable!==false&&!pre?.linked)" in identity

# El pago y la atención siguen confirmando primero en SQLite local; cloud sync
# va en un worker separado y no en el HTTP de guardado.
assert "def v466_fast_local_attention_save" in app
assert "Depends(_v466_local_attention_db)" in app
assert "_v466_sync_attention_queue_later()" in app

# La seguridad LAN no se relaja: cada handoff resuelve un vínculo verificado
# consultando Neon y solo entonces envía a Historia.
assert "AND l.verified=1" in transport
assert "AND l.deleted_at IS NULL" in transport
assert "SELECT event_id,payload_json,attempt_count" in transport
flush = transport[transport.index("def _flush_lan_outbox"):transport.index("def remap_pending_patient_id")]
assert flush.index("verified_id = _cloud_link_id(patient_id)") < flush.index("if send_lan(payload):")
assert "if not verified_id:" in flush
assert "_recent_unlinked_retry_seconds(" in flush
assert "30 if transient else _recent_unlinked_retry_seconds(" in flush
assert "else \"Ficha clínica pendiente de verificar o vincular\"" in flush

# Evaluación real del helper: cinco reintentos cortos y limitados a los
# primeros tres minutos; los turnos antiguos vuelven a cinco minutos.
tree = ast.parse(transport)
fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
          and node.name == "_recent_unlinked_retry_seconds")
env = {"datetime": datetime}
exec(compile(ast.Module(body=[fn], type_ignores=[]), "<retry-helper>", "exec"), env)
delay = env["_recent_unlinked_retry_seconds"]
fresh = datetime.now().isoformat(timespec="seconds")
old = (datetime.now() - timedelta(minutes=5)).isoformat(timespec="seconds")
assert [delay(fresh, i) for i in range(5)] == [8, 15, 25, 40, 60]
assert delay(fresh, 5) == 300
assert delay(old, 0) == 300
assert delay("broken-date", 0) == 300
print("RECEPTION_FAST_SAVE_SAFE_LAN_RETRY_48124_OK")

from __future__ import annotations

import json
import py_compile
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "updates" / "v4_6_5_historia_procedure_names"
OUT = ROOT / "updates" / "v4_6_6_fast_attention_save"
CHANNEL = ROOT / "launcher-v1" / "app-channel-source.json"

if OUT.exists():
    shutil.rmtree(OUT)
shutil.copytree(BASE, OUT)

app_path = OUT / "app.py"
app = app_path.read_text(encoding="utf-8-sig")

# The production 4.6.5 source must be the exact audited baseline.
assert 'v4.6.5: sólo enriquece la etiqueta administrativa enviada a Historia.' in app
assert 'Guardando atención e imprimiendo recibo…' in app
assert 'def v4544_print_visit_exact_status(' in app
assert 'def v4535_create_visit_batch_payment(' in app

TAIL = r'''

# ---------------------------------------------------------------------------
# v4.6.6 — Guardado de atención local-first + sincronización en segundo plano.
#
# Objetivos:
# - Guardar Consulta/Procedimiento primero en SQLite local para que la PC vieja
#   no tenga que esperar la latencia de Neon antes de volver a Inicio.
# - Reutilizar EXACTAMENTE la cola offline ya auditada: visit.create crea en
#   nube el Visit + BillingRecord y v4.4.51 conserva source_row/forma de pago.
# - Mantener el handoff Historia de v4.6.5 y el recibo SOLO para Consulta.
# - La impresión lee siempre SQLite local y nunca bloquea por una conexión Neon.
# - Ningún cambio de esquema, precios, AZUR, WhatsApp, Bendo ni datos clínicos.
# ---------------------------------------------------------------------------

_V466_BASE_BATCH = None
for _route in list(app.router.routes):
    if (
        getattr(_route, "path", None) == "/api/visits/batch-payment"
        and "POST" in set(getattr(_route, "methods", set()) or set())
    ):
        _V466_BASE_BATCH = getattr(_route, "endpoint", None)
        app.router.routes.remove(_route)
        break
if _V466_BASE_BATCH is None:
    raise RuntimeError("v4.6.6 no encontró la ruta activa de guardado de atención")


def _v466_local_attention_db():
    """Sesión SQLite duradera para el guardado crítico de Nueva atención."""
    db = core.LocalSessionLocal()
    try:
        db.info["offline"] = True
        db.info["local_first"] = True
        db.info["v466_attention_write_behind"] = True
        yield db
    finally:
        db.close()


def _v466_sync_attention_queue_later():
    # Dar tiempo al POST de impresión de Consulta para leer el mismo ID local.
    # La cola queda persistida antes de que este hilo exista, por lo que un
    # cierre/corte de luz no pierde el cambio: el recovery normal la reintenta.
    def _worker():
        try:
            time.sleep(1.0)
            core.process_offline_queue()
        except Exception as exc:
            try:
                core.logging.getLogger(__name__).warning(
                    "v4.6.6: sync posterior a atención pendiente: %s", exc
                )
            except Exception:
                pass

    try:
        core.threading.Thread(
            target=_worker,
            name="rp-attention-cloud-sync",
            daemon=True,
        ).start()
    except Exception:
        # La atención YA está confirmada en SQLite + OfflineQueue.
        pass


@app.post("/api/visits/batch-payment")
def v466_fast_local_attention_save(
    data: bridge_v4508.payment_core.V4504VisitBatchPaymentIn,
    db=core.Depends(_v466_local_attention_db),
    user=core.Depends(core.current_user),
):
    started = time.perf_counter()
    result = _V466_BASE_BATCH(data, db, user)
    save_ms = (time.perf_counter() - started) * 1000.0
    _v466_sync_attention_queue_later()
    if isinstance(result, dict):
        result["local_first"] = True
        result["cloud_sync_scheduled"] = True
        result["save_ms"] = round(save_ms, 1)
    return result


# Impresión: la atención acaba de nacer en SQLite, así que imprimir desde la
# copia local evita una segunda ida a Neon. También protege la carrera ID local
# -> ID cloud mientras el write-behind se sincroniza.
_V466_BASE_PRINT = None
for _route in list(app.router.routes):
    if (
        getattr(_route, "path", None) == "/api/v4470/print-visit/{visit_id}"
        and "POST" in set(getattr(_route, "methods", set()) or set())
    ):
        _V466_BASE_PRINT = getattr(_route, "endpoint", None)
        app.router.routes.remove(_route)
        break
if _V466_BASE_PRINT is None:
    raise RuntimeError("v4.6.6 no encontró la ruta activa de impresión de recibo")


@app.post("/api/v4470/print-visit/{visit_id}")
def v466_print_visit_local_first(
    visit_id: int,
    data: _V4544PrintVisitIn,
    db=core.Depends(_v466_local_attention_db),
    user=core.Depends(core.current_user),
):
    return _V466_BASE_PRINT(visit_id, data, db, user)


# v4.4.70 mostraba "imprimiendo recibo" desde ANTES de saber si lo guardado
# era una consulta. Los procedimientos no imprimen y nunca deben insinuarlo.
_V466_OLD_BUSY = "Guardando atención e imprimiendo recibo…"
_V466_NEW_BUSY = "Guardando atención…"
_V466_BUSY_REPLACEMENTS = (getattr(core, "V460_OVERLAY_JS", "") or "").count(
    _V466_OLD_BUSY
)
if _V466_BUSY_REPLACEMENTS < 1:
    raise RuntimeError("v4.6.6 no encontró el texto legacy de impresión")
core.V460_OVERLAY_JS = (getattr(core, "V460_OVERLAY_JS", "") or "").replace(
    _V466_OLD_BUSY,
    _V466_NEW_BUSY,
)


@app.get("/api/v466/health")
def v466_health(user=core.Depends(core.current_user)):
    return {
        "ok": True,
        "version": APP_VERSION,
        "attention_write": "sqlite-first-cloud-write-behind",
        "cloud_sync_background": True,
        "print_source": "sqlite-local",
        "procedure_auto_print": False,
        "consultation_auto_print": True,
        "procedure_printing_label_removed": True,
        "database_schema_changes": False,
        "billing_logic_changes": False,
        "azur_logic_changes": False,
        "whatsapp_logic_changes": False,
    }
'''

# Version is derived from recepcion-version.json at runtime, so app.py itself
# does not hard-code 4.6.6. Append only the final behavioral override.
app = app.rstrip() + "\n" + TAIL.lstrip()
app_path.write_text(app, encoding="utf-8", newline="\n")

# Canonical version.
(OUT / "recepcion-version.json").write_text(
    json.dumps({"version": "4.6.6"}, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
    newline="\n",
)

# Manifest: preserve contracts and change only explicit 4.6.6 metadata.
manifest_path = OUT / "update_manifest.json"
manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
manifest["version"] = "4.6.6"
manifest["app_version"] = "4.6.6"
manifest["runtime_version"] = "4.6.6"
manifest["notes"]["purpose"] = (
    "Guardado de Nueva atención local-first para respuesta inmediata; "
    "sincronización a Neon en segundo plano e impresión local sin espera de nube."
)
manifest["notes"]["previous_version"] = "4.6.5"
manifest["notes"]["printing_changes"] = True
manifest["notes"]["procedure_auto_print"] = False
manifest["notes"]["consultation_auto_print_preserved"] = True
manifest["notes"]["attention_write_mode"] = "sqlite-first-cloud-write-behind"
manifest["notes"]["offline_queue_reused"] = True
manifest["notes"]["billing_logic_changes"] = False
manifest["notes"]["azur_logic_changes"] = False
manifest["notes"]["whatsapp_logic_changes"] = False
manifest["notes"]["database_schema_changes"] = False
manifest["notes"]["patient_data_changes"] = False
manifest["notes"]["rollback_safe"] = True
manifest_path.write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
    newline="\n",
)

# Channel source points to one fully materialized runtime, never multipart.
channel = json.loads(CHANNEL.read_text(encoding="utf-8-sig"))
channel["appVersion"] = "4.6.6"
channel["notes"] = (
    "Recepción 4.6.6: Nueva atención se confirma primero en SQLite local y "
    "sincroniza Neon en segundo plano. Procedimientos no muestran ni ejecutan "
    "impresión; consultas conservan recibo automático sin depender de Neon para imprimir."
)
for item in channel["files"]:
    src = str(item.get("sourcePath") or "")
    if "v4_6_5_historia_procedure_names" in src:
        item["sourcePath"] = src.replace(
            "v4_6_5_historia_procedure_names",
            "v4_6_6_fast_attention_save",
        )
CHANNEL.write_text(
    json.dumps(channel, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
    newline="\n",
)

# Static safety contracts.
py_compile.compile(str(app_path), doraise=True)
assert json.loads((OUT / "recepcion-version.json").read_text())["version"] == "4.6.6"
manifest2 = json.loads(manifest_path.read_text())
for key in ("version", "app_version", "runtime_version"):
    assert manifest2[key] == "4.6.6", (key, manifest2[key])
assert "sqlite-first-cloud-write-behind" in app
assert 'reason": "procedure_only"' in app
assert 'Atención guardada. Los procedimientos no generan recibo.' in app
assert '_v466_local_attention_db' in app
assert '_v466_sync_attention_queue_later' in app
assert 'core.process_offline_queue()' in app
assert '_V466_OLD_BUSY = "Guardando atención e imprimiendo recibo…"' in app

# No helper/transport drift is allowed in this performance release.
for rel in ("historia_bridge.py", "historia_lan_transport.py", "static/runtime_keep.txt"):
    assert (OUT / rel).read_bytes() == (BASE / rel).read_bytes(), rel

print("Generated Recepción 4.6.6 candidate")
print("app bytes", app_path.stat().st_size)

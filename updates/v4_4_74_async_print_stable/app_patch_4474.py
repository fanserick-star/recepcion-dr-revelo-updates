from __future__ import annotations

# v4.4.74 — impresión desacoplada sin tocar el flujo visual estable.
# - Parte de v4.4.73, confirmada funcionando en la PC del consultorio.
# - NO reemplaza saveAttention ni agrega MutationObserver.
# - La atención sigue guardándose con el flujo probado de v4.4.70.
# - Solo desacopla el trabajo pesado de Windows: el recibo entra a una cola
#   local y la interfaz puede volver a Inicio apenas el guardado fue confirmado.
# - La cola usa un único worker para no saturar la PC antigua ni mezclar recibos.
# - Conserva el diseño térmico aprobado v4.4.69.

import os
import queue
import threading
import time

import app_patch_4473 as previous

core = previous.core
app = previous.app
APP_VERSION = "4.4.74"

_mod = previous
_seen = set()
for _ in range(24):
    if _mod is None or id(_mod) in _seen:
        break
    _seen.add(id(_mod))
    try:
        _mod.APP_VERSION = APP_VERSION
    except Exception:
        pass
    _mod = getattr(_mod, "previous", None)
core.APP_VERSION = APP_VERSION

PATCH_BOOT_OK = False
PATCH_BOOT_ERROR = ""

_PRINT_QUEUE = queue.Queue(maxsize=16)
_PRINT_LOCK = threading.Lock()
_PRINT_STATE = {
    "queued_total": 0,
    "printed_total": 0,
    "failed_total": 0,
    "last_status": "idle",
    "last_error": "",
    "last_printer": "",
    "last_finished_at": 0.0,
}

try:
    _stable_print_receipt_windows = core._print_receipt_windows

    def _record_state(**values):
        with _PRINT_LOCK:
            _PRINT_STATE.update(values)

    def _resolve_printer_name_fast(printer_name: str = "") -> str:
        chosen = str(printer_name or "").strip()
        if chosen:
            return chosen
        if os.name != "nt":
            raise RuntimeError("La impresión directa solo está disponible en Windows")
        try:
            import clr  # type: ignore
            clr.AddReference("System.Drawing")
            from System.Drawing.Printing import PrinterSettings  # type: ignore
            chosen = str(PrinterSettings().PrinterName or "").strip()
        except Exception as exc:
            raise RuntimeError(f"No se pudo consultar la impresora predeterminada: {exc}") from exc
        if not chosen:
            raise RuntimeError("Windows no tiene una impresora predeterminada")
        return chosen

    def _print_worker():
        while True:
            payload, printer_name, show_blood_pressure = _PRINT_QUEUE.get()
            try:
                _record_state(
                    last_status="printing",
                    last_error="",
                    last_printer=str(printer_name or ""),
                )
                used = _stable_print_receipt_windows(
                    payload,
                    printer_name,
                    show_blood_pressure,
                )
                with _PRINT_LOCK:
                    _PRINT_STATE["printed_total"] += 1
                    _PRINT_STATE["last_status"] = "printed"
                    _PRINT_STATE["last_error"] = ""
                    _PRINT_STATE["last_printer"] = str(used or printer_name or "")
                    _PRINT_STATE["last_finished_at"] = time.time()
            except Exception as exc:
                with _PRINT_LOCK:
                    _PRINT_STATE["failed_total"] += 1
                    _PRINT_STATE["last_status"] = "error"
                    _PRINT_STATE["last_error"] = str(exc)[:240]
                    _PRINT_STATE["last_finished_at"] = time.time()
                try:
                    core.logging.getLogger(__name__).warning(
                        "v4.4.74: fallo de impresión en segundo plano: %s", exc
                    )
                except Exception:
                    pass
            finally:
                _PRINT_QUEUE.task_done()

    _PRINT_THREAD = threading.Thread(
        target=_print_worker,
        name="rp-receipt-printer",
        daemon=True,
    )
    _PRINT_THREAD.start()

    def _print_receipt_windows_v4474(
        payload,
        printer_name: str = "",
        show_blood_pressure: bool = True,
    ) -> str:
        """Encola el recibo y devuelve enseguida; el worker habla con Windows."""
        chosen = _resolve_printer_name_fast(printer_name)
        try:
            _PRINT_QUEUE.put_nowait(
                (payload, chosen, bool(show_blood_pressure))
            )
        except queue.Full as exc:
            raise RuntimeError(
                "Hay demasiados recibos esperando impresión. Reintenta en unos segundos."
            ) from exc
        with _PRINT_LOCK:
            _PRINT_STATE["queued_total"] += 1
            _PRINT_STATE["last_status"] = "queued"
            _PRINT_STATE["last_error"] = ""
            _PRINT_STATE["last_printer"] = chosen
        return chosen

    core._print_receipt_windows = _print_receipt_windows_v4474

    # Mantener el rótulo visible actualizado con el mismo método seguro de 4.4.73:
    # sustitución estática antes de servir el HTML, sin observers ni ciclos DOM.
    _js = getattr(core, "V460_OVERLAY_JS", "") or ""
    _js = _js.replace("const VERSION='4.4.73';", "const VERSION='4.4.74';")
    core.V460_OVERLAY_JS = _js

    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f"{type(exc).__name__}: {exc}"
    try:
        core.logging.getLogger(__name__).error(
            "v4.4.74 background print patch failed: %s", PATCH_BOOT_ERROR
        )
    except Exception:
        pass


@app.get("/api/v4474/print-queue-health")
def v4474_print_queue_health(user=core.Depends(core.current_user)):
    with _PRINT_LOCK:
        state = dict(_PRINT_STATE)
    state.update({
        "ok": PATCH_BOOT_OK,
        "version": APP_VERSION,
        "boot_error": PATCH_BOOT_ERROR,
        "queue_depth": _PRINT_QUEUE.qsize(),
        "worker_alive": bool(globals().get("_PRINT_THREAD") and _PRINT_THREAD.is_alive()),
        "base_ui": "4.4.73 / v4.4.70 flow",
        "changes_save_attention_js": False,
        "uses_dom_observer": False,
        "background_print": True,
        "single_worker": True,
        "receipt_layout_version": "4.4.69",
    })
    return state


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=core.LOCAL_HTTP_PORT,
        reload=False,
        access_log=False,
        log_level="warning",
        workers=1,
    )

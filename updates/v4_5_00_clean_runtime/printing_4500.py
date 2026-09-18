from __future__ import annotations

# v4.5.0 — punto único para impresión y diagnóstico.
# Los diseños aprobados (recibo v4.4.69, comprobante v4.4.88 y formulario
# v4.4.91) se conservan exactamente; este módulo solo centraliza el acceso y
# añade una impresión de prueba corta.

import os
import sys
import threading
from datetime import datetime

import runtime_4500 as previous

core = previous.core
app = previous.app
APP_VERSION = "4.5.0"

_payment_mod = sys.modules.get("app_patch_4485")
_form_mod = sys.modules.get("app_patch_4489")
_queue_mod = sys.modules.get("app_patch_4474")

_STABLE_RECEIPT_PRINT = core._print_receipt_windows
_STABLE_PAYMENT_PRINT = getattr(_payment_mod, "_print_payment_proof_windows", None)
_STABLE_FORM_PRINT = getattr(_form_mod, "_print_billing_data_form_windows", None)

_PRINT_API_LOCK = threading.RLock()


def selected_printer_name() -> str:
    prefs = core._app_preferences()
    configured = str(prefs.get("printer") or "").strip()
    if configured:
        return configured
    info = core._windows_printer_info()
    return str(info.get("default_printer") or "").strip()


def print_receipt(payload, printer_name: str = "", show_blood_pressure: bool = True) -> str:
    # Mantiene la cola asíncrona existente: no bloquea la pantalla.
    return _STABLE_RECEIPT_PRINT(payload, printer_name, show_blood_pressure)


def print_payment_proof(*args, **kwargs):
    if not callable(_STABLE_PAYMENT_PRINT):
        raise RuntimeError("El módulo estable de comprobantes no está disponible")
    return _STABLE_PAYMENT_PRINT(*args, **kwargs)


def print_billing_data_form(printer_name: str = "") -> str:
    if not callable(_STABLE_FORM_PRINT):
        raise RuntimeError("El módulo estable del formulario no está disponible")
    return _STABLE_FORM_PRINT(printer_name)


# Redirige los puntos antiguos a esta capa, preservando las firmas y diseños.
try:
    core._print_receipt_windows = print_receipt
except Exception:
    pass
try:
    if _payment_mod is not None:
        _payment_mod._print_payment_proof_windows = print_payment_proof
except Exception:
    pass
try:
    if _form_mod is not None:
        _form_mod._print_billing_data_form_windows = print_billing_data_form
except Exception:
    pass


def print_queue_status() -> dict:
    out = {
        "available": False,
        "worker_alive": False,
        "queue_depth": 0,
        "last_status": "unknown",
        "last_error": "",
        "printed_total": 0,
        "failed_total": 0,
    }
    try:
        if _queue_mod is None:
            return out
        lock = getattr(_queue_mod, "_PRINT_LOCK", None)
        state = getattr(_queue_mod, "_PRINT_STATE", {}) or {}
        if lock is not None:
            with lock:
                state = dict(state)
        else:
            state = dict(state)
        queue = getattr(_queue_mod, "_PRINT_QUEUE", None)
        thread = getattr(_queue_mod, "_PRINT_THREAD", None)
        out.update(state)
        out["available"] = True
        out["queue_depth"] = int(queue.qsize()) if queue is not None else 0
        out["worker_alive"] = bool(thread and thread.is_alive())
    except Exception as exc:
        out["last_error"] = str(exc)[:220]
    return out


def _print_test_ticket_windows(printer_name: str = "") -> str:
    if os.name != "nt":
        raise RuntimeError("La impresión directa solo está disponible en Windows")

    import clr  # type: ignore
    clr.AddReference("System.Drawing")
    from System.Drawing import (  # type: ignore
        Font, FontStyle, Brushes, Pen, Image, Color,
        StringFormat, StringAlignment, RectangleF
    )
    from System.Drawing.Printing import (  # type: ignore
        PrintDocument, PrinterSettings, PaperSize, Margins
    )

    available = [str(name) for name in PrinterSettings.InstalledPrinters]
    chosen = str(printer_name or "").strip() or str(PrinterSettings().PrinterName or "").strip()
    if not chosen:
        raise RuntimeError("Windows no tiene una impresora predeterminada")
    if available and chosen not in available:
        raise RuntimeError(f"La impresora ‘{chosen}’ ya no está disponible")

    doc = PrintDocument()
    doc.PrinterSettings.PrinterName = chosen
    if not doc.PrinterSettings.IsValid:
        raise RuntimeError(f"Windows no puede usar la impresora ‘{chosen}’")

    doc.DocumentName = "Prueba impresora Recepción"
    doc.OriginAtMargins = True
    doc.DefaultPageSettings.PaperSize = PaperSize("Prueba 80 mm", 315, 260)
    doc.DefaultPageSettings.Margins = Margins(10, 10, 6, 6)

    fonts = []
    logo = {"img": None}

    def font(size, bold=False):
        f = Font("Arial", float(size), FontStyle.Bold if bold else FontStyle.Regular)
        fonts.append(f)
        return f

    f_head = font(10.0, True)
    f_sub = font(7.0)
    f_ok = font(12.0, True)
    f_body = font(7.2)
    f_small = font(6.3)
    pen = Pen(Color.Black, 1.0)
    center = StringFormat()
    center.Alignment = StringAlignment.Center
    center.LineAlignment = StringAlignment.Near

    stamp = datetime.now().astimezone().strftime("%d/%m/%Y %H:%M")

    def on_page(sender, e):
        g = e.Graphics
        width = float(e.MarginBounds.Width)
        y = 0.0
        logo_path = os.path.join(str(core.BASE_DIR), "static", "doctor_isotype.png")
        if os.path.exists(logo_path):
            try:
                logo["img"] = Image.FromFile(logo_path)
                g.DrawImage(logo["img"], 0.0, 1.0, 34.0, 34.0)
            except Exception:
                logo["img"] = None
        x = 39.0 if logo["img"] is not None else 0.0
        g.DrawString("DR. ARMANDO REVELO", f_head, Brushes.Black,
                     RectangleF(x, 2.0, width - x, 16.0), center)
        g.DrawString("CIRUJANO URÓLOGO", f_sub, Brushes.Black,
                     RectangleF(x, 19.0, width - x, 13.0), center)
        y = 42.0
        g.DrawLine(pen, 0.0, y, width, y)
        y += 12.0
        g.DrawString("IMPRESORA OK", f_ok, Brushes.Black,
                     RectangleF(0.0, y, width, 22.0), center)
        y += 29.0
        g.DrawString(f"Recepción v{APP_VERSION}", f_body, Brushes.Black,
                     RectangleF(0.0, y, width, 15.0), center)
        y += 18.0
        g.DrawString(stamp, f_body, Brushes.Black,
                     RectangleF(0.0, y, width, 15.0), center)
        y += 22.0
        g.DrawString("Texto normal  ·  TEXTO EN NEGRITA", f_small, Brushes.Black,
                     RectangleF(0.0, y, width, 14.0), center)
        y += 18.0
        g.DrawLine(pen, 0.0, y, width, y)
        y += 8.0
        g.DrawString("80 mm · prueba de margen y corte", f_small, Brushes.Black,
                     RectangleF(0.0, y, width, 14.0), center)
        e.HasMorePages = False

    doc.PrintPage += on_page
    try:
        doc.Print()
    finally:
        try:
            doc.PrintPage -= on_page
        except Exception:
            pass
        if logo.get("img") is not None:
            try:
                logo["img"].Dispose()
            except Exception:
                pass
        for f in fonts:
            try:
                f.Dispose()
            except Exception:
                pass
        try:
            pen.Dispose()
        except Exception:
            pass
        try:
            center.Dispose()
        except Exception:
            pass
        try:
            doc.Dispose()
        except Exception:
            pass
    return chosen


@app.post("/api/v4500/printing/test")
def v4500_print_test(request: core.Request, user=core.Depends(core.current_user)):
    if hasattr(core, "_is_loopback_client") and not core._is_loopback_client(request):
        raise core.HTTPException(403, "Esta prueba solo se ejecuta desde la PC de Recepción")
    printer = selected_printer_name()
    with _PRINT_API_LOCK:
        try:
            used = _print_test_ticket_windows(printer)
        except Exception as exc:
            raise core.HTTPException(500, f"No se pudo imprimir la prueba: {exc}")
    return {"ok": True, "printer": used, "paper_width_mm": 80, "version": APP_VERSION}

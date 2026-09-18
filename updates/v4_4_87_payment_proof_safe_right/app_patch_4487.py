from __future__ import annotations

# v4.4.87 — margen derecho seguro en comprobante térmico.
# - Corrige el recorte de VALOR y TOTAL PAGADO visto en la impresora de 80 mm.
# - Reserva ~5.5 mm adicionales en el borde derecho para textos y montos.
# - Mueve Hora, columna VALOR y total hacia la izquierda sin achicar el recibo.
# - Hace el concepto un poco más marcado para mejorar legibilidad.
# - No cambia BD, Neon, AZUR, Agenda, atenciones, recibo clínico ni facturación.

import re as _re

import app_patch_4486 as previous

core = previous.core
app = previous.app
APP_VERSION = "4.4.87"

_mod = previous
_seen = set()
for _ in range(76):
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
PAYMENT_RENDER_PATCHED = False

try:
    # app_patch_4486 -> app_patch_4485. El endpoint de v4.4.85 resuelve esta
    # función por el namespace de su propio módulo, así que sustituirla allí
    # conserva el endpoint y cambia únicamente el dibujo del comprobante.
    _payment_mod = getattr(previous, "previous", None)
    if _payment_mod is None:
        raise RuntimeError("No se encontró la capa del comprobante v4.4.85")

    def _print_payment_proof_windows_v4487(
        *,
        patient_name: str,
        proof_ref: str,
        service_date,
        lines,
        payment_method: str,
        printer_name: str = "",
    ) -> str:
        import os as _os
        from datetime import datetime as _datetime

        if _os.name != "nt":
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

        estimated_h = 410 + max(0, len(lines) - 1) * 34
        doc.DocumentName = "Comprobante de pago"
        doc.OriginAtMargins = True
        doc.DefaultPageSettings.PaperSize = PaperSize(
            "Comprobante 80 mm",
            315,
            max(430, min(950, int(estimated_h))),
        )
        doc.DefaultPageSettings.Margins = Margins(10, 10, 6, 6)

        fonts = []
        image_holder = {"img": None}

        def font(size: float, bold: bool = False):
            f = Font("Arial", float(size), FontStyle.Bold if bold else FontStyle.Regular)
            fonts.append(f)
            return f

        f_doctor = font(9.4, True)
        f_specialty = font(7.0, False)
        f_title = font(11.4, True)
        f_ref = font(7.2, True)
        f_label = font(7.2, True)
        f_text = font(8.3, False)
        f_name = font(10.2, True)
        f_item = font(7.8, False)
        f_item_bold = font(7.8, True)
        f_total_label = font(9.4, True)
        f_total = font(14.2, True)
        f_paid = font(12.0, True)
        f_footer = font(6.5, False)

        pen = Pen(Color.Black, 1.0)

        center = StringFormat()
        center.Alignment = StringAlignment.Center
        center.LineAlignment = StringAlignment.Near

        right = StringFormat()
        right.Alignment = StringAlignment.Far
        right.LineAlignment = StringAlignment.Near

        def draw_line(g, y, width):
            g.DrawLine(pen, 0.0, float(y), float(width), float(y))

        def on_print_page(sender, e):
            g = e.Graphics
            width = float(e.MarginBounds.Width)
            # La impresora real recorta unos milímetros del extremo derecho aunque
            # Windows reporte el ancho completo. Todo lo alineado a la derecha
            # termina ahora antes de esa zona física insegura.
            safe_right = max(210.0, width - 22.0)  # ≈ 5.6 mm hacia la izquierda.
            y = 0.0

            logo_path = _os.path.join(str(core.BASE_DIR), "static", "doctor_isotype.png")
            if _os.path.exists(logo_path):
                try:
                    image_holder["img"] = Image.FromFile(logo_path)
                    g.DrawImage(image_holder["img"], 0.0, 1.0, 38.0, 38.0)
                except Exception:
                    image_holder["img"] = None

            title_x = 42.0 if image_holder["img"] is not None else 0.0
            title_w = width - title_x
            g.DrawString(
                "DR. ARMANDO REVELO",
                f_doctor,
                Brushes.Black,
                RectangleF(title_x, 2.0, title_w, 15.0),
                center,
            )
            g.DrawString(
                "CIRUJANO URÓLOGO",
                f_specialty,
                Brushes.Black,
                RectangleF(title_x, 18.0, title_w, 13.0),
                center,
            )
            y = 43.0
            draw_line(g, y, width)

            y += 9.0
            g.DrawString(
                "COMPROBANTE DE PAGO",
                f_title,
                Brushes.Black,
                RectangleF(0.0, y, width, 19.0),
                center,
            )
            y += 21.0
            g.DrawString(
                f"REF. {proof_ref}",
                f_ref,
                Brushes.Black,
                RectangleF(0.0, y, width, 13.0),
                center,
            )
            y += 18.0
            draw_line(g, y, width)

            y += 8.0
            printed_time = _datetime.now().strftime("%H:%M")
            g.DrawString("Fecha:", f_label, Brushes.Black, 0.0, y)
            g.DrawString(service_date.strftime("%d/%m/%Y"), f_text, Brushes.Black, 49.0, y - 1.0)
            g.DrawString("Hora:", f_label, Brushes.Black, safe_right - 88.0, y)
            g.DrawString(printed_time, f_text, Brushes.Black, safe_right - 48.0, y - 1.0)
            y += 22.0

            g.DrawString(
                "PACIENTE",
                f_label,
                Brushes.Black,
                RectangleF(0.0, y, width, 13.0),
                center,
            )
            y += 13.0
            name = " ".join(str(patient_name or "SIN NOMBRE").split()).upper()
            measured = g.MeasureString(name, f_name, int(width))
            name_h = max(24.0, min(46.0, float(measured.Height) + 4.0))
            g.DrawString(
                name,
                f_name,
                Brushes.Black,
                RectangleF(0.0, y, width, name_h),
                center,
            )
            y += name_h + 3.0
            draw_line(g, y, width)

            y += 8.0
            g.DrawString("CONCEPTO", f_label, Brushes.Black, 0.0, y)
            g.DrawString(
                "VALOR",
                f_label,
                Brushes.Black,
                RectangleF(safe_right - 72.0, y, 72.0, 14.0),
                right,
            )
            y += 16.0

            for desc, value in lines:
                item_rect = RectangleF(0.0, y, max(120.0, safe_right - 82.0), 40.0)
                size = g.MeasureString(str(desc), f_item_bold, int(max(120.0, safe_right - 82.0)))
                item_h = max(18.0, min(38.0, float(size.Height) + 2.0))
                g.DrawString(str(desc), f_item_bold, Brushes.Black, item_rect)
                g.DrawString(
                    f"${float(value):.2f}",
                    f_item_bold,
                    Brushes.Black,
                    RectangleF(safe_right - 74.0, y, 74.0, 18.0),
                    right,
                )
                y += item_h + 3.0

            draw_line(g, y, width)
            total = round(sum(float(value or 0) for _desc, value in lines), 2)
            y += 9.0
            g.DrawString("TOTAL PAGADO", f_total_label, Brushes.Black, 0.0, y + 3.0)
            g.DrawString(
                f"${total:.2f}",
                f_total,
                Brushes.Black,
                RectangleF(safe_right - 112.0, y, 112.0, 24.0),
                right,
            )
            y += 30.0

            g.DrawString("Forma de pago:", f_label, Brushes.Black, 0.0, y)
            y += 14.0
            g.DrawString(
                str(payment_method or "NO REGISTRADA"),
                f_item_bold,
                Brushes.Black,
                RectangleF(0.0, y, width, 18.0),
                center,
            )
            y += 24.0
            draw_line(g, y, width)

            y += 10.0
            g.DrawString(
                "PAGADO",
                f_paid,
                Brushes.Black,
                RectangleF(0.0, y, width, 22.0),
                center,
            )
            y += 26.0
            g.DrawString(
                "Gracias por su confianza.",
                f_item_bold,
                Brushes.Black,
                RectangleF(0.0, y, width, 16.0),
                center,
            )
            y += 20.0
            g.DrawString(
                "Comprobante interno de pago.\nNo reemplaza la factura electrónica.",
                f_footer,
                Brushes.Black,
                RectangleF(0.0, y, width, 30.0),
                center,
            )
            e.HasMorePages = False

        doc.PrintPage += on_print_page
        try:
            doc.Print()
        finally:
            try:
                doc.PrintPage -= on_print_page
            except Exception:
                pass
            if image_holder.get("img") is not None:
                try:
                    image_holder["img"].Dispose()
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
                right.Dispose()
            except Exception:
                pass
            try:
                doc.Dispose()
            except Exception:
                pass
        return chosen

    _payment_mod._print_payment_proof_windows = _print_payment_proof_windows_v4487
    PAYMENT_RENDER_PATCHED = True

    _js = (getattr(core, "V460_OVERLAY_JS", "") or "")
    _js = _re.sub(
        r"""const\s+VERSION\s*=\s*['\"]4\.4\.\d+['\"]\s*;""",
        "const VERSION='4.4.87';",
        _js,
    )
    _js = _re.sub(
        r"""const\s+V\s*=\s*['\"]4\.4\.\d+['\"]\s*;""",
        "const V='4.4.87';",
        _js,
    )

    V4487_CSS = r"""
.v460-version,#currentVersionBadge{font-size:0!important}
.v460-version::after,#currentVersionBadge::after{
  content:"v4.4.87"!important;font-size:9px!important;line-height:1!important;font-weight:850!important
}
"""

    V4487_JS = r"""
;(()=>{
  if(window.__v4487PaymentProofSafeRight)return;
  window.__v4487PaymentProofSafeRight=true;
  const VERSION='4.4.87';
  function paint(){
    document.querySelectorAll('.v460-version,#currentVersionBadge').forEach(el=>{
      el.textContent='v'+VERSION;el.setAttribute('data-version','v'+VERSION);
    });
  }
  paint();
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',paint,{once:true});
  setTimeout(paint,250);setTimeout(paint,900);
})();
"""

    core.V460_OVERLAY_CSS = (getattr(core, "V460_OVERLAY_CSS", "") or "") + "\n" + V4487_CSS
    core.V460_OVERLAY_JS = _js + "\n" + V4487_JS
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f"{type(exc).__name__}: {exc}"


@app.get("/api/v4487/health")
def v4487_health(user=core.Depends(core.current_user)):
    return {
        "ok": PATCH_BOOT_OK,
        "version": APP_VERSION,
        "error": PATCH_BOOT_ERROR,
        "payment_render_patched": PAYMENT_RENDER_PATCHED,
        "safe_right_shift_units": 22,
        "approx_safe_right_shift_mm": 5.6,
        "concept_bold": True,
        "database_changes": False,
        "neon_writes_added": False,
        "billing_changes": False,
        "receipt_layout_version": "4.4.69",
    }


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

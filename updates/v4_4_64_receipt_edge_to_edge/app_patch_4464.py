from __future__ import annotations

# v4.4.64 — CRM-308 / recibo 80 mm sin marco exterior.
# - Elimina la línea vertical/marco que aparecía a la izquierda.
# - Usa margen de página 0 para aprovechar el ancho imprimible real del driver.
# - Mantiene un pequeño colchón interno invisible para que SUBSECUENTE nunca se corte.
# - Conserva el formato grande, limpio y legible de v4.4.63.
# - No toca pacientes, agenda, facturación, Neon ni archivos clínicos.

import os
import app_patch_4463 as previous

core = previous.core
app = previous.app
APP_VERSION = "4.4.64"
previous.APP_VERSION = APP_VERSION
core.APP_VERSION = APP_VERSION
try:
    previous.previous.APP_VERSION = APP_VERSION
except Exception:
    pass

PATCH_BOOT_OK = False
PATCH_BOOT_ERROR = ""

try:
    def _receipt_name_lines_v4464(value):
        parts = [x for x in str(value or "").strip().upper().split() if x]
        if not parts:
            return "SIN NOMBRE", ""
        if len(parts) == 1:
            return parts[0], ""
        return " ".join(parts[:2]), " ".join(parts[2:])

    def _print_receipt_windows_v4464(payload, printer_name: str = "", show_blood_pressure: bool = True) -> str:
        if os.name != "nt":
            raise RuntimeError("La impresión directa solo está disponible en Windows")

        import clr  # type: ignore
        clr.AddReference("System.Drawing")
        from System.Drawing import (
            Font, FontStyle, Brushes, Pen, Image, StringFormat,
            StringAlignment, RectangleF, Color
        )  # type: ignore
        from System.Drawing.Drawing2D import DashStyle  # type: ignore
        from System.Drawing.Printing import (
            PrintDocument, PrinterSettings, PaperSize, Margins
        )  # type: ignore

        available = [str(name) for name in PrinterSettings.InstalledPrinters]
        chosen = str(printer_name or "").strip() or str(PrinterSettings().PrinterName or "")
        if not chosen:
            raise RuntimeError("Windows no tiene una impresora predeterminada")
        if available and chosen not in available:
            raise RuntimeError(f"La impresora ‘{chosen}’ ya no está disponible")

        doc = PrintDocument()
        doc.PrinterSettings.PrinterName = chosen
        if not doc.PrinterSettings.IsValid:
            raise RuntimeError(f"Windows no puede usar la impresora ‘{chosen}’")

        doc.DocumentName = "Recibo de consulta médica"
        doc.OriginAtMargins = True
        doc.DefaultPageSettings.PaperSize = PaperSize("Recibo 80 mm", 315, 600)
        # Sin márgenes lógicos: el driver conserva únicamente su margen físico.
        doc.DefaultPageSettings.Margins = Margins(0, 0, 0, 0)

        fonts = []
        image_holder = {"img": None}

        def font(size, bold=False):
            f = Font("Arial", float(size), FontStyle.Bold if bold else FontStyle.Regular)
            fonts.append(f)
            return f

        f_title = font(12.5, True)
        f_label = font(9.2, True)
        f_value = font(10.5, True)
        f_name_label = font(8.5, True)
        f_name = font(11.5, True)
        f_turn = font(13.0, True)
        # Mismo tamaño para ambas opciones; apenas más compacto para dar aire al borde derecho.
        f_status = font(8.5, True)

        solid_pen = Pen(Color.Black, 1.0)
        dotted_pen = Pen(Color.FromArgb(105, 105, 105), 1.0)
        dotted_pen.DashStyle = DashStyle.Dot
        check_pen = Pen(Color.Black, 1.5)

        def on_print_page(sender, e):
            g = e.Graphics
            width = float(e.MarginBounds.Width)

            # No hay marco exterior. Solo dejamos 2 px internos invisibles para
            # evitar que el cabezal/driver recorte el primer o último píxel.
            left = 2.0
            right = max(left + 80.0, width - 2.0)
            content_w = right - left
            y = 6.0

            center = StringFormat()
            center.Alignment = StringAlignment.Center
            center.LineAlignment = StringAlignment.Near

            logo_path = os.path.join(core.BASE_DIR, "static", "doctor_isotype.png")
            logo_box = 43.0
            if os.path.exists(logo_path):
                try:
                    image_holder["img"] = Image.FromFile(logo_path)
                    g.DrawImage(image_holder["img"], left + 2.0, y + 1.0, logo_box, logo_box)
                except Exception:
                    image_holder["img"] = None

            title_x = left + 49.0
            g.DrawString(
                "RECIBO DE\nCONSULTA MÉDICA",
                f_title,
                Brushes.Black,
                RectangleF(title_x, y + 1.0, max(24.0, right - title_x), 46.0),
                center,
            )
            y += 52.0
            g.DrawLine(solid_pen, left, y, right, y)

            def dotted_separator():
                g.DrawLine(dotted_pen, left, y, right, y)

            def row(label, value, value_x=104.0, value_font=None, height=31.0):
                nonlocal y
                top = y
                y += 8.0
                g.DrawString(str(label), f_label, Brushes.Black, left + 1.0, y)
                vx = left + float(value_x)
                g.DrawString(
                    str(value or ""),
                    value_font or f_value,
                    Brushes.Black,
                    RectangleF(vx, y - 1.0, max(20.0, right - vx - 2.0), height - 10.0),
                )
                y = top + height
                dotted_separator()

            row("Fecha:", payload.fecha, 91.0, f_value, 31.0)

            y += 10.0
            g.DrawString("Nombre", f_name_label, Brushes.Black, RectangleF(left, y, content_w, 14.0), center)
            y += 15.0
            surname, given = _receipt_name_lines_v4464(payload.nombre)
            g.DrawString(surname, f_name, Brushes.Black, RectangleF(left, y, content_w, 20.0), center)
            y += 20.0
            if given:
                g.DrawString(given, f_name, Brushes.Black, RectangleF(left, y, content_w, 20.0), center)
                y += 20.0
            y += 8.0
            g.DrawLine(solid_pen, left, y, right, y)

            if bool(payload.is_new) and payload.fecha_nacimiento:
                row("Fecha de nacimiento:", payload.fecha_nacimiento, 154.0, f_value, 34.0)

            if show_blood_pressure:
                top = y
                y += 8.0
                g.DrawString("Presión Arterial:", f_label, Brushes.Black, left + 1.0, y + 4.0)
                box_w = 82.0
                box_h = 31.0
                box_x = max(left + 151.0, right - box_w - 5.0)
                g.DrawRectangle(solid_pen, box_x, y, box_w, box_h)
                y = top + 47.0
                dotted_separator()

            row("Teléfono:", payload.celular or "Sin registrar", 96.0, f_value, 31.0)
            if payload.turno:
                row("Turno:", str(payload.turno), 96.0, f_turn, 34.0)

            # Opciones centradas pero con reserva extra a la derecha.
            y += 15.0
            box = 21.0
            gap = 5.0

            first_label = "PRIMERO"
            second_label = "SUBSECUENTE"
            first_w = float(g.MeasureString(first_label, f_status).Width)
            second_w = float(g.MeasureString(second_label, f_status).Width)
            first_group = box + gap + first_w
            second_group = box + gap + second_w

            # El primero queda centrado en el primer 42% del recibo.
            x1 = left + max(2.0, (content_w * 0.42 - first_group) / 2.0)
            # El subsecuente se ancla al borde derecho con 12 px de aire:
            # así no depende de la medición imperfecta de algunas fuentes/drivers.
            x2 = max(left + content_w * 0.47, right - second_group - 12.0)

            for x, label, checked, label_w in (
                (x1, first_label, bool(payload.is_new), first_w),
                (x2, second_label, not bool(payload.is_new), second_w),
            ):
                g.DrawRectangle(solid_pen, x, y, box, box)
                if checked:
                    g.DrawLine(check_pen, x + 5.0, y + 11.0, x + 9.0, y + 16.0)
                    g.DrawLine(check_pen, x + 9.0, y + 16.0, x + 17.0, y + 5.0)
                # Dibujar texto libre, no dentro de un rectángulo estrecho, evita
                # clipping de la última letra por redondeos de GDI.
                g.DrawString(label, f_status, Brushes.Black, x + box + gap, y + 2.0)

            # Línea final limpia; NO se dibuja marco vertical ni rectángulo exterior.
            y += 32.0
            g.DrawLine(solid_pen, left, y, right, y)
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
            for p in (solid_pen, dotted_pen, check_pen):
                try:
                    p.Dispose()
                except Exception:
                    pass
            try:
                doc.Dispose()
            except Exception:
                pass

        return chosen

    core._print_receipt_windows = _print_receipt_windows_v4464
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f"{type(exc).__name__}: {exc}"
    try:
        core.logging.getLogger(__name__).error("v4.4.64 receipt patch failed: %s", PATCH_BOOT_ERROR)
    except Exception:
        pass


@app.get("/api/v4464/receipt-health")
def v4464_receipt_health(user=core.Depends(core.current_user)):
    return {
        "ok": PATCH_BOOT_OK,
        "version": APP_VERSION,
        "error": PATCH_BOOT_ERROR,
        "schema_migration": False,
        "receipt_only": True,
        "paper_width_mm": 80,
        "logical_margins_mm": 0,
        "outer_frame": False,
        "subsequent_safe_right_padding": True,
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

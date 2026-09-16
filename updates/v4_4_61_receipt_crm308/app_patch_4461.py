from __future__ import annotations

# v4.4.61 — ajuste de recibo térmico 80 mm para Crome CRM-308.
# Solo modifica la composición de impresión: mantiene base de datos, agenda,
# facturación, forma de pago y demás funciones sin cambios.

import os
import app_patch_4459 as previous

core = previous.core
app = previous.app
APP_VERSION = "4.4.61"
previous.APP_VERSION = APP_VERSION
core.APP_VERSION = APP_VERSION
try:
    previous.previous.APP_VERSION = APP_VERSION
except Exception:
    pass

PATCH_BOOT_OK = False
PATCH_BOOT_ERROR = ""

try:
    def _print_receipt_windows_v4461(payload, printer_name: str = "", show_blood_pressure: bool = True) -> str:
        if os.name != "nt":
            raise RuntimeError("La impresión directa solo está disponible en Windows")

        import clr  # type: ignore
        clr.AddReference("System.Drawing")
        from System.Drawing import (
            Font, FontStyle, Brushes, Pen, Image, StringFormat,
            StringAlignment, RectangleF, Color
        )  # type: ignore
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

        # 315 centésimas de pulgada ≈ 80 mm. Margen pequeño y simétrico para
        # aprovechar la zona imprimible real de la CRM-308 sin tocar el corte.
        doc.DefaultPageSettings.PaperSize = PaperSize("Recibo 80 mm", 315, 600)
        doc.DefaultPageSettings.Margins = Margins(7, 7, 7, 7)

        fonts = []
        image_holder = {"img": None}

        def font(size, bold=False):
            f = Font("Arial", float(size), FontStyle.Bold if bold else FontStyle.Regular)
            fonts.append(f)
            return f

        f_title = font(11, True)
        f_label = font(7.4, True)
        f_text = font(8.4, True)
        f_name = font(9.3, True)
        f_turn = font(11, True)
        f_check = font(6.7, True)
        pen = Pen(Color.Black, 1.0)

        def on_print_page(sender, e):
            g = e.Graphics
            width = float(e.MarginBounds.Width)
            y = 0.0

            center = StringFormat()
            center.Alignment = StringAlignment.Center
            center.LineAlignment = StringAlignment.Near

            # Logo un poco mayor para que el isotipo no se pierda en térmico 203 dpi.
            logo_path = os.path.join(core.BASE_DIR, "static", "doctor_isotype.png")
            logo_box = 46.0
            if os.path.exists(logo_path):
                try:
                    image_holder["img"] = Image.FromFile(logo_path)
                    g.DrawImage(image_holder["img"], 0.0, 0.0, logo_box, logo_box)
                except Exception:
                    image_holder["img"] = None

            title_x = 49.0
            g.DrawString(
                "RECIBO DE\nCONSULTA MÉDICA",
                f_title,
                Brushes.Black,
                RectangleF(title_x, 4.0, max(20.0, width - title_x), 42.0),
                center,
            )
            y = 49.0
            g.DrawLine(pen, 0.0, y, width, y)

            def row(label, value, value_font=None, dotted=False):
                nonlocal y
                y += 7.0
                g.DrawString(str(label), f_label, Brushes.Black, 0.0, y)
                g.DrawString(str(value or ""), value_font or f_text, Brushes.Black, 86.0, y - 1.0)
                y += 18.0
                g.DrawLine(pen, 0.0, y, width, y)

            row("Fecha:", payload.fecha, f_text)
            y += 7.0
            g.DrawString("Nombre", f_label, Brushes.Black, RectangleF(0.0, y, width, 14.0), center)
            y += 13.0

            name = str(payload.nombre or "SIN NOMBRE").upper()
            name_fmt = StringFormat()
            name_fmt.Alignment = StringAlignment.Center
            name_size = g.MeasureString(name, f_name, int(width))
            g.DrawString(
                name,
                f_name,
                Brushes.Black,
                RectangleF(0.0, y, width, max(24.0, float(name_size.Height) + 3.0)),
                name_fmt,
            )
            y += max(22.0, float(name_size.Height) + 5.0)
            g.DrawLine(pen, 0.0, y, width, y)

            if payload.is_new and payload.fecha_nacimiento:
                row("Nacimiento:", payload.fecha_nacimiento, f_text)

            if show_blood_pressure:
                y += 7.0
                g.DrawString("Presión Arterial:", f_label, Brushes.Black, 0.0, y + 5.0)
                g.DrawRectangle(pen, 105.0, y, 52.0, 22.0)
                y += 29.0
                g.DrawLine(pen, 0.0, y, width, y)

            row("Teléfono:", payload.celular or "Sin registrar", f_text)
            if payload.turno:
                row("Turno:", str(payload.turno), f_turn)

            y += 9.0
            box = 15.0

            # El driver de la CRM-308 deja una zona imprimible ligeramente menor
            # que los 80 mm nominales. Calculamos el segundo bloque por su ancho
            # real para que “SUBSECUENTE” nunca salga cortado.
            left_x = 10.0
            right_label = "SUBSECUENTE"
            right_label_w = float(g.MeasureString(right_label, f_check).Width)
            right_group_w = box + 4.0 + right_label_w
            right_x = max(width / 2.0 - 2.0, width - right_group_w - 2.0)

            groups = (
                (left_x, "PRIMERO", bool(payload.is_new)),
                (right_x, right_label, not bool(payload.is_new)),
            )
            for x, label, checked in groups:
                g.DrawRectangle(pen, x, y, box, box)
                if checked:
                    g.DrawString("X", f_text, Brushes.Black, x + 2.0, y - 1.5)
                label_x = x + box + 4.0
                label_w = max(1.0, width - label_x - 1.0)
                g.DrawString(
                    label,
                    f_check,
                    Brushes.Black,
                    RectangleF(label_x, y + 1.0, label_w, 16.0),
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
                doc.Dispose()
            except Exception:
                pass

        return chosen

    core._print_receipt_windows = _print_receipt_windows_v4461
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f"{type(exc).__name__}: {exc}"
    try:
        core.logging.getLogger(__name__).error("v4.4.61 receipt patch failed: %s", PATCH_BOOT_ERROR)
    except Exception:
        pass


@app.get("/api/v4461/receipt-health")
def v4461_receipt_health(user=core.Depends(core.current_user)):
    return {
        "ok": PATCH_BOOT_OK,
        "version": APP_VERSION,
        "error": PATCH_BOOT_ERROR,
        "schema_migration": False,
        "receipt_only": True,
        "paper_width_mm": 80,
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

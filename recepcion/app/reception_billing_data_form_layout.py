from __future__ import annotations

import os as _os
import core_runtime as core

app = core.app
APP_VERSION = getattr(core, "APP_VERSION", "")


def _print_billing_data_form_windows(printer_name: str = "") -> str:
    if _os.name != "nt":
        raise RuntimeError("La impresión directa solo está disponible en Windows")
    import clr
    clr.AddReference("System.Drawing")
    from System.Drawing import Font, FontStyle, Brushes, Pen, Image, Color, StringFormat, StringAlignment, RectangleF
    from System.Drawing.Printing import PrintDocument, PrinterSettings, PaperSize, Margins

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
    doc.DocumentName = "Datos para factura"
    doc.OriginAtMargins = True
    doc.DefaultPageSettings.PaperSize = PaperSize("Formulario factura 80 mm", 315, 485)
    doc.DefaultPageSettings.Margins = Margins(10, 10, 6, 6)
    fonts = []
    image_holder = {"img": None}

    def font(size: float, bold: bool = False):
        item = Font("Arial", float(size), FontStyle.Bold if bold else FontStyle.Regular)
        fonts.append(item)
        return item

    f_doctor = font(9.4, True)
    f_specialty = font(7.0)
    f_title = font(11.0, True)
    f_intro = font(7.2)
    f_label = font(7.5, True)
    f_footer = font(7.0, True)
    pen = Pen(Color.Black, 1.0)
    center = StringFormat()
    center.Alignment = StringAlignment.Center
    center.LineAlignment = StringAlignment.Near

    def draw_line(graphics, y, width):
        graphics.DrawLine(pen, 0.0, float(y), float(width), float(y))

    def on_print_page(_sender, event):
        graphics = event.Graphics
        width = float(event.MarginBounds.Width)
        y = 0.0
        logo_path = _os.path.join(str(core.BASE_DIR), "static", "doctor_isotype.png")
        if _os.path.exists(logo_path):
            try:
                image_holder["img"] = Image.FromFile(logo_path)
                graphics.DrawImage(image_holder["img"], 0.0, 1.0, 38.0, 38.0)
            except Exception:
                image_holder["img"] = None
        title_x = 42.0 if image_holder["img"] is not None else 0.0
        graphics.DrawString("DR. ARMANDO REVELO", f_doctor, Brushes.Black, RectangleF(title_x, 2.0, width-title_x, 15.0), center)
        graphics.DrawString("CIRUJANO URÓLOGO", f_specialty, Brushes.Black, RectangleF(title_x, 18.0, width-title_x, 13.0), center)
        y = 43.0
        draw_line(graphics, y, width)
        y += 10.0
        graphics.DrawString("DATOS PARA FACTURA", f_title, Brushes.Black, RectangleF(0.0, y, width, 20.0), center)
        y += 25.0
        graphics.DrawString("Complete los datos de la persona o empresa\na quien desea facturar.", f_intro, Brushes.Black, RectangleF(0.0, y, width, 30.0), center)
        y += 34.0
        draw_line(graphics, y, width)

        def field(label: str, spaces: int = 1):
            nonlocal y
            y += 11.0
            graphics.DrawString(label, f_label, Brushes.Black, 0.0, y)
            y += 32.0
            if spaces > 1:
                y += 24.0 * (spaces - 1)

        field("CÉDULA / RUC:")
        field("NOMBRE / RAZÓN SOCIAL:")
        field("DIRECCIÓN:", 2)
        field("TELÉFONO:")
        field("CORREO (OPCIONAL):")
        y += 6.0
        graphics.DrawString("ENTREGAR EN RECEPCIÓN", f_footer, Brushes.Black, RectangleF(0.0, y, width, 18.0), center)
        event.HasMorePages = False

    doc.PrintPage += on_print_page
    try:
        doc.Print()
    finally:
        try: doc.PrintPage -= on_print_page
        except Exception: pass
        if image_holder.get("img") is not None:
            try: image_holder["img"].Dispose()
            except Exception: pass
        for item in fonts:
            try: item.Dispose()
            except Exception: pass
        try: pen.Dispose()
        except Exception: pass
        try: center.Dispose()
        except Exception: pass
        try: doc.Dispose()
        except Exception: pass
    return chosen


@app.post("/api/billing/print-data-form")
def print_billing_data_form(user=core.Depends(core.current_user)):
    prefs = core._app_preferences()
    printer = str(prefs.get("printer") or "").strip()
    try:
        used = _print_billing_data_form_windows(printer)
    except Exception as exc:
        raise core.HTTPException(500, f"No se pudo imprimir el formulario: {exc}")
    return {"ok": True, "printed": True, "printer": used, "message": "Formulario para datos de factura enviado a la impresora."}


@app.get("/api/billing/print-data-form/health")
def billing_data_form_health(user=core.Depends(core.current_user)):
    return {"ok": True, "version": APP_VERSION, "canonical": True, "frontend_overlay": False}

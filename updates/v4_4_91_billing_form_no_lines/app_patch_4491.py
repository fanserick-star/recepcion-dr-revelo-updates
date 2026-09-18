from __future__ import annotations

# v4.4.91 — formulario de datos para factura sin líneas.
# - Conserva el formato compacto aprobado de v4.4.90.
# - Quita las líneas horizontales de escritura y mantiene espacios amplios.
# - Dirección conserva dos espacios de escritura.
# - No cambia BD, Neon, AZUR, Agenda, atenciones, recibos ni comprobantes.

import os as _os
import re as _re

import app_patch_4490 as previous

core = previous.core
app = previous.app
APP_VERSION = "4.4.91"

_mod = previous
_seen = set()
for _ in range(92):
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
FORM_RENDER_PATCHED = False


def _print_billing_data_form_windows_v4491(printer_name: str = "") -> str:
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

    doc.DocumentName = "Datos para factura"
    doc.OriginAtMargins = True
    doc.DefaultPageSettings.PaperSize = PaperSize("Formulario factura 80 mm", 315, 485)
    doc.DefaultPageSettings.Margins = Margins(10, 10, 6, 6)

    fonts = []
    image_holder = {"img": None}

    def font(size: float, bold: bool = False):
        f = Font("Arial", float(size), FontStyle.Bold if bold else FontStyle.Regular)
        fonts.append(f)
        return f

    f_doctor = font(9.4, True)
    f_specialty = font(7.0, False)
    f_title = font(11.0, True)
    f_intro = font(7.2, False)
    f_label = font(7.5, True)
    f_footer = font(7.0, True)

    pen = Pen(Color.Black, 1.0)
    center = StringFormat()
    center.Alignment = StringAlignment.Center
    center.LineAlignment = StringAlignment.Near

    def draw_line(g, y, width):
        g.DrawLine(pen, 0.0, float(y), float(width), float(y))

    def on_print_page(sender, e):
        g = e.Graphics
        width = float(e.MarginBounds.Width)
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
        g.DrawString("DR. ARMANDO REVELO", f_doctor, Brushes.Black,
                     RectangleF(title_x, 2.0, title_w, 15.0), center)
        g.DrawString("CIRUJANO URÓLOGO", f_specialty, Brushes.Black,
                     RectangleF(title_x, 18.0, title_w, 13.0), center)
        y = 43.0
        draw_line(g, y, width)

        y += 10.0
        g.DrawString("DATOS PARA FACTURA", f_title, Brushes.Black,
                     RectangleF(0.0, y, width, 20.0), center)
        y += 25.0
        g.DrawString(
            "Complete los datos de la persona o empresa\na quien desea facturar.",
            f_intro,
            Brushes.Black,
            RectangleF(0.0, y, width, 30.0),
            center,
        )
        y += 34.0
        draw_line(g, y, width)

        def field(label: str, spaces: int = 1):
            nonlocal y
            y += 11.0
            g.DrawString(label, f_label, Brushes.Black, 0.0, y)
            # Sin rayas: se conserva espacio amplio para escribir a mano.
            y += 32.0
            if spaces > 1:
                y += 24.0 * (spaces - 1)

        field("CÉDULA / RUC:")
        field("NOMBRE / RAZÓN SOCIAL:")
        field("DIRECCIÓN:", 2)
        field("TELÉFONO:")
        field("CORREO (OPCIONAL):")

        y += 6.0
        g.DrawString("ENTREGAR EN RECEPCIÓN", f_footer, Brushes.Black,
                     RectangleF(0.0, y, width, 18.0), center)
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
        except Exception:
            pass
        try:
            doc.Dispose()
        except Exception:
            pass

    return chosen


try:
    previous._print_billing_data_form_windows_v4490 = _print_billing_data_form_windows_v4491
    previous.previous._print_billing_data_form_windows = _print_billing_data_form_windows_v4491
    FORM_RENDER_PATCHED = True

    _js = (getattr(core, "V460_OVERLAY_JS", "") or "")
    _js = _re.sub(
        r"""const\s+VERSION\s*=\s*['\"]4\.4\.\d+['\"]\s*;""",
        "const VERSION='4.4.91';",
        _js,
    )
    _js = _re.sub(
        r"""const\s+V\s*=\s*['\"]4\.4\.\d+['\"]\s*;""",
        "const V='4.4.91';",
        _js,
    )

    V4491_CSS = r"""
.v460-version,#currentVersionBadge{font-size:0!important}
.v460-version::after,#currentVersionBadge::after{
  content:"v4.4.91"!important;font-size:9px!important;line-height:1!important;font-weight:850!important
}
"""

    V4491_JS = r"""
;(()=>{
  if(window.__v4491BillingDataFormNoLines)return;
  window.__v4491BillingDataFormNoLines=true;
  const VERSION='4.4.91';
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

    core.V460_OVERLAY_CSS = (getattr(core, "V460_OVERLAY_CSS", "") or "") + "\n" + V4491_CSS
    core.V460_OVERLAY_JS = _js + "\n" + V4491_JS
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f"{type(exc).__name__}: {exc}"


@app.get("/api/v4491/health")
def v4491_health(user=core.Depends(core.current_user)):
    return {
        "ok": PATCH_BOOT_OK,
        "version": APP_VERSION,
        "error": PATCH_BOOT_ERROR,
        "form_render_patched": FORM_RENDER_PATCHED,
        "writing_lines_removed": True,
        "address_extra_space": True,
        "database_changes": False,
        "neon_writes_added": False,
        "billing_changes": False,
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

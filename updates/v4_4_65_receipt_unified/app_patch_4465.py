from __future__ import annotations

# v4.4.65 — recibo CRM-308 unificado (vista previa = impresión directa)
# - La impresión DIRECTA conserva el estilo grande y legible de la vista previa.
# - Ambos modos usan un ancho seguro para que no se corte el borde derecho.
# - PRIMERO / SUBSECUENTE se centran dentro de dos columnas y siempre caben.
# - Texto optimizado a 1 bit para cabezal térmico de 203 dpi.
# - El isotipo se convierte a negro/blanco antes de imprimir para evitar el logo "roto".
# - No modifica pacientes, agenda, facturación, Neon ni archivos clínicos.

import os
import app_patch_4464 as previous

core = previous.core
app = previous.app
APP_VERSION = "4.4.65"
previous.APP_VERSION = APP_VERSION
core.APP_VERSION = APP_VERSION
try:
    previous.previous.APP_VERSION = APP_VERSION
except Exception:
    pass

PATCH_BOOT_OK = False
PATCH_BOOT_ERROR = ""

try:
    def _receipt_name_lines_v4465(value):
        parts = [x for x in str(value or "").strip().upper().split() if x]
        if not parts:
            return "SIN NOMBRE", ""
        if len(parts) == 1:
            return parts[0], ""
        return " ".join(parts[:2]), " ".join(parts[2:])

    def _thermal_logo_bitmap_v4465(path):
        """Devuelve una versión B/N de alto contraste apta para 203 dpi."""
        from System.Drawing import Bitmap, Color  # type: ignore

        src = Bitmap(path)
        try:
            out = Bitmap(src.Width, src.Height)
            for yy in range(src.Height):
                for xx in range(src.Width):
                    c = src.GetPixel(xx, yy)
                    # El PNG original tiene fondo blanco y figura verde/azul.
                    # Todo píxel claramente distinto de blanco se imprime negro.
                    is_ink = c.A > 20 and min(c.R, c.G, c.B) < 238
                    out.SetPixel(xx, yy, Color.Black if is_ink else Color.White)
            return out
        finally:
            src.Dispose()

    def _print_receipt_windows_v4465(payload, printer_name: str = "", show_blood_pressure: bool = True) -> str:
        if os.name != "nt":
            raise RuntimeError("La impresión directa solo está disponible en Windows")

        import clr  # type: ignore
        clr.AddReference("System.Drawing")
        from System.Drawing import (
            Font, FontStyle, Brushes, Pen, StringFormat,
            StringAlignment, RectangleF, Color
        )  # type: ignore
        from System.Drawing.Drawing2D import DashStyle, InterpolationMode, PixelOffsetMode  # type: ignore
        from System.Drawing.Text import TextRenderingHint  # type: ignore
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
        doc.OriginAtMargins = False
        doc.DefaultPageSettings.PaperSize = PaperSize("Recibo 80 mm", 315, 620)
        doc.DefaultPageSettings.Margins = Margins(0, 0, 0, 0)

        fonts = []
        image_holder = {"img": None}

        def font(size, bold=False):
            f = Font("Arial", float(size), FontStyle.Bold if bold else FontStyle.Regular)
            fonts.append(f)
            return f

        # Arial Bold: trazos gruesos y abiertos, muy legibles a 203 dpi.
        f_title = font(12.0, True)
        f_label = font(8.8, True)
        f_value = font(10.2, True)
        f_name_label = font(8.3, True)
        f_name = font(11.2, True)
        f_turn = font(12.8, True)
        f_status = font(8.25, True)

        border_pen = Pen(Color.Black, 1.2)
        solid_pen = Pen(Color.Black, 1.0)
        dotted_pen = Pen(Color.FromArgb(85, 85, 85), 1.0)
        dotted_pen.DashStyle = DashStyle.Dot
        check_pen = Pen(Color.Black, 1.6)

        def on_print_page(sender, e):
            g = e.Graphics
            # 1-bit/GridFit evita grises y bordes blandos en térmica 203 dpi.
            try:
                g.TextRenderingHint = TextRenderingHint.SingleBitPerPixelGridFit
                g.InterpolationMode = InterpolationMode.NearestNeighbor
                g.PixelOffsetMode = PixelOffsetMode.Half
            except Exception:
                pass

            page_w = float(e.PageBounds.Width)
            # Zona segura: 6 px por lado. Visualmente casi sin margen, pero evita
            # que el driver POS-80C/CRM-308 recorte el último carácter.
            outer_left = 6.0
            outer_right = max(outer_left + 240.0, page_w - 8.0)
            outer_w = outer_right - outer_left
            inner_left = outer_left + 7.0
            inner_right = outer_right - 7.0
            inner_w = inner_right - inner_left
            y = 7.0

            center = StringFormat()
            center.Alignment = StringAlignment.Center
            center.LineAlignment = StringAlignment.Near

            # Encabezado: misma jerarquía visual de la vista previa.
            logo_path = os.path.join(core.BASE_DIR, "static", "doctor_isotype.png")
            if os.path.exists(logo_path):
                try:
                    image_holder["img"] = _thermal_logo_bitmap_v4465(logo_path)
                    g.DrawImage(image_holder["img"], inner_left + 2.0, y + 1.0, 34.0, 34.0)
                except Exception:
                    image_holder["img"] = None

            title_x = inner_left + 42.0
            g.DrawString(
                "RECIBO DE\nCONSULTA MÉDICA",
                f_title,
                Brushes.Black,
                RectangleF(title_x, y, max(30.0, inner_right - title_x), 39.0),
                center,
            )
            y += 41.0
            g.DrawLine(solid_pen, inner_left, y, inner_right, y)

            def dotted_separator():
                g.DrawLine(dotted_pen, inner_left, y, inner_right, y)

            def draw_row(label, value, value_x, value_font=None, height=29.0):
                nonlocal y
                top = y
                y += 7.0
                g.DrawString(str(label), f_label, Brushes.Black, inner_left, y)
                vx = inner_left + float(value_x)
                g.DrawString(
                    str(value or ""),
                    value_font or f_value,
                    Brushes.Black,
                    RectangleF(vx, y - 1.0, max(18.0, inner_right - vx), height - 9.0),
                )
                y = top + height
                dotted_separator()

            draw_row("Fecha:", payload.fecha, 83.0, f_value, 29.0)

            # Nombre: APELLIDOS / NOMBRES, como el diseño de vista previa.
            y += 8.0
            g.DrawString("Nombre", f_name_label, Brushes.Black, RectangleF(inner_left, y, inner_w, 13.0), center)
            y += 13.0
            surname, given = _receipt_name_lines_v4465(payload.nombre)
            g.DrawString(surname, f_name, Brushes.Black, RectangleF(inner_left, y, inner_w, 19.0), center)
            y += 19.0
            if given:
                g.DrawString(given, f_name, Brushes.Black, RectangleF(inner_left, y, inner_w, 19.0), center)
                y += 19.0
            y += 6.0
            g.DrawLine(solid_pen, inner_left, y, inner_right, y)

            if bool(payload.is_new) and payload.fecha_nacimiento:
                # Se mantiene el texto completo, pero con posición calculada para 70-72 mm útiles.
                draw_row("Fecha de nacimiento:", payload.fecha_nacimiento, 142.0, f_value, 32.0)

            if show_blood_pressure:
                top = y
                y += 7.0
                g.DrawString("Presión Arterial:", f_label, Brushes.Black, inner_left, y + 4.0)
                box_w = 72.0
                box_h = 28.0
                box_x = inner_right - box_w
                g.DrawRectangle(solid_pen, box_x, y, box_w, box_h)
                y = top + 43.0
                dotted_separator()

            draw_row("Teléfono:", payload.celular or "Sin registrar", 91.0, f_value, 29.0)
            if payload.turno:
                draw_row("Turno:", str(payload.turno), 91.0, f_turn, 32.0)

            # Dos columnas reales: evita cualquier corte independientemente de la medición GDI.
            y += 12.0
            box = 19.0
            gap = 5.0
            col_gap = 4.0
            col_w = (inner_w - col_gap) / 2.0

            def draw_option(col_left, label, checked):
                label_w = float(g.MeasureString(label, f_status).Width)
                group_w = box + gap + label_w
                # Se centra, pero nunca sale de su propia columna.
                x = col_left + max(0.0, (col_w - group_w) / 2.0)
                max_x = col_left + col_w - group_w
                x = min(x, max_x)
                g.DrawRectangle(solid_pen, x, y, box, box)
                if checked:
                    g.DrawLine(check_pen, x + 4.0, y + 10.0, x + 8.0, y + 15.0)
                    g.DrawLine(check_pen, x + 8.0, y + 15.0, x + 16.0, y + 4.0)
                g.DrawString(label, f_status, Brushes.Black, x + box + gap, y + 1.0)

            draw_option(inner_left, "PRIMERO", bool(payload.is_new))
            draw_option(inner_left + col_w + col_gap, "SUBSECUENTE", not bool(payload.is_new))
            y += box + 10.0

            # Marco completo como el recibo de vista previa, pero dentro de la zona imprimible.
            g.DrawRectangle(border_pen, outer_left, 3.0, outer_w, max(20.0, y + 4.0))
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
            for p in (border_pen, solid_pen, dotted_pen, check_pen):
                try:
                    p.Dispose()
                except Exception:
                    pass
            try:
                doc.Dispose()
            except Exception:
                pass

        return chosen

    core._print_receipt_windows = _print_receipt_windows_v4465

    # Vista previa/diálogo: mismo ancho seguro, Arial Bold y misma distribución.
    PREVIEW_FIX_JS = r"""
;(()=>{
  if(window.__v4465ReceiptPreview)return;
  window.__v4465ReceiptPreview=true;

  function install(){
    if(typeof window.attentionSlipHtml!=='function' || typeof window.printAttentionSlipData!=='function'){
      setTimeout(install,120);return;
    }
    const patched=function(visit,patient,dayNumber=null){
      const card=window.attentionSlipHtml(visit,patient,dayNumber);
      document.querySelector('#receiptPrintFrame')?.remove();
      const frame=document.createElement('iframe');
      frame.id='receiptPrintFrame';frame.title='Impresión de recibo';frame.setAttribute('aria-hidden','true');
      Object.assign(frame.style,{position:'fixed',right:'-10000px',bottom:'0',width:'80mm',height:'160mm',border:'0',opacity:'0',pointerEvents:'none'});
      document.body.appendChild(frame);
      const doc=frame.contentDocument||frame.contentWindow?.document;
      if(!doc){frame.remove();alert('No se pudo preparar la impresión. Intenta nuevamente.');return}
      let printing=false,cleaned=false;
      const cleanup=()=>{if(cleaned)return;cleaned=true;setTimeout(()=>frame.remove(),120)};
      const doPrint=()=>{if(printing||cleaned)return;printing=true;try{const win=frame.contentWindow;if(!win)throw Error('Ventana de impresión no disponible');try{win.addEventListener('afterprint',cleanup,{once:true})}catch{}win.focus();win.print();setTimeout(cleanup,120000)}catch{frame.remove();alert('No se pudo abrir la impresión. Intenta nuevamente.')}};
      const printWhenReady=()=>{const img=doc.querySelector('.receipt-brand-icon');if(img&&!img.complete){let fired=false;const ready=()=>{if(fired)return;fired=true;setTimeout(doPrint,80)};img.addEventListener('load',ready,{once:true});img.addEventListener('error',ready,{once:true});setTimeout(ready,700)}else setTimeout(doPrint,80)};
      frame.onload=printWhenReady;
      doc.open();
      doc.write(`<!doctype html><html><head><meta charset="utf-8"><title>Recibo de consulta médica</title><style>
        *{box-sizing:border-box}html,body{margin:0;padding:0;background:#fff;color:#111;font-family:Arial,Helvetica,sans-serif}
        body{width:72mm;padding:0;margin:0 auto}.attention-slip{width:100%;border:1.2px solid #111;padding:3mm 2.5mm;background:#fff}
        .receipt-brand-row{display:grid;grid-template-columns:10.5mm 1fr;gap:1.5mm;align-items:center;padding-bottom:2.4mm;border-bottom:1px solid #222}
        .receipt-brand-icon{width:9.5mm;height:9.5mm;object-fit:contain;filter:grayscale(1) contrast(3.2)}
        .receipt-title{text-align:center;font-size:12pt;font-weight:900;line-height:1.08;letter-spacing:.1px}
        .receipt-date-row,.receipt-line-row,.receipt-turn-row,.receipt-pressure-row{display:flex;align-items:center;gap:1.6mm;padding:2mm 0;border-bottom:1px dotted #777}
        .receipt-date-row span,.receipt-line-row span,.receipt-turn-row span,.receipt-pressure-row span:first-child{font-size:8.8pt;font-weight:800;white-space:nowrap}
        .receipt-date-row strong,.receipt-line-row strong,.receipt-turn-row strong{font-size:10.2pt;font-weight:800;overflow-wrap:anywhere}.receipt-turn-row strong{font-size:12.8pt}
        .receipt-name-block{padding:2.6mm 0;border-bottom:1px solid #222;text-align:center}.receipt-name-block span{display:block;font-size:8.3pt;font-weight:800;margin-bottom:1mm}.receipt-name-block strong{display:block;font-size:11.2pt;line-height:1.18;font-weight:900;overflow-wrap:anywhere}.receipt-name-block strong em{display:block;font-style:normal}.receipt-name-block strong em+em{margin-top:.6mm}
        .receipt-pressure-row{justify-content:space-between}.receipt-pressure-box{display:inline-block;width:19mm;height:7.5mm;border:1.2px solid #111;margin-left:auto;background:#fff}
        .receipt-status-row{display:grid!important;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:1mm;padding-top:3.5mm}.receipt-check-item{display:flex!important;align-items:center;justify-content:center;gap:1mm;font-size:8.25pt;white-space:nowrap;min-width:0}.receipt-check-box{display:inline-flex;width:5mm;height:5mm;border:1.4px solid #111;align-items:center;justify-content:center;font-size:11pt;font-weight:900;line-height:1;flex:0 0 5mm}
        @media print{body{width:72mm;padding:0}@page{size:80mm auto;margin:4mm}}
      </style></head><body>${card}</body></html>`);
      doc.close();setTimeout(printWhenReady,350);
    };
    patched.__v4465=true;window.printAttentionSlipData=patched;
  }
  install();
})();
"""
    core.V460_OVERLAY_JS = (getattr(core, "V460_OVERLAY_JS", "") or "") + "\n" + PREVIEW_FIX_JS

    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f"{type(exc).__name__}: {exc}"
    try:
        core.logging.getLogger(__name__).error("v4.4.65 receipt patch failed: %s", PATCH_BOOT_ERROR)
    except Exception:
        pass


@app.get("/api/v4465/receipt-health")
def v4465_receipt_health(user=core.Depends(core.current_user)):
    return {
        "ok": PATCH_BOOT_OK,
        "version": APP_VERSION,
        "error": PATCH_BOOT_ERROR,
        "schema_migration": False,
        "receipt_only": True,
        "direct_matches_preview": True,
        "safe_print_width_mm": 72,
        "font": "Arial Bold",
        "text_rendering": "SingleBitPerPixelGridFit",
        "thermal_logo_monochrome": True,
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

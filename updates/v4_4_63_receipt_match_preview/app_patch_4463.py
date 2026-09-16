from __future__ import annotations

# v4.4.63 — CRM-308 / 80 mm
# 1) La impresión DIRECTA usa las mismas proporciones y tamaños visuales de la
#    vista previa grande: título, nombre, fecha, nacimiento, presión, teléfono,
#    turno y clasificación.
# 2) La vista previa deja de cortar SUBSECUENTE: la fila inferior usa flex y
#    conserva el mismo tamaño de letra en PRIMERO y SUBSECUENTE.
# 3) No toca pacientes, agenda, facturación, Neon ni archivos clínicos.

import os
import app_patch_4462 as previous

core = previous.core
app = previous.app
APP_VERSION = "4.4.63"
previous.APP_VERSION = APP_VERSION
core.APP_VERSION = APP_VERSION
try:
    previous.previous.APP_VERSION = APP_VERSION
    previous.previous.previous.APP_VERSION = APP_VERSION
except Exception:
    pass

PATCH_BOOT_OK = False
PATCH_BOOT_ERROR = ""


try:
    def _receipt_name_lines_v4463(value):
        parts = [x for x in str(value or "").strip().upper().split() if x]
        if not parts:
            return "SIN NOMBRE", ""
        if len(parts) == 1:
            return parts[0], ""
        return " ".join(parts[:2]), " ".join(parts[2:])


    def _print_receipt_windows_v4463(payload, printer_name: str = "", show_blood_pressure: bool = True) -> str:
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
        # 315 = 80,0 mm. El ancho queda fijo; el driver térmico ejecuta su corte
        # al finalizar el trabajo.
        doc.DefaultPageSettings.PaperSize = PaperSize("Recibo 80 mm", 315, 600)
        # Margen mínimo seguro para aprovechar el rollo completo de la CRM-308.
        doc.DefaultPageSettings.Margins = Margins(4, 4, 4, 4)

        fonts = []
        image_holder = {"img": None}

        def font(size, bold=False):
            f = Font("Arial", float(size), FontStyle.Bold if bold else FontStyle.Regular)
            fonts.append(f)
            return f

        # Mismos tamaños que la plantilla grande de vista previa.
        f_title = font(12.5, True)
        f_label = font(9.2, True)
        f_value = font(10.5, True)
        f_name_label = font(8.5, True)
        f_name = font(11.5, True)
        f_turn = font(13.0, True)
        f_status = font(9.0, True)

        outer_pen = Pen(Color.Black, 1.2)
        solid_pen = Pen(Color.Black, 1.0)
        dotted_pen = Pen(Color.FromArgb(105, 105, 105), 1.0)
        dotted_pen.DashStyle = DashStyle.Dot
        check_pen = Pen(Color.Black, 1.5)

        def on_print_page(sender, e):
            g = e.Graphics
            width = float(e.MarginBounds.Width)
            left = 7.0
            right = max(left + 40.0, width - 7.0)
            content_w = right - left
            y = 6.0

            center = StringFormat()
            center.Alignment = StringAlignment.Center
            center.LineAlignment = StringAlignment.Near

            # Encabezado grande, como el recibo de la vista previa.
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
                    RectangleF(vx, y - 1.0, max(20.0, right - vx), height - 10.0),
                )
                y = top + height
                dotted_separator()

            row("Fecha:", payload.fecha, 91.0, f_value, 31.0)

            # Nombre con el mismo corte visual de la vista previa:
            # APELLIDO APELLIDO / NOMBRE(S).
            y += 10.0
            g.DrawString("Nombre", f_name_label, Brushes.Black, RectangleF(left, y, content_w, 14.0), center)
            y += 15.0
            surname, given = _receipt_name_lines_v4463(payload.nombre)
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
                box_w = 84.0
                box_h = 31.0
                box_x = max(left + 151.0, right - box_w - 7.0)
                g.DrawRectangle(solid_pen, box_x, y, box_w, box_h)
                y = top + 47.0
                dotted_separator()

            row("Teléfono:", payload.celular or "Sin registrar", 96.0, f_value, 31.0)

            if payload.turno:
                row("Turno:", str(payload.turno), 96.0, f_turn, 34.0)

            # PRIMERO / SUBSECUENTE: mismo cuadro, fuente, tamaño y línea base.
            y += 15.0
            box = 22.0       # ≈ 5,5 mm
            gap = 6.0
            options = (
                ("PRIMERO", bool(payload.is_new), left + content_w * 0.25),
                ("SUBSECUENTE", not bool(payload.is_new), left + content_w * 0.75),
            )
            for label, checked, half_center in options:
                label_w = float(g.MeasureString(label, f_status).Width)
                group_w = box + gap + label_w
                x = half_center - (group_w / 2.0)
                x = max(left + 1.0, min(x, right - group_w - 1.0))

                g.DrawRectangle(solid_pen, x, y, box, box)
                if checked:
                    # Visto dibujado con líneas para que no dependa de la fuente.
                    g.DrawLine(check_pen, x + 5.0, y + 12.0, x + 9.0, y + 17.0)
                    g.DrawLine(check_pen, x + 9.0, y + 17.0, x + 18.0, y + 5.0)

                g.DrawString(
                    label,
                    f_status,
                    Brushes.Black,
                    RectangleF(x + box + gap, y + 2.0, label_w + 4.0, 20.0),
                )

            y += 31.0
            # Borde exterior como la vista previa grande.
            g.DrawRectangle(outer_pen, left - 3.0, 2.0, content_w + 6.0, max(20.0, y + 5.0))

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
            for p in (outer_pen, solid_pen, dotted_pen, check_pen):
                try:
                    p.Dispose()
                except Exception:
                    pass
            try:
                doc.Dispose()
            except Exception:
                pass

        return chosen


    # Impresión automática/directa.
    core._print_receipt_windows = _print_receipt_windows_v4463

    # Vista previa: misma tipografía grande, pero la fila inferior usa flex
    # para que SUBSECUENTE jamás se salga del ancho de 80 mm.
    PREVIEW_FIX_JS = r"""
;(()=>{
  if(window.__v4463ReceiptPreview)return;
  window.__v4463ReceiptPreview=true;

  function install(){
    if(typeof window.attentionSlipHtml!=='function' || typeof window.printAttentionSlipData!=='function'){
      setTimeout(install,120);
      return;
    }
    if(window.printAttentionSlipData.__v4463)return;

    const patched=function(visit,patient,dayNumber=null){
      const card=window.attentionSlipHtml(visit,patient,dayNumber);
      document.querySelector('#receiptPrintFrame')?.remove();

      const frame=document.createElement('iframe');
      frame.id='receiptPrintFrame';
      frame.title='Impresión de recibo';
      frame.setAttribute('aria-hidden','true');
      Object.assign(frame.style,{
        position:'fixed',right:'-10000px',bottom:'0',
        width:'80mm',height:'160mm',border:'0',opacity:'0',pointerEvents:'none'
      });
      document.body.appendChild(frame);

      const doc=frame.contentDocument||frame.contentWindow?.document;
      if(!doc){frame.remove();alert('No se pudo preparar la impresión. Intenta nuevamente.');return}

      let printing=false,cleaned=false;
      const cleanup=()=>{if(cleaned)return;cleaned=true;setTimeout(()=>frame.remove(),120)};
      const doPrint=()=>{
        if(printing||cleaned)return;
        printing=true;
        try{
          const win=frame.contentWindow;
          if(!win)throw Error('Ventana de impresión no disponible');
          try{win.addEventListener('afterprint',cleanup,{once:true})}catch{}
          win.focus();win.print();setTimeout(cleanup,120000);
        }catch{
          frame.remove();alert('No se pudo abrir la impresión. Intenta nuevamente.');
        }
      };
      const printWhenReady=()=>{
        const img=doc.querySelector('.receipt-brand-icon');
        if(img&&!img.complete){
          let fired=false;
          const ready=()=>{if(fired)return;fired=true;setTimeout(doPrint,80)};
          img.addEventListener('load',ready,{once:true});
          img.addEventListener('error',ready,{once:true});
          setTimeout(ready,700);
        }else setTimeout(doPrint,80);
      };

      frame.onload=printWhenReady;
      doc.open();
      doc.write(`<!doctype html><html><head><meta charset="utf-8"><title>Recibo de consulta médica</title><style>
        *{box-sizing:border-box}
        html,body{margin:0;padding:0;background:#fff;color:#111;font-family:Arial,Helvetica,sans-serif}
        body{width:76mm;padding:0;margin:0 auto}
        .attention-slip{width:100%;border:1.2px solid #111;padding:3mm 2.5mm;background:#fff}
        .receipt-brand-row{display:grid;grid-template-columns:12mm 1fr;gap:2mm;align-items:center;padding-bottom:2.6mm;border-bottom:1px solid #222}
        .receipt-brand-icon{width:11mm;height:11mm;object-fit:contain;filter:grayscale(1) contrast(1.35)}
        .receipt-title{text-align:center;font-size:12.5pt;font-weight:900;line-height:1.12;letter-spacing:.2px}
        .receipt-date-row,.receipt-line-row,.receipt-turn-row,.receipt-pressure-row{display:flex;align-items:center;gap:2mm;padding:2.1mm 0;border-bottom:1px dotted #777}
        .receipt-date-row span,.receipt-line-row span,.receipt-turn-row span,.receipt-pressure-row span:first-child{font-size:9.2pt;font-weight:800;white-space:nowrap}
        .receipt-date-row strong,.receipt-line-row strong,.receipt-turn-row strong{font-size:10.5pt;font-weight:800;overflow-wrap:anywhere}
        .receipt-turn-row strong{font-size:13pt}
        .receipt-name-block{padding:2.8mm 0;border-bottom:1px solid #222;text-align:center}
        .receipt-name-block span{display:block;font-size:8.5pt;font-weight:800;margin-bottom:1.2mm}
        .receipt-name-block strong{display:block;font-size:11.5pt;line-height:1.2;font-weight:900;overflow-wrap:anywhere}
        .receipt-name-block strong em{display:block;font-style:normal}
        .receipt-name-block strong em+em{margin-top:.7mm}
        .receipt-pressure-box{display:inline-block;width:22mm;height:8mm;border:1.2px solid #111;margin-left:1mm;background:#fff}
        .receipt-status-row{display:flex!important;align-items:center;justify-content:space-between;gap:2mm;padding-top:4mm}
        .receipt-check-item{display:flex!important;align-items:center;justify-content:center;gap:1.5mm;font-size:9pt;white-space:nowrap;flex:0 0 auto;min-width:0}
        .receipt-check-box{display:inline-flex;width:5.5mm;height:5.5mm;border:1.5px solid #111;align-items:center;justify-content:center;font-size:12pt;font-weight:900;line-height:1;flex:0 0 5.5mm}
        @media print{
          body{width:76mm;padding:0}
          @page{size:80mm auto;margin:2mm}
        }
      </style></head><body>${card}</body></html>`);
      doc.close();
      setTimeout(printWhenReady,350);
    };

    patched.__v4463=true;
    window.printAttentionSlipData=patched;
  }

  install();
})();
"""
    core.V460_OVERLAY_JS = (getattr(core, "V460_OVERLAY_JS", "") or "") + "\n" + PREVIEW_FIX_JS

    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f"{type(exc).__name__}: {exc}"
    try:
        core.logging.getLogger(__name__).error("v4.4.63 receipt patch failed: %s", PATCH_BOOT_ERROR)
    except Exception:
        pass


@app.get("/api/v4463/receipt-health")
def v4463_receipt_health(user=core.Depends(core.current_user)):
    return {
        "ok": PATCH_BOOT_OK,
        "version": APP_VERSION,
        "error": PATCH_BOOT_ERROR,
        "schema_migration": False,
        "receipt_only": True,
        "direct_matches_preview": True,
        "preview_subsequent_clip_fixed": True,
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

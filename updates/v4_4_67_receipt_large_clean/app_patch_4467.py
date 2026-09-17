from __future__ import annotations

# v4.4.67 — recibo térmico más legible, sin marco exterior.
# Mantiene UN SOLO raster para impresión automática y desde vista previa.
# Recupera proporciones más grandes del formato anterior, deja SUBSECUENTE completo
# y elimina la línea vertical izquierda y la línea inferior del borde exterior.

import os
import app_patch_4466 as previous

core = previous.core
app = previous.app
APP_VERSION = "4.4.67"
previous.APP_VERSION = APP_VERSION
core.APP_VERSION = APP_VERSION
try:
    previous.previous.APP_VERSION = APP_VERSION
except Exception:
    pass

PATCH_BOOT_OK = False
PATCH_BOOT_ERROR = ""

try:
    def _name_lines_v4467(value):
        parts = [x for x in str(value or "").strip().upper().split() if x]
        if not parts:
            return "SIN NOMBRE", ""
        if len(parts) == 1:
            return parts[0], ""
        return " ".join(parts[:2]), " ".join(parts[2:])

    def _render_receipt_png_v4467(payload, show_blood_pressure=True):
        import clr  # type: ignore
        clr.AddReference("System.Drawing")
        clr.AddReference("System")
        from System.IO import MemoryStream  # type: ignore
        from System.Drawing import (
            Bitmap, Graphics, Color, Font, FontStyle, GraphicsUnit, Brushes, Pen,
            Rectangle, RectangleF, StringFormat, StringAlignment
        )  # type: ignore
        from System.Drawing.Drawing2D import (
            DashStyle, InterpolationMode, PixelOffsetMode, SmoothingMode
        )  # type: ignore
        from System.Drawing.Text import TextRenderingHint  # type: ignore
        from System.Drawing.Imaging import ImageFormat, PixelFormat  # type: ignore

        W, H = 576, 860
        bmp = Bitmap(W, H, PixelFormat.Format24bppRgb)
        g = Graphics.FromImage(bmp)
        fonts = []
        logo = None
        pens = []
        try:
            g.Clear(Color.White)
            g.TextRenderingHint = TextRenderingHint.SingleBitPerPixelGridFit
            g.InterpolationMode = InterpolationMode.NearestNeighbor
            g.PixelOffsetMode = PixelOffsetMode.Half
            try:
                g.SmoothingMode = getattr(SmoothingMode, "None")
            except Exception:
                pass

            def font(px, bold=True):
                f = Font(
                    "Arial", float(px),
                    FontStyle.Bold if bold else FontStyle.Regular,
                    GraphicsUnit.Pixel
                )
                fonts.append(f)
                return f

            f_title = font(30)
            f_label = font(26)
            f_value = font(30)
            f_name_label = font(23)
            f_name = font(35)
            f_turn = font(38)
            f_status = font(22)

            solid = Pen(Color.Black, 2.0); pens.append(solid)
            dotted = Pen(Color.FromArgb(65, 65, 65), 1.7); pens.append(dotted)
            dotted.DashStyle = DashStyle.Dot
            check = Pen(Color.Black, 3.2); pens.append(check)

            inner_l, inner_r = 12.0, W - 12.0
            inner_w = inner_r - inner_l
            y = 10.0

            center = StringFormat()
            center.Alignment = StringAlignment.Center
            center.LineAlignment = StringAlignment.Near

            logo_path = os.path.join(core.BASE_DIR, "static", "doctor_isotype.png")
            if os.path.exists(logo_path):
                try:
                    logo = previous._thermal_logo_v4466(logo_path)
                    if logo is not None:
                        g.DrawImage(logo, 17.0, y + 1.0, 82.0, 82.0)
                except Exception:
                    logo = None

            g.DrawString(
                "RECIBO DE\nCONSULTA MÉDICA",
                f_title, Brushes.Black,
                RectangleF(102.0, y + 4.0, W - 114.0, 78.0),
                center,
            )
            y += 88.0
            g.DrawLine(solid, inner_l, y, inner_r, y)

            def separator():
                g.DrawLine(dotted, inner_l, y, inner_r, y)

            def row(label, value, value_x, vf=None, height=61.0, lf=None):
                nonlocal y
                top = y
                y += 16.0
                g.DrawString(str(label), lf or f_label, Brushes.Black, inner_l, y)
                vx = float(value_x)
                g.DrawString(
                    str(value or ""),
                    vf or f_value,
                    Brushes.Black,
                    RectangleF(vx, y - 3.0, inner_r - vx, 42.0),
                )
                y = top + height
                separator()

            row("Fecha:", payload.fecha, 218.0, f_value, 60.0)

            y += 17.0
            g.DrawString(
                "Nombre", f_name_label, Brushes.Black,
                RectangleF(inner_l, y, inner_w, 30.0), center
            )
            y += 30.0
            surname, given = _name_lines_v4467(payload.nombre)
            g.DrawString(
                surname, f_name, Brushes.Black,
                RectangleF(inner_l, y, inner_w, 43.0), center
            )
            y += 43.0
            if given:
                g.DrawString(
                    given, f_name, Brushes.Black,
                    RectangleF(inner_l, y, inner_w, 43.0), center
                )
                y += 43.0
            y += 11.0
            g.DrawLine(solid, inner_l, y, inner_r, y)

            if bool(payload.is_new) and payload.fecha_nacimiento:
                birth_label = font(24)
                row(
                    "Fecha de nacimiento:",
                    payload.fecha_nacimiento,
                    340.0,
                    f_value,
                    65.0,
                    birth_label,
                )

            if show_blood_pressure:
                top = y
                y += 16.0
                g.DrawString(
                    "Presión Arterial:", f_label, Brushes.Black, inner_l, y + 9.0
                )
                bw, bh = 142.0, 60.0
                g.DrawRectangle(solid, inner_r - bw, y, bw, bh)
                y = top + 88.0
                separator()

            row("Teléfono:", payload.celular or "Sin registrar", 215.0, f_value, 61.0)
            if payload.turno:
                row("Turno:", str(payload.turno), 215.0, f_turn, 67.0)

            y += 21.0
            box = 40.0
            gap = 10.0
            col_gap = 10.0
            col_w = (inner_w - col_gap) / 2.0

            def option(col_l, label, checked):
                label_w = float(g.MeasureString(label, f_status).Width)
                group_w = box + gap + label_w
                x = col_l + max(0.0, (col_w - group_w) / 2.0)
                x = min(x, col_l + col_w - group_w)
                g.DrawRectangle(solid, x, y, box, box)
                if checked:
                    g.DrawLine(check, x + 8.0, y + 22.0, x + 17.0, y + 32.0)
                    g.DrawLine(check, x + 17.0, y + 32.0, x + 34.0, y + 8.0)
                g.DrawString(label, f_status, Brushes.Black, x + box + gap, y + 7.0)

            option(inner_l, "PRIMERO", bool(payload.is_new))
            option(inner_l + col_w + col_gap, "SUBSECUENTE", not bool(payload.is_new))
            y += box + 16.0

            # SIN marco exterior. Solo quedan las líneas internas de lectura.
            final_h = int(min(H, y + 8.0))
            cropped = bmp.Clone(
                Rectangle(0, 0, W, final_h),
                PixelFormat.Format24bppRgb
            )
            try:
                ms = MemoryStream()
                cropped.Save(ms, ImageFormat.Png)
                data = bytes(bytearray(ms.ToArray()))
                ms.Dispose()
                return data
            finally:
                cropped.Dispose()
        finally:
            try:
                g.Dispose()
            except Exception:
                pass
            if logo is not None:
                try:
                    logo.Dispose()
                except Exception:
                    pass
            for f in fonts:
                try:
                    f.Dispose()
                except Exception:
                    pass
            for p in pens:
                try:
                    p.Dispose()
                except Exception:
                    pass
            try:
                bmp.Dispose()
            except Exception:
                pass

    def _print_receipt_windows_v4467(
        payload, printer_name: str = "", show_blood_pressure: bool = True
    ) -> str:
        if os.name != "nt":
            raise RuntimeError("La impresión directa solo está disponible en Windows")

        import clr  # type: ignore
        clr.AddReference("System.Drawing")
        clr.AddReference("System")
        from System.IO import MemoryStream  # type: ignore
        from System.Drawing import Image, RectangleF  # type: ignore
        from System.Drawing.Printing import (
            PrintDocument, PrinterSettings, PaperSize, Margins
        )  # type: ignore

        available = [str(name) for name in PrinterSettings.InstalledPrinters]
        chosen = (
            str(printer_name or "").strip()
            or str(PrinterSettings().PrinterName or "")
        )
        if not chosen:
            raise RuntimeError("Windows no tiene una impresora predeterminada")
        if available and chosen not in available:
            raise RuntimeError(f"La impresora ‘{chosen}’ ya no está disponible")

        png = _render_receipt_png_v4467(payload, show_blood_pressure)
        doc = PrintDocument()
        doc.PrinterSettings.PrinterName = chosen
        if not doc.PrinterSettings.IsValid:
            raise RuntimeError(f"Windows no puede usar la impresora ‘{chosen}’")

        doc.DocumentName = "Recibo de consulta médica"
        doc.OriginAtMargins = False
        doc.DefaultPageSettings.PaperSize = PaperSize("Recibo 80 mm", 315, 760)
        doc.DefaultPageSettings.Margins = Margins(0, 0, 0, 0)

        holder = {"stream": None, "img": None}

        def on_print_page(sender, e):
            from System import Array, Byte  # type: ignore
            arr = Array[Byte](bytearray(png))
            holder["stream"] = MemoryStream(arr)
            holder["img"] = Image.FromStream(holder["stream"])
            target_w = 283.5  # 72 mm
            target_h = target_w * float(holder["img"].Height) / float(holder["img"].Width)
            x = max(0.0, (float(e.PageBounds.Width) - target_w) / 2.0)
            e.Graphics.DrawImage(
                holder["img"], RectangleF(x, 0.0, target_w, target_h)
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
            if holder.get("img") is not None:
                try:
                    holder["img"].Dispose()
                except Exception:
                    pass
            if holder.get("stream") is not None:
                try:
                    holder["stream"].Dispose()
                except Exception:
                    pass
            try:
                doc.Dispose()
            except Exception:
                pass
        return chosen

    core._print_receipt_windows = _print_receipt_windows_v4467

    from fastapi import Response  # type: ignore

    @app.post("/api/v4467/receipt-image")
    def v4467_receipt_image(
        data: core.ReceiptPrintIn,
        user=core.Depends(core.current_user),
    ):
        prefs = core._app_preferences()
        png = _render_receipt_png_v4467(
            data, bool(prefs.get("show_blood_pressure", True))
        )
        return Response(
            content=png,
            media_type="image/png",
            headers={"Cache-Control": "no-store"},
        )

    PREVIEW_JS = r"""
;(()=>{
  if(window.__v4467ReceiptRaster)return;
  window.__v4467ReceiptRaster=true;
  function install(){
    if(typeof window.printAttentionSlipData!=='function'||typeof window.receiptPrintPayload!=='function'){
      setTimeout(install,100);return;
    }
    const patched=async function(visit,patient,dayNumber=null){
      try{
        const payload=window.receiptPrintPayload(visit,patient,dayNumber);
        const r=await fetch('/api/v4467/receipt-image',{
          method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)
        });
        if(!r.ok)throw Error('HTTP '+r.status);
        const blob=await r.blob();const url=URL.createObjectURL(blob);
        document.querySelector('#receiptPrintFrame')?.remove();
        const frame=document.createElement('iframe');frame.id='receiptPrintFrame';frame.title='Impresión de recibo';frame.setAttribute('aria-hidden','true');
        Object.assign(frame.style,{position:'fixed',right:'-10000px',bottom:'0',width:'80mm',height:'190mm',border:'0',opacity:'0',pointerEvents:'none'});
        document.body.appendChild(frame);
        const doc=frame.contentDocument||frame.contentWindow?.document;if(!doc)throw Error('Sin documento de impresión');
        let cleaned=false;const cleanup=()=>{if(cleaned)return;cleaned=true;try{URL.revokeObjectURL(url)}catch{}setTimeout(()=>frame.remove(),120)};
        doc.open();doc.write(`<!doctype html><html><head><meta charset="utf-8"><style>
          *{box-sizing:border-box}html,body{margin:0;padding:0;background:#fff;width:80mm}
          body{display:flex;justify-content:center;align-items:flex-start}
          img{display:block;width:72mm;height:auto;margin:0;padding:0}
          @media print{@page{size:80mm auto;margin:0}html,body{width:80mm;margin:0;padding:0}img{width:72mm;margin:0 auto}}
        </style></head><body><img id="rimg" src="${url}"></body></html>`);doc.close();
        const img=doc.getElementById('rimg');
        const go=()=>setTimeout(()=>{try{const w=frame.contentWindow;w.addEventListener('afterprint',cleanup,{once:true});w.focus();w.print();setTimeout(cleanup,120000)}catch(e){cleanup();alert('No se pudo imprimir el recibo.')}},80);
        if(img&&!img.complete){img.addEventListener('load',go,{once:true});img.addEventListener('error',go,{once:true});setTimeout(go,800)}else go();
      }catch(e){
        alert('No se pudo preparar el recibo. Se usará el formato anterior.');
        try{return window.__v4466PrintFallback?.(visit,patient,dayNumber)}catch{}
      }
    };
    window.__v4466PrintFallback=window.printAttentionSlipData;
    patched.__v4467=true;window.printAttentionSlipData=patched;
  }
  install();
})();
"""
    core.V460_OVERLAY_JS = (
        (getattr(core, "V460_OVERLAY_JS", "") or "") + "\n" + PREVIEW_JS
    )

    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f"{type(exc).__name__}: {exc}"
    try:
        core.logging.getLogger(__name__).error(
            "v4.4.67 receipt patch failed: %s", PATCH_BOOT_ERROR
        )
    except Exception:
        pass

@app.get("/api/v4467/receipt-health")
def v4467_receipt_health(user=core.Depends(core.current_user)):
    return {
        "ok": PATCH_BOOT_OK,
        "version": APP_VERSION,
        "error": PATCH_BOOT_ERROR,
        "same_raster_for_preview_and_direct": True,
        "thermal_width_px": 576,
        "thermal_width_mm": 72,
        "outer_border": False,
        "larger_legacy_typography": True,
        "subsecuente_safe": True,
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

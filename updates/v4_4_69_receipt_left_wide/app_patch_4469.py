from __future__ import annotations

# v4.4.69 — mismo diseño de v4.4.68, mejor aprovechamiento horizontal.
# - Conserva tamaños, negritas y altura que ya quedaron aprobados visualmente.
# - Expande suavemente el raster dentro del ancho físico seguro de 72 mm.
# - Desplaza el recibo ~1.5 mm hacia la izquierda en impresión directa y vista previa.
# - Mantiene vista previa e impresión automática idénticas.
# - No modifica datos, agenda ni facturación.

import os
import app_patch_4468 as previous

core = previous.core
app = previous.app
APP_VERSION = "4.4.69"
previous.APP_VERSION = APP_VERSION
core.APP_VERSION = APP_VERSION
try:
    previous.previous.APP_VERSION = APP_VERSION
except Exception:
    pass

PATCH_BOOT_OK = False
PATCH_BOOT_ERROR = ""

try:
    _render_v4468 = previous._render_receipt_png_v4468

    def _render_receipt_png_v4469(payload, show_blood_pressure=True):
        """Mantiene el diseño de 4.4.68, usando mejor los 576 puntos imprimibles."""
        base_png = _render_v4468(payload, show_blood_pressure)

        import clr  # type: ignore
        clr.AddReference("System.Drawing")
        clr.AddReference("System")
        from System import Array, Byte  # type: ignore
        from System.IO import MemoryStream  # type: ignore
        from System.Drawing import Bitmap, Graphics, Color, Rectangle, GraphicsUnit  # type: ignore
        from System.Drawing.Drawing2D import InterpolationMode, PixelOffsetMode, SmoothingMode  # type: ignore
        from System.Drawing.Imaging import ImageFormat, PixelFormat  # type: ignore

        source_stream = None
        src = None
        out = None
        g = None
        out_stream = None
        try:
            arr = Array[Byte](bytearray(base_png))
            source_stream = MemoryStream(arr)
            src = Bitmap(source_stream)

            # v4.4.68 dejaba unos pocos puntos blancos laterales dentro del raster.
            # Recortamos solo 8 px por lado (≈1 mm) y volvemos a 576 px usando
            # vecino más cercano: el contenido gana ~2.9 % de ancho sin superar
            # los 72 mm físicos de la cabeza térmica.
            crop_left = 8
            crop_right = 8
            crop_width = max(1, int(src.Width) - crop_left - crop_right)

            out = Bitmap(576, int(src.Height), PixelFormat.Format24bppRgb)
            g = Graphics.FromImage(out)
            g.Clear(Color.White)
            g.InterpolationMode = InterpolationMode.NearestNeighbor
            g.PixelOffsetMode = PixelOffsetMode.Half
            try:
                g.SmoothingMode = getattr(SmoothingMode, "None")
            except Exception:
                pass

            g.DrawImage(
                src,
                Rectangle(0, 0, 576, int(src.Height)),
                Rectangle(crop_left, 0, crop_width, int(src.Height)),
                GraphicsUnit.Pixel,
            )

            out_stream = MemoryStream()
            out.Save(out_stream, ImageFormat.Png)
            return bytes(bytearray(out_stream.ToArray()))
        finally:
            try:
                if g is not None:
                    g.Dispose()
            except Exception:
                pass
            try:
                if out is not None:
                    out.Dispose()
            except Exception:
                pass
            try:
                if src is not None:
                    src.Dispose()
            except Exception:
                pass
            try:
                if source_stream is not None:
                    source_stream.Dispose()
            except Exception:
                pass
            try:
                if out_stream is not None:
                    out_stream.Dispose()
            except Exception:
                pass

    def _print_receipt_windows_v4469(
        payload, printer_name: str = "", show_blood_pressure: bool = True
    ) -> str:
        if os.name != "nt":
            raise RuntimeError("La impresión directa solo está disponible en Windows")

        import clr  # type: ignore
        clr.AddReference("System.Drawing")
        clr.AddReference("System")
        from System import Array, Byte  # type: ignore
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

        png = _render_receipt_png_v4469(payload, show_blood_pressure)
        doc = PrintDocument()
        doc.PrinterSettings.PrinterName = chosen
        if not doc.PrinterSettings.IsValid:
            raise RuntimeError(f"Windows no puede usar la impresora ‘{chosen}’")

        doc.DocumentName = "Recibo de consulta médica"
        doc.OriginAtMargins = False
        doc.DefaultPageSettings.PaperSize = PaperSize("Recibo 80 mm largo", 315, 1050)
        doc.DefaultPageSettings.Margins = Margins(0, 0, 0, 0)

        holder = {"stream": None, "img": None}

        def on_print_page(sender, e):
            arr = Array[Byte](bytearray(png))
            holder["stream"] = MemoryStream(arr)
            holder["img"] = Image.FromStream(holder["stream"])

            target_w = 283.5  # 72 mm: ancho nativo seguro del cabezal de 576 dots.
            target_h = (
                target_w
                * float(holder["img"].Height)
                / float(holder["img"].Width)
            )

            # 2.5 mm desde el borde izquierdo del papel. Antes estaba centrado
            # (~4 mm por lado), así que todo queda ~1.5 mm más a la izquierda.
            x = 9.84
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

    core._print_receipt_windows = _print_receipt_windows_v4469

    from fastapi import Response  # type: ignore

    @app.post("/api/v4469/receipt-image")
    def v4469_receipt_image(
        data: core.ReceiptPrintIn,
        user=core.Depends(core.current_user),
    ):
        prefs = core._app_preferences()
        png = _render_receipt_png_v4469(
            data, bool(prefs.get("show_blood_pressure", True))
        )
        return Response(
            content=png,
            media_type="image/png",
            headers={"Cache-Control": "no-store"},
        )

    PREVIEW_JS = r"""
;(()=>{
  if(window.__v4469ReceiptRaster)return;
  window.__v4469ReceiptRaster=true;
  function install(){
    if(typeof window.printAttentionSlipData!=='function'||typeof window.receiptPrintPayload!=='function'){
      setTimeout(install,100);return;
    }
    const patched=async function(visit,patient,dayNumber=null){
      try{
        const payload=window.receiptPrintPayload(visit,patient,dayNumber);
        const r=await fetch('/api/v4469/receipt-image',{
          method:'POST',credentials:'same-origin',
          headers:{'Content-Type':'application/json'},
          body:JSON.stringify(payload)
        });
        if(!r.ok)throw Error('HTTP '+r.status);
        const blob=await r.blob();
        const url=URL.createObjectURL(blob);
        document.querySelector('#receiptPrintFrame')?.remove();
        const frame=document.createElement('iframe');
        frame.id='receiptPrintFrame';
        frame.title='Impresión de recibo';
        frame.setAttribute('aria-hidden','true');
        Object.assign(frame.style,{
          position:'fixed',right:'-10000px',bottom:'0',
          width:'80mm',height:'260mm',border:'0',opacity:'0',pointerEvents:'none'
        });
        document.body.appendChild(frame);
        const doc=frame.contentDocument||frame.contentWindow?.document;
        if(!doc)throw Error('Sin documento de impresión');
        let cleaned=false;
        const cleanup=()=>{
          if(cleaned)return;cleaned=true;
          try{URL.revokeObjectURL(url)}catch{}
          setTimeout(()=>frame.remove(),120)
        };
        doc.open();
        doc.write(`<!doctype html><html><head><meta charset="utf-8"><style>
          *{box-sizing:border-box}
          html,body{margin:0;padding:0;background:#fff;width:80mm}
          body{display:block}
          img{display:block;width:72mm;height:auto;margin-left:2.5mm;margin-right:5.5mm;padding:0}
          @media print{
            @page{size:80mm auto;margin:0}
            html,body{width:80mm;margin:0;padding:0}
            img{width:72mm;height:auto;margin-left:2.5mm;margin-right:5.5mm}
          }
        </style></head><body><img id="rimg" src="${url}"></body></html>`);
        doc.close();
        const img=doc.getElementById('rimg');
        const go=()=>setTimeout(()=>{
          try{
            const w=frame.contentWindow;
            w.addEventListener('afterprint',cleanup,{once:true});
            w.focus();w.print();setTimeout(cleanup,120000)
          }catch(e){
            cleanup();alert('No se pudo imprimir el recibo.')
          }
        },80);
        if(img&&!img.complete){
          img.addEventListener('load',go,{once:true});
          img.addEventListener('error',go,{once:true});
          setTimeout(go,900)
        }else go();
      }catch(e){
        alert('No se pudo preparar el recibo. Se usará el formato anterior.');
        try{return window.__v4468PrintFallback?.(visit,patient,dayNumber)}catch{}
      }
    };
    window.__v4468PrintFallback=window.printAttentionSlipData;
    patched.__v4469=true;
    window.printAttentionSlipData=patched;
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
            "v4.4.69 receipt patch failed: %s", PATCH_BOOT_ERROR
        )
    except Exception:
        pass


@app.get("/api/v4469/receipt-health")
def v4469_receipt_health(user=core.Depends(core.current_user)):
    return {
        "ok": PATCH_BOOT_OK,
        "version": APP_VERSION,
        "error": PATCH_BOOT_ERROR,
        "same_raster_for_preview_and_direct": True,
        "thermal_width_px": 576,
        "thermal_width_mm": 72,
        "paper_left_offset_mm": 2.5,
        "horizontal_content_expansion_percent": 2.9,
        "keeps_v4468_typography_and_height": True,
        "outer_border": False,
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

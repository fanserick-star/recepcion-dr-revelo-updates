from __future__ import annotations
from runtime_registry import layers as _rf_layers, module_lookup as _rf_module_lookup

import os
previous = _rf_layers['app_patch_4468']
core = previous.core
app = previous.app
APP_VERSION = '4.4.69'
previous.APP_VERSION = APP_VERSION
core.APP_VERSION = APP_VERSION
try:
    previous.previous.APP_VERSION = APP_VERSION
except Exception:
    pass
PATCH_BOOT_OK = False
PATCH_BOOT_ERROR = ''
try:
    _render_v4468 = previous._render_receipt_png_v4468

    def _render_receipt_png_v4469(payload, show_blood_pressure=True):
        """Mantiene el diseño de 4.4.68, usando mejor los 576 puntos imprimibles."""
        base_png = _render_v4468(payload, show_blood_pressure)
        import clr
        clr.AddReference('System.Drawing')
        clr.AddReference('System')
        from System import Array, Byte
        from System.IO import MemoryStream
        from System.Drawing import Bitmap, Graphics, Color, Rectangle, GraphicsUnit
        from System.Drawing.Drawing2D import InterpolationMode, PixelOffsetMode, SmoothingMode
        from System.Drawing.Imaging import ImageFormat, PixelFormat
        source_stream = None
        src = None
        out = None
        g = None
        out_stream = None
        try:
            arr = Array[Byte](bytearray(base_png))
            source_stream = MemoryStream(arr)
            src = Bitmap(source_stream)
            crop_left = 8
            crop_right = 8
            crop_width = max(1, int(src.Width) - crop_left - crop_right)
            out = Bitmap(576, int(src.Height), PixelFormat.Format24bppRgb)
            g = Graphics.FromImage(out)
            g.Clear(Color.White)
            g.InterpolationMode = InterpolationMode.NearestNeighbor
            g.PixelOffsetMode = PixelOffsetMode.Half
            try:
                g.SmoothingMode = getattr(SmoothingMode, 'None')
            except Exception:
                pass
            g.DrawImage(src, Rectangle(0, 0, 576, int(src.Height)), Rectangle(crop_left, 0, crop_width, int(src.Height)), GraphicsUnit.Pixel)
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

    def _print_receipt_windows_v4469(payload, printer_name: str='', show_blood_pressure: bool=True) -> str:
        if os.name != 'nt':
            raise RuntimeError('La impresión directa solo está disponible en Windows')
        import clr
        clr.AddReference('System.Drawing')
        clr.AddReference('System')
        from System import Array, Byte
        from System.IO import MemoryStream
        from System.Drawing import Image, RectangleF
        from System.Drawing.Printing import PrintDocument, PrinterSettings, PaperSize, Margins
        available = [str(name) for name in PrinterSettings.InstalledPrinters]
        chosen = str(printer_name or '').strip() or str(PrinterSettings().PrinterName or '')
        if not chosen:
            raise RuntimeError('Windows no tiene una impresora predeterminada')
        if available and chosen not in available:
            raise RuntimeError(f'La impresora ‘{chosen}’ ya no está disponible')
        png = _render_receipt_png_v4469(payload, show_blood_pressure)
        doc = PrintDocument()
        doc.PrinterSettings.PrinterName = chosen
        if not doc.PrinterSettings.IsValid:
            raise RuntimeError(f'Windows no puede usar la impresora ‘{chosen}’')
        doc.DocumentName = 'Recibo de consulta médica'
        doc.OriginAtMargins = False
        doc.DefaultPageSettings.PaperSize = PaperSize('Recibo 80 mm largo', 315, 1050)
        doc.DefaultPageSettings.Margins = Margins(0, 0, 0, 0)
        holder = {'stream': None, 'img': None}

        def on_print_page(sender, e):
            arr = Array[Byte](bytearray(png))
            holder['stream'] = MemoryStream(arr)
            holder['img'] = Image.FromStream(holder['stream'])
            target_w = 283.5
            target_h = target_w * float(holder['img'].Height) / float(holder['img'].Width)
            x = 9.84
            e.Graphics.DrawImage(holder['img'], RectangleF(x, 0.0, target_w, target_h))
            e.HasMorePages = False
        doc.PrintPage += on_print_page
        try:
            doc.Print()
        finally:
            try:
                doc.PrintPage -= on_print_page
            except Exception:
                pass
            if holder.get('img') is not None:
                try:
                    holder['img'].Dispose()
                except Exception:
                    pass
            if holder.get('stream') is not None:
                try:
                    holder['stream'].Dispose()
                except Exception:
                    pass
            try:
                doc.Dispose()
            except Exception:
                pass
        return chosen
    core._print_receipt_windows = _print_receipt_windows_v4469
    from fastapi import Response

    @app.post('/api/v4469/receipt-image')
    def v4469_receipt_image(data: core.ReceiptPrintIn, user=core.Depends(core.current_user)):
        prefs = core._app_preferences()
        png = _render_receipt_png_v4469(data, bool(prefs.get('show_blood_pressure', True)))
        return Response(content=png, media_type='image/png', headers={'Cache-Control': 'no-store'})
    PREVIEW_JS = '\n;(()=>{\n  if(window.__v4469ReceiptRaster)return;\n  window.__v4469ReceiptRaster=true;\n  function install(){\n    if(typeof window.printAttentionSlipData!==\'function\'||typeof window.receiptPrintPayload!==\'function\'){\n      setTimeout(install,100);return;\n    }\n    const patched=async function(visit,patient,dayNumber=null){\n      try{\n        const payload=window.receiptPrintPayload(visit,patient,dayNumber);\n        const r=await fetch(\'/api/v4469/receipt-image\',{\n          method:\'POST\',credentials:\'same-origin\',\n          headers:{\'Content-Type\':\'application/json\'},\n          body:JSON.stringify(payload)\n        });\n        if(!r.ok)throw Error(\'HTTP \'+r.status);\n        const blob=await r.blob();\n        const url=URL.createObjectURL(blob);\n        document.querySelector(\'#receiptPrintFrame\')?.remove();\n        const frame=document.createElement(\'iframe\');\n        frame.id=\'receiptPrintFrame\';\n        frame.title=\'Impresión de recibo\';\n        frame.setAttribute(\'aria-hidden\',\'true\');\n        Object.assign(frame.style,{\n          position:\'fixed\',right:\'-10000px\',bottom:\'0\',\n          width:\'80mm\',height:\'260mm\',border:\'0\',opacity:\'0\',pointerEvents:\'none\'\n        });\n        document.body.appendChild(frame);\n        const doc=frame.contentDocument||frame.contentWindow?.document;\n        if(!doc)throw Error(\'Sin documento de impresión\');\n        let cleaned=false;\n        const cleanup=()=>{\n          if(cleaned)return;cleaned=true;\n          try{URL.revokeObjectURL(url)}catch{}\n          setTimeout(()=>frame.remove(),120)\n        };\n        doc.open();\n        doc.write(`<!doctype html><html><head><meta charset="utf-8"><style>\n          *{box-sizing:border-box}\n          html,body{margin:0;padding:0;background:#fff;width:80mm}\n          body{display:block}\n          img{display:block;width:72mm;height:auto;margin-left:2.5mm;margin-right:5.5mm;padding:0}\n          @media print{\n            @page{size:80mm auto;margin:0}\n            html,body{width:80mm;margin:0;padding:0}\n            img{width:72mm;height:auto;margin-left:2.5mm;margin-right:5.5mm}\n          }\n        </style></head><body><img id="rimg" src="${url}"></body></html>`);\n        doc.close();\n        const img=doc.getElementById(\'rimg\');\n        const go=()=>setTimeout(()=>{\n          try{\n            const w=frame.contentWindow;\n            w.addEventListener(\'afterprint\',cleanup,{once:true});\n            w.focus();w.print();setTimeout(cleanup,120000)\n          }catch(e){\n            cleanup();alert(\'No se pudo imprimir el recibo.\')\n          }\n        },80);\n        if(img&&!img.complete){\n          img.addEventListener(\'load\',go,{once:true});\n          img.addEventListener(\'error\',go,{once:true});\n          setTimeout(go,900)\n        }else go();\n      }catch(e){\n        alert(\'No se pudo preparar el recibo. Se usará el formato anterior.\');\n        try{return window.__v4468PrintFallback?.(visit,patient,dayNumber)}catch{}\n      }\n    };\n    window.__v4468PrintFallback=window.printAttentionSlipData;\n    patched.__v4469=true;\n    window.printAttentionSlipData=patched;\n  }\n  install();\n})();\n'
    core.V460_OVERLAY_JS = (getattr(core, 'V460_OVERLAY_JS', '') or '') + '\n' + PREVIEW_JS
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f'{type(exc).__name__}: {exc}'
    try:
        core.logging.getLogger(__name__).error('v4.4.69 receipt patch failed: %s', PATCH_BOOT_ERROR)
    except Exception:
        pass

@app.get('/api/v4469/receipt-health')
def v4469_receipt_health(user=core.Depends(core.current_user)):
    return {'ok': PATCH_BOOT_OK, 'version': APP_VERSION, 'error': PATCH_BOOT_ERROR, 'same_raster_for_preview_and_direct': True, 'thermal_width_px': 576, 'thermal_width_mm': 72, 'paper_left_offset_mm': 2.5, 'horizontal_content_expansion_percent': 2.9, 'keeps_v4468_typography_and_height': True, 'outer_border': False}
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=core.LOCAL_HTTP_PORT, reload=False, access_log=False, log_level='warning', workers=1)

from __future__ import annotations
from runtime_registry import layers as _rf_layers, module_lookup as _rf_module_lookup

import os
previous = _rf_layers['app_patch_4467']
core = previous.core
app = previous.app
APP_VERSION = '4.4.68'
previous.APP_VERSION = APP_VERSION
core.APP_VERSION = APP_VERSION
try:
    previous.previous.APP_VERSION = APP_VERSION
except Exception:
    pass
PATCH_BOOT_OK = False
PATCH_BOOT_ERROR = ''
try:

    def _name_lines_v4468(value):
        parts = [x for x in str(value or '').strip().upper().split() if x]
        if not parts:
            return ('SIN NOMBRE', '')
        if len(parts) == 1:
            return (parts[0], '')
        if len(parts) == 2:
            return (' '.join(parts), '')
        if len(parts) == 3:
            return (' '.join(parts[:2]), parts[2])
        return (' '.join(parts[:2]), ' '.join(parts[2:]))

    def _render_receipt_png_v4468(payload, show_blood_pressure=True):
        import clr
        clr.AddReference('System.Drawing')
        clr.AddReference('System')
        from System.IO import MemoryStream
        from System.Drawing import Bitmap, Graphics, Color, Font, FontStyle, GraphicsUnit, Brushes, Pen, Rectangle, RectangleF, StringFormat, StringAlignment
        from System.Drawing.Drawing2D import DashStyle, InterpolationMode, PixelOffsetMode, SmoothingMode
        from System.Drawing.Text import TextRenderingHint
        from System.Drawing.Imaging import ImageFormat, PixelFormat
        W, H = (576, 1120)
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
                g.SmoothingMode = getattr(SmoothingMode, 'None')
            except Exception:
                pass

            def font(px, bold=True, family='Arial'):
                f = Font(family, float(px), FontStyle.Bold if bold else FontStyle.Regular, GraphicsUnit.Pixel)
                fonts.append(f)
                return f
            f_title = font(36, True, 'Arial Black')
            f_label = font(29, True)
            f_value = font(33, True)
            f_name_label = font(25, True)
            f_name_pref = 42
            f_turn = font(42, True)
            f_status = font(24, True)
            solid = Pen(Color.Black, 2.2)
            pens.append(solid)
            dotted = Pen(Color.FromArgb(55, 55, 55), 1.8)
            pens.append(dotted)
            dotted.DashStyle = DashStyle.Dot
            check = Pen(Color.Black, 3.4)
            pens.append(check)
            inner_l, inner_r = (10.0, W - 10.0)
            inner_w = inner_r - inner_l
            y = 12.0
            center = StringFormat()
            center.Alignment = StringAlignment.Center
            center.LineAlignment = StringAlignment.Near

            def fit_bold(text, preferred_px, min_px, max_width, family='Arial Black'):
                px = float(preferred_px)
                f = font(px, True, family)
                while px > float(min_px) and float(g.MeasureString(str(text), f).Width) > float(max_width):
                    px -= 1.0
                    f = font(px, True, family)
                return f
            logo_path = os.path.join(core.BASE_DIR, 'static', 'doctor_isotype.png')
            if os.path.exists(logo_path):
                try:
                    logo_func = getattr(getattr(previous, 'previous', None), '_thermal_logo_v4466', None)
                    if logo_func:
                        logo = logo_func(logo_path)
                    if logo is not None:
                        g.DrawImage(logo, 13.0, y + 4.0, 92.0, 92.0)
                except Exception:
                    logo = None
            title_text = 'RECIBO DE\nCONSULTA MÉDICA'
            g.DrawString(title_text, f_title, Brushes.Black, RectangleF(108.0, y + 6.0, W - 120.0, 94.0), center)
            y += 104.0
            g.DrawLine(solid, inner_l, y, inner_r, y)

            def separator():
                g.DrawLine(dotted, inner_l, y, inner_r, y)

            def row(label, value, value_x, vf=None, height=70.0, lf=None):
                nonlocal y
                top = y
                y += 18.0
                g.DrawString(str(label), lf or f_label, Brushes.Black, inner_l, y)
                vx = float(value_x)
                g.DrawString(str(value or ''), vf or f_value, Brushes.Black, RectangleF(vx, y - 4.0, inner_r - vx, 48.0))
                y = top + height
                separator()
            row('Fecha:', payload.fecha, 212.0, f_value, 69.0)
            y += 21.0
            g.DrawString('Nombre', f_name_label, Brushes.Black, RectangleF(inner_l, y, inner_w, 34.0), center)
            y += 34.0
            surname, given = _name_lines_v4468(payload.nombre)
            name_font_1 = fit_bold(surname, f_name_pref, 32, inner_w - 8.0)
            g.DrawString(surname, name_font_1, Brushes.Black, RectangleF(inner_l, y, inner_w, 52.0), center)
            y += 52.0
            if given:
                name_font_2 = fit_bold(given, f_name_pref, 32, inner_w - 8.0)
                g.DrawString(given, name_font_2, Brushes.Black, RectangleF(inner_l, y, inner_w, 52.0), center)
                y += 52.0
            y += 17.0
            g.DrawLine(solid, inner_l, y, inner_r, y)
            if bool(payload.is_new) and payload.fecha_nacimiento:
                birth_label = fit_bold('Fecha de nacimiento:', 26, 23, 320.0, 'Arial')
                row('Fecha de nacimiento:', payload.fecha_nacimiento, 342.0, f_value, 74.0, birth_label)
            if show_blood_pressure:
                top = y
                y += 18.0
                g.DrawString('Presión Arterial:', f_label, Brushes.Black, inner_l, y + 10.0)
                bw, bh = (148.0, 67.0)
                g.DrawRectangle(solid, inner_r - bw, y, bw, bh)
                y = top + 98.0
                separator()
            row('Teléfono:', payload.celular or 'Sin registrar', 215.0, f_value, 70.0)
            if payload.turno:
                row('Turno:', str(payload.turno), 215.0, f_turn, 77.0)
            y += 27.0
            box = 44.0
            gap = 10.0
            col_gap = 8.0
            col_w = (inner_w - col_gap) / 2.0

            def option(col_l, label, checked):
                label_font = f_status
                label_w = float(g.MeasureString(label, label_font).Width)
                if box + gap + label_w > col_w:
                    label_font = fit_bold(label, 24, 20, col_w - box - gap - 2.0, 'Arial')
                    label_w = float(g.MeasureString(label, label_font).Width)
                group_w = box + gap + label_w
                x = col_l + max(0.0, (col_w - group_w) / 2.0)
                x = min(x, col_l + col_w - group_w)
                g.DrawRectangle(solid, x, y, box, box)
                if checked:
                    g.DrawLine(check, x + 9.0, y + 24.0, x + 19.0, y + 35.0)
                    g.DrawLine(check, x + 19.0, y + 35.0, x + 37.0, y + 8.0)
                g.DrawString(label, label_font, Brushes.Black, x + box + gap, y + 8.0)
            option(inner_l, 'PRIMERO', bool(payload.is_new))
            option(inner_l + col_w + col_gap, 'SUBSECUENTE', not bool(payload.is_new))
            y += box + 26.0
            final_h = int(min(H, y + 12.0))
            cropped = bmp.Clone(Rectangle(0, 0, W, final_h), PixelFormat.Format24bppRgb)
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

    def _print_receipt_windows_v4468(payload, printer_name: str='', show_blood_pressure: bool=True) -> str:
        if os.name != 'nt':
            raise RuntimeError('La impresión directa solo está disponible en Windows')
        import clr
        clr.AddReference('System.Drawing')
        clr.AddReference('System')
        from System.IO import MemoryStream
        from System.Drawing import Image, RectangleF
        from System.Drawing.Printing import PrintDocument, PrinterSettings, PaperSize, Margins
        available = [str(name) for name in PrinterSettings.InstalledPrinters]
        chosen = str(printer_name or '').strip() or str(PrinterSettings().PrinterName or '')
        if not chosen:
            raise RuntimeError('Windows no tiene una impresora predeterminada')
        if available and chosen not in available:
            raise RuntimeError(f'La impresora ‘{chosen}’ ya no está disponible')
        png = _render_receipt_png_v4468(payload, show_blood_pressure)
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
            from System import Array, Byte
            arr = Array[Byte](bytearray(png))
            holder['stream'] = MemoryStream(arr)
            holder['img'] = Image.FromStream(holder['stream'])
            target_w = 283.5
            target_h = target_w * float(holder['img'].Height) / float(holder['img'].Width)
            x = max(0.0, (float(e.PageBounds.Width) - target_w) / 2.0)
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
    core._print_receipt_windows = _print_receipt_windows_v4468
    from fastapi import Response

    @app.post('/api/v4468/receipt-image')
    def v4468_receipt_image(data: core.ReceiptPrintIn, user=core.Depends(core.current_user)):
        prefs = core._app_preferences()
        png = _render_receipt_png_v4468(data, bool(prefs.get('show_blood_pressure', True)))
        return Response(content=png, media_type='image/png', headers={'Cache-Control': 'no-store'})
    PREVIEW_JS = '\n;(()=>{\n  if(window.__v4468ReceiptRaster)return;\n  window.__v4468ReceiptRaster=true;\n  function install(){\n    if(typeof window.printAttentionSlipData!==\'function\'||typeof window.receiptPrintPayload!==\'function\'){\n      setTimeout(install,100);return;\n    }\n    const patched=async function(visit,patient,dayNumber=null){\n      try{\n        const payload=window.receiptPrintPayload(visit,patient,dayNumber);\n        const r=await fetch(\'/api/v4468/receipt-image\',{\n          method:\'POST\',credentials:\'same-origin\',\n          headers:{\'Content-Type\':\'application/json\'},\n          body:JSON.stringify(payload)\n        });\n        if(!r.ok)throw Error(\'HTTP \'+r.status);\n        const blob=await r.blob();\n        const url=URL.createObjectURL(blob);\n        document.querySelector(\'#receiptPrintFrame\')?.remove();\n        const frame=document.createElement(\'iframe\');\n        frame.id=\'receiptPrintFrame\';\n        frame.title=\'Impresión de recibo\';\n        frame.setAttribute(\'aria-hidden\',\'true\');\n        Object.assign(frame.style,{\n          position:\'fixed\',right:\'-10000px\',bottom:\'0\',\n          width:\'80mm\',height:\'260mm\',border:\'0\',opacity:\'0\',pointerEvents:\'none\'\n        });\n        document.body.appendChild(frame);\n        const doc=frame.contentDocument||frame.contentWindow?.document;\n        if(!doc)throw Error(\'Sin documento de impresión\');\n        let cleaned=false;\n        const cleanup=()=>{\n          if(cleaned)return;cleaned=true;\n          try{URL.revokeObjectURL(url)}catch{}\n          setTimeout(()=>frame.remove(),120)\n        };\n        doc.open();\n        doc.write(`<!doctype html><html><head><meta charset="utf-8"><style>\n          *{box-sizing:border-box}html,body{margin:0;padding:0;background:#fff;width:80mm}\n          body{display:flex;justify-content:center;align-items:flex-start}\n          img{display:block;width:72mm;height:auto;margin:0;padding:0}\n          @media print{\n            @page{size:80mm auto;margin:0}\n            html,body{width:80mm;margin:0;padding:0}\n            img{width:72mm;margin:0 auto}\n          }\n        </style></head><body><img id="rimg" src="${url}"></body></html>`);\n        doc.close();\n        const img=doc.getElementById(\'rimg\');\n        const go=()=>setTimeout(()=>{\n          try{\n            const w=frame.contentWindow;\n            w.addEventListener(\'afterprint\',cleanup,{once:true});\n            w.focus();w.print();setTimeout(cleanup,120000)\n          }catch(e){\n            cleanup();alert(\'No se pudo imprimir el recibo.\')\n          }\n        },80);\n        if(img&&!img.complete){\n          img.addEventListener(\'load\',go,{once:true});\n          img.addEventListener(\'error\',go,{once:true});\n          setTimeout(go,900)\n        }else go();\n      }catch(e){\n        alert(\'No se pudo preparar el recibo. Se usará el formato anterior.\');\n        try{return window.__v4467PrintFallback?.(visit,patient,dayNumber)}catch{}\n      }\n    };\n    window.__v4467PrintFallback=window.printAttentionSlipData;\n    patched.__v4468=true;\n    window.printAttentionSlipData=patched;\n  }\n  install();\n})();\n'
    core.V460_OVERLAY_JS = (getattr(core, 'V460_OVERLAY_JS', '') or '') + '\n' + PREVIEW_JS
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f'{type(exc).__name__}: {exc}'
    try:
        core.logging.getLogger(__name__).error('v4.4.68 receipt patch failed: %s', PATCH_BOOT_ERROR)
    except Exception:
        pass

@app.get('/api/v4468/receipt-health')
def v4468_receipt_health(user=core.Depends(core.current_user)):
    return {'ok': PATCH_BOOT_OK, 'version': APP_VERSION, 'error': PATCH_BOOT_ERROR, 'same_raster_for_preview_and_direct': True, 'thermal_width_px': 576, 'thermal_width_mm': 72, 'longer_receipt': True, 'larger_fonts': True, 'title_bold_large': True, 'name_bold_large': True, 'outer_border': False}
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=core.LOCAL_HTTP_PORT, reload=False, access_log=False, log_level='warning', workers=1)

from __future__ import annotations

# v4.4.66 — un solo motor visual para recibo térmico CRM-308.
# La impresión directa y la impresión desde vista previa usan el MISMO PNG raster
# de 576 px (≈72 mm a 203 dpi), evitando diferencias de GDI vs HTML/CSS.
# También recorta/umbraliza el isotipo para que salga grande y limpio en térmica.

import io
import os
import app_patch_4465 as previous

core = previous.core
app = previous.app
APP_VERSION = "4.4.66"
previous.APP_VERSION = APP_VERSION
core.APP_VERSION = APP_VERSION
try:
    previous.previous.APP_VERSION = APP_VERSION
except Exception:
    pass

PATCH_BOOT_OK = False
PATCH_BOOT_ERROR = ""

try:
    def _name_lines_v4466(value):
        parts = [x for x in str(value or "").strip().upper().split() if x]
        if not parts:
            return "SIN NOMBRE", ""
        if len(parts) == 1:
            return parts[0], ""
        return " ".join(parts[:2]), " ".join(parts[2:])

    def _thermal_logo_v4466(path):
        """Recorta el blanco del PNG y devuelve un isotipo B/N 96x96."""
        import clr  # type: ignore
        clr.AddReference("System.Drawing")
        from System.Drawing import Bitmap, Color, Graphics, Rectangle, Brushes, GraphicsUnit  # type: ignore
        from System.Drawing.Drawing2D import InterpolationMode, PixelOffsetMode  # type: ignore

        src = Bitmap(path)
        try:
            min_x, min_y = src.Width, src.Height
            max_x = max_y = -1
            for yy in range(src.Height):
                for xx in range(src.Width):
                    c = src.GetPixel(xx, yy)
                    if c.A > 20 and min(c.R, c.G, c.B) < 235:
                        min_x = min(min_x, xx); min_y = min(min_y, yy)
                        max_x = max(max_x, xx); max_y = max(max_y, yy)
            if max_x < min_x or max_y < min_y:
                return None
            crop_w = max_x - min_x + 1
            crop_h = max_y - min_y + 1
            out = Bitmap(96, 96)
            g = Graphics.FromImage(out)
            try:
                g.Clear(Color.White)
                g.InterpolationMode = InterpolationMode.HighQualityBicubic
                g.PixelOffsetMode = PixelOffsetMode.HighQuality
                scale = min(82.0 / crop_w, 82.0 / crop_h)
                dw = max(1, int(crop_w * scale)); dh = max(1, int(crop_h * scale))
                dx = (96 - dw) // 2; dy = (96 - dh) // 2
                g.DrawImage(src, Rectangle(dx, dy, dw, dh), Rectangle(min_x, min_y, crop_w, crop_h), GraphicsUnit.Pixel)
            finally:
                g.Dispose()
            for yy in range(out.Height):
                for xx in range(out.Width):
                    c = out.GetPixel(xx, yy)
                    lum = (int(c.R) * 299 + int(c.G) * 587 + int(c.B) * 114) // 1000
                    out.SetPixel(xx, yy, Color.Black if lum < 205 else Color.White)
            return out
        finally:
            src.Dispose()

    def _render_receipt_png_v4466(payload, show_blood_pressure=True):
        import clr  # type: ignore
        clr.AddReference("System.Drawing"); clr.AddReference("System")
        from System.IO import MemoryStream  # type: ignore
        from System.Drawing import Bitmap, Graphics, Color, Font, FontStyle, GraphicsUnit, Brushes, Pen, Rectangle, RectangleF, StringFormat, StringAlignment  # type: ignore
        from System.Drawing.Drawing2D import DashStyle, InterpolationMode, PixelOffsetMode, SmoothingMode  # type: ignore
        from System.Drawing.Text import TextRenderingHint  # type: ignore
        from System.Drawing.Imaging import ImageFormat, PixelFormat  # type: ignore

        W, H = 576, 820
        bmp = Bitmap(W, H, PixelFormat.Format24bppRgb)
        g = Graphics.FromImage(bmp); fonts = []; logo = None
        try:
            g.Clear(Color.White)
            g.TextRenderingHint = TextRenderingHint.SingleBitPerPixelGridFit
            g.InterpolationMode = InterpolationMode.NearestNeighbor
            g.PixelOffsetMode = PixelOffsetMode.Half
            g.SmoothingMode = getattr(SmoothingMode, "None")
            def font(px, bold=True):
                f = Font("Arial", float(px), FontStyle.Bold if bold else FontStyle.Regular, GraphicsUnit.Pixel); fonts.append(f); return f
            f_title=font(31); f_label=font(23); f_value=font(27); f_name_label=font(21); f_name=font(30); f_turn=font(34); f_status=font(21)
            solid=Pen(Color.Black,2.0); border=Pen(Color.Black,2.2); dotted=Pen(Color.FromArgb(80,80,80),1.5); dotted.DashStyle=DashStyle.Dot; check=Pen(Color.Black,3.0)
            outer_l,outer_r=7.0,W-7.0; inner_l,inner_r=22.0,W-22.0; inner_w=inner_r-inner_l; y=13.0
            center=StringFormat(); center.Alignment=StringAlignment.Center; center.LineAlignment=StringAlignment.Near
            logo_path=os.path.join(core.BASE_DIR,"static","doctor_isotype.png")
            if os.path.exists(logo_path):
                try:
                    logo=_thermal_logo_v4466(logo_path)
                    if logo is not None: g.DrawImage(logo,26.0,y+1.0,74.0,74.0)
                except Exception: logo=None
            g.DrawString("RECIBO DE\nCONSULTA MÉDICA",f_title,Brushes.Black,RectangleF(110.0,y+3.0,inner_r-110.0,75.0),center)
            y+=83.0; g.DrawLine(solid,inner_l,y,inner_r,y)
            def separator(): g.DrawLine(dotted,inner_l,y,inner_r,y)
            def row(label,value,value_x,vf=None,height=56.0,lf=None):
                nonlocal y
                top=y; y+=14.0; g.DrawString(str(label),lf or f_label,Brushes.Black,inner_l,y); vx=float(value_x)
                g.DrawString(str(value or ""),vf or f_value,Brushes.Black,RectangleF(vx,y-2.0,inner_r-vx,36.0)); y=top+height; separator()
            row("Fecha:",payload.fecha,235.0,f_value,55.0)
            y+=16.0; g.DrawString("Nombre",f_name_label,Brushes.Black,RectangleF(inner_l,y,inner_w,28.0),center); y+=28.0
            surname,given=_name_lines_v4466(payload.nombre)
            g.DrawString(surname,f_name,Brushes.Black,RectangleF(inner_l,y,inner_w,39.0),center); y+=39.0
            if given: g.DrawString(given,f_name,Brushes.Black,RectangleF(inner_l,y,inner_w,39.0),center); y+=39.0
            y+=12.0; g.DrawLine(solid,inner_l,y,inner_r,y)
            if bool(payload.is_new) and payload.fecha_nacimiento:
                birth_label=font(21); row("Fecha de nacimiento:",payload.fecha_nacimiento,350.0,f_value,60.0,birth_label)
            if show_blood_pressure:
                top=y; y+=15.0; g.DrawString("Presión Arterial:",f_label,Brushes.Black,inner_l,y+8.0); bw,bh=148.0,58.0
                g.DrawRectangle(solid,inner_r-bw,y,bw,bh); y=top+84.0; separator()
            row("Teléfono:",payload.celular or "Sin registrar",225.0,f_value,57.0)
            if payload.turno: row("Turno:",str(payload.turno),225.0,f_turn,62.0)
            y+=20.0; box=39.0; gap=11.0; col_gap=12.0; col_w=(inner_w-col_gap)/2.0
            def option(col_l,label,checked):
                label_w=float(g.MeasureString(label,f_status).Width); group_w=box+gap+label_w
                x=col_l+max(0.0,(col_w-group_w)/2.0); x=min(x,col_l+col_w-group_w)
                g.DrawRectangle(solid,x,y,box,box)
                if checked:
                    g.DrawLine(check,x+8.0,y+21.0,x+17.0,y+31.0); g.DrawLine(check,x+17.0,y+31.0,x+33.0,y+8.0)
                g.DrawString(label,f_status,Brushes.Black,x+box+gap,y+6.0)
            option(inner_l,"PRIMERO",bool(payload.is_new)); option(inner_l+col_w+col_gap,"SUBSECUENTE",not bool(payload.is_new))
            y+=box+24.0; final_h=int(min(H,y+13.0)); g.DrawRectangle(border,outer_l,5.0,outer_r-outer_l,final_h-10.0)
            cropped=bmp.Clone(Rectangle(0,0,W,final_h),PixelFormat.Format24bppRgb)
            try:
                ms=MemoryStream(); cropped.Save(ms,ImageFormat.Png); data=bytes(bytearray(ms.ToArray())); ms.Dispose(); return data
            finally: cropped.Dispose()
        finally:
            try: g.Dispose()
            except Exception: pass
            if logo is not None:
                try: logo.Dispose()
                except Exception: pass
            for f in fonts:
                try: f.Dispose()
                except Exception: pass
            try: bmp.Dispose()
            except Exception: pass

    def _print_receipt_windows_v4466(payload, printer_name: str = "", show_blood_pressure: bool = True) -> str:
        if os.name != "nt": raise RuntimeError("La impresión directa solo está disponible en Windows")
        import clr  # type: ignore
        clr.AddReference("System.Drawing"); clr.AddReference("System")
        from System.IO import MemoryStream  # type: ignore
        from System.Drawing import Image, RectangleF  # type: ignore
        from System.Drawing.Printing import PrintDocument, PrinterSettings, PaperSize, Margins  # type: ignore
        available=[str(name) for name in PrinterSettings.InstalledPrinters]; chosen=str(printer_name or "").strip() or str(PrinterSettings().PrinterName or "")
        if not chosen: raise RuntimeError("Windows no tiene una impresora predeterminada")
        if available and chosen not in available: raise RuntimeError(f"La impresora ‘{chosen}’ ya no está disponible")
        png=_render_receipt_png_v4466(payload,show_blood_pressure); doc=PrintDocument(); doc.PrinterSettings.PrinterName=chosen
        if not doc.PrinterSettings.IsValid: raise RuntimeError(f"Windows no puede usar la impresora ‘{chosen}’")
        doc.DocumentName="Recibo de consulta médica"; doc.OriginAtMargins=False; doc.DefaultPageSettings.PaperSize=PaperSize("Recibo 80 mm",315,700); doc.DefaultPageSettings.Margins=Margins(0,0,0,0)
        holder={"stream":None,"img":None}
        def on_print_page(sender,e):
            from System import Array, Byte  # type: ignore
            arr=Array[Byte](bytearray(png)); holder["stream"]=MemoryStream(arr); holder["img"]=Image.FromStream(holder["stream"])
            target_w=283.5; target_h=target_w*float(holder["img"].Height)/float(holder["img"].Width); x=max(0.0,(float(e.PageBounds.Width)-target_w)/2.0)
            e.Graphics.DrawImage(holder["img"],RectangleF(x,0.0,target_w,target_h)); e.HasMorePages=False
        doc.PrintPage+=on_print_page
        try: doc.Print()
        finally:
            try: doc.PrintPage-=on_print_page
            except Exception: pass
            if holder.get("img") is not None:
                try: holder["img"].Dispose()
                except Exception: pass
            if holder.get("stream") is not None:
                try: holder["stream"].Dispose()
                except Exception: pass
            try: doc.Dispose()
            except Exception: pass
        return chosen

    core._print_receipt_windows = _print_receipt_windows_v4466
    from fastapi import Response  # type: ignore
    @app.post("/api/v4466/receipt-image")
    def v4466_receipt_image(data: core.ReceiptPrintIn, user=core.Depends(core.current_user)):
        prefs=core._app_preferences(); png=_render_receipt_png_v4466(data,bool(prefs.get("show_blood_pressure",True)))
        return Response(content=png,media_type="image/png",headers={"Cache-Control":"no-store"})

    PREVIEW_JS=r"""
;(()=>{
  if(window.__v4466ReceiptRaster)return;window.__v4466ReceiptRaster=true;
  function install(){
    if(typeof window.printAttentionSlipData!=='function'||typeof window.receiptPrintPayload!=='function'){setTimeout(install,100);return;}
    const patched=async function(visit,patient,dayNumber=null){
      try{
        const payload=window.receiptPrintPayload(visit,patient,dayNumber);
        const r=await fetch('/api/v4466/receipt-image',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
        if(!r.ok)throw Error('HTTP '+r.status);const blob=await r.blob();const url=URL.createObjectURL(blob);
        document.querySelector('#receiptPrintFrame')?.remove();const frame=document.createElement('iframe');frame.id='receiptPrintFrame';frame.title='Impresión de recibo';frame.setAttribute('aria-hidden','true');
        Object.assign(frame.style,{position:'fixed',right:'-10000px',bottom:'0',width:'80mm',height:'180mm',border:'0',opacity:'0',pointerEvents:'none'});document.body.appendChild(frame);
        const doc=frame.contentDocument||frame.contentWindow?.document;if(!doc)throw Error('Sin documento de impresión');let cleaned=false;
        const cleanup=()=>{if(cleaned)return;cleaned=true;try{URL.revokeObjectURL(url)}catch{}setTimeout(()=>frame.remove(),120)};
        doc.open();doc.write(`<!doctype html><html><head><meta charset="utf-8"><style>*{box-sizing:border-box}html,body{margin:0;padding:0;background:#fff;width:80mm}body{display:flex;justify-content:center;align-items:flex-start}img{display:block;width:72mm;height:auto;margin:0;padding:0}@media print{@page{size:80mm auto;margin:0}html,body{width:80mm;margin:0;padding:0}img{width:72mm;margin:0 auto}}</style></head><body><img id="rimg" src="${url}"></body></html>`);doc.close();
        const img=doc.getElementById('rimg');const go=()=>setTimeout(()=>{try{const w=frame.contentWindow;w.addEventListener('afterprint',cleanup,{once:true});w.focus();w.print();setTimeout(cleanup,120000)}catch(e){cleanup();alert('No se pudo imprimir el recibo.')}},80);
        if(img&&!img.complete){img.addEventListener('load',go,{once:true});img.addEventListener('error',go,{once:true});setTimeout(go,800)}else go();
      }catch(e){alert('No se pudo preparar el recibo unificado. Se usará el formato anterior.');try{return window.__v4465PrintFallback?.(visit,patient,dayNumber)}catch{}}
    };
    window.__v4465PrintFallback=window.printAttentionSlipData;patched.__v4466=true;window.printAttentionSlipData=patched;
  }install();
})();
"""
    core.V460_OVERLAY_JS=(getattr(core,"V460_OVERLAY_JS","") or "")+"\n"+PREVIEW_JS
    PATCH_BOOT_OK=True
except Exception as exc:
    PATCH_BOOT_ERROR=f"{type(exc).__name__}: {exc}"
    try: core.logging.getLogger(__name__).error("v4.4.66 receipt patch failed: %s",PATCH_BOOT_ERROR)
    except Exception: pass

@app.get("/api/v4466/receipt-health")
def v4466_receipt_health(user=core.Depends(core.current_user)):
    return {"ok":PATCH_BOOT_OK,"version":APP_VERSION,"error":PATCH_BOOT_ERROR,"same_raster_for_preview_and_direct":True,"thermal_width_px":576,"thermal_width_mm":72,"logo_cropped_monochrome":True}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app,host="0.0.0.0",port=core.LOCAL_HTTP_PORT,reload=False,access_log=False,log_level="warning",workers=1)

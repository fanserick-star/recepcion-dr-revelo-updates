from __future__ import annotations
import reception_billing_optional_email as _dep_billing_optional_email
import os as _os
import re as _re
from datetime import date as _date, datetime as _datetime
core = _dep_billing_optional_email.core
app = _dep_billing_optional_email.app
APP_VERSION = '4.4.85'
core.APP_VERSION = APP_VERSION
PATCH_BOOT_OK = False
PATCH_BOOT_ERROR = ''
HOME_BUTTON_PATCHED = False
_PAYMENT_SENTINELS = {-442901: 'EFECTIVO', -442920: 'TRANSFERENCIA BANCARIA'}

def _payment_method_for_visits(visits) -> str:
    methods = set()
    for visit in visits:
        try:
            source_row = int(getattr(visit, 'source_row', 0) or 0)
        except Exception:
            source_row = 0
        method = _PAYMENT_SENTINELS.get(source_row)
        if method:
            methods.add(method)
    if len(methods) == 1:
        return next(iter(methods))
    if len(methods) > 1:
        return 'PAGO MIXTO'
    return 'NO REGISTRADA'

def _payment_proof_lines(visits) -> list[tuple[str, float]]:
    lines: list[tuple[str, float]] = []
    for visit in visits:
        desc = ' '.join(str(getattr(visit, 'procedimiento', None) or '').split())
        if not desc:
            desc = 'CONSULTA MÉDICA'
        try:
            value = round(float(getattr(visit, 'valor', 0) or 0), 2)
        except Exception:
            value = 0.0
        lines.append((desc.upper(), value))
    return lines

def _print_payment_proof_windows(*, patient_name: str, proof_ref: str, service_date: _date, lines: list[tuple[str, float]], payment_method: str, printer_name: str='') -> str:
    if _os.name != 'nt':
        raise RuntimeError('La impresión directa solo está disponible en Windows')
    import clr
    clr.AddReference('System.Drawing')
    from System.Drawing import Font, FontStyle, Brushes, Pen, Image, Color, StringFormat, StringAlignment, RectangleF
    from System.Drawing.Printing import PrintDocument, PrinterSettings, PaperSize, Margins
    available = [str(name) for name in PrinterSettings.InstalledPrinters]
    chosen = str(printer_name or '').strip() or str(PrinterSettings().PrinterName or '').strip()
    if not chosen:
        raise RuntimeError('Windows no tiene una impresora predeterminada')
    if available and chosen not in available:
        raise RuntimeError(f'La impresora ‘{chosen}’ ya no está disponible')
    doc = PrintDocument()
    doc.PrinterSettings.PrinterName = chosen
    if not doc.PrinterSettings.IsValid:
        raise RuntimeError(f'Windows no puede usar la impresora ‘{chosen}’')
    estimated_h = 410 + max(0, len(lines) - 1) * 34
    doc.DocumentName = 'Comprobante de pago'
    doc.OriginAtMargins = True
    doc.DefaultPageSettings.PaperSize = PaperSize('Comprobante 80 mm', 315, max(430, min(950, int(estimated_h))))
    doc.DefaultPageSettings.Margins = Margins(10, 10, 6, 6)
    fonts = []
    image_holder = {'img': None}

    def font(size: float, bold: bool=False):
        f = Font('Arial', float(size), FontStyle.Bold if bold else FontStyle.Regular)
        fonts.append(f)
        return f
    f_doctor = font(9.4, True)
    f_specialty = font(7.0, False)
    f_title = font(11.4, True)
    f_ref = font(7.2, True)
    f_label = font(7.2, True)
    f_text = font(8.3, False)
    f_name = font(10.2, True)
    f_item = font(7.8, False)
    f_item_bold = font(7.8, True)
    f_total_label = font(9.4, True)
    f_total = font(14.2, True)
    f_paid = font(12.0, True)
    f_footer = font(6.5, False)
    pen = Pen(Color.Black, 1.0)
    center = StringFormat()
    center.Alignment = StringAlignment.Center
    center.LineAlignment = StringAlignment.Near
    right = StringFormat()
    right.Alignment = StringAlignment.Far
    right.LineAlignment = StringAlignment.Near

    def draw_line(g, y, width):
        g.DrawLine(pen, 0.0, float(y), float(width), float(y))

    def on_print_page(sender, e):
        g = e.Graphics
        width = float(e.MarginBounds.Width)
        y = 0.0
        logo_path = _os.path.join(str(core.BASE_DIR), 'static', 'doctor_isotype.png')
        if _os.path.exists(logo_path):
            try:
                image_holder['img'] = Image.FromFile(logo_path)
                g.DrawImage(image_holder['img'], 0.0, 1.0, 38.0, 38.0)
            except Exception:
                image_holder['img'] = None
        title_x = 42.0 if image_holder['img'] is not None else 0.0
        title_w = width - title_x
        g.DrawString('DR. ARMANDO REVELO', f_doctor, Brushes.Black, RectangleF(title_x, 2.0, title_w, 15.0), center)
        g.DrawString('CIRUJANO URÓLOGO', f_specialty, Brushes.Black, RectangleF(title_x, 18.0, title_w, 13.0), center)
        y = 43.0
        draw_line(g, y, width)
        y += 9.0
        g.DrawString('COMPROBANTE DE PAGO', f_title, Brushes.Black, RectangleF(0.0, y, width, 19.0), center)
        y += 21.0
        g.DrawString(f'REF. {proof_ref}', f_ref, Brushes.Black, RectangleF(0.0, y, width, 13.0), center)
        y += 18.0
        draw_line(g, y, width)
        y += 8.0
        printed_time = _datetime.now().strftime('%H:%M')
        g.DrawString('Fecha:', f_label, Brushes.Black, 0.0, y)
        g.DrawString(service_date.strftime('%d/%m/%Y'), f_text, Brushes.Black, 49.0, y - 1.0)
        g.DrawString('Hora:', f_label, Brushes.Black, width - 95.0, y)
        g.DrawString(printed_time, f_text, Brushes.Black, width - 56.0, y - 1.0)
        y += 22.0
        g.DrawString('PACIENTE', f_label, Brushes.Black, RectangleF(0.0, y, width, 13.0), center)
        y += 13.0
        name = ' '.join(str(patient_name or 'SIN NOMBRE').split()).upper()
        measured = g.MeasureString(name, f_name, int(width))
        name_h = max(24.0, min(46.0, float(measured.Height) + 4.0))
        g.DrawString(name, f_name, Brushes.Black, RectangleF(0.0, y, width, name_h), center)
        y += name_h + 3.0
        draw_line(g, y, width)
        y += 8.0
        g.DrawString('CONCEPTO', f_label, Brushes.Black, 0.0, y)
        g.DrawString('VALOR', f_label, Brushes.Black, RectangleF(width - 74.0, y, 74.0, 14.0), right)
        y += 16.0
        for desc, value in lines:
            item_rect = RectangleF(0.0, y, width - 78.0, 40.0)
            size = g.MeasureString(str(desc), f_item, int(width - 78.0))
            item_h = max(18.0, min(38.0, float(size.Height) + 2.0))
            g.DrawString(str(desc), f_item, Brushes.Black, item_rect)
            g.DrawString(f'${float(value):.2f}', f_item_bold, Brushes.Black, RectangleF(width - 75.0, y, 75.0, 18.0), right)
            y += item_h + 3.0
        draw_line(g, y, width)
        total = round(sum((float(value or 0) for _desc, value in lines)), 2)
        y += 9.0
        g.DrawString('TOTAL PAGADO', f_total_label, Brushes.Black, 0.0, y + 3.0)
        g.DrawString(f'${total:.2f}', f_total, Brushes.Black, RectangleF(width - 110.0, y, 110.0, 24.0), right)
        y += 30.0
        g.DrawString('Forma de pago:', f_label, Brushes.Black, 0.0, y)
        y += 14.0
        g.DrawString(str(payment_method or 'NO REGISTRADA'), f_item_bold, Brushes.Black, RectangleF(0.0, y, width, 18.0), center)
        y += 24.0
        draw_line(g, y, width)
        y += 10.0
        g.DrawString('PAGADO', f_paid, Brushes.Black, RectangleF(0.0, y, width, 22.0), center)
        y += 26.0
        g.DrawString('Gracias por su confianza.', f_item_bold, Brushes.Black, RectangleF(0.0, y, width, 16.0), center)
        y += 20.0
        g.DrawString('Comprobante interno de pago.\nNo reemplaza la factura electrónica.', f_footer, Brushes.Black, RectangleF(0.0, y, width, 30.0), center)
        e.HasMorePages = False
    doc.PrintPage += on_print_page
    try:
        doc.Print()
    finally:
        try:
            doc.PrintPage -= on_print_page
        except Exception:
            pass
        if image_holder.get('img') is not None:
            try:
                image_holder['img'].Dispose()
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
            right.Dispose()
        except Exception:
            pass
        try:
            doc.Dispose()
        except Exception:
            pass
    return chosen

@app.post('/api/v4485/payment-proof/{patient_id}/{fecha}')
def v4485_print_payment_proof(patient_id: int, fecha: str, db=core.Depends(core.get_db), user=core.Depends(core.current_user)):
    try:
        target_date = _date.fromisoformat(str(fecha or '')[:10])
    except Exception:
        raise core.HTTPException(400, 'Fecha inválida para el comprobante')
    patient = db.get(core.Patient, int(patient_id))
    if not patient:
        raise core.HTTPException(404, 'Paciente no encontrado')
    visits = list(db.scalars(core.select(core.Visit).where(core.Visit.patient_id == int(patient_id), core.Visit.fecha == target_date).order_by(core.Visit.id.asc())))
    if not visits:
        raise core.HTTPException(404, 'No hay atenciones registradas para ese paciente en esa fecha')
    lines = _payment_proof_lines(visits)
    total = round(sum((value for _desc, value in lines)), 2)
    if total <= 0:
        raise core.HTTPException(400, 'No hay un valor pagado para imprimir el comprobante')
    first_id = min((abs(int(getattr(v, 'id', 0) or 0)) for v in visits))
    proof_ref = f'CP-{first_id:06d}'
    payment_method = _payment_method_for_visits(visits)
    prefs = core._app_preferences()
    printer = str(prefs.get('printer') or '').strip()
    try:
        used = _print_payment_proof_windows(patient_name=str(getattr(patient, 'nombre', '') or '').strip(), proof_ref=proof_ref, service_date=target_date, lines=lines, payment_method=payment_method, printer_name=printer)
    except Exception as exc:
        raise core.HTTPException(500, f'No se pudo imprimir el comprobante: {exc}')
    return {'ok': True, 'printed': True, 'printer': used, 'reference': proof_ref, 'patient_id': int(patient_id), 'fecha': target_date.isoformat(), 'total': total, 'payment_method': payment_method, 'message': 'Comprobante de pago enviado a la impresora.'}
try:
    _js = getattr(core, 'V460_OVERLAY_JS', '') or ''
    _old_tail = '${homeMore(primary)}</div>`}'
    _new_tail = '<button type="button" class="v4485-payment-proof" onclick="printPaymentProofFromHome(${pid},\'${eh(fecha)}\')">${homeActionIcon(\'receipt\')}<span>Comprobante</span></button>${homeMore(primary)}</div>`}'
    if _old_tail in _js:
        _js = _js.replace(_old_tail, _new_tail, 1)
        HOME_BUTTON_PATCHED = True
    _js = _re.sub('const\\s+VERSION\\s*=\\s*[\'\\"]4\\.4\\.\\d+[\'\\"]\\s*;', "const VERSION='4.4.85';", _js)
    _js = _re.sub('const\\s+V\\s*=\\s*[\'\\"]4\\.4\\.\\d+[\'\\"]\\s*;', "const V='4.4.85';", _js)
    V4485_CSS = '\n.v4485-payment-proof{\n  border-color:#b8d7c4!important;\n  background:#f2fbf5!important;\n  color:#2f6e49!important;\n}\n.v4485-payment-proof:hover{background:#e5f6eb!important}\n.v4485-pay-toast{\n  position:fixed;right:18px;bottom:18px;z-index:2147483600;\n  max-width:390px;padding:11px 14px;border-radius:11px;\n  background:#225f42;color:#fff;box-shadow:0 10px 30px rgba(25,62,45,.22);\n  font-size:11px;font-weight:850\n}\n.v460-version,#currentVersionBadge{font-size:0!important}\n.v460-version::after,#currentVersionBadge::after{\n  content:"v4.4.85"!important;font-size:9px!important;line-height:1!important;font-weight:850!important\n}\n'
    V4485_JS = "\n;(()=>{\n  if(window.__v4485PaymentProof)return;\n  window.__v4485PaymentProof=true;\n  const VERSION='4.4.85';\n\n  function toast(msg){\n    document.querySelector('.v4485-pay-toast')?.remove();\n    const el=document.createElement('div');\n    el.className='v4485-pay-toast';\n    el.textContent=String(msg||'Comprobante enviado a la impresora.');\n    document.body.appendChild(el);\n    setTimeout(()=>el.remove(),4200);\n  }\n\n  window.printPaymentProofFromHome=async function(patientId,fecha){\n    const id=Number(patientId||0),day=String(fecha||'').slice(0,10);\n    if(!id||!day)return;\n    const buttons=[...document.querySelectorAll('.v4485-payment-proof')];\n    buttons.forEach(b=>b.disabled=true);\n    try{\n      const r=await fetch(`/api/v4485/payment-proof/${id}/${encodeURIComponent(day)}`,{\n        method:'POST',credentials:'same-origin',\n        headers:{'Content-Type':'application/json'},\n        body:'{}',\n        cache:'no-store'\n      });\n      const d=await r.json().catch(()=>({}));\n      if(!r.ok||d.ok===false)throw new Error(d.detail||d.message||'No se pudo imprimir el comprobante.');\n      toast(`✓ ${d.message||'Comprobante de pago enviado a la impresora.'}`);\n    }catch(e){\n      alert(e?.message||String(e));\n    }finally{\n      buttons.forEach(b=>b.disabled=false);\n    }\n  };\n\n  function paint(){\n    document.querySelectorAll('.v460-version,#currentVersionBadge').forEach(el=>{\n      el.textContent='v'+VERSION;el.setAttribute('data-version','v'+VERSION);\n    });\n  }\n  paint();\n  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',paint,{once:true});\n  setTimeout(paint,250);setTimeout(paint,900);\n})();\n"
    core.V460_OVERLAY_CSS = (getattr(core, 'V460_OVERLAY_CSS', '') or '') + '\n' + V4485_CSS
    core.V460_OVERLAY_JS = _js + '\n' + V4485_JS
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f'{type(exc).__name__}: {exc}'

@app.get('/api/v4485/health')
def v4485_health(user=core.Depends(core.current_user)):
    return {'ok': PATCH_BOOT_OK, 'version': APP_VERSION, 'error': PATCH_BOOT_ERROR, 'payment_proof': True, 'home_button_patched': HOME_BUTTON_PATCHED, 'automatic_print': False, 'database_changes': False, 'neon_writes_added': False, 'billing_changes': False, 'receipt_layout_version': '4.4.69'}
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=core.LOCAL_HTTP_PORT, reload=False, access_log=False, log_level='warning', workers=1)

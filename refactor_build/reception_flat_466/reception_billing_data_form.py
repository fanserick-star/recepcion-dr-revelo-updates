from __future__ import annotations
from runtime_registry import layers as _rf_layers, module_lookup as _rf_module_lookup

import os as _os
import re as _re
previous = _rf_layers['app_patch_4488']
core = previous.core
app = previous.app
APP_VERSION = '4.4.89'
_mod = previous
_seen = set()
for _ in range(84):
    if _mod is None or id(_mod) in _seen:
        break
    _seen.add(id(_mod))
    try:
        _mod.APP_VERSION = APP_VERSION
    except Exception:
        pass
    _mod = getattr(_mod, 'previous', None)
core.APP_VERSION = APP_VERSION
PATCH_BOOT_OK = False
PATCH_BOOT_ERROR = ''

def _print_billing_data_form_windows(printer_name: str='') -> str:
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
    doc.DocumentName = 'Datos para factura'
    doc.OriginAtMargins = True
    doc.DefaultPageSettings.PaperSize = PaperSize('Formulario factura 80 mm', 315, 600)
    doc.DefaultPageSettings.Margins = Margins(10, 10, 6, 6)
    fonts = []
    image_holder = {'img': None}

    def font(size: float, bold: bool=False):
        f = Font('Arial', float(size), FontStyle.Bold if bold else FontStyle.Regular)
        fonts.append(f)
        return f
    f_doctor = font(9.4, True)
    f_specialty = font(7.0, False)
    f_title = font(11.0, True)
    f_intro = font(7.2, False)
    f_label = font(7.5, True)
    f_note = font(6.4, False)
    f_footer = font(7.0, True)
    pen = Pen(Color.Black, 1.0)
    center = StringFormat()
    center.Alignment = StringAlignment.Center
    center.LineAlignment = StringAlignment.Near

    def draw_line(g, y, width, x1=0.0, x2=None):
        g.DrawLine(pen, float(x1), float(y), float(width if x2 is None else x2), float(y))

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
        y += 10.0
        g.DrawString('DATOS PARA FACTURA', f_title, Brushes.Black, RectangleF(0.0, y, width, 20.0), center)
        y += 25.0
        g.DrawString('Complete los datos de la persona o empresa\na quien desea facturar.', f_intro, Brushes.Black, RectangleF(0.0, y, width, 30.0), center)
        y += 34.0
        draw_line(g, y, width)

        def field(label: str, lines: int=1, note: str=''):
            nonlocal y
            y += 10.0
            g.DrawString(label, f_label, Brushes.Black, 0.0, y)
            if note:
                g.DrawString(note, f_note, Brushes.Black, RectangleF(0.0, y + 12.0, width, 12.0))
                y += 13.0
            y += 18.0
            for _ in range(lines):
                draw_line(g, y, width - 4.0, 0.0, width - 4.0)
                y += 21.0
        field('CÉDULA / RUC:')
        field('NOMBRES / RAZÓN SOCIAL:', 2)
        field('DIRECCIÓN:', 2)
        field('TELÉFONO:')
        field('CORREO:', 2, '(OPCIONAL)')
        y += 2.0
        draw_line(g, y, width)
        y += 12.0
        g.DrawString('ENTREGAR EN RECEPCIÓN', f_footer, Brushes.Black, RectangleF(0.0, y, width, 18.0), center)
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
        except Exception:
            pass
        try:
            doc.Dispose()
        except Exception:
            pass
    return chosen

@app.post('/api/v4489/print-billing-data-form')
def v4489_print_billing_data_form(user=core.Depends(core.current_user)):
    prefs = core._app_preferences()
    printer = str(prefs.get('printer') or '').strip()
    try:
        used = _print_billing_data_form_windows(printer)
    except Exception as exc:
        raise core.HTTPException(500, f'No se pudo imprimir el formulario: {exc}')
    return {'ok': True, 'printed': True, 'printer': used, 'message': 'Formulario para datos de factura enviado a la impresora.'}
try:
    _js = getattr(core, 'V460_OVERLAY_JS', '') or ''
    _js = _re.sub('const\\s+VERSION\\s*=\\s*[\'\\"]4\\.4\\.\\d+[\'\\"]\\s*;', "const VERSION='4.4.89';", _js)
    _js = _re.sub('const\\s+V\\s*=\\s*[\'\\"]4\\.4\\.\\d+[\'\\"]\\s*;', "const V='4.4.89';", _js)
    V4489_CSS = '\n.v4489-billing-form-print{\n  margin-top:10px;padding:10px 11px;border:1px dashed #b8cbe0;border-radius:10px;\n  background:#f7fbff;display:flex;align-items:center;justify-content:space-between;gap:10px\n}\n.v4489-billing-form-print div{min-width:0}\n.v4489-billing-form-print b{display:block;font-size:10px;color:#334f70;margin-bottom:2px}\n.v4489-billing-form-print small{display:block;font-size:8px;line-height:1.3;color:#70839a}\n.v4489-billing-form-print button{\n  flex:0 0 auto;border:1px solid #b9cee4;background:#fff;color:#355f88;border-radius:8px;\n  padding:7px 9px;font-size:9px;font-weight:850;cursor:pointer\n}\n.v4489-billing-form-print button:hover{background:#edf5ff}\n.v4489-billing-form-print button:disabled{opacity:.55;cursor:wait}\n.v460-version,#currentVersionBadge{font-size:0!important}\n.v460-version::after,#currentVersionBadge::after{\n  content:"v4.4.89"!important;font-size:9px!important;line-height:1!important;font-weight:850!important\n}\n'
    V4489_JS = '\n;(()=>{\n  if(window.__v4489BillingDataForm)return;\n  window.__v4489BillingDataForm=true;\n  const VERSION=\'4.4.89\';\n\n  async function printBillingDataForm(btn){\n    if(btn)btn.disabled=true;\n    try{\n      const r=await fetch(\'/api/v4489/print-billing-data-form\',{\n        method:\'POST\',\n        credentials:\'same-origin\',\n        headers:{\'Content-Type\':\'application/json\'},\n        body:\'{}\',\n        cache:\'no-store\'\n      });\n      const d=await r.json().catch(()=>({}));\n      if(!r.ok||d.ok===false)throw new Error(d.detail||d.message||\'No se pudo imprimir el formulario.\');\n      const old=btn?.textContent;\n      if(btn){btn.textContent=\'✓ Enviado\';setTimeout(()=>{btn.textContent=old||\'Imprimir formulario\';},1600)}\n    }catch(e){\n      alert(e?.message||String(e));\n    }finally{\n      if(btn)btn.disabled=false;\n    }\n  }\n  window.printBillingDataForm=printBillingDataForm;\n\n  function inject(){\n    const alt=document.querySelector(\'#billingRecipientAlt\');\n    if(!alt||alt.querySelector(\'.v4489-billing-form-print\'))return;\n    const help=alt.querySelector(\'.billing-recipient-help\');\n    const box=document.createElement(\'div\');\n    box.className=\'v4489-billing-form-print\';\n    box.innerHTML=\'<div><b>¿El paciente llenará otros datos?</b><small>Imprime una hoja térmica para que escriba los datos de facturación.</small></div><button type="button">🖨 Imprimir formulario</button>\';\n    box.querySelector(\'button\')?.addEventListener(\'click\',function(){printBillingDataForm(this)});\n    if(help)alt.insertBefore(box,help);else alt.appendChild(box);\n  }\n\n  const oldOpen=window.openBillingRecipientEditor;\n  if(typeof oldOpen===\'function\'&&!oldOpen.__v4489){\n    const wrapped=async function(){\n      const r=await oldOpen.apply(this,arguments);\n      setTimeout(inject,0);setTimeout(inject,70);\n      return r;\n    };\n    wrapped.__v4489=true;\n    window.openBillingRecipientEditor=wrapped;\n  }\n\n  function paint(){\n    document.querySelectorAll(\'.v460-version,#currentVersionBadge\').forEach(el=>{\n      el.textContent=\'v\'+VERSION;el.setAttribute(\'data-version\',\'v\'+VERSION);\n    });\n  }\n  paint();\n  if(document.readyState===\'loading\')document.addEventListener(\'DOMContentLoaded\',paint,{once:true});\n  setTimeout(paint,250);setTimeout(paint,900);\n})();\n'
    core.V460_OVERLAY_CSS = (getattr(core, 'V460_OVERLAY_CSS', '') or '') + '\n' + V4489_CSS
    core.V460_OVERLAY_JS = _js + '\n' + V4489_JS
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f'{type(exc).__name__}: {exc}'

@app.get('/api/v4489/health')
def v4489_health(user=core.Depends(core.current_user)):
    return {'ok': PATCH_BOOT_OK, 'version': APP_VERSION, 'error': PATCH_BOOT_ERROR, 'billing_data_form': True, 'only_in_alternate_recipient_ui': True, 'database_changes': False, 'neon_writes_added': False, 'billing_changes': False, 'receipt_layout_version': '4.4.69'}
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=core.LOCAL_HTTP_PORT, reload=False, access_log=False, log_level='warning', workers=1)

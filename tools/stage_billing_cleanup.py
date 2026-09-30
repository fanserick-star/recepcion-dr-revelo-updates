from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "recepcion" / "app"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def regex_once(text: str, pattern: str, repl: str, label: str, flags: int = 0) -> str:
    out, count = re.subn(pattern, repl, text, count=1, flags=flags)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one regex match, found {count}")
    return out


# ---------------------------------------------------------------------------
# 1) Make the canonical frontend own the final billing behaviour directly.
# ---------------------------------------------------------------------------
app_js_path = APP / "static" / "app.js"
js = read(app_js_path)

js = replace_once(
    js,
    "let billingGroupsCache=[];\nlet billingPreferencesCache={};",
    "let billingGroupsCache=[];\nlet billingPreferencesCache={};\nlet billingViewState='PENDIENTE';",
    "billing view state",
)

js = replace_once(
    js,
    "const EXTERNAL_APP_URLS={\n  confirmafy:'https://confirmafy.com/app/calendar',\n  facturero:'https://app.factureromovil.com/documentos/facturas'\n};",
    "const EXTERNAL_APP_URLS={\n  confirmafy:'https://confirmafy.com/app/calendar'\n};",
    "remove Facturero destination",
)

js = regex_once(
    js,
    r"function billingMissingFields\(p=\{\}\)\{\s*const out=\[\];if\(!String\(p\.cedula\|\|''\)\.trim\(\)\)out\.push\('cédula'\);if\(!String\(p\.correo\|\|''\)\.trim\(\)\)out\.push\('correo'\);return out;\s*\}",
    "function billingMissingFields(p={}){\n  const out=[];if(!String(p.cedula||'').trim())out.push('cédula');return out;\n}",
    "optional billing email source",
)

js = replace_once(
    js,
    "missingPatientFields(p).filter(x=>['cédula','correo'].includes(x))",
    "missingPatientFields(p).filter(x=>['cédula'].includes(x))",
    "review next optional email",
)

js = replace_once(
    js,
    "if(!email.includes('@'))throw Error('Ingresa un correo válido.');",
    "if(email&&!email.includes('@'))throw Error('Ingresa un correo válido.');",
    "alternate recipient optional email",
)

js = replace_once(
    js,
    '<label>Correo</label><input id="brEmail" type="email"',
    '<label>Correo (opcional)</label><input id="brEmail" type="email"',
    "alternate recipient optional email label",
)

# Data form is now a first-class source feature instead of a post-render overlay.
insert_before = "async function openBillingRecipientEditor(patientId,fecha=null){"
printer_fn = """async function printBillingDataForm(button=null){
  const old=button?.textContent||'';
  if(button){button.disabled=true;button.textContent='Enviando…'}
  try{
    const out=await api('/api/billing/print-data-form',{method:'POST',body:'{}'});
    if(button){button.textContent='✓ Enviado';setTimeout(()=>{if(button.isConnected){button.textContent=old||'Imprimir formulario';button.disabled=false}},1300)}
    return out;
  }catch(e){if(button){button.disabled=false;button.textContent=old||'Imprimir formulario'}alert(e.message||String(e));return null}
}
"""
if printer_fn.strip() not in js:
    js = replace_once(js, insert_before, printer_fn + insert_before, "billing data form source function")

js = replace_once(
    js,
    '<div class="billing-recipient-help">Esta preferencia se guardará en la base y la respetarán tanto la emisión individual como “Emitir todas”.</div>',
    '<div class="billing-data-form-actions"><div><b>¿El paciente llenará otros datos?</b><small>Imprime una hoja térmica para completar los datos de facturación.</small></div><button type="button" onclick="printBillingDataForm(this)">🖨 Imprimir formulario</button></div><div class="billing-recipient-help">Esta preferencia se guardará en la base y la respetarán tanto la emisión individual como “Emitir todas”.</div>',
    "billing data form source button",
)

# No hidden DOM input is the authority for the billing view any more.
js = replace_once(
    js,
    "const estado=$('#bEstado')?.value||'PENDIENTE';",
    "const estado=billingViewState||'PENDIENTE';",
    "billing state read",
)
js = replace_once(
    js,
    "async function setBillingStatus(state){\n  if($('#bEstado'))$('#bEstado').value=state;await loadBilling();\n}",
    "async function setBillingStatus(state){\n  billingViewState=String(state||'PENDIENTE').toUpperCase();await loadBilling();\n}",
    "billing state write",
)

# Render discard action directly in the card source; no decorator/wrapper needed.
js = replace_once(
    js,
    "  const recipientButton=`<button onclick=\"openBillingRecipientEditor(${g.patient.id},'${g.fecha}')\">👤 ${alt?.alternate?'Editar datos de factura':'Facturar con otros datos'}</button>`;",
    "  const recipientButton=`<button onclick=\"openBillingRecipientEditor(${g.patient.id},'${g.fecha}')\">👤 ${alt?.alternate?'Editar datos de factura':'Facturar con otros datos'}</button>`;\n  const discardButton=`<button class=\"billing-discard\" onclick=\"discardPendingBilling(${g.patient.id},'${g.fecha}',event)\">🗑 Quitar de Por emitir</button>`;",
    "billing discard source button",
)
js = replace_once(
    js,
    "actions=alt?.alternate?`${recipientButton}${approve}`:(missing.length?`<button class=\"complete-patient-list-btn\" onclick=\"editPatientFromBilling(${g.patient.id})\">✎ Completar datos</button>${recipientButton}`:`${recipientButton}${approve}`);",
    "actions=alt?.alternate?`${discardButton}${recipientButton}${approve}`:(missing.length?`${discardButton}<button class=\"complete-patient-list-btn\" onclick=\"editPatientFromBilling(${g.patient.id})\">✎ Completar datos</button>${recipientButton}`:`${discardButton}${recipientButton}${approve}`);",
    "pending discard action",
)
js = replace_once(
    js,
    "actions=`${recipientButton}<button class=\"primary\" onclick=\"previewAzurInvoice(${g.patient.id},'${g.fecha}')\">⚡ Emitir en AZUR</button><button onclick=\"reopenBilling(${g.patient.id},'${g.fecha}')\">Volver a pendiente</button><button onclick=\"markBillingEmitted(${g.patient.id},'${g.fecha}')\">Marcar emitida manualmente</button>`;",
    "actions=`${discardButton}${recipientButton}<button class=\"primary\" onclick=\"previewAzurInvoice(${g.patient.id},'${g.fecha}')\">⚡ Emitir en AZUR</button><button onclick=\"reopenBilling(${g.patient.id},'${g.fecha}')\">Volver a pendiente</button><button onclick=\"markBillingEmitted(${g.patient.id},'${g.fecha}')\">Marcar emitida manualmente</button>`;",
    "approved discard action",
)

# Facturero Móvil is no longer part of the product. Remove the last source button.
js, facturero_buttons = re.subn(
    r'<button class="external-billing-link" onclick="openExternalApp\(\\\'facturero\\\'\)">Abrir Facturero Móvil ↗</button>',
    '',
    js,
)
if facturero_buttons != 1:
    raise RuntimeError(f"Facturero source button: expected 1 removal, found {facturero_buttons}")

write(app_js_path, js)

style_path = APP / "static" / "style.css"
style = read(style_path)
style_block = """

/* Facturación consolidada: acciones nativas, sin decoradores de parches. */
#facturacion .billing-discard{border:1px solid #dfb4b4;background:#fff6f6;color:#963d3d}
#facturacion .billing-discard:hover{background:#fdecec;border-color:#cf8f8f}
.billing-data-form-actions{margin-top:10px;padding:10px 11px;border:1px dashed #b8cbe0;border-radius:10px;background:#f7fbff;display:flex;align-items:center;justify-content:space-between;gap:10px}
.billing-data-form-actions>div{min-width:0}.billing-data-form-actions b{display:block;font-size:10px;color:#334f70;margin-bottom:2px}.billing-data-form-actions small{display:block;font-size:8px;line-height:1.3;color:#70839a}.billing-data-form-actions button{flex:0 0 auto}
"""
if "Facturación consolidada: acciones nativas" not in style:
    style += style_block
write(style_path, style)


# ---------------------------------------------------------------------------
# 2) Consolidate discard into one implementation (backend + one tiny function).
# ---------------------------------------------------------------------------
discard = r'''from __future__ import annotations

from datetime import date as _date
import core_runtime as core

app = core.app
APP_VERSION = getattr(core, "APP_VERSION", "")
PATCH_BOOT_OK = False
PATCH_BOOT_ERROR = ""


class DiscardBillingIn(core.BaseModel):
    patient_id: int
    fecha: _date


_stable_billing_group_records = core.billing_group_records


def _billing_group_records_without_discarded(db, patient_id: int, fecha):
    rows = _stable_billing_group_records(db, int(patient_id), fecha)
    return [
        (billing, visit)
        for billing, visit in rows
        if str(getattr(billing, "estado", "") or "").upper() != "DESCARTADA"
    ]


core.billing_group_records = _billing_group_records_without_discarded


@app.post("/api/billing/discard")
def discard_pending_billing(
    data: DiscardBillingIn,
    db=core.Depends(core.get_db),
    user=core.Depends(core.current_user),
):
    if core.is_offline_db(db):
        raise core.HTTPException(503, "Quitar una factura de Por emitir requiere conexión a Internet.")
    patient = db.get(core.Patient, int(data.patient_id))
    if not patient:
        raise core.HTTPException(404, "Paciente no encontrado")
    rows = _stable_billing_group_records(db, int(data.patient_id), data.fecha)
    rows = [
        (billing, visit)
        for billing, visit in rows
        if str(getattr(billing, "estado", "") or "").upper() in {"PENDIENTE", "APROBADA"}
    ]
    if not rows:
        raise core.HTTPException(404, "Esta factura ya no está en Por emitir.")
    group_key = core._azur_group_key_for_rows(int(data.patient_id), data.fecha, rows)
    emission = db.scalar(core.select(core.AzurEmission).where(core.AzurEmission.group_key == group_key))
    if emission and (
        str(getattr(emission, "clave_acceso", "") or "").strip()
        or str(getattr(emission, "numero_factura", "") or "").strip()
    ):
        raise core.HTTPException(409, "Esta factura ya fue enviada a AZUR y no puede eliminarse de Por emitir.")
    touched = []
    for billing, _visit in rows:
        billing.estado = "DESCARTADA"
        billing.approved_at = None
        billing.numero_factura = None
        billing.emitted_at = None
        touched.append(billing)
    core.audit(
        db,
        user,
        "descartar_factura_pendiente",
        f"Paciente {int(data.patient_id)}, fecha {data.fecha}, líneas {len(touched)}",
    )
    db.commit()
    for billing in touched:
        try:
            core.mirror_billing_to_local(billing)
        except Exception:
            pass
    return {
        "ok": True,
        "patient_id": int(data.patient_id),
        "fecha": data.fecha.isoformat(),
        "discarded": len(touched),
        "message": "Factura quitada de Por emitir. La atención y el paciente se conservaron.",
    }


BILLING_DISCARD_JS = r''';(()=>{
 if(window.__billingDiscardCanonical)return;window.__billingDiscardCanonical=true;
 window.discardPendingBilling=async function(patientId,fecha,event){
   try{event?.preventDefault?.();event?.stopPropagation?.()}catch(_e){}
   const msg='¿Quitar esta factura de Por emitir?\n\nLa atención y el paciente NO se borrarán. Solo desaparecerá de la cola de facturación.\n\nSi ya fue enviada a AZUR, el sistema no permitirá quitarla.';
   const ok=typeof window.rpConfirm==='function'?await window.rpConfirm(msg,'Quitar de Por emitir'):window.confirm(msg);
   if(!ok)return;
   try{
     const fn=window.api;if(typeof fn!=='function')throw new Error('API no disponible');
     const out=await fn('/api/billing/discard',{method:'POST',body:JSON.stringify({patient_id:Number(patientId),fecha:String(fecha||'').slice(0,10)})});
     if(typeof window.loadBilling==='function')await window.loadBilling();
     try{if(typeof window.refreshPendingBadges==='function')await window.refreshPendingBadges()}catch(_e){}
     const message=out?.message||'Factura quitada de Por emitir.';
     if(typeof window.rpNotice==='function')window.rpNotice(message);else alert(message);
   }catch(e){alert(e?.message||String(e))}
 };
})();'''

try:
    core.V460_OVERLAY_JS = (getattr(core, "V460_OVERLAY_JS", "") or "") + "\n" + BILLING_DISCARD_JS
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f"{type(exc).__name__}: {exc}"


@app.get("/api/billing/discard/health")
def billing_discard_health(user=core.Depends(core.current_user)):
    return {
        "ok": PATCH_BOOT_OK,
        "version": APP_VERSION,
        "error": PATCH_BOOT_ERROR,
        "canonical": True,
        "post_render_decorator": False,
        "version_painter": False,
    }
'''
write(APP / "reception_billing_discard.py", discard)


# ---------------------------------------------------------------------------
# 3) Data form: one final backend implementation, no patch-over-patch rendering.
# ---------------------------------------------------------------------------
data_form = r'''from __future__ import annotations

import os as _os
import core_runtime as core

app = core.app
APP_VERSION = getattr(core, "APP_VERSION", "")


def _print_billing_data_form_windows(printer_name: str = "") -> str:
    if _os.name != "nt":
        raise RuntimeError("La impresión directa solo está disponible en Windows")
    import clr
    clr.AddReference("System.Drawing")
    from System.Drawing import Font, FontStyle, Brushes, Pen, Image, Color, StringFormat, StringAlignment, RectangleF
    from System.Drawing.Printing import PrintDocument, PrinterSettings, PaperSize, Margins

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
        item = Font("Arial", float(size), FontStyle.Bold if bold else FontStyle.Regular)
        fonts.append(item)
        return item

    f_doctor = font(9.4, True)
    f_specialty = font(7.0)
    f_title = font(11.0, True)
    f_intro = font(7.2)
    f_label = font(7.5, True)
    f_footer = font(7.0, True)
    pen = Pen(Color.Black, 1.0)
    center = StringFormat()
    center.Alignment = StringAlignment.Center
    center.LineAlignment = StringAlignment.Near

    def draw_line(graphics, y, width):
        graphics.DrawLine(pen, 0.0, float(y), float(width), float(y))

    def on_print_page(_sender, event):
        graphics = event.Graphics
        width = float(event.MarginBounds.Width)
        y = 0.0
        logo_path = _os.path.join(str(core.BASE_DIR), "static", "doctor_isotype.png")
        if _os.path.exists(logo_path):
            try:
                image_holder["img"] = Image.FromFile(logo_path)
                graphics.DrawImage(image_holder["img"], 0.0, 1.0, 38.0, 38.0)
            except Exception:
                image_holder["img"] = None
        title_x = 42.0 if image_holder["img"] is not None else 0.0
        graphics.DrawString("DR. ARMANDO REVELO", f_doctor, Brushes.Black, RectangleF(title_x, 2.0, width-title_x, 15.0), center)
        graphics.DrawString("CIRUJANO URÓLOGO", f_specialty, Brushes.Black, RectangleF(title_x, 18.0, width-title_x, 13.0), center)
        y = 43.0
        draw_line(graphics, y, width)
        y += 10.0
        graphics.DrawString("DATOS PARA FACTURA", f_title, Brushes.Black, RectangleF(0.0, y, width, 20.0), center)
        y += 25.0
        graphics.DrawString("Complete los datos de la persona o empresa\na quien desea facturar.", f_intro, Brushes.Black, RectangleF(0.0, y, width, 30.0), center)
        y += 34.0
        draw_line(graphics, y, width)

        def field(label: str, spaces: int = 1):
            nonlocal y
            y += 11.0
            graphics.DrawString(label, f_label, Brushes.Black, 0.0, y)
            y += 32.0
            if spaces > 1:
                y += 24.0 * (spaces - 1)

        field("CÉDULA / RUC:")
        field("NOMBRE / RAZÓN SOCIAL:")
        field("DIRECCIÓN:", 2)
        field("TELÉFONO:")
        field("CORREO (OPCIONAL):")
        y += 6.0
        graphics.DrawString("ENTREGAR EN RECEPCIÓN", f_footer, Brushes.Black, RectangleF(0.0, y, width, 18.0), center)
        event.HasMorePages = False

    doc.PrintPage += on_print_page
    try:
        doc.Print()
    finally:
        try: doc.PrintPage -= on_print_page
        except Exception: pass
        if image_holder.get("img") is not None:
            try: image_holder["img"].Dispose()
            except Exception: pass
        for item in fonts:
            try: item.Dispose()
            except Exception: pass
        try: pen.Dispose()
        except Exception: pass
        try: center.Dispose()
        except Exception: pass
        try: doc.Dispose()
        except Exception: pass
    return chosen


@app.post("/api/billing/print-data-form")
def print_billing_data_form(user=core.Depends(core.current_user)):
    prefs = core._app_preferences()
    printer = str(prefs.get("printer") or "").strip()
    try:
        used = _print_billing_data_form_windows(printer)
    except Exception as exc:
        raise core.HTTPException(500, f"No se pudo imprimir el formulario: {exc}")
    return {"ok": True, "printed": True, "printer": used, "message": "Formulario para datos de factura enviado a la impresora."}


@app.get("/api/billing/print-data-form/health")
def billing_data_form_health(user=core.Depends(core.current_user)):
    return {"ok": True, "version": APP_VERSION, "canonical": True, "frontend_overlay": False}
'''
write(APP / "reception_billing_data_form_layout.py", data_form)


# ---------------------------------------------------------------------------
# 4) Interface cleanup becomes a passive compatibility shim only.
# ---------------------------------------------------------------------------
interface_cleanup = r'''from __future__ import annotations

import core_runtime as core

app = core.app
APP_VERSION = getattr(core, "APP_VERSION", "")
PATCH_BOOT_OK = False
PATCH_BOOT_ERROR = ""
FACTURERO_DESTINATION_REMOVED = False

try:
    destinations = getattr(core, "EXTERNAL_DESTINATIONS", None)
    if isinstance(destinations, dict):
        FACTURERO_DESTINATION_REMOVED = destinations.pop("facturero", None) is not None

    # Only compatibility CSS remains. Billing source itself no longer creates
    # these obsolete controls, so there are no loadBilling/setBillingStatus wrappers.
    core.V460_OVERLAY_CSS = (getattr(core, "V460_OVERLAY_CSS", "") or "") + r'''
[data-config-tab="services"],
[data-config-section="services"],
#v458ServicePanel,
#facturacion .billing-filters,
#v482BatchEmit,
#v4470ProcedureManager,
#v4475ProcedureManager,
[data-config-section="procedimientos"] > .v4476-service-old{display:none!important}
'''
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f"{type(exc).__name__}: {exc}"


@app.get("/api/interface-cleanup/health")
def interface_cleanup_health(user=core.Depends(core.current_user)):
    return {
        "ok": PATCH_BOOT_OK,
        "version": APP_VERSION,
        "error": PATCH_BOOT_ERROR,
        "facturero_destination_removed": FACTURERO_DESTINATION_REMOVED,
        "billing_dom_sweeps": False,
        "billing_function_wrappers": False,
        "version_painter": False,
    }
'''
write(APP / "reception_interface_cleanup.py", interface_cleanup)


# ---------------------------------------------------------------------------
# 5) Billing history: direct dependency and one-time legacy backfill per process.
# ---------------------------------------------------------------------------
history_path = APP / "reception_billing_history.py"
history = read(history_path)
history = replace_once(
    history,
    "import reception_attention_transaction as _dep_attention_transaction\nimport json as _json\nfrom datetime import date as _date, datetime as _datetime, timedelta as _timedelta\ncore = _dep_attention_transaction.core\napp = _dep_attention_transaction.app\nAPP_VERSION = '4.4.76'\ncore.APP_VERSION = APP_VERSION",
    "import core_runtime as core\nimport json as _json\nfrom datetime import date as _date, datetime as _datetime, timedelta as _timedelta\napp = core.app\nAPP_VERSION = getattr(core, 'APP_VERSION', '')",
    "billing history direct core dependency",
)
history = replace_once(
    history,
    "PATCH_BOOT_ERROR = ''\n",
    "PATCH_BOOT_ERROR = ''\n_BACKFILL_DONE = False\n",
    "billing history backfill flag",
)
history = replace_once(
    history,
    "    def v4476_billing_list(estado: str='TODAS', desde: _date | None=None, hasta: _date | None=None, db=core.Depends(core.get_db), user=core.Depends(core.current_user)):\n        try:\n            _backfill_active_trash_to_emissions(db)\n        except Exception:\n            pass\n",
    "    def v4476_billing_list(estado: str='TODAS', desde: _date | None=None, hasta: _date | None=None, db=core.Depends(core.get_db), user=core.Depends(core.current_user)):\n        global _BACKFILL_DONE\n        if not _BACKFILL_DONE:\n            try:\n                _backfill_active_trash_to_emissions(db)\n                _BACKFILL_DONE = True\n            except Exception:\n                pass\n",
    "billing history one-time backfill",
)
write(history_path, history)


# ---------------------------------------------------------------------------
# 6) Remove obsolete billing patch files from the runtime.
# ---------------------------------------------------------------------------
obsolete = {
    "reception_billing_actions.py",
    "reception_billing_issued_filters.py",
    "reception_billing_modal_cleanup.py",
    "reception_billing_optional_email.py",
    "reception_billing_data_form.py",
    "reception_billing_data_form_compact.py",
}
for name in obsolete:
    path = APP / name
    if not path.exists():
        raise RuntimeError(f"Expected obsolete file missing before cleanup: {name}")
    path.unlink()


# ---------------------------------------------------------------------------
# 7) Deterministic feature imports: drop removed patch layers.
# ---------------------------------------------------------------------------
features_path = APP / "features_runtime.py"
features = read(features_path)
for module in [name[:-3] for name in obsolete]:
    features = features.replace(f"import {module}\n", "")
    features = features.replace(f"    {module},\n", "")
write(features_path, features)


# ---------------------------------------------------------------------------
# 8) Version + manifest for a staged 4.6.26 candidate (branch only).
# ---------------------------------------------------------------------------
version_path = APP / "recepcion-version.json"
version_doc = json.loads(read(version_path))
version_doc["version"] = "4.6.26"
write(version_path, json.dumps(version_doc, ensure_ascii=False, indent=2) + "\n")

manifest_path = APP / "update_manifest.json"
manifest = json.loads(read(manifest_path))
for key in ("version", "app_version", "runtime_version"):
    manifest[key] = "4.6.26"
for key in ("required_dependencies", "copy"):
    manifest[key] = [x for x in manifest.get(key, []) if x not in obsolete]
notes = manifest.setdefault("notes", {})
notes.update({
    "purpose": "Consolida Facturación en código canónico: elimina capas redundantes, correo opcional real, formulario térmico único, descarte nativo y Facturero Móvil fuera del flujo.",
    "previous_version": "4.6.25",
    "candidate_only": True,
    "billing_cleanup_consolidated": True,
    "billing_removed_patch_modules": sorted(obsolete),
    "billing_email_optional_source_of_truth": True,
    "billing_facturero_removed_at_source": True,
    "billing_discard_native_card_action": True,
    "billing_data_form_single_implementation": True,
    "billing_hidden_dom_state_not_authoritative": True,
    "billing_history_backfill_once_per_process": True,
    "billing_post_render_discard_decorator": False,
    "billing_dom_cleanup_wrappers": False,
    "database_schema_changes": False,
    "patient_data_changes": False,
    "azur_logic_changes": False,
    "payment_storage_changes": False,
    "printing_changes": True,
    "production_status": "candidate",
})
write(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")


# ---------------------------------------------------------------------------
# 9) Static sanity checks before the repository validators run.
# ---------------------------------------------------------------------------
js = read(app_js_path)
checks = {
    "no Facturero source": "factureromovil" not in js.lower() and "openExternalApp('facturero')" not in js,
    "optional email": "if(email&&!email.includes('@'))" in js,
    "direct discard": "discardPendingBilling" in js and "billing-discard" in js,
    "direct data form": "/api/billing/print-data-form" in js,
    "view state variable": "billingViewState='PENDIENTE'" in js,
}
failed = [name for name, ok in checks.items() if not ok]
if failed:
    raise RuntimeError("Billing cleanup sanity checks failed: " + ", ".join(failed))

for name in obsolete:
    if (APP / name).exists():
        raise RuntimeError(f"Obsolete billing file survived: {name}")
    if name in read(features_path):
        raise RuntimeError(f"Obsolete billing file still referenced by features_runtime: {name}")

print("BILLING_CLEANUP_STAGED_OK 4.6.26")
print("removed", len(obsolete), "obsolete runtime modules")

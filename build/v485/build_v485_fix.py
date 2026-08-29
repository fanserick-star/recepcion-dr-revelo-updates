from __future__ import annotations
import importlib.util
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('v485base',HERE/'build_v485.py')
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)

def scoped_replace(s,start_marker,end_marker,old,new,label):
    i=s.find(start_marker)
    if i<0: raise SystemExit(label+': inicio no encontrado')
    j=s.find(end_marker,i+len(start_marker))
    if j<0: raise SystemExit(label+': fin no encontrado')
    seg=s[i:j]
    if seg.count(old)!=1: raise SystemExit(f'{label}: esperado 1, encontrado {seg.count(old)}')
    return s[:i]+seg.replace(old,new,1)+s[j:]

def patch_app(s):
    s=b.must_replace(s,'APP_VERSION = "4.3.84"','APP_VERSION = "4.3.85"',1,'version backend')
    s=b.must_replace(s,"const VERSION=\\'4.3.84\\';","const VERSION=\\'4.3.85\\';",1,'version visual')

    old="const save=findActionButton(modal);if(save){save.classList.add('v481-create-btn');if(/guardar|registrar/.test(norm(save.textContent)))save.textContent='Crear paciente'}"
    new="const save=findActionButton(modal);const initialSaveLabel=norm(save?.textContent);const headingText=norm(modal.querySelector('.modal-form-heading h2,h1,h2,h3')?.textContent||'');const editMode=!!window.__v485EditingPatientId||/editar|completar/.test(headingText)||/guardar cambios|actualizar/.test(initialSaveLabel);if(save){save.classList.add('v481-create-btn');if(!editMode&&/guardar|registrar/.test(norm(save.textContent)))save.textContent='Crear paciente'}"
    s=b.must_replace(s,old,new,1,'modo editar paciente')
    s=b.must_replace(s,"save.disabled=!String(name.value||'').trim()||!idOk||!mailOk||!required||state.duplicateCedula;","save.disabled=!String(name.value||'').trim()||!idOk||!mailOk||!required||(!editMode&&state.duplicateCedula);",1,'bloqueo duplicado')
    s=b.must_replace(s,"async function checkCedula(){\n     const q=digits(cedula.value);state.duplicateCedula=false;","async function checkCedula(){\n     if(editMode){state.duplicateCedula=false;if(!state.phoneDuplicate)showDup(null,null);updateSave();return}\n     const q=digits(cedula.value);state.duplicateCedula=false;",1,'cedula editar')
    s=b.must_replace(s,"async function checkPhone(){\n     if(!phone)return;","async function checkPhone(){\n     if(!phone)return;if(editMode){state.phoneDuplicate=false;if(!state.duplicateCedula)showDup(null,null);return}\n",1,'telefono editar')

    qold='BillingRecord.estado == "APROBADA"'
    qnew='BillingRecord.estado.in_(["PENDIENTE", "APROBADA"])'
    vold='any(b.estado != "APROBADA" for b, _ in rows)'
    vnew='any(str(b.estado or "").upper() not in {"PENDIENTE", "APROBADA"} for b, _ in rows)'
    s=scoped_replace(s,'def billing_azur_batch_preview','@app.post("/api/billing/azur/emit-all-pending")',qold,qnew,'preview query')
    s=scoped_replace(s,'def billing_azur_batch_preview','@app.post("/api/billing/azur/emit-all-pending")',vold,vnew,'preview estados')
    s=scoped_replace(s,'def billing_azur_emit_all_pending','def billing_group_records',qold,qnew,'emit-all query')
    s=scoped_replace(s,'def billing_azur_emit_all_pending','def billing_group_records',vold,vnew,'emit-all estados')
    s=s.replace('"La factura todavía no está completamente aprobada"','"La factura tiene estados que ya no están disponibles para emitir"')

    old_block='''            # La emisión masiva trabaja únicamente sobre facturas ya aprobadas.\n            db.commit()\n            mirror_azur_emission_to_local(record)\n            sent.append({"patient_id": int(patient_id), "nombre": p.nombre, "fecha": fecha, "numero_factura": invoice_number, "clave_acceso": access_key})'''
    new_block='''            touched=[]\n            for b, _v in rows:\n                b.estado = "EMITIDA"\n                b.approved_at = now\n                b.numero_factura = invoice_number\n                b.emitted_at = now\n                touched.append(b)\n            db.commit()\n            mirror_azur_emission_to_local(record)\n            for b in touched:\n                mirror_billing_to_local(b)\n            sent.append({"patient_id": int(patient_id), "nombre": p.nombre, "fecha": fecha, "numero_factura": invoice_number, "clave_acceso": access_key})'''
    s=scoped_replace(s,'def billing_azur_emit_all_pending','def billing_group_records',old_block,new_block,'cerrar facturas emitidas por lote')

    marker='@app.get("/v460/overlay.css")'
    if s.count(marker)!=1: raise SystemExit('overlay marker invalido')
    injected=('V485_FIX_CSS = r"""'+b.CSS+'"""\n'+'V485_FIX_JS = r"""'+b.JS+'"""\n'+'V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\\n" + V485_FIX_CSS\n'+'V460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\\n" + V485_FIX_JS\n\n'+marker)
    return s.replace(marker,injected,1)

b.patch_app=patch_app
b.main()

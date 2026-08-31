from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "updates" / "v4_4_34_payment_tick" / "app.py"
OUT = ROOT / "updates" / "v4_4_35_payment_per_card"
VERSION = "4.4.35"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: esperaba 1 coincidencia y encontró {count}")
    return text.replace(old, new, 1)


PAYMENT_CSS_BLOCK = r'''    PAYMENT_CSS = r"""
/* v4.4.35 — forma de pago individual, visible antes de emitir */
.v4431-pay-wrap{
  display:flex!important;align-items:center;gap:8px;flex-wrap:wrap;
  width:100%;box-sizing:border-box;margin:8px 0 10px;padding:9px 10px;
  border:1px solid #d7e2ed;border-radius:11px;background:#f8fbfe;
}
.v4431-pay-label{
  min-width:86px;font-size:8px;font-weight:950;letter-spacing:.055em;
  color:#687d93;text-transform:uppercase;margin-right:2px
}
.v4431-pay-choice{
  min-height:32px!important;padding:5px 10px!important;border-radius:9px!important;
  border:1px solid #cfdbe7!important;background:#fff!important;color:#405b75!important;
  font-size:9px!important;font-weight:900!important;display:inline-flex!important;
  align-items:center!important;gap:6px!important;box-shadow:none!important;cursor:pointer!important
}
.v4431-pay-choice .v4431-check{
  width:16px;height:16px;border:1.5px solid #a8b7c6;border-radius:50%;
  display:inline-grid;place-items:center;font-size:10px;line-height:1;
  color:transparent;background:#fff
}
.v4431-pay-choice.selected{
  border-color:#72ba91!important;background:#eaf8f0!important;color:#24643f!important
}
.v4431-pay-choice.selected .v4431-check{
  border-color:#2f8d59;background:#2f8d59;color:#fff;font-weight:950;
  box-shadow:0 0 0 2px rgba(47,141,89,.12)
}
.v4431-pay-choice.selected span:last-child{font-weight:950}
.v4431-pay-wrap.required{
  border-color:#dfa743!important;background:#fff8e9!important;
  box-shadow:0 0 0 3px rgba(223,167,67,.12)
}
.v4431-pay-wrap.required .v4431-pay-label{color:#9b6900}
.v4431-pay-saving{opacity:.58;pointer-events:none}
.billing-card .v4435-pay-locked{
  opacity:.55!important;filter:saturate(.6);cursor:not-allowed!important
}
.v4435-batch-button{
  display:inline-flex!important;align-items:center!important;justify-content:center!important;
  visibility:visible!important;opacity:1!important
}
.v4431-startup-toast{
  position:fixed;right:16px;bottom:16px;z-index:10060;padding:8px 11px;
  border-radius:10px;background:#1f405f;color:#fff;font-size:9px;font-weight:800;
  box-shadow:0 8px 26px rgba(18,43,66,.22)
}
@media(max-width:720px){
  .v4431-pay-wrap{width:100%;margin:7px 0 9px}
  .v4431-pay-label{width:100%;min-width:0}
  .v4431-pay-choice{flex:1;justify-content:center}
}
"""

'''


PAYMENT_JS_BLOCK = r'''    PAYMENT_JS = r"""
;(()=>{
  if(window.__v4435BillingPayment)return;
  window.__v4435BillingPayment=true;
  // Se conserva esta bandera porque las validaciones/instalaciones anteriores
  // la usan para confirmar que el módulo de pago arrancó.
  window.__v4431BillingPayment=true;

  const VERSION='4.4.35';
  let paymentMap=new Map();
  let refreshBusy=false;
  let decorateTimer=0;
  let listObserver=null;

  const key=(pid,fecha)=>`${Number(pid)}|${String(fecha||'').slice(0,10)}`;

  function cachedGroups(){
    try{
      return Array.isArray(billingGroupsCache)?billingGroupsCache:[];
    }catch(_e){return []}
  }

  function parseIdentityFromActions(card){
    const attrs=[...card.querySelectorAll('button[onclick],a[onclick]')]
      .map(el=>String(el.getAttribute('onclick')||''));
    // No dependemos exclusivamente de previewAzurInvoice: la capa visual actual
    // puede cambiar el botón a “Revisar y emitir”, pero otros botones de la misma
    // ficha todavía contienen patient_id + fecha.
    for(const raw of attrs){
      const m=/\(\s*(\d+)\s*,\s*['"](\d{4}-\d{2}-\d{2})['"]/.exec(raw);
      if(m)return {patient_id:Number(m[1]),fecha:m[2]};
    }
    return null;
  }

  function identityFromCache(card){
    const cards=[...document.querySelectorAll('#billingList .billing-card')];
    const idx=cards.indexOf(card);
    if(idx<0)return null;
    const g=cachedGroups()[idx];
    const patientId=Number(g?.patient?.id||0);
    const fecha=String(g?.fecha||'').slice(0,10);
    return patientId&&/^\d{4}-\d{2}-\d{2}$/.test(fecha)
      ?{patient_id:patientId,fecha,group:g}:null;
  }

  function identifyCard(card){
    if(!card)return null;
    const dsPid=Number(card.dataset.patientId||0);
    const dsFecha=String(card.dataset.fecha||'').slice(0,10);
    let id=(dsPid&&/^\d{4}-\d{2}-\d{2}$/.test(dsFecha))
      ?{patient_id:dsPid,fecha:dsFecha}:parseIdentityFromActions(card);
    const cached=identityFromCache(card);
    if(!id&&cached)id=cached;
    if(!id)return null;
    if(!id.group&&cached&&Number(cached.patient_id)===Number(id.patient_id)&&cached.fecha===id.fecha)id.group=cached.group;
    card.dataset.patientId=String(id.patient_id);
    card.dataset.fecha=id.fecha;
    return id;
  }

  function findEmitButton(card){
    const buttons=[...card.querySelectorAll('button')];
    let btn=buttons.find(b=>String(b.getAttribute('onclick')||'').includes('previewAzurInvoice'));
    if(btn)return btn;
    btn=buttons.find(b=>{
      const t=String(b.textContent||'').toLowerCase();
      return (t.includes('revisar')&&t.includes('emitir'))||t.includes('emitir en azur');
    });
    return btn||null;
  }

  function groupState(id,card){
    try{
      if(id?.group&&typeof billingGroupStatus==='function')return String(billingGroupStatus(id.group)||'').toUpperCase();
    }catch(_e){}
    if(card?.classList?.contains('aprobada'))return 'APROBADA';
    return findEmitButton(card)?'APROBADA':'';
  }

  function isEmissionCard(card,id){
    if(!id)return false;
    return groupState(id,card)==='APROBADA'||!!findEmitButton(card);
  }

  function setEmitLock(card,selected){
    const emit=findEmitButton(card);if(!emit)return;
    const locked=!selected;
    emit.disabled=locked;
    emit.classList.toggle('v4435-pay-locked',locked);
    emit.setAttribute('aria-disabled',locked?'true':'false');
    emit.title=locked?'Selecciona Efectivo o Transferencia antes de revisar y emitir':'';
  }

  function renderPicker(card){
    const id=identifyCard(card);if(!isEmissionCard(card,id))return;
    const k=key(id.patient_id,id.fecha);
    const selected=paymentMap.get(k)||'';
    let wrap=card.querySelector('.v4431-pay-wrap');
    if(!wrap){
      wrap=document.createElement('div');
      wrap.className='v4431-pay-wrap';
      const foot=card.querySelector('.billing-card-foot');
      const actions=card.querySelector('.billing-actions');
      // Ubicación buscada por recepción: justo después del TOTAL y antes de los
      // botones “Facturar con otros datos / Revisar y emitir”.
      if(foot&&actions&&actions.parentElement===foot)foot.insertBefore(wrap,actions);
      else if(actions)actions.insertAdjacentElement('beforebegin',wrap);
      else if(foot)foot.appendChild(wrap);
      else card.appendChild(wrap);
    }
    wrap.dataset.patientId=String(id.patient_id);
    wrap.dataset.fecha=id.fecha;
    wrap.innerHTML=`
      <span class="v4431-pay-label">Forma de pago</span>
      <button type="button" class="v4431-pay-choice ${selected==='EFECTIVO'?'selected':''}" data-pay="EFECTIVO">
        <span class="v4431-check">✓</span><span>💵 Efectivo</span>
      </button>
      <button type="button" class="v4431-pay-choice ${selected==='TRANSFERENCIA'?'selected':''}" data-pay="TRANSFERENCIA">
        <span class="v4431-check">✓</span><span>🏦 Transferencia</span>
      </button>`;
    wrap.querySelectorAll('.v4431-pay-choice').forEach(btn=>{
      btn.addEventListener('click',()=>saveChoice(wrap,String(btn.dataset.pay||'')));
    });
    setEmitLock(card,selected);
  }

  async function saveChoice(wrap,method){
    if(!['EFECTIVO','TRANSFERENCIA'].includes(method))return;
    const patient_id=Number(wrap.dataset.patientId||0);
    const fecha=String(wrap.dataset.fecha||'');
    if(!patient_id||!fecha)return;
    wrap.classList.add('v4431-pay-saving');
    try{
      const d=await api('/api/billing/payment-method',{
        method:'POST',
        body:JSON.stringify({patient_id,fecha,payment_method:method})
      });
      paymentMap.set(key(patient_id,fecha),String(d.payment_method||method));
      wrap.classList.remove('required');
      const card=wrap.closest('.billing-card');
      if(card)renderPicker(card);
    }catch(e){
      alert(e.message||'No se pudo guardar la forma de pago.');
    }finally{
      wrap.classList.remove('v4431-pay-saving');
    }
  }

  async function refreshPaymentMap(redecorate=true){
    if(refreshBusy)return;
    refreshBusy=true;
    try{
      const d=await api('/api/billing/payment-methods');
      paymentMap=new Map((d?.items||[]).map(x=>[
        key(x.patient_id,x.fecha),String(x.payment_method||'')
      ]));
      if(redecorate)decorate();
    }catch(_e){}
    finally{refreshBusy=false}
  }

  function cardMissingPayment(card){
    const id=identifyCard(card);
    if(!isEmissionCard(card,id))return false;
    return !paymentMap.get(key(id.patient_id,id.fecha));
  }

  async function batchPreflight(){
    await refreshPaymentMap(false);
    const cards=[...document.querySelectorAll('#billingList .billing-card')]
      .filter(card=>isEmissionCard(card,identifyCard(card)));
    const missing=cards.filter(card=>cardMissingPayment(card));
    if(missing.length){
      missing.forEach(card=>card.querySelector('.v4431-pay-wrap')?.classList.add('required'));
      try{missing[0]?.scrollIntoView({behavior:'smooth',block:'center'})}catch(_e){}
      alert(`Antes de emitir por lotes, selecciona Efectivo o Transferencia individualmente en ${missing.length} factura${missing.length===1?'':'s'}.`);
      return;
    }
    if(typeof emitAllPendingInvoices==='function')return emitAllPendingInvoices();
    alert('La emisión por lotes no está disponible en esta instalación.');
  }

  function ensureBatchButton(){
    let btn=document.getElementById('btnEmitAll')||document.getElementById('v4435EmitAll');
    if(!btn){
      const host=document.querySelector('#facturacion .billing-title-actions')
        ||document.querySelector('#facturacion .page-title-actions')
        ||document.querySelector('#facturacion .section-title-actions');
      if(!host)return;
      btn=document.createElement('button');
      btn.id='v4435EmitAll';
      btn.className='btn small secondary';
      host.appendChild(btn);
    }
    btn.hidden=false;
    btn.classList.add('v4435-batch-button');
    btn.textContent='📦 Emitir por lotes';
    btn.removeAttribute('onclick');
    if(!btn.__v4435BatchHook){
      btn.__v4435BatchHook=true;
      btn.addEventListener('click',batchPreflight);
    }
  }

  function decorate(){
    document.querySelectorAll('#billingList .billing-card').forEach(card=>renderPicker(card));
    ensureBatchButton();
  }

  function scheduleDecorate(){
    clearTimeout(decorateTimer);
    decorateTimer=setTimeout(decorate,20);
  }

  // Defensa visual adicional. Normalmente el botón queda disabled hasta escoger
  // forma de pago; esta captura también cubre botones recreados por otra capa.
  document.addEventListener('click',e=>{
    const btn=e.target?.closest?.('button');if(!btn)return;
    const card=btn.closest('.billing-card');if(!card)return;
    const emit=findEmitButton(card);if(btn!==emit)return;
    const id=identifyCard(card);if(!id)return;
    if(!paymentMap.get(key(id.patient_id,id.fecha))){
      e.preventDefault();e.stopImmediatePropagation();
      const wrap=card.querySelector('.v4431-pay-wrap');
      wrap?.classList.add('required');
      try{wrap?.scrollIntoView({behavior:'smooth',block:'center'})}catch(_e){}
      wrap?.querySelector('.v4431-pay-choice')?.focus();
      alert('Antes de emitir, selecciona Efectivo o Transferencia en esta ficha.');
    }
  },true);

  function hookBilling(){
    const fn=window.loadBilling;
    if(typeof fn!=='function')return false;
    if(fn.__v4435Hook)return true;
    const wrapped=async function(){
      const result=await fn.apply(this,arguments);
      await refreshPaymentMap(false);
      scheduleDecorate();
      return result;
    };
    wrapped.__v4435Hook=true;
    window.loadBilling=wrapped;
    return true;
  }

  function observeBillingList(){
    const list=document.querySelector('#billingList');
    if(!list||list.__v4435Observed)return;
    list.__v4435Observed=true;
    listObserver=new MutationObserver(mutations=>{
      if(mutations.some(m=>[...m.addedNodes].some(n=>n?.nodeType===1&&(n.matches?.('.billing-card')||n.querySelector?.('.billing-card'))))){
        refreshPaymentMap(false).finally(scheduleDecorate);
      }
    });
    // Solo hijos directos del listado. Así loadBilling dispara la decoración,
    // pero insertar el selector dentro de una tarjeta NO genera un bucle.
    listObserver.observe(list,{childList:true,subtree:false});
  }

  async function boot(){
    hookBilling();
    observeBillingList();
    ensureBatchButton();
    await refreshPaymentMap(false);
    decorate();
  }

  window.__v4435BillingPaymentTest={decorate,identifyCard,ensureBatchButton,batchPreflight};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});
  else boot();
})();
"""

'''


def main() -> None:
    src = SOURCE.read_text(encoding="utf-8")
    if 'APP_VERSION = "4.4.34"' not in src:
        raise SystemExit("La fuente ya no es v4.4.34")

    text = replace_once(src, 'APP_VERSION = "4.4.34"', f'APP_VERSION = "{VERSION}"', "APP_VERSION")

    css_start = text.index('    PAYMENT_CSS = r"""')
    js_start = text.index('    PAYMENT_JS = r"""')
    text = text[:css_start] + PAYMENT_CSS_BLOCK + text[js_start:]

    js_start = text.index('    PAYMENT_JS = r"""')
    js_end = text.index('    _v459_base =', js_start)
    text = text[:js_start] + PAYMENT_JS_BLOCK + text[js_end:]

    # El único marcador 4.4.34 que queda después de sustituir PAYMENT_JS es el
    # que actualiza la versión del overlay estable.
    text = replace_once(text, "const VERSION='4.4.34';", f"const VERSION='{VERSION}';", "versión overlay")

    required = [
        "import app_base_4428 as core",
        "PAYMENT_SENTINELS",
        '"EFECTIVO": "01"',
        '"TRANSFERENCIA": "20"',
        "/api/billing/payment-method",
        "window.__v4431BillingPayment=true",
        "window.__v4435BillingPayment=true",
        "parseIdentityFromActions",
        "identityFromCache",
        "openBillingRecipientEditor",
        "v4435-pay-locked",
        "📦 Emitir por lotes",
        "batchPreflight",
        "MutationObserver",
        "listObserver.observe(list,{childList:true,subtree:false})",
        "Antes de emitir, selecciona Efectivo o Transferencia en esta ficha.",
        "core._azur_payload_for_group = _azur_payload_for_group_v4431",
        "core.V459_SETTINGS_JS = _v459_base",
    ]
    for marker in required:
        if marker not in text:
            raise SystemExit(f"Se perdió funcionalidad requerida: {marker}")
    if "document.querySelectorAll('.billing-card.aprobada')" in text:
        raise SystemExit("Quedó el selector frágil antiguo")
    if "new MutationObserver(()=>" in text:
        raise SystemExit("No se permite reintroducir el observer global regresivo")

    compile(text, "app.py", "exec")
    OUT.mkdir(parents=True, exist_ok=True)
    app_path = OUT / "app.py"
    app_path.write_text(text, encoding="utf-8", newline="\n")

    manifest = {
        "product": "recepcion-pacientes",
        "version": VERSION,
        "app_version": VERSION,
        "runtime_version": VERSION,
        "launcher_version": "4.3.100-standalone-7-dynamic-port",
        "updater_version": "integrado-en-launcher",
        "copy": ["app.py", "update_manifest.json"],
        "notes": "Forma de pago individual visible entre TOTAL y acciones de cada factura POR EMITIR; bloquea Revisar y emitir hasta escoger Efectivo/Transferencia y restaura Emitir por lotes con prevalidación individual. No toca launcher, static, .env ni datos.",
    }
    manifest_path = OUT / "update_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

    candidate = {
        "product": "recepcion-pacientes",
        "version": VERSION,
        "app_version": VERSION,
        "runtime_version": VERSION,
        "mandatory": True,
        "channel": "files-v3",
        "message": "v4.4.35: Efectivo/Transferencia aparece dentro de cada ficha POR EMITIR, justo antes de Revisar y emitir. La elección es individual y obligatoria; también vuelve Emitir por lotes, que exige que cada factura tenga su forma de pago. No toca datos, .env ni static.",
        "files": [
            {
                "path": "app.py",
                "url": "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_35_payment_per_card/app.py",
                "sha256": sha256(app_path),
                "encoding": "utf-8",
            },
            {
                "path": "update_manifest.json",
                "url": "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_35_payment_per_card/update_manifest.json",
                "sha256": sha256(manifest_path),
                "encoding": "utf-8",
            },
        ],
    }
    (OUT / "candidate_latest.json").write_text(
        json.dumps(candidate, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print("V4435_BUILT", sha256(app_path))


if __name__ == "__main__":
    main()

from __future__ import annotations

# Deterministic current runtime. No historical release registry.
import json
import os
from pathlib import Path

import core_runtime
import reception_payments_and_agenda
import reception_billing_non_billable
import reception_receipt_thermal_layout
import reception_receipt_classification
import reception_receipt_preview
import reception_receipt_margins
import reception_receipt_unified_layout
import reception_receipt_raster
import reception_receipt_readability
import reception_receipt_size
import reception_receipt_width
import reception_attention_identity
import reception_interface_recovery
import reception_printing_queue
import reception_attention_transaction
import reception_billing_history
import reception_billing_discard
import reception_billing_actions
import reception_interface_cleanup
import reception_billing_issued_filters
import reception_billing_modal_cleanup
import reception_update_restart
import reception_update_launcher
import reception_billing_optional_email
import reception_payment_proof
import reception_printing_menu
import reception_payment_proof_margins
import reception_payment_proof_layout
import reception_billing_data_form
import reception_billing_data_form_compact
import reception_billing_data_form_layout
import reception_system_status
import reception_consultation_discount
import reception_payment_terminal
import reception_payment_terminal_interface
import reception_payment_terminal_config
import reception_payment_terminal_manual
import reception_history_bridge
import reception_launcher_status
import reception_version_display
import reception_version_sidebar
import reception_history_transport
import reception_history_attention_type
import reception_history_cancellation
import reception_payment_terminal_feedback
import reception_history_patient_details
import reception_payment_terminal_panel
import reception_history_identity_authority

FEATURE_MODULES = (
    reception_payments_and_agenda,
    reception_billing_non_billable,
    reception_receipt_thermal_layout,
    reception_receipt_classification,
    reception_receipt_preview,
    reception_receipt_margins,
    reception_receipt_unified_layout,
    reception_receipt_raster,
    reception_receipt_readability,
    reception_receipt_size,
    reception_receipt_width,
    reception_attention_identity,
    reception_interface_recovery,
    reception_printing_queue,
    reception_attention_transaction,
    reception_billing_history,
    reception_billing_discard,
    reception_billing_actions,
    reception_interface_cleanup,
    reception_billing_issued_filters,
    reception_billing_modal_cleanup,
    reception_update_restart,
    reception_update_launcher,
    reception_billing_optional_email,
    reception_payment_proof,
    reception_printing_menu,
    reception_payment_proof_margins,
    reception_payment_proof_layout,
    reception_billing_data_form,
    reception_billing_data_form_compact,
    reception_billing_data_form_layout,
    reception_system_status,
    reception_consultation_discount,
    reception_payment_terminal,
    reception_payment_terminal_interface,
    reception_payment_terminal_config,
    reception_payment_terminal_manual,
    reception_history_bridge,
    reception_launcher_status,
    reception_version_display,
    reception_version_sidebar,
    reception_history_transport,
    reception_history_attention_type,
    reception_history_cancellation,
    reception_payment_terminal_feedback,
    reception_history_patient_details,
    reception_payment_terminal_panel,
    reception_history_identity_authority,
)


# v4.6.11 — La ficha del paciente es también un punto explícito de identidad.
# No depende de abrir/guardar una atención para poder buscar y vincular Historia.
_PROFILE_HISTORY_CSS = r"""
.v4611-history-card{margin:14px 0;padding:13px 15px;border:1px solid #cfe0ee;border-radius:13px;background:#f7fbff;color:#274a69;display:flex;align-items:center;justify-content:space-between;gap:14px}
.v4611-history-card.warn{background:#fff8ea;border-color:#efd39d}
.v4611-history-copy{display:flex;flex-direction:column;gap:3px;min-width:0}
.v4611-history-copy b{font-size:13px;color:#183d5f}.v4611-history-copy small{font-size:11px;color:#687d91}
.v4611-history-actions{display:flex;align-items:center;gap:9px;flex-shrink:0}.v4611-history-count{font-size:12px;font-weight:800;color:#8b5a12;white-space:nowrap}
.v4611-link-btn{border:0;border-radius:10px;background:#2475d0;color:#fff;font-weight:800;padding:9px 13px;cursor:pointer;white-space:nowrap}.v4611-link-btn:hover{filter:brightness(.96)}
.v4611-overlay{position:fixed;inset:0;z-index:100050;background:rgba(25,42,58,.42);display:flex;align-items:center;justify-content:center;padding:22px}
.v4611-dialog{width:min(760px,96vw);max-height:84vh;overflow:auto;background:#fff;border-radius:18px;box-shadow:0 22px 70px rgba(0,0,0,.24);padding:20px}
.v4611-head{display:flex;align-items:flex-start;justify-content:space-between;gap:18px}.v4611-head h3{margin:0 0 4px;color:#173b5d}.v4611-head p{margin:0;color:#718497;font-size:12px}.v4611-close{border:0;background:#eef2f6;border-radius:9px;padding:7px 10px;cursor:pointer;font-weight:800;color:#587087}
.v4611-search{display:flex;gap:9px;margin:16px 0}.v4611-search input{flex:1;min-width:0;padding:11px 12px;border:1px solid #ccd9e5;border-radius:10px;font-size:13px}.v4611-search button{border:0;border-radius:10px;background:#2475d0;color:#fff;font-weight:800;padding:10px 18px;cursor:pointer}
.v4611-results{display:flex;flex-direction:column;gap:9px}.v4611-result{border:1px solid #d8e3ec;border-radius:12px;padding:12px;display:grid;grid-template-columns:1fr auto;gap:12px;align-items:center}.v4611-result b{display:block;color:#183d5f;font-size:13px}.v4611-result small{display:block;color:#718497;margin-top:3px}.v4611-result button{border:0;border-radius:9px;background:#1f8b55;color:#fff;font-weight:800;padding:9px 12px;cursor:pointer}.v4611-empty{padding:22px;text-align:center;border:1px dashed #d7e0e8;border-radius:11px;color:#718497}
@media(max-width:620px){.v4611-history-card{align-items:flex-start;flex-direction:column}.v4611-history-actions{width:100%;justify-content:space-between}.v4611-search{flex-direction:column}.v4611-result{grid-template-columns:1fr}}
"""

_PROFILE_HISTORY_JS = r"""
;(()=>{
  if(window.__v4611ProfileHistoryLink)return;
  window.__v4611ProfileHistoryLink=true;
  const text=v=>String(v??'').replace(/\s+/g,' ').trim();
  const html=v=>text(v).replace(/[&<>\"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[m]));
  const fmt=v=>{const s=text(v),m=/^(\d{4})-(\d{2})-(\d{2})/.exec(s);return m?`${m[3]}/${m[2]}/${m[1]}`:s};
  async function call(url,opt={}){
    if(typeof window.api==='function')return window.api(url,opt);
    const r=await fetch(url,{headers:{'Content-Type':'application/json',...(opt.headers||{})},...opt});
    const d=await r.json().catch(()=>({}));if(!r.ok)throw Error(d.detail||d.error||'Error al consultar Historia');return d;
  }
  function profile(){return document.querySelector('#modal .patient-profile-modal,.modal .patient-profile-modal,.patient-profile-modal')}
  function patientId(host){
    if(!host)return 0;
    for(const el of host.querySelectorAll('[onclick]')){
      const raw=String(el.getAttribute('onclick')||'');
      const m=/(?:attentionFor|editPatient|openPatient)\s*\(\s*(\d+)/.exec(raw);if(m)return Number(m[1]||0);
    }
    return 0;
  }
  function patientName(host){return text(host?.querySelector('.v4413-profile-name h2')?.textContent||'')}
  function patientIdLabel(host){return text(host?.querySelector('.v4413-profile-identity b')?.textContent||'')}
  function place(host,card){
    const continueWrap=host.querySelector('.v4417-continue-wrap');
    if(continueWrap){continueWrap.insertAdjacentElement('beforebegin',card);return}
    const tabs=host.querySelector('.v4413-profile-tabs');
    if(tabs){tabs.insertAdjacentElement('beforebegin',card);return}
    host.appendChild(card);
  }
  function closeSearch(){document.querySelector('.v4611-overlay')?.remove()}
  async function searchDialog(pid,initial){
    closeSearch();
    const overlay=document.createElement('div');overlay.className='v4611-overlay';
    overlay.innerHTML=`<div class="v4611-dialog"><div class="v4611-head"><div><h3>Buscar ficha en Historia Clínica</h3><p>Seleccione la ficha clínica correcta. Recepción conservará la autoridad de los datos personales.</p></div><button class="v4611-close" type="button">×</button></div><div class="v4611-search"><input autocomplete="off" placeholder="Cédula, apellidos y nombres o celular"><button type="button">Buscar</button></div><div class="v4611-results"><div class="v4611-empty">Escriba una búsqueda.</div></div></div>`;
    document.body.appendChild(overlay);overlay.querySelector('.v4611-close').onclick=closeSearch;overlay.addEventListener('click',e=>{if(e.target===overlay)closeSearch()});
    const input=overlay.querySelector('input'),go=overlay.querySelector('.v4611-search button'),results=overlay.querySelector('.v4611-results');input.value=text(initial);
    const run=async()=>{
      const q=text(input.value);if(q.length<2){results.innerHTML='<div class="v4611-empty">Escriba al menos 2 caracteres.</div>';return}
      results.innerHTML='<div class="v4611-empty">Buscando fichas…</div>';
      try{
        const out=await call('/api/historia-identity/search?q='+encodeURIComponent(q)+'&limit=30');
        if(out?.ok===false)throw Error(out.error||'No se pudo consultar Historia');
        const rows=Array.isArray(out?.results)?out.results:[];
        if(!rows.length){results.innerHTML='<div class="v4611-empty">No encontré una ficha con esa búsqueda.</div>';return}
        results.innerHTML='';
        for(const r of rows){
          const card=document.createElement('div');card.className='v4611-result';
          const count=Number(r.history_date_count||0),last=fmt(r.last_history_date||'');
          card.innerHTML=`<div><b>${html(r.name||'SIN NOMBRE')}</b><small>${html(r.national_id||'Sin identificación')}${r.phone?' · '+html(r.phone):''}</small><small>${count===1?'1 fecha con historia clínica':count+' fechas con historias clínicas'}${last?' · Última: '+html(last):''}</small></div><button type="button">Vincular esta ficha</button>`;
          card.querySelector('button').onclick=async()=>{
            const btn=card.querySelector('button');btn.disabled=true;btn.textContent='Vinculando…';
            try{
              const linked=await call('/api/historia-identity/link',{method:'POST',body:JSON.stringify({reception_patient_id:Number(pid),clinical_patient_id:String(r.id)})});
              if(linked?.ok===false)throw Error(linked.error||'No se pudo vincular');
              closeSearch();const host=profile();if(host)await render(host,true);
              if(typeof window.rpAlert==='function')window.rpAlert('Ficha vinculada correctamente.','Historia Clínica');
              else alert('Ficha vinculada correctamente.');
            }catch(err){btn.disabled=false;btn.textContent='Vincular esta ficha';alert(err.message||err)}
          };
          results.appendChild(card);
        }
      }catch(err){results.innerHTML=`<div class="v4611-empty">${html(err.message||'No se pudo consultar Historia Clínica.')}</div>`}
    };
    go.onclick=run;input.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();run()}});input.focus();if(text(initial).length>=2)run();
  }
  async function render(host=profile(),force=false){
    if(!host)return;
    const pid=patientId(host);if(!pid)return;
    host.querySelector('.v468-history-card')?.remove();
    let card=host.querySelector('.v4611-history-card');
    if(card&&!force&&Number(card.dataset.pid||0)===pid&&card.dataset.loaded==='1')return;
    if(!card){card=document.createElement('div');card.className='v4611-history-card';place(host,card)}
    card.dataset.pid=String(pid);card.dataset.loaded='0';card.innerHTML='<div class="v4611-history-copy"><b>Historia clínica</b><small>Consultando vínculo…</small></div>';
    try{
      const data=await call('/api/historia-identity/status/'+pid);if(!card.isConnected||Number(card.dataset.pid)!==pid)return;
      const linked=!!data?.linked,count=Number(data?.history_date_count||0),last=fmt(data?.last_history_date||'');card.classList.toggle('warn',!linked);
      if(linked){
        card.innerHTML=`<div class="v4611-history-copy"><b>Historia clínica vinculada</b><small>${count===1?'1 fecha con historia clínica':count+' fechas con historias clínicas'}${last?' · Última: '+html(last):''}</small></div><div class="v4611-history-actions"><span class="v4611-history-count">${count}</span></div>`;
      }else{
        card.innerHTML='<div class="v4611-history-copy"><b>Historia clínica · SIN VÍNCULO</b><small>Busque y seleccione la ficha clínica correcta antes de continuar.</small></div><div class="v4611-history-actions"><button type="button" class="v4611-link-btn">🔗 Buscar y vincular ficha</button></div>';
        card.querySelector('.v4611-link-btn').onclick=()=>searchDialog(pid,patientIdLabel(host)||patientName(host));
      }
      card.dataset.loaded='1';
    }catch(err){card.classList.add('warn');card.innerHTML=`<div class="v4611-history-copy"><b>Historia clínica</b><small>${html(err.message||'No se pudo consultar el vínculo en este momento.')}</small></div>`;card.dataset.loaded='1'}
  }
  let timer=0;const schedule=()=>{clearTimeout(timer);timer=setTimeout(()=>render(),35)};
  new MutationObserver(schedule).observe(document.documentElement,{childList:true,subtree:true});
  document.addEventListener('click',()=>setTimeout(schedule,40),true);
  setTimeout(schedule,250);setTimeout(schedule,900);
})();
"""

core_runtime.V460_OVERLAY_CSS = (getattr(core_runtime, "V460_OVERLAY_CSS", "") or "") + "\n" + _PROFILE_HISTORY_CSS
core_runtime.V460_OVERLAY_JS = (getattr(core_runtime, "V460_OVERLAY_JS", "") or "") + "\n" + _PROFILE_HISTORY_JS


def _read_current_app_version() -> str:
    version_doc = json.loads(
        Path(__file__).with_name("recepcion-version.json").read_text(encoding="utf-8-sig")
    )
    version = str(version_doc.get("version") or "").strip()
    if not version:
        raise RuntimeError("recepcion-version.json does not contain a valid version")
    return version


def _install_versioned_overlay_home() -> None:
    """Evita que WebView reutilice overlay.js/CSS de una versión anterior.

    El runtime histórico inyectaba /v460/overlay.* con el query fijo v=4.3.72.
    Como todo el UI acumulado se sirve desde esos dos endpoints, una caché vieja
    podía ocultar cambios ya instalados (por ejemplo el botón de vincular Historia).
    Conservamos exactamente los assets anteriores, pero el overlay usa la versión
    canónica actual como cache-buster.
    """
    app = core_runtime.app
    for route in list(app.router.routes):
        if getattr(route, "path", None) == "/" and "GET" in set(getattr(route, "methods", set()) or set()):
            app.router.routes.remove(route)

    @app.get("/", response_class=core_runtime.HTMLResponse)
    def _versioned_home():
        with open(os.path.join(core_runtime.BASE_DIR, "static", "index.html"), encoding="utf-8") as handle:
            html = handle.read()
        version = _read_current_app_version()
        addon = (
            '<link rel="stylesheet" href="/v458/settings.css?v=4.3.58">'
            '<script defer src="/v458/settings.js?v=4.3.58"></script>'
            '<link rel="stylesheet" href="/v459/settings.css?v=4.3.59">'
            '<script defer src="/v459/settings.js?v=4.3.59"></script>'
            f'<link rel="stylesheet" href="/v460/overlay.css?v={version}">'
            f'<script defer src="/v460/overlay.js?v={version}"></script>'
        )
        return html.replace("</head>", addon + "</head>", 1) if "</head>" in html else html + addon

    try:
        app.openapi_schema = None
    except Exception:
        pass


_install_versioned_overlay_home()

CURRENT_APP_VERSION = _read_current_app_version()
core_runtime.APP_VERSION = CURRENT_APP_VERSION
for _feature_module in FEATURE_MODULES:
    _feature_module.APP_VERSION = CURRENT_APP_VERSION
del _feature_module

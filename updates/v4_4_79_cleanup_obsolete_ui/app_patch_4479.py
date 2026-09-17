from __future__ import annotations

# v4.4.79 — limpieza de interfaz y capas obsoletas.
# - Parte de v4.4.78 y conserva todos los flujos estables actuales.
# - Retira Facturero Móvil del programa y bloquea su destino externo heredado.
# - Elimina de la interfaz controles obsoletos/duplicados de Facturación y Configuración.
# - Desactiva administradores antiguos de Servicios y el observador viejo que repintaba versión.
# - Mantiene AZUR, No facturables, Actividad/Papelera, impresión, WhatsApp, Agenda y diagnósticos.
# - No cambia base de datos, recibo térmico, guardado de atención ni integración Bendo experimental.

import re as _re

import app_patch_4478 as previous

core = previous.core
app = previous.app
APP_VERSION = "4.4.79"

_mod = previous
_seen = set()
for _ in range(44):
    if _mod is None or id(_mod) in _seen:
        break
    _seen.add(id(_mod))
    try:
        _mod.APP_VERSION = APP_VERSION
    except Exception:
        pass
    _mod = getattr(_mod, "previous", None)
core.APP_VERSION = APP_VERSION

PATCH_BOOT_OK = False
PATCH_BOOT_ERROR = ""
LEGACY_SERVICE_MANAGER_DISABLED = False
LEGACY_VERSION_OBSERVER_DISABLED = False
FACTURERO_DESTINATION_REMOVED = False

try:
    try:
        destinations = getattr(core, "EXTERNAL_DESTINATIONS", None)
        if isinstance(destinations, dict):
            FACTURERO_DESTINATION_REMOVED = destinations.pop("facturero", None) is not None
    except Exception:
        FACTURERO_DESTINATION_REMOVED = False

    _js = (getattr(core, "V460_OVERLAY_JS", "") or "")
    _prelude = "window.__v4475FastSaveAndServiceDelete=true;\n"

    _before = _js
    _js = _js.replace(
        "    installProcedureManager();\n    installVersionPainter();",
        "    /* v4.4.79: administradores visuales heredados desactivados */",
    )
    LEGACY_SERVICE_MANAGER_DISABLED = _js != _before

    _before = _js
    _js = _js.replace(
        "    installVersionPainter();",
        "    /* v4.4.79: observador heredado de versión desactivado */",
    )
    if _js != _before:
        LEGACY_VERSION_OBSERVER_DISABLED = True
    else:
        LEGACY_VERSION_OBSERVER_DISABLED = LEGACY_SERVICE_MANAGER_DISABLED

    _js = _re.sub(
        r"""const\s+VERSION\s*=\s*['"]4\.4\.\d+['"]\s*;""",
        "const VERSION='4.4.79';",
        _js,
    )
    _js = _re.sub(
        r"""const\s+V\s*=\s*['"]4\.4\.\d+['"]\s*;""",
        "const V='4.4.79';",
        _js,
    )

    V4479_CSS = r"""
.v460-version,#currentVersionBadge{font-size:0!important}
.v460-version::after,#currentVersionBadge::after{
  content:"v4.4.79"!important;
  font-size:9px!important;line-height:1!important;font-weight:850!important
}
[data-config-tab="services"],
[data-config-section="services"],
#v458ServicePanel{display:none!important}
#facturacion .billing-filters,
#v482BatchEmit{display:none!important}
#v4470ProcedureManager,
#v4475ProcedureManager,
[data-config-section="procedimientos"] > .v4476-service-old{display:none!important}
"""

    V4479_JS = r"""
;(()=>{
  if(window.__v4479Cleanup)return;
  window.__v4479Cleanup=true;
  const VERSION='4.4.79';

  const txt=v=>String(v??'').replace(/\s+/g,' ').trim();
  const norm=v=>txt(v).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();

  function isFactureroControl(el){
    const blob=[
      txt(el?.textContent),
      String(el?.getAttribute?.('href')||''),
      String(el?.getAttribute?.('onclick')||''),
      String(el?.dataset?.target||''),
      String(el?.dataset?.destination||'')
    ].join(' ').toLowerCase();
    return blob.includes('facturero movil')
      || blob.includes('factureromovil')
      || /\bfacturero\b/.test(blob);
  }

  function cleanupBilling(){
    const sec=document.querySelector('#facturacion');
    if(!sec)return;
    [...sec.querySelectorAll('button,a')].forEach(el=>{
      if(isFactureroControl(el))el.remove();
    });
    const summary=sec.querySelector('#billingSummary');
    if(summary){
      [...summary.querySelectorAll('button')].forEach(btn=>{
        if(norm(btn.textContent).includes('aprobada'))btn.remove();
      });
    }
    sec.querySelector('.billing-filters')?.remove();
    sec.querySelector('#v482BatchEmit')?.remove();
    [...sec.querySelectorAll('.billing-title-actions')].forEach(row=>{
      const useful=[...row.querySelectorAll('button,a')].filter(el=>!isFactureroControl(el));
      if(!useful.length)row.style.display='none';
      else row.style.display='';
    });
  }

  function cleanupConfig(){
    const config=document.querySelector('#config');
    if(!config)return;
    config.querySelector('[data-config-tab="services"]')?.remove();
    config.querySelector('[data-config-section="services"]')?.remove();
    config.querySelector('#v458ServicePanel')?.remove();

    const proc=config.querySelector('[data-config-section="procedimientos"]');
    if(proc&&proc.querySelector('#v4476ServicePanel')){
      proc.querySelector('#v4470ProcedureManager')?.remove();
      proc.querySelector('#v4475ProcedureManager')?.remove();
      [...proc.querySelectorAll(':scope > .v4476-service-old')].forEach(el=>el.remove());
    }
  }

  function stabilizeVersion(){
    document.querySelectorAll('.v460-version,#currentVersionBadge').forEach(el=>{
      el.textContent='v'+VERSION;
      el.setAttribute('data-version','v'+VERSION);
    });
  }

  function cleanupAll(){
    cleanupBilling();
    cleanupConfig();
    stabilizeVersion();
  }

  const stableLoadBilling=window.loadBilling;
  if(typeof stableLoadBilling==='function'){
    window.loadBilling=async function(){
      const out=await stableLoadBilling.apply(this,arguments);
      cleanupBilling();
      stabilizeVersion();
      return out;
    };
  }

  const stableSetBillingStatus=window.setBillingStatus;
  if(typeof stableSetBillingStatus==='function'){
    window.setBillingStatus=async function(){
      const out=await stableSetBillingStatus.apply(this,arguments);
      cleanupBilling();
      stabilizeVersion();
      return out;
    };
  }

  const stableLoadProcedures=window.loadProcedures;
  if(typeof stableLoadProcedures==='function'){
    window.loadProcedures=async function(){
      const out=await stableLoadProcedures.apply(this,arguments);
      cleanupConfig();
      return out;
    };
  }

  const stableShowConfigTab=window.showConfigTab;
  if(typeof stableShowConfigTab==='function'){
    window.showConfigTab=function(tab){
      if(String(tab||'').toLowerCase()==='services')tab='sistema';
      const args=[...arguments];
      args[0]=tab;
      const out=stableShowConfigTab.apply(this,args);
      setTimeout(cleanupConfig,0);
      return out;
    };
  }

  document.addEventListener('click',event=>{
    const nav=event.target?.closest?.(
      '[data-section="facturacion"],[data-config-tab="facturacion"],'
      +'[data-section="config"],[data-config-tab="procedimientos"],'
      +'[data-config-tab="sistema"]'
    );
    if(nav)setTimeout(cleanupAll,30);
  },true);

  function boot(){
    cleanupAll();
    setTimeout(cleanupAll,120);
    setTimeout(cleanupAll,600);
  }
  if(document.readyState==='loading'){
    document.addEventListener('DOMContentLoaded',boot,{once:true});
  }else{
    boot();
  }
})();
"""

    core.V460_OVERLAY_CSS = (
        (getattr(core, "V460_OVERLAY_CSS", "") or "") + "\n" + V4479_CSS
    )
    core.V460_OVERLAY_JS = _prelude + _js + "\n" + V4479_JS

    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f"{type(exc).__name__}: {exc}"
    try:
        core.logging.getLogger(__name__).error(
            "v4.4.79 cleanup patch failed: %s", PATCH_BOOT_ERROR
        )
    except Exception:
        pass


@app.get("/api/v4479/health")
def v4479_health(user=core.Depends(core.current_user)):
    return {
        "ok": PATCH_BOOT_OK,
        "version": APP_VERSION,
        "error": PATCH_BOOT_ERROR,
        "facturero_destination_removed": FACTURERO_DESTINATION_REMOVED,
        "legacy_service_manager_disabled": LEGACY_SERVICE_MANAGER_DISABLED,
        "legacy_version_observer_disabled": LEGACY_VERSION_OBSERVER_DISABLED,
        "obsolete_services_tab_removed": True,
        "obsolete_billing_filters_removed": True,
        "obsolete_approved_tab_removed": True,
        "batch_emit_ui_removed": True,
        "azur_preserved": True,
        "no_facturables_preserved": True,
        "activity_trash_preserved": True,
        "receipt_layout_version": "4.4.69",
        "database_changes": False,
        "bendo_enabled": False,
        "base": "4.4.78",
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

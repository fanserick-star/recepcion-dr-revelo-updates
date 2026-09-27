from __future__ import annotations
from runtime_registry import layers as _rf_layers, module_lookup as _rf_module_lookup

import re as _re
previous = _rf_layers['app_patch_4477']
core = previous.core
app = previous.app
APP_VERSION = '4.4.78'
_mod = previous
_seen = set()
for _ in range(40):
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
try:
    V4478_CSS = '\n/* v4.4.78 — versión estable + botón seguro de descarte */\n.v4478-discard-billing{\n  border:1px solid #dfb4b4!important;\n  background:#fff6f6!important;\n  color:#963d3d!important;\n}\n.v4478-discard-billing:hover{\n  background:#fdecec!important;\n  border-color:#cf8f8f!important;\n}\n/* Los parches antiguos todavía pueden intentar escribir su versión unos ms.\n   Ocultamos ese texto interno y mostramos una única versión estable. */\n.v460-version,#currentVersionBadge{\n  font-size:0!important;\n}\n.v460-version::after,#currentVersionBadge::after{\n  content:"v4.4.78";\n  font-size:9px!important;\n  line-height:1!important;\n  font-weight:850!important;\n}\n'
    V4478_JS = '\n;(()=>{\n  if(window.__v4478VisibleDiscardAndStableVersion)return;\n  window.__v4478VisibleDiscardAndStableVersion=true;\n  const VERSION=\'4.4.78\';\n\n  const state=()=>String(document.querySelector(\'#bEstado\')?.value||\'PENDIENTE\').toUpperCase();\n\n  function identityFromCard(card,index){\n    if(!card)return null;\n    const dsPid=Number(card.dataset.patientId||0);\n    const dsFecha=String(card.dataset.fecha||\'\').slice(0,10);\n    if(dsPid&&/^\\d{4}-\\d{2}-\\d{2}$/.test(dsFecha)){\n      return {patient_id:dsPid,fecha:dsFecha};\n    }\n\n    for(const el of [...card.querySelectorAll(\'[onclick]\')]){\n      const raw=String(el.getAttribute(\'onclick\')||\'\');\n      const m=/\\(\\s*(\\d+)\\s*,\\s*[\'"](\\d{4}-\\d{2}-\\d{2})[\'"]/.exec(raw);\n      if(m)return {patient_id:Number(m[1]),fecha:m[2]};\n    }\n\n    try{\n      const groups=Array.isArray(billingGroupsCache)?billingGroupsCache:[];\n      const g=groups[index];\n      const pid=Number(g?.patient?.id||0);\n      const fecha=String(g?.fecha||g?.items?.[0]?.visit?.fecha||\'\').slice(0,10);\n      if(pid&&/^\\d{4}-\\d{2}-\\d{2}$/.test(fecha)){\n        return {patient_id:pid,fecha};\n      }\n    }catch(_e){}\n    return null;\n  }\n\n  function decoratePendingCards(){\n    if(state()===\'EMITIDA\')return;\n    const cards=[...document.querySelectorAll(\'#billingList .billing-card\')];\n    cards.forEach((card,index)=>{\n      if(card.classList.contains(\'emitida\'))return;\n      if(card.querySelector(\'.v4478-discard-billing,.v4477-discard-billing\'))return;\n\n      const id=identityFromCard(card,index);\n      if(!id)return;\n\n      let actions=card.querySelector(\'.billing-actions\');\n      if(!actions){\n        const foot=card.querySelector(\'.billing-card-foot\')||card;\n        actions=document.createElement(\'div\');\n        actions.className=\'billing-actions\';\n        foot.appendChild(actions);\n      }\n\n      const btn=document.createElement(\'button\');\n      btn.type=\'button\';\n      btn.className=\'v4478-discard-billing\';\n      btn.textContent=\'🗑 Quitar de Por emitir\';\n      btn.addEventListener(\'click\',event=>{\n        event.preventDefault();\n        event.stopPropagation();\n        if(typeof window.v4477DiscardPendingBilling===\'function\'){\n          window.v4477DiscardPendingBilling(id.patient_id,id.fecha,event);\n        }else{\n          alert(\'La opción para quitar esta factura todavía no está disponible. Cierra y vuelve a abrir Recepción.\');\n        }\n      });\n      actions.prepend(btn);\n    });\n  }\n\n  function stabilizeVersion(){\n    try{\n      document.querySelectorAll(\'.v460-version,#currentVersionBadge\').forEach(el=>{\n        el.textContent=\'v\'+VERSION;\n        el.setAttribute(\'data-version\',\'v\'+VERSION);\n      });\n    }catch(_e){}\n  }\n\n  const stableLoadBilling=window.loadBilling;\n  if(typeof stableLoadBilling===\'function\'){\n    window.loadBilling=async function(){\n      const out=await stableLoadBilling.apply(this,arguments);\n      decoratePendingCards();\n      stabilizeVersion();\n      setTimeout(decoratePendingCards,40);\n      setTimeout(decoratePendingCards,140);\n      return out;\n    };\n  }\n\n  const stableSetBillingStatus=window.setBillingStatus;\n  if(typeof stableSetBillingStatus===\'function\'){\n    window.setBillingStatus=async function(){\n      const out=await stableSetBillingStatus.apply(this,arguments);\n      decoratePendingCards();\n      stabilizeVersion();\n      setTimeout(decoratePendingCards,50);\n      return out;\n    };\n  }\n\n  document.addEventListener(\'click\',event=>{\n    const billingNav=event.target?.closest?.(\'[data-section="facturacion"],[data-config-tab="facturacion"]\');\n    if(billingNav){\n      setTimeout(decoratePendingCards,80);\n      setTimeout(decoratePendingCards,260);\n    }\n  },true);\n\n  function boot(){\n    stabilizeVersion();\n    decoratePendingCards();\n    setTimeout(()=>{stabilizeVersion();decoratePendingCards()},180);\n    setTimeout(()=>{stabilizeVersion();decoratePendingCards()},700);\n    setTimeout(()=>{stabilizeVersion();decoratePendingCards()},1600);\n  }\n  if(document.readyState===\'loading\')document.addEventListener(\'DOMContentLoaded\',boot,{once:true});\n  else boot();\n})();\n'
    _js = getattr(core, 'V460_OVERLAY_JS', '') or ''
    _js = _re.sub('const\\s+VERSION\\s*=\\s*[\'"]4\\.4\\.\\d+[\'"]\\s*;', "const VERSION='4.4.78';", _js)
    _js = _re.sub('const\\s+V\\s*=\\s*[\'"]4\\.4\\.\\d+[\'"]\\s*;', "const V='4.4.78';", _js)
    core.V460_OVERLAY_CSS = (getattr(core, 'V460_OVERLAY_CSS', '') or '') + '\n' + V4478_CSS
    core.V460_OVERLAY_JS = _js + '\n' + V4478_JS
    PATCH_BOOT_OK = True
except Exception as exc:
    PATCH_BOOT_ERROR = f'{type(exc).__name__}: {exc}'
    try:
        core.logging.getLogger(__name__).error('v4.4.78 visible discard/stable version patch failed: %s', PATCH_BOOT_ERROR)
    except Exception:
        pass

@app.get('/api/v4478/health')
def v4478_health(user=core.Depends(core.current_user)):
    return {'ok': PATCH_BOOT_OK, 'version': APP_VERSION, 'error': PATCH_BOOT_ERROR, 'pending_discard_button_post_render': True, 'stable_visible_version': True, 'uses_new_dom_observer': False, 'backend_changes': False, 'base': '4.4.77'}
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=core.LOCAL_HTTP_PORT, reload=False, access_log=False, log_level='warning', workers=1)

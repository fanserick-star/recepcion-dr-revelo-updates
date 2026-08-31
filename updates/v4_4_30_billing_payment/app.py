from __future__ import annotations

# v4.4.30 — Forma de pago en Facturación, justo antes de emitir.
#
# Conserva íntegro el backend 4.4.29, pero mueve la elección de Efectivo /
# Transferencia fuera de "Nueva atención". La forma de pago se marca en cada
# ficha APROBADA de Facturación y queda persistida en la atención antes de
# construir el payload de AZUR/SRI.
#
# También corrige el distintivo visual de versión que podía quedar mostrando
# v4.4.28 aunque el backend ya estuviera actualizado.

import hashlib
import json
import os
import urllib.request
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE_PATH = ROOT / "app_base_4429.py"
BASE_SHA256 = "ed1cc2ffb24b586558e35973dd042429f5d6c65ee55042a3f5a3f066bec93ad9"
BASE_URL = (
    "https://raw.githubusercontent.com/fanserick-star/"
    "recepcion-dr-revelo-updates/main/updates/v4_4_29_payment_method/app.py"
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _looks_like_base(data: bytes) -> bool:
    if hashlib.sha256(data).hexdigest() != BASE_SHA256:
        return False
    return (
        b'APP_VERSION = "4.4.29"' in data
        and b"PAYMENT_SENTINELS" in data
        and b"app = base.app" in data
    )


def _save_base(data: bytes) -> bool:
    if not _looks_like_base(data):
        return False
    tmp = BASE_PATH.with_suffix(".py.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, BASE_PATH)
    return True


def _recover_base_from_backups() -> bool:
    candidates = []
    for folder_name in ("_update_backups", "backups", "_backups"):
        folder = ROOT / folder_name
        if folder.exists():
            try:
                candidates.extend(folder.rglob("app.py"))
                candidates.extend(folder.rglob("*.zip"))
            except Exception:
                pass

    def modified(path: Path) -> float:
        try:
            return path.stat().st_mtime
        except Exception:
            return 0.0

    for path in sorted(set(candidates), key=modified, reverse=True):
        try:
            if path.suffix.lower() == ".zip":
                with zipfile.ZipFile(path) as zf:
                    names = [
                        name for name in zf.namelist()
                        if name.replace("\\", "/").lower().endswith("/app.py")
                        or name.replace("\\", "/").lower() == "app.py"
                    ]
                    for name in names:
                        if _save_base(zf.read(name)):
                            return True
            else:
                if path.resolve() == Path(__file__).resolve():
                    continue
                if _save_base(path.read_bytes()):
                    return True
        except Exception:
            continue
    return False


def _recover_base_from_official_channel() -> bool:
    try:
        req = urllib.request.Request(
            BASE_URL,
            headers={
                "User-Agent": "Recepcion-Dr-Revelo/4.4.30",
                "Cache-Control": "no-cache",
            },
        )
        with urllib.request.urlopen(req, timeout=20) as response:
            data = response.read(2_000_000)
        return _save_base(data)
    except Exception:
        return False


def _ensure_base() -> None:
    try:
        if BASE_PATH.exists() and _sha256(BASE_PATH) == BASE_SHA256:
            return
    except Exception:
        pass
    try:
        BASE_PATH.unlink(missing_ok=True)
    except Exception:
        pass
    if _recover_base_from_backups():
        return
    if _recover_base_from_official_channel():
        return
    raise RuntimeError(
        "No se pudo recuperar el backend estable 4.4.29 para iniciar v4.4.30. "
        "No se modificó ninguna base de datos. Conéctate a Internet y vuelve "
        "a abrir Recepción."
    )


_ensure_base()

import app_base_4429 as prev  # noqa: E402

core = prev.base
app = prev.app
APP_VERSION = "4.4.30"
prev.APP_VERSION = APP_VERSION
core.APP_VERSION = APP_VERSION

# El selector de v4.4.29 estaba dentro de Nueva atención. Lo retiramos del
# overlay sin tocar ninguna atención ya registrada ni su forma de pago.
try:
    core.V460_OVERLAY_CSS = (core.V460_OVERLAY_CSS or "").replace(prev.PAYMENT_CSS, "")
    core.V460_OVERLAY_JS = (core.V460_OVERLAY_JS or "").replace(prev.PAYMENT_JS, "")
except Exception:
    pass


class BillingPaymentChoiceIn(core.BaseModel):
    patient_id: int
    fecha: date
    payment_method: str


def _group_payment_method(rows) -> str | None:
    methods = []
    for _billing, visit in rows:
        method = prev._payment_from_visit(visit)
        if method:
            methods.append(method)
        else:
            return None
    unique = set(methods)
    return next(iter(unique)) if len(unique) == 1 else None


@app.get("/api/billing/payment-methods")
def billing_payment_methods_v4430(user=core.Depends(core.current_user)):
    """Lectura local para pintar el visto de pago sin despertar Neon."""
    with core.LocalSessionLocal() as db:
        rows = db.execute(
            core.select(core.BillingRecord, core.Visit)
            .join(core.Visit, core.BillingRecord.visit_id == core.Visit.id)
            .where(core.BillingRecord.estado.in_(["PENDIENTE", "APROBADA"]))
            .order_by(core.Visit.fecha.desc(), core.Visit.patient_id, core.Visit.id)
        ).all()

        grouped = {}
        for billing, visit in rows:
            key = (int(visit.patient_id), visit.fecha)
            grouped.setdefault(key, []).append((billing, visit))

        items = []
        for (patient_id, fecha), group_rows in grouped.items():
            method = _group_payment_method(group_rows)
            states = {str(b.estado or "").upper() for b, _ in group_rows}
            items.append(
                {
                    "patient_id": patient_id,
                    "fecha": fecha.isoformat() if fecha else "",
                    "payment_method": method or "",
                    "sri_payment_code": prev.SRI_PAYMENT_CODES.get(method, "") if method else "",
                    "ready": bool(method),
                    "state": (
                        "EMITIDA" if "EMITIDA" in states
                        else "APROBADA" if "APROBADA" in states
                        else "PENDIENTE"
                    ),
                }
            )
        return {"items": items, "source": "sqlite-local"}


@app.post("/api/billing/payment-method")
def billing_set_payment_method_v4430(
    data: BillingPaymentChoiceIn,
    db=core.Depends(core.get_db),
    user=core.Depends(core.current_user),
):
    method = prev._normalize_payment_method(data.payment_method)
    sentinel = prev.PAYMENT_SENTINELS[method]

    rows = db.execute(
        core.select(core.Visit, core.BillingRecord)
        .join(core.BillingRecord, core.BillingRecord.visit_id == core.Visit.id)
        .where(
            core.Visit.patient_id == int(data.patient_id),
            core.Visit.fecha == data.fecha,
        )
        .order_by(core.Visit.id)
    ).all()
    if not rows:
        raise core.HTTPException(404, "No se encontró la ficha de facturación.")

    if any(str(b.estado or "").upper() == "EMITIDA" for v, b in rows):
        raise core.HTTPException(
            409,
            "La factura ya fue emitida. La forma de pago no puede cambiarse desde aquí.",
        )
    if not any(str(b.estado or "").upper() == "APROBADA" for v, b in rows):
        raise core.HTTPException(
            409,
            "Primero aprueba la ficha para facturar y luego marca la forma de pago.",
        )

    visits = [visit for visit, _billing in rows]
    for visit in visits:
        visit.source_row = sentinel

    offline = core.is_offline_db(db)
    if offline:
        for visit in visits:
            core.add_queue(
                db,
                "billing.payment_method",
                "visit",
                {
                    "visit_id": int(visit.id),
                    "payment_method": method,
                },
                user.username,
                int(visit.id),
            )

    core.audit(
        db,
        user,
        "forma_pago_facturacion",
        f"Paciente {int(data.patient_id)} · {data.fecha.isoformat()} · {method}",
    )
    db.commit()

    if not offline:
        for visit in visits:
            core.mirror_visit_to_local(visit)

    return {
        "ok": True,
        "patient_id": int(data.patient_id),
        "fecha": data.fecha.isoformat(),
        "payment_method": method,
        "sri_payment_code": prev.SRI_PAYMENT_CODES[method],
        "offline": offline,
    }


# La forma de pago elegida en Facturación también puede quedar en la cola si
# justo en ese momento no hay Internet. Al volver la conexión se aplica al Visit
# definitivo en Neon antes de cualquier emisión.
_previous_sync_one_operation = core.sync_one_operation


def _sync_one_operation_v4430(q, ldb, cdb):
    if getattr(q, "operation", "") != "billing.payment_method":
        return _previous_sync_one_operation(q, ldb, cdb)

    payload = json.loads(q.payload or "{}")
    local_visit_id = int(payload["visit_id"])
    cloud_visit_id = core.resolve_cloud_id(ldb, "visit", local_visit_id)
    visit = cdb.get(core.Visit, cloud_visit_id)
    if visit is None:
        raise RuntimeError(f"Atención {cloud_visit_id} no existe en la nube")

    method = prev._normalize_payment_method(payload.get("payment_method"))
    visit.source_row = prev.PAYMENT_SENTINELS[method]
    core.audit(
        cdb,
        q.username,
        "sincronizar_forma_pago",
        f"Atención {cloud_visit_id}: {method}",
    )
    cdb.add(
        core.SyncOperation(
            token=q.token,
            operation=q.operation,
            result_id=int(cloud_visit_id),
        )
    )
    return int(cloud_visit_id)


core.sync_one_operation = _sync_one_operation_v4430


# Protección final: AZUR nunca recibe una factura sin la elección hecha en la
# ficha. Así evitamos que el valor global 01 convierta accidentalmente una
# transferencia en efectivo.
_previous_azur_payload_for_group = core._azur_payload_for_group


def _azur_payload_for_group_v4430(data, patient, rows):
    methods = []
    for _billing, visit in rows:
        method = prev._payment_from_visit(visit)
        if not method:
            raise core.HTTPException(
                409,
                "Antes de emitir en AZUR, marca Efectivo o Transferencia en la ficha.",
            )
        methods.append(method)
    if len(set(methods)) != 1:
        raise core.HTTPException(
            409,
            "La ficha tiene formas de pago diferentes. Vuelve a marcar una sola forma de pago.",
        )
    return _previous_azur_payload_for_group(data, patient, rows)


core._azur_payload_for_group = _azur_payload_for_group_v4430


BILLING_PAYMENT_CSS = r"""
/* v4.4.30 — forma de pago visible en la ficha aprobada */
.v4430-payment-strip{
  display:grid!important;grid-template-columns:minmax(125px,.7fr) minmax(0,1.3fr)!important;
  gap:10px!important;align-items:center!important;margin:10px 0 0!important;
  padding:10px 11px!important;border:1px solid #dce5ee!important;
  border-radius:11px!important;background:#f8fafc!important
}
.v4430-payment-copy{display:grid!important;gap:2px!important;min-width:0!important}
.v4430-payment-copy b{font-size:10.5px!important;color:#314a64!important}
.v4430-payment-copy small{font-size:8px!important;color:#78899a!important;line-height:1.25!important}
.v4430-payment-choices{display:grid!important;grid-template-columns:repeat(2,minmax(0,1fr))!important;gap:6px!important}
.v4430-pay-btn{
  min-height:35px!important;border:1px solid #cfd9e4!important;border-radius:9px!important;
  background:#fff!important;color:#4b6178!important;font-size:9px!important;font-weight:900!important;
  padding:7px 9px!important;display:flex!important;align-items:center!important;
  justify-content:center!important;gap:6px!important;white-space:nowrap!important
}
.v4430-pay-btn:hover{background:#f2f6fa!important;border-color:#b9c8d8!important}
.v4430-pay-btn .v4430-check{
  width:16px!important;height:16px!important;border-radius:50%!important;border:1px solid #bfcbd7!important;
  display:grid!important;place-items:center!important;font-size:10px!important;color:transparent!important;
  background:#fff!important;flex:0 0 16px!important
}
.v4430-pay-btn.is-selected{
  background:#edf8f1!important;border-color:#83b99a!important;color:#2c6b49!important;
  box-shadow:0 0 0 2px rgba(60,139,91,.08)!important
}
.v4430-pay-btn.is-selected .v4430-check{
  background:#429466!important;border-color:#429466!important;color:#fff!important
}
.v4430-payment-strip.is-required{border-color:#dda64f!important;background:#fffaf0!important}
.v4430-payment-strip.is-saving{opacity:.72!important;pointer-events:none!important}
.v4430-payment-ready{
  display:inline-flex!important;align-items:center!important;gap:4px!important;margin-left:5px!important;
  padding:2px 6px!important;border-radius:999px!important;background:#e9f7ee!important;
  color:#34724d!important;font-size:7px!important;font-weight:950!important
}
@media(max-width:720px){
  .v4430-payment-strip{grid-template-columns:1fr!important}
}
"""

BILLING_PAYMENT_JS = r"""
;(()=>{
  if(window.__v4430BillingPayment)return;
  window.__v4430BillingPayment=true;

  const VERSION='4.4.30';
  const cache=new Map();
  const key=(pid,fecha)=>`${Number(pid)||0}|${String(fecha||'').slice(0,10)}`;

  function fixVersion(){
    const badge=document.querySelector('#currentVersionBadge');
    if(badge)badge.textContent='v'+VERSION;
    document.querySelectorAll('span,b,small,div').forEach(el=>{
      if(el.children.length)return;
      const t=String(el.textContent||'').trim();
      if(/^v4\.4\.(28|29)$/.test(t))el.textContent='v'+VERSION;
    });
  }

  function paymentStrip(pid,fecha){
    return `<div class="v4430-payment-strip" data-v4430-payment="${Number(pid)}|${String(fecha).slice(0,10)}">
      <div class="v4430-payment-copy">
        <b>Forma de pago</b>
        <small>Márcala antes de emitir en AZUR.</small>
      </div>
      <div class="v4430-payment-choices">
        <button type="button" class="v4430-pay-btn" data-method="EFECTIVO"
          onclick="setBillingPayment4430(${Number(pid)},'${String(fecha).slice(0,10)}','EFECTIVO',this)">
          <span class="v4430-check">✓</span><span>💵 Efectivo</span>
        </button>
        <button type="button" class="v4430-pay-btn" data-method="TRANSFERENCIA"
          onclick="setBillingPayment4430(${Number(pid)},'${String(fecha).slice(0,10)}','TRANSFERENCIA',this)">
          <span class="v4430-check">✓</span><span>🏦 Transferencia</span>
        </button>
      </div>
    </div>`;
  }

  function installCardRenderer(){
    const original=window.billingCardHtml;
    if(typeof original!=='function')return false;
    if(original.__v4430Wrapped)return true;

    const wrapped=function(g){
      let html=original.apply(this,arguments);
      try{
        const pid=Number(g?.patient?.id||0);
        const fecha=String(g?.fecha||'').slice(0,10);
        const state=typeof window.billingGroupStatus==='function'
          ? String(window.billingGroupStatus(g)||'').toUpperCase()
          : (()=>{
              const states=(g?.items||[]).map(x=>String(x?.billing?.estado||'').toUpperCase());
              if(states.length&&states.every(x=>x==='EMITIDA'))return 'EMITIDA';
              if(states.some(x=>x==='APROBADA'))return 'APROBADA';
              return 'PENDIENTE';
            })();
        if(pid&&fecha){
          html=html.replace(
            '<article class="billing-card ',
            `<article data-v4430-patient="${pid}" data-v4430-date="${fecha}" class="billing-card `
          );
          if(state==='APROBADA'&&!html.includes('v4430-payment-strip')){
            html=html.replace(
              '<div class="billing-card-foot">',
              paymentStrip(pid,fecha)+'<div class="billing-card-foot">'
            );
          }
        }
      }catch(_e){}
      return html;
    };
    wrapped.__v4430Wrapped=true;
    wrapped.__v4430Original=original;
    window.billingCardHtml=wrapped;
    return true;
  }

  function stripFor(k){
    return [...document.querySelectorAll('.v4430-payment-strip')]
      .find(el=>String(el.dataset.v4430Payment||'')===String(k||''))||null;
  }

  function applyChoice(pid,fecha,method){
    const k=key(pid,fecha);
    if(method)cache.set(k,method);else cache.delete(k);
    const strip=stripFor(k);
    if(!strip)return;
    strip.classList.remove('is-required');
    strip.querySelectorAll('.v4430-pay-btn').forEach(btn=>{
      btn.classList.toggle('is-selected',String(btn.dataset.method||'')===String(method||''));
    });
  }

  async function refreshChoices(){
    installCardRenderer();
    fixVersion();
    try{
      const d=await window.api('/api/billing/payment-methods');
      for(const item of (d?.items||[])){
        const method=String(item?.payment_method||'').toUpperCase();
        const k=key(item?.patient_id,item?.fecha);
        if(method)cache.set(k,method);else cache.delete(k);
      }
      document.querySelectorAll('.v4430-payment-strip').forEach(strip=>{
        const raw=String(strip.dataset.v4430Payment||'');
        const [pid,fecha]=raw.split('|');
        applyChoice(pid,fecha,cache.get(key(pid,fecha))||'');
      });
    }catch(_e){}
  }

  window.setBillingPayment4430=async function(pid,fecha,method,button){
    const k=key(pid,fecha);
    const strip=button?.closest?.('.v4430-payment-strip');
    if(strip?.classList.contains('is-saving'))return;
    strip?.classList.add('is-saving');
    try{
      const d=await window.api('/api/billing/payment-method',{
        method:'POST',
        body:JSON.stringify({
          patient_id:Number(pid),
          fecha:String(fecha).slice(0,10),
          payment_method:String(method||'').toUpperCase()
        })
      });
      const selected=String(d?.payment_method||method||'').toUpperCase();
      cache.set(k,selected);
      applyChoice(pid,fecha,selected);
    }catch(e){
      if(typeof window.rpNotice==='function')window.rpNotice(e?.message||String(e),'Forma de pago');
      else alert(e?.message||String(e));
    }finally{
      strip?.classList.remove('is-saving');
    }
  };

  function installEmitGuard(){
    const original=window.previewAzurInvoice;
    if(typeof original!=='function')return false;
    if(original.__v4430Wrapped)return true;
    const wrapped=async function(pid,fecha){
      const k=key(pid,fecha);
      let method=cache.get(k)||'';
      if(!method){
        try{await refreshChoices();method=cache.get(k)||''}catch(_e){}
      }
      if(!method){
        const strip=stripFor(k);
        strip?.classList.add('is-required');
        try{strip?.scrollIntoView({behavior:'smooth',block:'center'})}catch(_e){}
        if(typeof window.rpNotice==='function'){
          window.rpNotice('Marca Efectivo o Transferencia antes de emitir en AZUR.','Forma de pago');
        }else{
          alert('Marca Efectivo o Transferencia antes de emitir en AZUR.');
        }
        return;
      }
      return original.apply(this,arguments);
    };
    wrapped.__v4430Wrapped=true;
    wrapped.__v4430Original=original;
    window.previewAzurInvoice=wrapped;
    return true;
  }

  function installBillingRefresh(){
    const original=window.loadBilling;
    if(typeof original!=='function')return false;
    if(original.__v4430Wrapped)return true;
    const wrapped=async function(){
      const result=await original.apply(this,arguments);
      setTimeout(refreshChoices,0);
      return result;
    };
    wrapped.__v4430Wrapped=true;
    wrapped.__v4430Original=original;
    window.loadBilling=wrapped;
    return true;
  }

  function install(){
    installCardRenderer();
    installEmitGuard();
    installBillingRefresh();
    fixVersion();
    setTimeout(refreshChoices,80);
  }

  const observer=new MutationObserver(()=>{
    fixVersion();
    installCardRenderer();
    installEmitGuard();
    installBillingRefresh();
  });
  observer.observe(document.documentElement,{childList:true,subtree:true});

  if(document.readyState==='loading'){
    document.addEventListener('DOMContentLoaded',install,{once:true});
  }else{
    install();
  }
})();
"""

core.V460_OVERLAY_CSS = (core.V460_OVERLAY_CSS or "") + "\n" + BILLING_PAYMENT_CSS
core.V460_OVERLAY_JS = (core.V460_OVERLAY_JS or "") + "\n" + BILLING_PAYMENT_JS


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=core.LOCAL_HTTP_PORT,
        reload=False,
        access_log=False,
        log_level="warning",
        workers=1,
    )

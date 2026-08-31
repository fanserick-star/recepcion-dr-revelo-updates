from __future__ import annotations

# v4.4.29 — Forma de pago real por atención sin tocar el histórico.
#
# Esta versión envuelve el backend estable 4.4.28. La primera vez conserva una
# copia verificada del backend base y luego añade únicamente:
#   EFECTIVO -> SRI 01
#   TRANSFERENCIA -> SRI 20
#
# No intenta modificar el estado interno "Pago: Pendiente" de AZUR.

import hashlib
import json
import os
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE_PATH = ROOT / "app_base_4428.py"
BASE_SHA256 = "e5d3d96b9289169aa52524e8cc2f5f0ec9567c8da5e11d482151b12fc8ff85ba"
BASE_URL = (
    "https://raw.githubusercontent.com/fanserick-star/"
    "recepcion-dr-revelo-updates/main/updates/v4_4_28_overlay_hotfix/app.py"
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
        b'APP_VERSION = "4.4.28"' in data
        and b'FastAPI(title="Recepci' in data
    )


def _save_base(data: bytes) -> bool:
    if not _looks_like_base(data):
        return False
    tmp = BASE_PATH.with_suffix(".py.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, BASE_PATH)
    return True


def _recover_base_from_backups() -> bool:
    # Tanto el actualizador del launcher como el actualizador interno conservan
    # copias antes de reemplazar archivos. Revisamos únicamente dentro de la
    # instalación y validamos SHA-256 antes de aceptar cualquier app.py.
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
                "User-Agent": "Recepcion-Dr-Revelo/4.4.29",
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
        "No se pudo recuperar el backend estable 4.4.28 para iniciar v4.4.29. "
        "La actualización no toca las bases de datos; vuelve a conectarte a "
        "Internet y abre Recepción nuevamente."
    )


_ensure_base()

import app_base_4428 as base  # noqa: E402

APP_VERSION = "4.4.29"
base.APP_VERSION = APP_VERSION
app = base.app

PAYMENT_SENTINELS = {
    "EFECTIVO": -442901,
    "TRANSFERENCIA": -442920,
}
SRI_PAYMENT_CODES = {
    "EFECTIVO": "01",
    "TRANSFERENCIA": "20",
}


def _normalize_payment_method(value: object) -> str:
    raw = " ".join(str(value or "").strip().upper().split())
    aliases = {
        "TRANSFERENCIA BANCARIA": "TRANSFERENCIA",
        "BANCO": "TRANSFERENCIA",
        "CASH": "EFECTIVO",
    }
    raw = aliases.get(raw, raw)
    if raw not in PAYMENT_SENTINELS:
        raise base.HTTPException(
            400,
            "Selecciona la forma de pago: Efectivo o Transferencia bancaria.",
        )
    return raw


def _payment_from_visit(visit) -> str | None:
    try:
        value = int(getattr(visit, "source_row", 0) or 0)
    except Exception:
        return None
    for method, sentinel in PAYMENT_SENTINELS.items():
        if value == sentinel:
            return method
    return None


class VisitBatchPaymentIn(base.VisitBatchIn):
    payment_method: str


@app.post("/api/visits/batch-payment")
def create_visit_batch_payment(
    data: VisitBatchPaymentIn,
    db=base.Depends(base.get_db),
    user=base.Depends(base.current_user),
):
    """Registra la atención y su forma real de cobro.

    source_row ya existe en el esquema y las atenciones normales nuevas no lo
    utilizan. Dos valores negativos reservados guardan la forma de pago sin
    añadir columnas ni migraciones a SQLite/Neon.
    """
    method = _normalize_payment_method(data.payment_method)
    sentinel = PAYMENT_SENTINELS[method]

    result = base.create_visit_batch(data, db, user)
    visit_ids = [
        int(item.get("id"))
        for item in (result.get("items") or [])
        if isinstance(item, dict) and item.get("id") is not None
    ]
    visits = []
    for visit_id in visit_ids:
        visit = db.get(base.Visit, visit_id)
        if visit is not None:
            visit.source_row = sentinel
            visits.append(visit)

    # Si la atención se guardó sin Internet, adjuntamos el método al payload de
    # la cola. El wrapper de sync_one_operation lo aplica al ID definitivo de
    # Neon cuando regrese la conexión.
    if base.is_offline_db(db) and visit_ids:
        queued = list(db.scalars(
            base.select(base.OfflineQueue).where(
                base.OfflineQueue.operation == "visit.create",
                base.OfflineQueue.local_entity_id.in_(visit_ids),
            )
        ))
        for row in queued:
            try:
                payload = json.loads(row.payload or "{}")
            except Exception:
                payload = {}
            payload["_payment_method_v4429"] = method
            row.payload = json.dumps(payload, ensure_ascii=False, default=str)

    base.audit(
        db,
        user,
        "registrar_forma_pago",
        f"Atenciones {','.join(map(str, visit_ids)) or 'sin id'}: {method}",
    )
    db.commit()

    if not base.is_offline_db(db):
        for visit in visits:
            base.mirror_visit_to_local(visit)

    result["payment_method"] = method
    result["sri_payment_code"] = SRI_PAYMENT_CODES[method]
    return result


# Sincronización offline: conserva la forma de pago al crear el Visit definitivo
# en Neon, sin cambiar la lógica de IDs/cola del backend estable.
_original_sync_one_operation = base.sync_one_operation


def _sync_one_operation_v4429(q, ldb, cdb):
    payment_method = None
    if getattr(q, "operation", "") == "visit.create":
        try:
            payload = json.loads(q.payload or "{}")
            raw = payload.get("_payment_method_v4429")
            if raw:
                payment_method = _normalize_payment_method(raw)
        except Exception:
            payment_method = None

    result_id = _original_sync_one_operation(q, ldb, cdb)

    if payment_method and result_id is not None:
        visit = cdb.get(base.Visit, int(result_id))
        if visit is not None:
            visit.source_row = PAYMENT_SENTINELS[payment_method]
    return result_id


base.sync_one_operation = _sync_one_operation_v4429


# Facturación AZUR/SRI: reemplaza únicamente el bloque "pagos" que arma 4.4.28.
# Todo lo demás (receptor, ítems, secuencial, autorización y protección contra
# duplicados) sigue siendo exactamente el backend estable.
_original_azur_payload_for_group = base._azur_payload_for_group


def _azur_payload_for_group_v4429(data, patient, rows):
    payload = _original_azur_payload_for_group(data, patient, rows)
    totals: dict[str, float] = {}

    for _billing, visit in rows:
        method = _payment_from_visit(visit)
        code = (
            SRI_PAYMENT_CODES[method]
            if method
            else (str(base.AZUR_FORMA_PAGO or "01").strip() or "01")
        )
        amount = round(float(getattr(visit, "valor", 0) or 0), 2)
        totals[code] = round(totals.get(code, 0.0) + amount, 2)

    if totals:
        payload["pagos"] = [
            {
                "tipo": code,
                "total": amount,
                "tiempo": "dias",
                "plazo": 0,
            }
            for code, amount in sorted(totals.items())
        ]
    return payload


base._azur_payload_for_group = _azur_payload_for_group_v4429


PAYMENT_CSS = r"""
/* v4.4.29 — forma de pago real */
.v4429-payment-card{
  width:100%!important;box-sizing:border-box!important;margin:12px 0!important;
  padding:12px 13px!important;border:1px solid #cfe0f2!important;
  border-radius:13px!important;background:#f7fbff!important;
}
.v4429-payment-head{display:flex;align-items:center;justify-content:space-between;
  gap:10px;margin-bottom:7px}
.v4429-payment-head b{font-size:12px;color:#274866}
.v4429-payment-head span{font-size:8px;font-weight:900;letter-spacing:.08em;
  color:#6b8299;text-transform:uppercase}
.v4429-payment-card select{
  width:100%!important;min-height:43px!important;box-sizing:border-box!important;
  border:1px solid #bfcee0!important;border-radius:10px!important;background:#fff!important;
  color:#243b55!important;padding:8px 10px!important;font-size:11px!important;
  font-weight:850!important;outline:none!important;
}
.v4429-payment-card select:focus{border-color:#6296cb!important;
  box-shadow:0 0 0 3px rgba(72,133,193,.12)!important}
.v4429-payment-card small{display:block;margin-top:6px;font-size:8.5px;
  color:#71859a;line-height:1.3}
.v4429-payment-card.v4429-required{border-color:#d99a42!important;
  background:#fffaf1!important}
"""

PAYMENT_JS = r"""
;(()=>{
  if(window.__v4429PaymentMethod)return;
  window.__v4429PaymentMethod=true;

  let currentForm=null;
  let currentValue='';

  function formNow(){
    return document.querySelector('#modal .attention-form-modal');
  }

  function ensurePaymentField(){
    const form=formNow();
    if(!form)return false;

    if(form!==currentForm){
      currentForm=form;
      currentValue='';
    }

    let card=form.querySelector('.v4429-payment-card');
    if(!card){
      card=document.createElement('section');
      card.className='v4429-payment-card';
      card.innerHTML=`
        <div class="v4429-payment-head">
          <b>Forma de pago</b><span>Obligatorio</span>
        </div>
        <select id="aPaymentMethod" aria-label="Forma de pago">
          <option value="">Selecciona cómo pagó</option>
          <option value="EFECTIVO">💵 Efectivo</option>
          <option value="TRANSFERENCIA">🏦 Transferencia bancaria</option>
        </select>
        <small>Se usará en la factura: efectivo = SRI 01 · transferencia = SRI 20.</small>`;

      const observation=form.querySelector('.attention-observation');
      const actions=form.querySelector('.form-actions,.v492-sticky-actions');
      const services=form.querySelector('.service-groups');
      if(observation)observation.insertAdjacentElement('beforebegin',card);
      else if(actions)actions.insertAdjacentElement('beforebegin',card);
      else if(services)services.insertAdjacentElement('afterend',card);
      else form.appendChild(card);

      const select=card.querySelector('#aPaymentMethod');
      if(currentValue)select.value=currentValue;
      select.addEventListener('change',()=>{
        currentValue=String(select.value||'').trim().toUpperCase();
        card.classList.remove('v4429-required');
      });
    }
    return true;
  }

  function paymentChoice(){
    ensurePaymentField();
    const select=document.querySelector('#modal #aPaymentMethod');
    const value=String(select?.value||'').trim().toUpperCase();
    if(!['EFECTIVO','TRANSFERENCIA'].includes(value)){
      const card=select?.closest('.v4429-payment-card');
      card?.classList.add('v4429-required');
      select?.focus();
      try{select?.scrollIntoView({behavior:'smooth',block:'center'})}catch(_e){}
      throw new Error('Selecciona la forma de pago: Efectivo o Transferencia bancaria.');
    }
    currentValue=value;
    return value;
  }

  function installApiHook(){
    const original=window.api;
    if(typeof original!=='function')return false;
    if(original.__v4429PaymentHook)return true;

    const hooked=async function(url,opt={}){
      const method=String(opt?.method||'GET').toUpperCase();
      if(String(url)==='/api/visits/batch'&&method==='POST'){
        const payment_method=paymentChoice();
        let body={};
        try{body=JSON.parse(String(opt?.body||'{}'))||{}}catch(_e){
          throw new Error('No se pudo preparar la atención para guardar.');
        }
        body.payment_method=payment_method;
        return original.call(
          this,
          '/api/visits/batch-payment',
          {...opt,body:JSON.stringify(body)}
        );
      }
      return original.call(this,url,opt);
    };
    hooked.__v4429PaymentHook=true;
    hooked.__v4429Original=original;
    window.api=hooked;
    return true;
  }

  const observer=new MutationObserver(()=>{
    if(formNow())ensurePaymentField();
    installApiHook();
  });
  observer.observe(document.documentElement,{childList:true,subtree:true});

  document.addEventListener('click',()=>{
    setTimeout(ensurePaymentField,0);
    setTimeout(ensurePaymentField,80);
    setTimeout(ensurePaymentField,220);
  },true);

  if(document.readyState==='loading'){
    document.addEventListener('DOMContentLoaded',()=>{
      installApiHook();setTimeout(ensurePaymentField,120);
    },{once:true});
  }else{
    installApiHook();setTimeout(ensurePaymentField,120);
  }
})();
"""

base.V460_OVERLAY_CSS = (base.V460_OVERLAY_CSS or "") + "\n" + PAYMENT_CSS
base.V460_OVERLAY_JS = (base.V460_OVERLAY_JS or "") + "\n" + PAYMENT_JS


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=base.LOCAL_HTTP_PORT,
        reload=False,
        access_log=False,
        log_level="warning",
        workers=1,
    )

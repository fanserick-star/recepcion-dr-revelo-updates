from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "updates" / "v4_4_50_patient_cache_identity"
OUT = ROOT / "updates" / "v4_4_51_payment_source_of_truth"
VERSION = "4.4.51"


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise RuntimeError(msg)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dump(obj: dict) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


PATCH = r'''
    # -----------------------------------------------------------------------
    # v4.4.51 — forma de pago nace en Nueva atención y llega intacta a SRI.
    # -----------------------------------------------------------------------
    # La pantalla de Facturación ya tenía los botones Efectivo/Transferencia,
    # pero no existía una unión real con Nueva atención. Peor: el frontend
    # pintaba Efectivo como seleccionado aunque no hubiese valor persistido.
    # Esta capa vuelve la atención la fuente de verdad y conserva la posibilidad
    # de corregir el método después en Facturación antes de emitir.

    class V4451VisitBatchPaymentIn(core.VisitBatchIn):
        payment_method: str

    def _v4451_apply_payment_to_group(db, user, patient_id: int, fecha, method: str):
        method = _normalize_payment_method(method)
        sentinel = PAYMENT_SENTINELS[method]
        rows = db.execute(
            core.select(core.Visit, core.BillingRecord)
            .join(core.BillingRecord, core.BillingRecord.visit_id == core.Visit.id)
            .where(
                core.Visit.patient_id == int(patient_id),
                core.Visit.fecha == fecha,
                core.BillingRecord.estado != "EMITIDA",
            )
            .order_by(core.Visit.id)
        ).all()
        if not rows:
            raise core.HTTPException(404, "No se encontró la atención recién guardada para registrar su forma de pago.")

        visits = []
        visit_ids = set()
        for visit, _billing in rows:
            visit.source_row = sentinel
            visits.append(visit)
            visit_ids.add(int(visit.id))

        offline = core.is_offline_db(db)
        if offline and visit_ids:
            # La cola offline debe transportar también la forma de pago. El
            # sincronizador v4.4.51 la aplicará al Visit creado en Neon.
            queued = list(db.scalars(
                core.select(core.OfflineQueue).where(
                    core.OfflineQueue.operation == "visit.create",
                    core.OfflineQueue.local_entity_id.in_(sorted(visit_ids)),
                )
            ))
            for item in queued:
                try:
                    payload = core.json.loads(item.payload or "{}")
                except Exception:
                    payload = {}
                payload["source_row"] = sentinel
                item.payload = core.json.dumps(payload, ensure_ascii=False)

        core.audit(
            db,
            user,
            "registrar_forma_pago_atencion",
            f"Paciente {patient_id}, {fecha}: {method}",
        )
        db.commit()

        if not offline:
            for visit in visits:
                try:
                    core.mirror_visit_to_local(visit)
                except Exception:
                    pass
        return method

    # El sincronizador estable crea primero el Visit remoto. Si la operación
    # offline contiene source_row, lo fijamos en la misma transacción antes del
    # commit que ya hace process_offline_queue.
    _v4451_stable_sync_one_operation = core.sync_one_operation

    def _v4451_sync_one_operation(q, ldb, cdb):
        result_id = _v4451_stable_sync_one_operation(q, ldb, cdb)
        if str(getattr(q, "operation", "") or "") == "visit.create" and result_id is not None:
            try:
                payload = core.json.loads(getattr(q, "payload", "") or "{}")
                source_row = int(payload.get("source_row") or 0)
            except Exception:
                source_row = 0
            if source_row in set(PAYMENT_SENTINELS.values()):
                visit = cdb.get(core.Visit, int(result_id))
                if visit is not None:
                    visit.source_row = source_row
        return result_id

    core.sync_one_operation = _v4451_sync_one_operation

    @app.post("/api/visits/batch-payment")
    def v4451_create_visit_batch_payment(
        data: V4451VisitBatchPaymentIn,
        db=core.Depends(core.get_db),
        user=core.Depends(core.current_user),
    ):
        method = _normalize_payment_method(data.payment_method)
        stable_data = core.VisitBatchIn(
            patient_id=int(data.patient_id),
            fecha=data.fecha,
            tipo=data.tipo,
            services=data.services,
            observacion=data.observacion,
        )
        result = core.create_visit_batch(stable_data, db, user)
        _v4451_apply_payment_to_group(db, user, int(data.patient_id), data.fecha, method)
        if isinstance(result, dict):
            result = dict(result)
            result["payment_method"] = method
            result["sri_payment_code"] = SRI_PAYMENT_CODES[method]
        return result

    V4451_PAYMENT_ATTENTION_JS = r"""
;(()=>{
  if(window.__v4451PaymentSourceOfTruth)return;
  window.__v4451PaymentSourceOfTruth=true;

  let attentionPaymentMethod='';

  function paymentLabel(method){
    return method==='TRANSFERENCIA'?'Transferencia bancaria':method==='EFECTIVO'?'Efectivo':'';
  }

  function renderAttentionPayment(){
    const modal=document.querySelector('.attention-form-modal');
    if(!modal)return;
    let box=modal.querySelector('#v4451AttentionPayment');
    if(!box){
      box=document.createElement('div');
      box.id='v4451AttentionPayment';
      box.className='v4451-attention-payment';
      const obs=modal.querySelector('.attention-observation');
      if(obs)obs.insertAdjacentElement('beforebegin',box);else modal.querySelector('.actions')?.insertAdjacentElement('beforebegin',box);
    }
    const selected=String(attentionPaymentMethod||'');
    box.classList.toggle('required',!selected);
    box.innerHTML=`
      <div class="v4451-pay-head">
        <div><b>Forma de pago</b><small>Obligatorio · se usará después en la factura/SRI.</small></div>
        <span>${selected?`✓ ${paymentLabel(selected)}`:'Sin seleccionar'}</span>
      </div>
      <div class="v4451-pay-options">
        <button type="button" class="v4451-pay-option ${selected==='EFECTIVO'?'selected':''}" onclick="v4451ChooseAttentionPayment('EFECTIVO')"><span>💵</span><b>Efectivo</b><small>SRI 01</small></button>
        <button type="button" class="v4451-pay-option ${selected==='TRANSFERENCIA'?'selected':''}" onclick="v4451ChooseAttentionPayment('TRANSFERENCIA')"><span>🏦</span><b>Transferencia bancaria</b><small>SRI 20</small></button>
      </div>`;
  }

  window.v4451ChooseAttentionPayment=function(method){
    const m=String(method||'').toUpperCase();
    if(!['EFECTIVO','TRANSFERENCIA'].includes(m))return;
    attentionPaymentMethod=m;
    renderAttentionPayment();
  };

  const stableAttentionFor=window.attentionFor;
  if(typeof stableAttentionFor==='function')window.attentionFor=async function(id,draft=null){
    attentionPaymentMethod=String(draft?.paymentMethod||'').toUpperCase();
    if(!['EFECTIVO','TRANSFERENCIA'].includes(attentionPaymentMethod))attentionPaymentMethod='';
    const out=await stableAttentionFor.apply(this,arguments);
    renderAttentionPayment();
    return out;
  };

  const stableSaveAttention=window.saveAttention;
  if(typeof stableSaveAttention==='function')window.saveAttention=async function(id){
    const method=String(attentionPaymentMethod||'').toUpperCase();
    if(!['EFECTIVO','TRANSFERENCIA'].includes(method)){
      const box=document.querySelector('#v4451AttentionPayment');
      box?.classList.add('required');
      try{box?.scrollIntoView({behavior:'smooth',block:'center'})}catch(_e){}
      alert('Selecciona la forma de pago antes de guardar la atención.');
      return;
    }

    const stableApi=window.api||api;
    const intercept=async function(url,opt={}){
      if(String(url)==='/api/visits/batch'){
        let body={};
        try{body=JSON.parse(opt?.body||'{}')}catch(_e){body={}}
        body.payment_method=method;
        return stableApi('/api/visits/batch-payment',{...opt,body:JSON.stringify(body)});
      }
      return stableApi(url,opt);
    };

    // api es una función global mutable en esta aplicación. Se intercepta solo
    // durante el guardado y únicamente cambia /api/visits/batch.
    const previousApi=api;
    try{
      api=intercept;
      return await stableSaveAttention.apply(this,arguments);
    }finally{
      api=previousApi;
    }
  };

  window.__v4451PaymentTest={renderAttentionPayment,getMethod:()=>attentionPaymentMethod};
})();
"""

    V4451_PAYMENT_ATTENTION_CSS = r"""
.v4451-attention-payment{margin:12px 0 14px;padding:12px;border:1px solid #d8e4ef;border-radius:13px;background:#f8fbfe}
.v4451-attention-payment.required{border-color:#dda944;background:#fff9ed;box-shadow:0 0 0 3px rgba(221,169,68,.10)}
.v4451-pay-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:9px}
.v4451-pay-head>div{display:flex;flex-direction:column;gap:2px}.v4451-pay-head b{font-size:10px;color:#254761}.v4451-pay-head small{font-size:8px;color:#75899b}.v4451-pay-head>span{font-size:8px;font-weight:900;color:#55728a}
.v4451-pay-options{display:grid;grid-template-columns:1fr 1fr;gap:8px}.v4451-pay-option{min-height:54px;border:1px solid #ccd9e5!important;border-radius:11px!important;background:#fff!important;color:#3e5c74!important;display:grid!important;grid-template-columns:auto 1fr auto;align-items:center;gap:7px;text-align:left!important;padding:9px 11px!important;box-shadow:none!important}.v4451-pay-option>b{font-size:9px}.v4451-pay-option>small{font-size:8px;color:#7a8c9d}.v4451-pay-option.selected{border-color:#62af84!important;background:#eaf8f0!important;color:#22613d!important;box-shadow:0 0 0 2px rgba(61,143,91,.09)!important}.v4451-pay-option.selected>small{color:#397052}
@media(max-width:720px){.v4451-pay-options{grid-template-columns:1fr}.v4451-pay-head{flex-direction:column}}
"""

    core.V460_OVERLAY_JS = (core.V460_OVERLAY_JS or "") + "\n" + V4451_PAYMENT_ATTENTION_JS
    core.V460_OVERLAY_CSS = (core.V460_OVERLAY_CSS or "") + "\n" + V4451_PAYMENT_ATTENTION_CSS
'''


def main() -> None:
    app_text = (SOURCE / "app.py").read_text(encoding="utf-8-sig")
    require('APP_VERSION = "4.4.50"' in app_text, "La base app no es 4.4.50")
    require("FEATURE_BOOT_OK = True" in app_text, "No se encontró punto de inserción seguro")

    app_text = app_text.replace('APP_VERSION = "4.4.50"', 'APP_VERSION = "4.4.51"', 1)
    app_text = app_text.replace("const VERSION='4.4.50';", "const VERSION='4.4.51';")

    # No mostrar Efectivo seleccionado si el método real aún está vacío.
    old_selected = "const selected=paymentMap.get(key(id.patient_id,id.fecha))||'EFECTIVO';"
    require(old_selected in app_text, "No se encontró el falso default visual de Efectivo")
    app_text = app_text.replace(old_selected, "const selected=paymentMap.get(key(id.patient_id,id.fecha))||'';", 1)

    # La validación de lote también debe revisar el dato real, no un fallback.
    old_missing = "return !(paymentMap.get(key(id.patient_id,id.fecha))||'EFECTIVO');"
    require(old_missing in app_text, "No se encontró cardMissingPayment antiguo")
    app_text = app_text.replace(old_missing, "return !paymentMap.get(key(id.patient_id,id.fecha));", 1)

    # Defensa SRI: si por cualquier razón llega una emisión sin método guardado,
    # no asumir Efectivo silenciosamente.
    old_payload = '            method = _payment_from_visit(visit) or "EFECTIVO"\n            code = SRI_PAYMENT_CODES[method]'
    require(old_payload in app_text, "No se encontró fallback SRI antiguo")
    new_payload = '            method = _payment_from_visit(visit)\n            if not method:\n                raise core.HTTPException(409, "La forma de pago no está registrada. Vuelve a la atención o selecciónala en Facturación antes de emitir.")\n            code = SRI_PAYMENT_CODES[method]'
    app_text = app_text.replace(old_payload, new_payload, 1)

    app_text = app_text.replace("    FEATURE_BOOT_OK = True\n", PATCH + "\n    FEATURE_BOOT_OK = True\n", 1)
    compile(app_text, "app.py", "exec")

    app = app_text.encode("utf-8")
    # Normalizar LF para que SHA local == Raw GitHub también en runner Windows.
    app_base = (SOURCE / "app_base_4428.py").read_text(encoding="utf-8-sig").replace("\r\n", "\n").encode("utf-8")
    launcher_parts = [(SOURCE / f"ABRIR_RECEPCION.part{i}").read_bytes() for i in range(1, 5)]
    launcher = b"".join(launcher_parts)
    compile(app_base.decode("utf-8-sig"), "app_base_4428.py", "exec")
    compile(launcher.decode("utf-8-sig"), "ABRIR_RECEPCION.py", "exec")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "app.py").write_bytes(app)
    (OUT / "app_base_4428.py").write_bytes(app_base)
    for i, data in enumerate(launcher_parts, 1):
        (OUT / f"ABRIR_RECEPCION.part{i}").write_bytes(data)

    manifest = {
        "product": "recepcion-pacientes",
        "version": VERSION,
        "app_version": VERSION,
        "runtime_version": VERSION,
        "launcher_version": "4.4.48-update-before-focus-dependency-safe-1",
        "updater_version": "integrado-en-launcher-update-before-focus",
        "required_dependencies": ["app_base_4428.py"],
        "required_python_packages": [{"import": "pg8000", "pip": "pg8000==1.31.2"}],
        "copy": ["app.py", "app_base_4428.py", "ABRIR_RECEPCION.py", "update_manifest.json"],
    }
    manifest_bytes = dump(manifest)
    (OUT / "update_manifest.json").write_bytes(manifest_bytes)

    raw = "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_51_payment_source_of_truth/"
    candidate = {
        "product": "recepcion-pacientes",
        "version": VERSION,
        "app_version": VERSION,
        "runtime_version": VERSION,
        "mandatory": True,
        "channel": "files-v3",
        "message": (
            "v4.4.51: Nueva atención exige Efectivo o Transferencia sin opción preseleccionada; "
            "el método se guarda con la atención y Facturación lo hereda automáticamente; "
            "se elimina el falso Efectivo visual y SRI ya no asume un método inexistente. "
            "Conserva todos los arreglos de v4.4.50."
        ),
        "files": [
            {"path": "app.py", "url": raw + "app.py", "sha256": sha(app), "encoding": "utf-8"},
            {"path": "app_base_4428.py", "url": raw + "app_base_4428.py", "sha256": sha(app_base), "encoding": "utf-8"},
            {"path": "ABRIR_RECEPCION.py", "parts": [raw + f"ABRIR_RECEPCION.part{i}" for i in range(1, 5)], "sha256": sha(launcher), "encoding": "utf-8"},
            {"path": "update_manifest.json", "url": raw + "update_manifest.json", "sha256": sha(manifest_bytes), "encoding": "utf-8"},
        ],
    }
    (OUT / "candidate_latest.json").write_bytes(dump(candidate))
    print("BUILD_V4451_OK", sha(app), sha(app_base), sha(launcher))


if __name__ == "__main__":
    main()

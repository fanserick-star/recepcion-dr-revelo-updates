from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "updates" / "v4_4_46_phone_guard"
SOURCE_REF = "6fca4c5511054bef790273a81c109f4c05a63717"
SOURCE_PREFIX = "updates/v4_4_45_attention_agenda_identity_fix"
SOURCE_APP_SHA256 = "59d074befb07c7b7b0ffb5ebfc00eed193b8cd367589bf79c12eeeb215d09527"
VERSION = "4.4.46"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise RuntimeError(msg)


def git_bytes(path: str) -> bytes:
    return subprocess.check_output(["git", "show", f"{SOURCE_REF}:{SOURCE_PREFIX}/{path}"], cwd=ROOT)


def dump(obj: dict) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


FEATURE_BLOCK = r'''

    # -----------------------------------------------------------------------
    # v4.4.46 — guardia de celular también al EDITAR / COMPLETAR datos.
    # -----------------------------------------------------------------------
    # v4.4.45 ya evita crear una ficha staged si el celular de la cita pertenece
    # a un paciente existente. Esta capa cubre el hueco restante: la protección
    # visual antigua omitía checkPhone() en editMode. No hay UNIQUE ni migración;
    # solo se comprueba contra OTRAS fichas antes de guardar.
    @app.get("/api/identity/phone-owner")
    def v4446_phone_owner(
        phone: str,
        exclude_id: int = 0,
        db=core.Depends(core.get_db),
        user=core.Depends(core.current_user),
    ):
        normalized = core.normalize_lookup_phone(phone)
        if not normalized or len(normalized) < 9:
            return {"duplicate": False, "patient": None}
        variants = {normalized}
        if len(normalized) == 10 and normalized.startswith("0"):
            variants.add("593" + normalized[1:])
        rows = list(db.scalars(
            core.select(core.Patient)
            .where(core.Patient.celular.in_(sorted(variants)))
            .order_by(core.Patient.id)
        ))
        for patient in rows:
            if int(exclude_id or 0) and int(patient.id) == int(exclude_id):
                continue
            if core.normalize_lookup_phone(patient.celular) == normalized:
                return {
                    "duplicate": True,
                    "patient": {
                        "id": int(patient.id),
                        "nombre": patient.nombre,
                        "cedula": patient.cedula,
                        "celular": patient.celular,
                    },
                    "normalized": normalized,
                }
        return {"duplicate": False, "patient": None, "normalized": normalized}

    V4446_PHONE_GUARD_CSS = r"""
.v4446-phone-duplicate{margin:7px 0 0;padding:10px 11px;border-radius:10px;border:1px solid #e2b66a;background:#fff7e8;color:#6d5223;display:grid;gap:3px}
.v4446-phone-duplicate b{font-size:11px;color:#8a5910}.v4446-phone-duplicate span{font-size:10px;line-height:1.35}.v4446-phone-duplicate small{font-size:9px;color:#806b49}
.v4446-phone-duplicate button{justify-self:start;margin-top:5px;min-height:30px;padding:5px 9px;border:1px solid #c99c50;border-radius:8px;background:#fff;color:#725019;font-size:9px;font-weight:900;cursor:pointer}
"""

    V4446_PHONE_GUARD_JS = r"""
;(()=>{
  if(window.__v4446PhoneDuplicateGuard)return;
  window.__v4446PhoneDuplicateGuard=true;
  let watcherSeq=0,watcherTimer=0,stagedContext=null,lastOwner=null;

  const cleanPhone=v=>String(v||'').replace(/\D/g,'');
  async function phoneOwner(value,excludeId=0){
    const q=cleanPhone(value);if(q.length<9)return null;
    try{
      const d=await api('/api/identity/phone-owner?phone='+encodeURIComponent(q)+'&exclude_id='+Number(excludeId||0));
      return d?.duplicate&&d?.patient?d.patient:null;
    }catch(_e){return null}
  }
  function warningHost(){return $('#fCel')?.closest('.form-field')||$('#fCel')?.parentElement||null}
  function clearWarning(){document.querySelector('#v4446PhoneDuplicateWarning')?.remove();lastOwner=null}
  function renderWarning(owner,allowUse=false){
    clearWarning();if(!owner)return;
    lastOwner=owner;const host=warningHost();if(!host)return;
    const box=document.createElement('div');box.id='v4446PhoneDuplicateWarning';box.className='v4446-phone-duplicate';
    const phone=formatPhoneValue(owner.celular||'')||String(owner.celular||'');
    box.innerHTML=`<b>⚠ Este celular ya está registrado</b><span>${esc(owner.nombre||'Paciente existente')}</span><small>${esc(owner.cedula||'Sin cédula')} · ${esc(phone)}</small>${allowUse?'<button type="button" id="v4446UseExistingPhoneOwner">Usar esta ficha</button>':''}`;
    host.appendChild(box);
    if(allowUse){
      box.querySelector('#v4446UseExistingPhoneOwner')?.addEventListener('click',async()=>{
        const ctx=stagedContext,hit=lastOwner;if(!ctx||!hit)return;
        await usePatientForStaged(Number(ctx.itemId),Number(hit.id),String(ctx.fecha||toISO(new Date())).slice(0,10));
      });
    }
  }
  async function checkVisiblePhone(excludeId=0,allowUse=false){
    const input=$('#fCel');if(!input)return null;
    const seq=++watcherSeq,owner=await phoneOwner(input.value,excludeId);if(seq!==watcherSeq)return null;
    renderWarning(owner,allowUse);return owner;
  }
  function installWatcher(excludeId=0,ctx=null){
    stagedContext=ctx||null;const input=$('#fCel');if(!input)return;
    const allowUse=!!ctx?.itemId;
    const run=()=>{clearTimeout(watcherTimer);watcherTimer=setTimeout(()=>checkVisiblePhone(excludeId,allowUse),220)};
    input.addEventListener('input',run);
    input.addEventListener('blur',()=>checkVisiblePhone(excludeId,allowUse));
    // Fundamental para citas: el celular puede venir precargado y no recibir input.
    setTimeout(()=>checkVisiblePhone(excludeId,allowUse),25);
  }
  async function stopIfDuplicate(excludeId=0,allowUse=false){
    const owner=await checkVisiblePhone(excludeId,allowUse);if(!owner)return false;
    alert(`⚠ Este celular ya está registrado\n\n${owner.nombre||'Paciente existente'}\n${formatPhoneValue(owner.celular||'')||owner.celular||''}\n\nNo se guardó ningún cambio. Revisa o usa la ficha existente.`);
    return true;
  }

  // BUG reportado: Completar datos desde Nueva atención entraba en editMode y
  // el código anterior saltaba la comprobación del número. Aquí se excluye solo
  // el paciente actual, por lo que mantener su propio celular sigue permitido.
  const stableEditFromAttention=window.editPatientFromAttention;
  if(typeof stableEditFromAttention==='function')window.editPatientFromAttention=async function(id){
    const r=await stableEditFromAttention.apply(this,arguments);
    setTimeout(()=>installWatcher(Number(id||0),null),35);
    return r;
  };
  const stableSaveAndReturn=window.savePatientAndReturnToAttention;
  if(typeof stableSaveAndReturn==='function')window.savePatientAndReturnToAttention=async function(id){
    if(await stopIfDuplicate(Number(id||0),false))return;
    return stableSaveAndReturn.apply(this,arguments);
  };

  // La misma defensa se aplica al editor normal de pacientes.
  const stableEditPatient=window.editPatient;
  if(typeof stableEditPatient==='function')window.editPatient=async function(id){
    const r=await stableEditPatient.apply(this,arguments);
    setTimeout(()=>installWatcher(Number(id||0),null),35);
    return r;
  };
  const stableSavePatient=window.savePatient;
  if(typeof stableSavePatient==='function')window.savePatient=async function(id){
    if(await stopIfDuplicate(Number(id||0),false))return;
    return stableSavePatient.apply(this,arguments);
  };

  // Nuevos pacientes: el aviso visual ya existía, pero ahora el guardado queda
  // protegido de verdad para que no dependa de que recepción haya visto el texto.
  const stableNewPatient=window.newPatient;
  if(typeof stableNewPatient==='function')window.newPatient=async function(){
    const r=await stableNewPatient.apply(this,arguments);setTimeout(()=>installWatcher(0,null),35);return r;
  };
  const stableSaveNewPatient=window.saveNewPatient;
  if(typeof stableSaveNewPatient==='function')window.saveNewPatient=async function(){
    if(await stopIfDuplicate(0,false))return;
    return stableSaveNewPatient.apply(this,arguments);
  };

  // Si v4.4.45 deja crear "Es otra persona", el número staged sigue protegido.
  const stableNewFromStaged=window.newPatientFromStaged;
  if(typeof stableNewFromStaged==='function')window.newPatientFromStaged=async function(itemId,fecha){
    const r=await stableNewFromStaged.apply(this,arguments);
    setTimeout(()=>installWatcher(0,{itemId:Number(itemId),fecha:String(fecha||'').slice(0,10)}),35);return r;
  };
  const stableSaveNewFromStaged=window.saveNewPatientFromStaged;
  if(typeof stableSaveNewFromStaged==='function')window.saveNewPatientFromStaged=async function(itemId,fecha){
    stagedContext={itemId:Number(itemId),fecha:String(fecha||'').slice(0,10)};
    if(await stopIfDuplicate(0,true))return;
    return stableSaveNewFromStaged.apply(this,arguments);
  };
  // v4.4.45 había capturado la función original antes de esta capa. Redirigirla
  // garantiza que "Es otra persona" también pase por la guardia nueva.
  if(typeof window.v4445CreateDifferentStaged==='function')window.v4445CreateDifferentStaged=function(itemId,fecha){
    return window.newPatientFromStaged(Number(itemId),String(fecha||toISO(new Date())).slice(0,10));
  };

  const stableSaveFromConfirmafy=window.saveNewPatientFromConfirmafy;
  if(typeof stableSaveFromConfirmafy==='function')window.saveNewPatientFromConfirmafy=async function(){
    if(await stopIfDuplicate(0,false))return;
    return stableSaveFromConfirmafy.apply(this,arguments);
  };

  window.__v4446PhoneGuardTest={phoneOwner,checkVisiblePhone,installWatcher};
})();
"""

    core.V460_OVERLAY_CSS = (core.V460_OVERLAY_CSS or "") + "\n" + V4446_PHONE_GUARD_CSS
    core.V460_OVERLAY_JS = (core.V460_OVERLAY_JS or "") + "\n" + V4446_PHONE_GUARD_JS
'''


def build() -> None:
    app_src = git_bytes("app.py")
    require(sha(app_src) == SOURCE_APP_SHA256, "app.py v4.4.45 cambió respecto al release verificado")
    app_text = app_src.decode("utf-8-sig")
    require(app_text.count('APP_VERSION = "4.4.45"') == 1, "APP_VERSION 4.4.45 ambiguo")
    require('/api/agenda/appointments/guarded' in app_text, "Se perdió guardia semanal de v4.4.44")
    require('_v4445_sync_cloud_agenda_for_dates' in app_text, "Se perdió sync completo de v4.4.45")
    require('window.__v4445StagedIdentityFix' in app_text, "Se perdió identidad staged de v4.4.45")

    app_text = app_text.replace('APP_VERSION = "4.4.45"', 'APP_VERSION = "4.4.46"', 1)
    app_text = app_text.replace("const VERSION='4.4.45';", "const VERSION='4.4.46';")
    app_text = app_text.replace('"const VERSION=\\\'4.4.45\\\';"', '"const VERSION=\\\'4.4.46\\\';"')
    anchor = "\n    FEATURE_BOOT_OK = True\n"
    require(app_text.count(anchor) == 1, "Ancla FEATURE_BOOT_OK ambigua")
    app_text = app_text.replace(anchor, FEATURE_BLOCK + anchor, 1)
    compile(app_text, "app.py", "exec")
    app_bytes = app_text.encode("utf-8")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "app.py").write_bytes(app_bytes)

    manifest = {
        "product": "recepcion-pacientes",
        "version": VERSION,
        "app_version": VERSION,
        "runtime_version": VERSION,
        "launcher_version": "4.4.42-dynamic-port-file-python-dependency-guard-1",
        "updater_version": "integrado-en-launcher",
        "required_dependencies": ["app_base_4428.py"],
        "required_python_packages": [{"import": "pg8000", "pip": "pg8000==1.31.2"}],
        "copy": ["app.py", "update_manifest.json"],
    }
    manifest_bytes = dump(manifest)
    (OUT / "update_manifest.json").write_bytes(manifest_bytes)

    raw = "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_46_phone_guard/"
    candidate = {
        "product": "recepcion-pacientes",
        "version": VERSION,
        "app_version": VERSION,
        "runtime_version": VERSION,
        "mandatory": True,
        "channel": "files-v3",
        "message": (
            "v4.4.46: conserva la agenda completa Cloud/WhatsApp y la reutilización de ficha por celular de v4.4.45, más la protección semanal de citas. "
            "Corrige el caso restante de Nueva atención: al Completar datos o editar una ficha, el celular vuelve a comprobarse contra otros pacientes; si ya está registrado muestra la advertencia y no guarda silenciosamente. "
            "El propio número del paciente se excluye para no generar falsos avisos. No cambia tablas, .env, data, launcher, base ni archivos estáticos."
        ),
        "files": [
            {"path": "app.py", "url": raw + "app.py", "sha256": sha(app_bytes), "encoding": "utf-8"},
            {"path": "update_manifest.json", "url": raw + "update_manifest.json", "sha256": sha(manifest_bytes), "encoding": "utf-8"},
        ],
    }
    (OUT / "candidate_latest.json").write_bytes(dump(candidate))
    print("BUILD_V4446_OK", sha(app_bytes))


if __name__ == "__main__":
    build()

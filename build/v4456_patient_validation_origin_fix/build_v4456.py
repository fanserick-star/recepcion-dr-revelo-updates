from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "updates" / "v4_4_55_patient_dob_error_guard"
OUT = ROOT / "updates" / "v4_4_56_patient_validation_origin_fix"
VERSION = "4.4.56"


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise RuntimeError(msg)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dump(obj: dict) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


FEATURE_PATCH = r'''
    # -----------------------------------------------------------------------
    # v4.4.56 — corregir el origen de [object Object] al crear pacientes.
    # -----------------------------------------------------------------------
    # La interfaz estable usa rpNotice(), no solo window.alert(). Además, el
    # helper API antiguo puede convertir un detail estructurado de FastAPI en
    # Error('[object Object]'). Guardamos el último error HTTP estructurado sin
    # consumir el body original (response.clone) y lo recuperamos al mostrar el
    # aviso. Así la ventana Recepción siempre enseña un texto entendible.
    V4456_PATIENT_ERROR_JS = r"""
;(()=>{
  if(window.__v4456PatientErrorGuard)return;
  window.__v4456PatientErrorGuard=true;
  const FALLBACK='No se pudo guardar el paciente. Revisa los datos e inténtalo nuevamente.';
  const labels={fecha_nacimiento:'Fecha de nacimiento',cedula:'Cédula o identificación',nombre:'Apellidos y nombres',celular:'Celular',correo:'Correo',lugar:'Lugar'};

  function detailLine(item){
    if(item==null)return '';
    if(typeof item==='string')return item.trim();
    if(typeof item!=='object')return String(item);
    const loc=Array.isArray(item.loc)?item.loc:[];
    const key=loc.length?String(loc[loc.length-1]||''):'';
    let msg=typeof item.msg==='string'?item.msg.trim():'';
    if(key==='fecha_nacimiento'&&/valid date|date or datetime|invalid character|date/i.test(msg))msg='Fecha inválida. Usa dd/mm/aaaa.';
    const label=labels[key]||key.replaceAll('_',' ');
    if(label&&msg)return `${label}: ${msg}`;
    if(msg)return msg;
    try{const s=JSON.stringify(item);return s==='{}'?'':s}catch(_e){return ''}
  }

  function structured(value){
    if(value==null)return '';
    if(Array.isArray(value))return value.map(detailLine).filter(Boolean).join('\n');
    if(typeof value==='object'){
      if(Array.isArray(value.detail)){
        const t=value.detail.map(detailLine).filter(Boolean).join('\n');
        if(t)return t;
      }
      if(typeof value.detail==='string'&&value.detail.trim())return value.detail.trim();
      if(value.detail&&typeof value.detail==='object'){
        const t=detailLine(value.detail);if(t)return t;
      }
      if(typeof value.message==='string'){
        const m=value.message.trim();if(m&&m!=='[object Object]')return m;
      }
      try{const s=JSON.stringify(value);if(s&&s!=='{}'&&!s.includes('[object Object]'))return s}catch(_e){}
      return '';
    }
    const t=String(value).trim();return t&&t!=='[object Object]'?t:'';
  }

  function recentServerError(){
    const x=window.__v4456LastHttpError;
    if(!x||Date.now()-Number(x.ts||0)>10000)return '';
    return structured(x.data);
  }

  function readable(value){
    let t=structured(value);
    if(!t||t==='[object Object]')t=recentServerError();
    return t&&t!=='[object Object]'?t:FALLBACK;
  }

  if(typeof window.fetch==='function'&&!window.fetch.__v4456ErrorCapture){
    const previousFetch=window.fetch.bind(window);
    const wrapped=async function(...args){
      const response=await previousFetch(...args);
      if(response&&!response.ok){
        try{
          const data=await response.clone().json();
          window.__v4456LastHttpError={data,ts:Date.now(),url:String(args[0]?.url||args[0]||'')};
        }catch(_e){}
      }
      return response;
    };
    wrapped.__v4456ErrorCapture=true;
    window.fetch=wrapped;
  }

  const previousNotice=typeof window.rpNotice==='function'?window.rpNotice.bind(window):null;
  if(previousNotice){
    window.rpNotice=function(message,title){return previousNotice(readable(message),title)};
  }
  const previousAlert=typeof window.alert==='function'?window.alert.bind(window):null;
  if(previousAlert){
    window.alert=function(message){return previousAlert(readable(message))};
  }
  window.__v4456ReadablePatientError=readable;
})();
"""
    core.V460_OVERLAY_JS = (core.V460_OVERLAY_JS or "") + "\n" + V4456_PATIENT_ERROR_JS
'''


def main() -> None:
    app_text = (SOURCE / "app.py").read_text(encoding="utf-8-sig")
    require('APP_VERSION = "4.4.55"' in app_text, "La base app no es 4.4.55")
    app_text = app_text.replace('APP_VERSION = "4.4.55"', 'APP_VERSION = "4.4.56"', 1)
    app_text = app_text.replace("const VERSION='4.4.55';", "const VERSION='4.4.56';")
    require("    FEATURE_BOOT_OK = True\n" in app_text, "No se encontró punto de inserción de feature")
    app_text = app_text.replace("    FEATURE_BOOT_OK = True\n", FEATURE_PATCH + "\n    FEATURE_BOOT_OK = True\n", 1)
    compile(app_text, "app.py", "exec")

    base_text = (SOURCE / "app_base_4428.py").read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    old_model = "class PatientIn(BaseModel):\n    cedula: Optional[str] = None\n    nombre: str\n    fecha_nacimiento: Optional[date] = None\n"
    new_model = "class PatientIn(BaseModel):\n    cedula: Optional[str] = None\n    nombre: str\n    # v4.4.56: aceptar el texto visual antes de normalizarlo a date.\n    fecha_nacimiento: Optional[str] = None\n"
    require(base_text.count(old_model) == 1, "No se encontró exactamente un PatientIn con date")
    base_text = base_text.replace(old_model, new_model, 1)
    require("def normalize_patient_payload(data) -> dict:" in base_text, "Se perdió normalizador estable de paciente")
    require('values["fecha_nacimiento"] = date.fromisoformat' in base_text, "Se perdió conversión final a date")
    app_base = base_text.encode("utf-8")

    app = app_text.encode("utf-8")
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

    raw = "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_56_patient_validation_origin_fix/"
    candidate = {
        "product": "recepcion-pacientes",
        "version": VERSION,
        "app_version": VERSION,
        "runtime_version": VERSION,
        "mandatory": True,
        "channel": "files-v3",
        "message": "v4.4.56: corrige el origen de [object Object] al crear pacientes, captura el error real de FastAPI y permite normalizar dd/mm/aaaa antes de la validación de fecha. Conserva todo v4.4.55.",
        "files": [
            {"path": "app.py", "url": raw + "app.py", "sha256": sha(app), "encoding": "utf-8"},
            {"path": "app_base_4428.py", "url": raw + "app_base_4428.py", "sha256": sha(app_base), "encoding": "utf-8"},
            {"path": "ABRIR_RECEPCION.py", "parts": [raw + f"ABRIR_RECEPCION.part{i}" for i in range(1, 5)], "sha256": sha(launcher), "encoding": "utf-8"},
            {"path": "update_manifest.json", "url": raw + "update_manifest.json", "sha256": sha(manifest_bytes), "encoding": "utf-8"},
        ],
    }
    (OUT / "candidate_latest.json").write_bytes(dump(candidate))
    print("BUILD_V4456_OK", sha(app), sha(app_base), sha(launcher))


if __name__ == "__main__":
    main()

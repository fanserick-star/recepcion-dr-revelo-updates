from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "updates" / "v4_4_54_slot_event_capture"
OUT = ROOT / "updates" / "v4_4_55_patient_dob_error_guard"
VERSION = "4.4.55"


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise RuntimeError(msg)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dump(obj: dict) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


TOP_PATCH = r'''

def _v4455_normalize_birth_date_text(value: object) -> str | None:
    """Acepta fecha ISO o la forma visual ecuatoriana dd/mm/aaaa sin invertir día/mes."""
    text = str(value or "").strip()
    if not text:
        return None
    if _re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        try:
            return _date.fromisoformat(text).isoformat()
        except ValueError as exc:
            raise ValueError("Fecha de nacimiento inválida. Revisa día, mes y año.") from exc
    m = _re.fullmatch(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})", text)
    if not m:
        raise ValueError("Fecha de nacimiento inválida. Usa dd/mm/aaaa.")
    dd, mm, yyyy = (int(x) for x in m.groups())
    try:
        return _date(yyyy, mm, dd).isoformat()
    except ValueError as exc:
        raise ValueError("Fecha de nacimiento inválida. Revisa día, mes y año.") from exc
'''


FEATURE_PATCH = r'''
    # -----------------------------------------------------------------------
    # v4.4.55 — fecha de nacimiento robusta + errores legibles.
    # -----------------------------------------------------------------------
    # El input visual puede verse como dd/mm/aaaa y algunos WebView/navegadores
    # pueden entregar esa representación al flujo de guardado. La base estable
    # llamaba date.fromisoformat directamente, que solo admite aaaa-mm-dd.
    # Normalizamos ambas representaciones antes de entrar al guardado estable.
    _v4455_stable_normalize_patient_payload = core.normalize_patient_payload

    def _v4455_normalize_patient_payload(data):
        target = data
        raw = getattr(data, "fecha_nacimiento", None)
        if isinstance(raw, str) and raw.strip():
            try:
                normalized = _v4455_normalize_birth_date_text(raw)
            except ValueError as exc:
                raise core.HTTPException(400, str(exc)) from exc
            if normalized and normalized != raw.strip():
                if hasattr(data, "model_copy"):
                    target = data.model_copy(update={"fecha_nacimiento": normalized})
                elif hasattr(data, "copy"):
                    target = data.copy(update={"fecha_nacimiento": normalized})
                else:
                    try:
                        setattr(data, "fecha_nacimiento", normalized)
                    except Exception:
                        pass
        try:
            return _v4455_stable_normalize_patient_payload(target)
        except ValueError as exc:
            # Nunca filtrar al navegador un ValueError técnico de fecha.
            if "date" in str(exc).lower() or "isoformat" in str(exc).lower():
                raise core.HTTPException(400, "Fecha de nacimiento inválida. Usa dd/mm/aaaa.") from exc
            raise

    core.normalize_patient_payload = _v4455_normalize_patient_payload

    V4455_READABLE_ERRORS_JS = r"""
;(()=>{
  if(window.__v4455ReadableErrors)return;
  window.__v4455ReadableErrors=true;
  const originalAlert=typeof window.alert==='function'?window.alert.bind(window):null;

  function readable(value){
    if(value==null)return 'Error inesperado.';
    if(typeof value==='string'){
      const t=value.trim();
      return t&&t!=='[object Object]'?t:'No se pudo guardar. Revisa los datos e inténtalo nuevamente.';
    }
    const detail=value?.detail;
    if(Array.isArray(detail)){
      const lines=detail.map(x=>{
        if(typeof x==='string')return x;
        if(x&&typeof x.msg==='string')return x.msg;
        try{return JSON.stringify(x)}catch(_e){return String(x)}
      }).filter(Boolean);
      if(lines.length)return lines.join('\n');
    }
    if(typeof detail==='string'&&detail.trim())return detail.trim();
    if(detail&&typeof detail==='object'){
      if(typeof detail.msg==='string')return detail.msg;
      try{const s=JSON.stringify(detail);if(s&&s!=='{}'&&!s.includes('[object Object]'))return s}catch(_e){}
    }
    if(typeof value?.message==='string'){
      const m=value.message.trim();
      if(m&&m!=='[object Object]')return m;
      if(m==='[object Object]')return 'No se pudo guardar. Revisa los datos e inténtalo nuevamente.';
    }
    try{const s=JSON.stringify(value);if(s&&s!=='{}'&&!s.includes('[object Object]'))return s}catch(_e){}
    return 'No se pudo guardar. Revisa los datos e inténtalo nuevamente.';
  }

  if(originalAlert){
    window.alert=function(message){return originalAlert(readable(message))};
  }
  window.__v4455ReadableErrorText=readable;
})();
"""
    core.V460_OVERLAY_JS = (core.V460_OVERLAY_JS or "") + "\n" + V4455_READABLE_ERRORS_JS
'''


def main() -> None:
    app_text = (SOURCE / "app.py").read_text(encoding="utf-8-sig")
    require('APP_VERSION = "4.4.54"' in app_text, "La base app no es 4.4.54")
    app_text = app_text.replace('APP_VERSION = "4.4.54"', 'APP_VERSION = "4.4.55"', 1)
    app_text = app_text.replace("const VERSION='4.4.54';", "const VERSION='4.4.55';")

    # Helper puro, antes del bloque try de mejoras.
    require("import traceback\n" in app_text, "No se encontró bloque de imports")
    app_text = app_text.replace("import traceback\n", "import traceback\nimport re as _re\n", 1)
    marker = "\n\nclass BillingPaymentMethodIn(core.BaseModel):"
    require(marker in app_text, "No se encontró punto para helper de fecha")
    app_text = app_text.replace(marker, TOP_PATCH + marker, 1)

    require("    FEATURE_BOOT_OK = True\n" in app_text, "No se encontró punto de inserción de feature")
    app_text = app_text.replace("    FEATURE_BOOT_OK = True\n", FEATURE_PATCH + "\n    FEATURE_BOOT_OK = True\n", 1)
    compile(app_text, "app.py", "exec")

    app = app_text.encode("utf-8")
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

    raw = "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_55_patient_dob_error_guard/"
    candidate = {
        "product": "recepcion-pacientes",
        "version": VERSION,
        "app_version": VERSION,
        "runtime_version": VERSION,
        "mandatory": True,
        "channel": "files-v3",
        "message": "v4.4.55: fecha de nacimiento acepta dd/mm/aaaa o aaaa-mm-dd sin invertir día/mes y los errores de validación se muestran de forma legible. Conserva todo v4.4.54.",
        "files": [
            {"path": "app.py", "url": raw + "app.py", "sha256": sha(app), "encoding": "utf-8"},
            {"path": "app_base_4428.py", "url": raw + "app_base_4428.py", "sha256": sha(app_base), "encoding": "utf-8"},
            {"path": "ABRIR_RECEPCION.py", "parts": [raw + f"ABRIR_RECEPCION.part{i}" for i in range(1, 5)], "sha256": sha(launcher), "encoding": "utf-8"},
            {"path": "update_manifest.json", "url": raw + "update_manifest.json", "sha256": sha(manifest_bytes), "encoding": "utf-8"},
        ],
    }
    (OUT / "candidate_latest.json").write_bytes(dump(candidate))
    print("BUILD_V4455_OK", sha(app), sha(app_base), sha(launcher))


if __name__ == "__main__":
    main()

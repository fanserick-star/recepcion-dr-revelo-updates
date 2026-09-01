from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "updates" / "v4_4_43_daily_emitted_whatsapp_schedule"
OUT.mkdir(parents=True, exist_ok=True)

SOURCE_REF = "5d219d0451b1998e9adf5299134c6d62a87bd059"
SOURCE_PREFIX = "updates/v4_4_42_python_dependency_guard"
VERSION = "4.4.43"
APP_VERSION = "4.4.43"
SOURCE_LAUNCHER_SHA = "39ee0e178c9f86387b220905f2f8612f6c61e721a928fd8ed3ca514a639b007e"
EXPECTED = {
    "app_base_4428.py": "e5d3d96b9289169aa52524e8cc2f5f0ec9567c8da5e11d482151b12fc8ff85ba",
    "app.py": "2d8c6bac37a603c911b9fca6848e839b00b6b7975cf13fd9c3088c4542e4508e",
    "static/app.js": "0657c3b76721df2e28ec812856a2fc25944d2908382b13fbf3f115dad3e18d90",
    "static/index.html": "16d30060a0be19215e612c4ba897e801873dd359712e90d4dc14e32513b25728",
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dump(obj: dict) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise RuntimeError(msg)


def git_bytes(path: str) -> bytes:
    return subprocess.check_output(["git", "show", f"{SOURCE_REF}:{SOURCE_PREFIX}/{path}"], cwd=ROOT)


FEATURE_BLOCK = r'''

    # -----------------------------------------------------------------------
    # v4.4.43 — EMITIDAS: Hoy / Últimos 7 días + horario exacto WhatsApp
    # -----------------------------------------------------------------------
    # La automatización ya calcula `due_at`; solo convertimos ese mismo valor
    # en un texto legible. No se duplica ni se cambia la lógica de envío.
    _v4443_base_wa_timeline_defs = core._wa_timeline_defs

    def _v4443_planned_label(raw_due_at: object) -> str:
        raw = str(raw_due_at or "").strip()
        if not raw:
            return ""
        try:
            dt = core.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            return ""
        dias = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")
        meses = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")
        hour = dt.hour % 12 or 12
        ampm = "a. m." if dt.hour < 12 else "p. m."
        return f"Se enviará: {dias[dt.weekday()]} {dt.day} {meses[dt.month - 1]} · {hour}:{dt.minute:02d} {ampm}"

    def _wa_timeline_defs_v4443(fecha, hora, created_at=None):
        items = _v4443_base_wa_timeline_defs(fecha, hora, created_at)
        for item in items:
            if not isinstance(item, dict):
                continue
            planned = _v4443_planned_label(item.get("due_at"))
            if planned:
                item["planned"] = planned
        return items

    core._wa_timeline_defs = _wa_timeline_defs_v4443

    V4443_UI_CSS = r"""
#facturacion .v4443-emitted-range{
  display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;
  margin:4px 0 12px;padding:8px 10px;border:1px solid #dce6f0;border-radius:12px;background:#f8fbfe
}
#facturacion .v4443-emitted-range>span{font-size:9px;font-weight:900;letter-spacing:.04em;text-transform:uppercase;color:#6a8096}
#facturacion .v4443-emitted-range-buttons{display:flex;gap:5px;flex-wrap:wrap}
#facturacion .v4443-emitted-range button{min-height:31px;padding:6px 10px;border:1px solid #cfdae6;border-radius:9px;background:#fff;color:#4d657e;font-size:9px;font-weight:900;cursor:pointer}
#facturacion .v4443-emitted-range button.active{border-color:#79a7d5;background:#eaf4ff;color:#245b91;box-shadow:0 0 0 2px rgba(70,128,187,.08)}
#facturacion .v4443-emitted-empty{padding:22px 16px;border:1px dashed #cfdae6;border-radius:12px;text-align:center;color:#71849a;background:#fbfcfe;font-size:11px}
.native-appointment-detail .v459-wa-copy>small{display:block!important;margin-top:3px!important;font-size:11px!important;line-height:1.3!important;font-weight:750!important;color:#5f748b!important}
@media(max-width:720px){#facturacion .v4443-emitted-range{align-items:stretch}#facturacion .v4443-emitted-range>span{width:100%}.v4443-emitted-range-buttons{width:100%}#facturacion .v4443-emitted-range button{flex:1}}
"""

    V4443_UI_JS = r"""
;(()=>{
  if(window.__v4443DailyEmitted)return;
  window.__v4443DailyEmitted=true;
  let emittedRange='today';

  const state=()=>String(document.querySelector('#bEstado')?.value||'PENDIENTE').toUpperCase();
  const isoLocal=d=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
  const todayIso=()=>isoLocal(new Date());
  const weekStartIso=()=>{const d=new Date();d.setHours(12,0,0,0);d.setDate(d.getDate()-6);return isoLocal(d)};
  const groups=()=>{try{return Array.isArray(billingGroupsCache)?billingGroupsCache:[]}catch(_e){return []}};

  function visibleGroups(mode=emittedRange){
    const all=groups(),today=todayIso(),start=weekStartIso();
    return all.filter(g=>{
      const f=String(g?.fecha||'').slice(0,10);
      return mode==='week' ? (f>=start&&f<=today) : f===today;
    });
  }

  function ensureBar(){
    const list=document.querySelector('#billingList');
    let bar=document.getElementById('v4443EmittedRange');
    if(!list||state()!=='EMITIDA'){
      bar?.remove();
      return null;
    }
    if(!bar){
      bar=document.createElement('div');
      bar.id='v4443EmittedRange';
      bar.className='v4443-emitted-range';
      list.parentElement?.insertBefore(bar,list);
    }
    const todayCount=visibleGroups('today').length,weekCount=visibleGroups('week').length;
    bar.innerHTML=`<span>Facturas emitidas</span><div class="v4443-emitted-range-buttons"><button type="button" data-range="today" class="${emittedRange==='today'?'active':''}">Hoy · ${todayCount}</button><button type="button" data-range="week" class="${emittedRange==='week'?'active':''}">Últimos 7 días · ${weekCount}</button></div>`;
    bar.querySelectorAll('button[data-range]').forEach(btn=>btn.addEventListener('click',()=>{
      emittedRange=btn.dataset.range==='week'?'week':'today';
      renderEmittedRange();
    }));
    return bar;
  }

  function renderEmittedRange(){
    if(state()!=='EMITIDA'){ensureBar();return}
    const list=document.querySelector('#billingList');if(!list)return;
    ensureBar();
    const visible=visibleGroups();
    try{
      list.innerHTML=visible.length
        ?visible.map(g=>billingCardHtml(g)).join('')
        :`<div class="v4443-emitted-empty">${emittedRange==='week'?'No hay facturas emitidas en los últimos 7 días.':'No hay facturas emitidas hoy.'}</div>`;
    }catch(_e){}
  }

  const oldLoad=window.loadBilling;
  if(typeof oldLoad==='function'){
    window.loadBilling=async function(){
      const result=await oldLoad.apply(this,arguments);
      if(state()==='EMITIDA')renderEmittedRange();else ensureBar();
      return result;
    };
  }

  const oldSet=window.setBillingStatus;
  if(typeof oldSet==='function'){
    window.setBillingStatus=async function(next){
      if(String(next||'').toUpperCase()==='EMITIDA')emittedRange='today';
      const result=await oldSet.apply(this,arguments);
      if(state()==='EMITIDA')renderEmittedRange();else ensureBar();
      return result;
    };
  }

  window.__v4443EmittedRangeTest={visibleGroups,renderEmittedRange,setRange:v=>{emittedRange=v==='week'?'week':'today';renderEmittedRange()},getRange:()=>emittedRange};
})();
"""

    core.V460_OVERLAY_CSS = (core.V460_OVERLAY_CSS or "") + "\n" + V4443_UI_CSS
    core.V460_OVERLAY_JS = (core.V460_OVERLAY_JS or "") + "\n" + V4443_UI_JS
'''


def split_four(data: bytes) -> list[bytes]:
    text = data.decode("utf-8-sig")
    lines = text.splitlines(keepends=True)
    target = max(1, len(text) // 4)
    chunks, buf, n = [], [], 0
    for line in lines:
        if len(chunks) < 3 and buf and n + len(line) > target:
            chunks.append("".join(buf).encode("utf-8")); buf=[]; n=0
        buf.append(line); n += len(line)
    chunks.append("".join(buf).encode("utf-8"))
    while len(chunks) < 4: chunks.append(b"")
    require(len(chunks)==4 and b"".join(chunks).decode("utf-8")==text, "Partición launcher inválida")
    return chunks


def build() -> None:
    launcher = b"".join(git_bytes(f"ABRIR_RECEPCION.part{i}") for i in range(1,5))
    require(sha(launcher)==SOURCE_LAUNCHER_SHA, "Launcher 4.4.42 cambió")
    launcher_text=launcher.decode("utf-8-sig")
    require('4.4.42-dynamic-port-file-python-dependency-guard-1' in launcher_text, "No es launcher 4.4.42")
    require("_rp_ensure_python_runtime" in launcher_text and "_rp_diag_upload_via_venv" in launcher_text and "_choose_app_port" in launcher_text, "Se perdió blindaje del launcher")

    fixed={}
    for rel,expected in EXPECTED.items():
        data=git_bytes(rel)
        require(sha(data)==expected, f"Fuente 4.4.42 cambió: {rel}")
        fixed[rel]=data

    app_text=fixed["app.py"].decode("utf-8-sig")
    require(app_text.count('APP_VERSION = "4.4.36"')==1, "APP_VERSION fuente inesperada")
    app_text=app_text.replace('APP_VERSION = "4.4.36"','APP_VERSION = "4.4.43"',1)
    app_text=app_text.replace("const VERSION='4.4.36';","const VERSION='4.4.43';")
    app_text=app_text.replace('"const VERSION=\'4.4.36\';"','"const VERSION=\'4.4.43\';"')
    anchor="\n    FEATURE_BOOT_OK = True\n"
    require(app_text.count(anchor)==1, "Ancla de features cambió")
    app_text=app_text.replace(anchor, FEATURE_BLOCK + anchor, 1)
    compile(app_text,"app.py","exec")
    app_bytes=app_text.encode("utf-8")
    require("_wa_timeline_defs_v4443" in app_text and "Se enviará:" in app_text, "Falta horario exacto WhatsApp")
    require("__v4443DailyEmitted" in app_text and "Últimos 7 días" in app_text, "Falta filtro emitidas")
    require("method = _payment_from_visit(visit) or \"EFECTIVO\"" in app_text, "Se perdió Efectivo por defecto")
    require("core._azur_payload_for_group = _azur_payload_for_group_v4431" in app_text, "Se perdió mapeo AZUR")

    OUT.mkdir(parents=True,exist_ok=True)
    for i,part in enumerate(split_four(launcher),1):(OUT/f"ABRIR_RECEPCION.part{i}").write_bytes(part)
    (OUT/"app_base_4428.py").write_bytes(fixed["app_base_4428.py"])
    (OUT/"app.py").write_bytes(app_bytes)
    (OUT/"static").mkdir(exist_ok=True)
    (OUT/"static/app.js").write_bytes(fixed["static/app.js"])
    (OUT/"static/index.html").write_bytes(fixed["static/index.html"])

    paths=["ABRIR_RECEPCION.py","app_base_4428.py","app.py","static/app.js","static/index.html","update_manifest.json"]
    inner={
        "product":"recepcion-pacientes","version":VERSION,"app_version":APP_VERSION,"runtime_version":APP_VERSION,
        "launcher_version":"4.4.42-dynamic-port-file-python-dependency-guard-1","updater_version":"integrado-en-launcher",
        "required_dependencies":["app_base_4428.py"],
        "required_python_packages":[{"import":"pg8000","pip":"pg8000==1.31.2"}],
        "copy":paths,
    }
    inner_bytes=dump(inner);(OUT/"update_manifest.json").write_bytes(inner_bytes)
    raw="https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_43_daily_emitted_whatsapp_schedule/"
    files=[
      {"path":"ABRIR_RECEPCION.py","parts":[raw+f"ABRIR_RECEPCION.part{i}" for i in range(1,5)],"sha256":sha(launcher),"encoding":"utf-8"},
      {"path":"app_base_4428.py","url":raw+"app_base_4428.py","sha256":sha(fixed["app_base_4428.py"]),"encoding":"utf-8"},
      {"path":"app.py","url":raw+"app.py","sha256":sha(app_bytes),"encoding":"utf-8"},
      {"path":"static/app.js","url":raw+"static/app.js","sha256":sha(fixed["static/app.js"]),"encoding":"utf-8"},
      {"path":"static/index.html","url":raw+"static/index.html","sha256":sha(fixed["static/index.html"]),"encoding":"utf-8"},
      {"path":"update_manifest.json","url":raw+"update_manifest.json","sha256":sha(inner_bytes),"encoding":"utf-8"},
    ]
    candidate={
      "product":"recepcion-pacientes","version":VERSION,"app_version":APP_VERSION,"runtime_version":APP_VERSION,
      "mandatory":True,"channel":"files-v3",
      "message":"v4.4.43: Facturación EMITIDAS abre mostrando solo Hoy y permite cambiar a Últimos 7 días. En Agenda, los mensajes WhatsApp PROGRAMADOS muestran debajo la fecha y hora exactas calculadas por el mismo due_at de la automatización. Conserva Efectivo por defecto, emisión AZUR, diagnóstico automático, puertos dinámicos y reparación de pg8000. No modifica .env, data, pacientes, citas, facturas ni bases locales.",
      "files":files,
    }
    (OUT/"candidate_latest.json").write_bytes(dump(candidate))
    print("BUILD_V4443_OK")
    print("APP_SHA",sha(app_bytes))
    print("LAUNCHER_SHA",sha(launcher))

if __name__=="__main__":build()

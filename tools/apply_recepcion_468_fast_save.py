from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "recepcion" / "app"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise RuntimeError(f"No se encontró bloque esperado: {label}")
    return text.replace(old, new, 1)


def patch_core() -> None:
    path = APP / "core_runtime.py"
    s = path.read_text(encoding="utf-8")
    read_block = '''def _prefer_local_read(request: Request) -> bool:\n    if request.method.upper() != "GET":\n        return False\n    if str(request.query_params.get("fresh") or "").strip() == "1":\n        return False\n    path = request.url.path\n    return any(path == prefix or path.startswith(prefix + "/") for prefix in LOCAL_FIRST_GET_PREFIXES)\n'''
    write_block = read_block + '''\n\n# v4.6.8: guardar una atención nunca espera a Neon. Se confirma primero en\n# SQLite y la cola offline ya existente la replica después a la nube. La\n# impresión de la atención recién creada también lee SQLite para conservar el\n# mismo ID local aunque la réplica a Neon esté ocurriendo en paralelo.\nLOCAL_FIRST_WRITE_PATHS = {"/api/visits/batch", "/api/visits/batch-payment"}\nLOCAL_FIRST_POST_PREFIXES = ("/api/v4470/print-visit/",)\n\n\ndef _prefer_local_write(request: Request) -> bool:\n    if request.method.upper() != "POST":\n        return False\n    path = request.url.path\n    return path in LOCAL_FIRST_WRITE_PATHS or any(path.startswith(prefix) for prefix in LOCAL_FIRST_POST_PREFIXES)\n'''
    if "LOCAL_FIRST_WRITE_PATHS" not in s:
        s = replace_once(s, read_block, write_block, "preferencia local de escritura")
    elif "LOCAL_FIRST_POST_PREFIXES" not in s:
        old = '''LOCAL_FIRST_WRITE_PATHS = {"/api/visits/batch", "/api/visits/batch-payment"}\n\n\ndef _prefer_local_write(request: Request) -> bool:\n    return request.method.upper() == "POST" and request.url.path in LOCAL_FIRST_WRITE_PATHS\n'''
        new = '''LOCAL_FIRST_WRITE_PATHS = {"/api/visits/batch", "/api/visits/batch-payment"}\nLOCAL_FIRST_POST_PREFIXES = ("/api/v4470/print-visit/",)\n\n\ndef _prefer_local_write(request: Request) -> bool:\n    if request.method.upper() != "POST":\n        return False\n    path = request.url.path\n    return path in LOCAL_FIRST_WRITE_PATHS or any(path.startswith(prefix) for prefix in LOCAL_FIRST_POST_PREFIXES)\n'''
        s = replace_once(s, old, new, "impresión local por ID local")

    old = '''    pending = queue_count()\n    if pending > 0 or _prefer_local_read(request):\n        use_cloud = False\n    else:\n        online = check_cloud()\n        use_cloud = bool(online and CloudSessionLocal)\n    factory = CloudSessionLocal if use_cloud else LocalSessionLocal\n    db = factory()\n    db.info["offline"] = not use_cloud\n    db.info["local_first"] = bool(not use_cloud and pending == 0 and _prefer_local_read(request))\n'''
    new = '''    pending = queue_count()\n    local_write = _prefer_local_write(request)\n    local_read = _prefer_local_read(request)\n    if pending > 0 or local_read or local_write:\n        use_cloud = False\n    else:\n        online = check_cloud()\n        use_cloud = bool(online and CloudSessionLocal)\n    factory = CloudSessionLocal if use_cloud else LocalSessionLocal\n    db = factory()\n    db.info["offline"] = not use_cloud\n    db.info["local_first"] = bool(not use_cloud and pending == 0 and local_read)\n    db.info["local_first_write"] = bool(local_write)\n'''
    if old in s:
        s = replace_once(s, old, new, "get_db local-first attention")
    path.write_text(s, encoding="utf-8")


def patch_identity() -> None:
    path = APP / "reception_history_identity_authority.py"
    s = path.read_text(encoding="utf-8")
    if "const identityCache=new Map();" not in s:
        s = replace_once(
            s,
            "  let panelTimer=0;\n",
            "  let panelTimer=0;\n  const identityCache=new Map();\n  const identityPending=new Map();\n",
            "cache de identidad",
        )

    helper = r'''  function startIdentityPrepare(pid){
    pid=Number(pid||patientIdFromModal()||0);if(!pid)return Promise.resolve(null);
    const cached=identityCache.get(pid);
    if(cached&&Date.now()-Number(cached.at||0)<60000)return Promise.resolve(cached.data||null);
    if(identityPending.has(pid))return identityPending.get(pid);
    const call=apiBase();if(typeof call!=='function')return Promise.resolve(null);
    const task=Promise.resolve(call('/api/historia-identity/prepare/'+pid,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}))
      .then(d=>{
        identityCache.set(pid,{at:Date.now(),data:d||null});
        if(d&&d.ok!==false){panel(d,pid);warnings(d)}
        return d||null;
      })
      .catch(()=>{identityCache.set(pid,{at:Date.now(),data:{ok:false,linked:false}});return null})
      .finally(()=>identityPending.delete(pid));
    identityPending.set(pid,task);
    return task;
  }

'''
    if "function startIdentityPrepare(pid)" not in s:
        s = replace_once(s, "  function installSaveGate(){\n", helper + "  function installSaveGate(){\n", "prefetch de identidad")

    pattern = re.compile(r"  function installSaveGate\(\)\{.*?\n  function installPatientSync", re.S)
    replacement = r'''  function installSaveGate(){
    const base=window.saveAttention;
    if(typeof base!=='function'||base.__v468HistoryGate)return false;
    const wrapped=async function(patientId){
      const pid=Number(patientId||patientIdFromModal()||0);
      const apiBefore=window.api;
      const globalBefore=(()=>{try{return api}catch(_e){return null}})();
      let blocked=false;
      const gate=async function(url,opt={}){
        const u=String(url||'');
        if((u==='/api/visits/batch-payment'||u==='/api/visits/batch')&&pid){
          let body={};try{body=JSON.parse(String(opt?.body||'{}'))}catch(_e){}
          const isSub=norm(body?.tipo)==='S'||norm(body?.tipo)==='SUBSECUENTE';
          const cached=identityCache.get(pid)?.data||null;
          if(isSub&&cached&&cached.ok!==false&&!cached.linked){
            blocked=true;
            showSearch(pid,cached?.reception_name||'');
            const err=new Error('__HISTORIA_LINK_REQUIRED__');err.__historiaLinkRequired=true;throw err;
          }
          // Nunca esperamos a Historia dentro del clic Guardar. Si todavía no
          // terminó el prefetch, la vinculación continúa en segundo plano y puede
          // reparar waiting_queue después de guardar.
          startIdentityPrepare(pid);
        }
        return apiBefore.apply(this,arguments);
      };
      gate.__v468Base=apiBase()||apiBefore;
      try{
        window.api=gate;try{api=gate}catch(_e){}
        return await base.apply(this,arguments);
      }catch(e){
        if(blocked||e?.__historiaLinkRequired||String(e?.message||'').includes('__HISTORIA_LINK_REQUIRED__'))return;
        throw e;
      }finally{
        window.api=apiBefore;try{api=globalBefore||apiBefore}catch(_e){}
      }
    };
    wrapped.__v468HistoryGate=true;wrapped.__v468Base=base;window.saveAttention=wrapped;
    return true;
  }

  function installPatientSync'''
    if not pattern.search(s):
        raise RuntimeError("No se encontró installSaveGate")
    s = pattern.sub(replacement, s, count=1)

    old = "            warnings(out);closeSearch();lastPanelPatient=0;await refreshPanel(pid,true);\n"
    new = "            identityCache.set(Number(pid),{at:Date.now(),data:out});warnings(out);closeSearch();lastPanelPatient=0;await refreshPanel(pid,true);\n"
    if old in s:
        s = replace_once(s, old, new, "cache tras vínculo manual")

    old = "      if(pid){setTimeout(async()=>{try{const d=await apiBase()('/api/historia-identity/sync/'+pid,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});warnings(d);lastPanelPatient=0;refreshPanel(pid,true)}catch(_e){}},80)}\n"
    new = "      if(pid){setTimeout(async()=>{try{const d=await apiBase()('/api/historia-identity/sync/'+pid,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});identityCache.set(Number(pid),{at:Date.now(),data:d});warnings(d);lastPanelPatient=0;refreshPanel(pid,true)}catch(_e){}},80)}\n"
    if old in s:
        s = replace_once(s, old, new, "cache tras sincronizar datos")

    old = '''  function boot(){\n    installSaveGate();\n    ['savePatient','savePatientAndReturnToAttention'].forEach(installPatientSync);\n    clearTimeout(panelTimer);panelTimer=setTimeout(()=>refreshPanel(0,false),80);\n  }\n'''
    new = '''  function boot(){\n    installSaveGate();\n    ['savePatient','savePatientAndReturnToAttention'].forEach(installPatientSync);\n    clearTimeout(panelTimer);panelTimer=setTimeout(()=>{const pid=Number(patientIdFromModal()||0);if(pid)startIdentityPrepare(pid)},80);\n  }\n'''
    if old in s:
        s = replace_once(s, old, new, "boot prefetch no bloqueante")
    path.write_text(s, encoding="utf-8")


def patch_print_flow() -> None:
    path = APP / "reception_attention_identity.py"
    s = path.read_text(encoding="utf-8")
    old = "const overlay=busyOverlay(\\'Guardando atención e imprimiendo recibo…\\');"
    new = "const overlay=busyOverlay(\\'Guardando atención…\\');"
    if old in s:
        s = replace_once(s, old, new, "mensaje guardando")
    old = "try{printResult=await apiBefore(\\'/api/v4470/print-visit/\\'+Number(consult.id),{method:\\'POST\\',headers:{\\'Content-Type\\':\\'application/json\\'},body:\\'{}\\'})}catch(e){printResult={printed:false}}"
    new = "try{const printPromise=apiBefore(\\'/api/v4470/print-visit/\\'+Number(consult.id),{method:\\'POST\\',headers:{\\'Content-Type\\':\\'application/json\\'},body:\\'{}\\'});printResult={printed:true,queued:true};Promise.resolve(printPromise).then(r=>{if(r&&r.printed===false)toast(\\'⚠ Atención guardada. No se pudo imprimir el recibo; puedes reimprimirlo desde Inicio.\\',true)}).catch(()=>toast(\\'⚠ Atención guardada. No se pudo imprimir el recibo; puedes reimprimirlo desde Inicio.\\',true))}catch(e){printResult={printed:false}}"
    if old in s:
        s = replace_once(s, old, new, "impresión no bloqueante")
    old = "else toast(\\'✓ Atención guardada.\\');"
    new = "else toast(\\'✓ Procedimiento guardado.\\');"
    if old in s:
        s = replace_once(s, old, new, "mensaje procedimiento")
    path.write_text(s, encoding="utf-8")


def patch_history_handoff() -> None:
    path = APP / "reception_history_attention_type.py"
    s = path.read_text(encoding="utf-8")
    old = '''            items = list((result or {}).get('items') or []) if isinstance(result, dict) else []\n            visit_ids = [x.get('id') for x in items if isinstance(x, dict) and x.get('id') is not None]\n            type_code = ''\n            if items and isinstance(items[0], dict):\n                type_code = str(items[0].get('tipo') or '').strip().upper()\n            if not type_code:\n                type_code = str(getattr(data, 'tipo', '') or '').strip().upper()\n            attention_type = _TYPE_LABELS.get(type_code)\n            if not attention_type:\n                attention_type = 'Subsecuente' if type_code == 'S' else 'Nuevo' if type_code == 'N' else 'Consulta'\n            historia_bridge.queue_attention(reception_patient_id=int(patient.id), display_name=str(getattr(patient, 'nombre', '') or 'Paciente'), identification=str(getattr(patient, 'cedula', '') or ''), attention_type=attention_type, visit_ids=visit_ids)\n'''
    new = '''            items = list((result or {}).get('items') or []) if isinstance(result, dict) else []\n            consultation_item = next((x for x in items if isinstance(x, dict) and not str(x.get('procedimiento') or '').strip()), None)\n            # Los procedimientos nunca consumen turno ni se envían a Pacientes en espera.\n            if consultation_item:\n                visit_ids = [consultation_item.get('id')] if consultation_item.get('id') is not None else []\n                type_code = str(consultation_item.get('tipo') or getattr(data, 'tipo', '') or '').strip().upper()\n                attention_type = _TYPE_LABELS.get(type_code)\n                if not attention_type:\n                    attention_type = 'Subsecuente' if type_code == 'S' else 'Nuevo' if type_code == 'N' else 'Consulta'\n                historia_bridge.queue_attention(reception_patient_id=int(patient.id), display_name=str(getattr(patient, 'nombre', '') or 'Paciente'), identification=str(getattr(patient, 'cedula', '') or ''), attention_type=attention_type, visit_ids=visit_ids)\n'''
    if old in s:
        s = replace_once(s, old, new, "handoff solo consultas")
    path.write_text(s, encoding="utf-8")


def patch_manifest() -> None:
    path = APP / "update_manifest.json"
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    notes = data.setdefault("notes", {})
    notes.update({
        "attention_write_mode": "sqlite-first-cloud-write-behind",
        "attention_save_never_waits_for_reception_neon": True,
        "history_identity_prepare_non_blocking": True,
        "consultation_print_non_blocking": True,
        "consultation_print_uses_local_visit_id": True,
        "procedure_auto_print": False,
        "procedure_print_message_removed": True,
        "procedure_historia_handoff": False,
        "procedure_turn_consumption": False,
    })
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def apply() -> None:
    patch_core()
    patch_identity()
    patch_print_flow()
    patch_history_handoff()
    patch_manifest()


if __name__ == "__main__":
    apply()

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSION = "4.4.11"
APP_VERSION = "4.4.9"
SOURCE_JS = "updates/v4_4_10_attention_search/static/app.js"
SOURCE_INDEX = "updates/v4_4_10_attention_search/static/index.html"
OUT = ROOT / "updates" / "v4_4_11_attention_ux"
EXPECTED_JS_SHA256 = "c7d380d8420c53dc8bce3a66b2b34eea1161a52674d5d4c48891a6aed5e302fb"
EXPECTED_INDEX_SHA256 = "e9a59657ccfcc90253fc52b8924f37621d8379886e95be330728bf8d0947c094"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_bytes(rel: str) -> bytes:
    return subprocess.check_output(["git", "show", f"HEAD:{rel}"], cwd=ROOT)


ATTENTION_SEARCH = r'''function setAttentionSearchView(active){
  const agenda=$('#attentionWeekBlock'),box=$('#aResults');
  const shell=document.querySelector('#modal .new-attention-start-modal');
  if(agenda)agenda.classList.toggle('hidden',!!active);
  if(shell)shell.classList.toggle('attention-searching',!!active);
  if(box){
    box.classList.toggle('attention-results-expanded',!!active);
    if(active){
      box.style.maxHeight='56vh';
      box.style.overflowY='auto';
      box.style.marginTop='8px';
    }else{
      box.style.removeProperty('max-height');
      box.style.removeProperty('overflow-y');
      box.style.removeProperty('margin-top');
    }
  }
}
function attentionSearch(immediate=false){
  clearTimeout(attentionSearchTimer);
  const run=async()=>{
    const input=$('#aSearch'),box=$('#aResults');
    if(!input||!box)return;
    const q=String(input.value||'').trim().toUpperCase();
    const active=q.length>=2;
    setAttentionSearchView(active);
    if(!active){
      attentionSearchSeq++;
      box.innerHTML='';
      box.classList.add('hidden');
      return;
    }

    const seq=++attentionSearchSeq;
    box.classList.remove('hidden');
    box.innerHTML='<div class="panel muted">Buscando paciente…</div>';
    try{
      const rows=await api('/api/patients?q='+encodeURIComponent(q)+'&limit=18');
      if(seq!==attentionSearchSeq)return;
      const usable=(rows||[]).slice(0,14);
      box.innerHTML=usable.length?usable.map(p=>{
        if(typeof isHistoricalPatient==='function'&&isHistoricalPatient(p)){
          const years=typeof historicalYears==='function'?historicalYears(p):'2020–2025';
          return `<article class="global-result historical-result"><div class="global-result-main"><div><b>${esc(p.nombre||'')}</b><span class="historical-badge">HISTÓRICO ${esc(years)}</span></div><span>${esc(p.cedula||'Sin cédula')} · ${esc(formatPhoneValue(p.celular||'')||'Sin celular')}</span></div><div class="global-result-actions"><button class="primary-soft" onclick="activateHistoricalPatient(${Number(p.historical_id)},'attention')">Atender</button></div></article>`;
        }
        return `<article class="global-result"><div class="global-result-main"><b>${esc(p.nombre||'')}</b><span>${esc(p.cedula||'Sin cédula')} · ${esc(formatPhoneValue(p.celular||'')||'Sin celular')}${p.correo?` · ${esc(p.correo)}`:''}</span></div><div class="global-result-actions"><button class="primary-soft" onclick="attentionFor(${Number(p.id)})">Atender</button></div></article>`;
      }).join(''):'<div class="panel muted">No encontramos coincidencias. Revisa nombre, cédula, celular o correo.</div>';
    }catch(e){
      if(seq!==attentionSearchSeq)return;
      box.innerHTML=`<div class="panel err">${esc(e.message||'No se pudo buscar el paciente.')}</div>`;
    }
  };
  if(immediate)return run();
  attentionSearchTimer=setTimeout(run,160);
}

'''

CEDULA_HINT_CLEANUP = r'''

/* v4.4.11 — el estado vacío de cédula no ocupa espacio; la validación útil se conserva. */
(()=>{
  const EMPTY_HINT='Ingresa la cédula para validarla localmente.';
  function cleanCedulaHint(){
    const modal=document.querySelector('#modal');
    const status=modal?.querySelector('.v481-id-status');
    if(!status)return;
    const text=String(status.textContent||'').trim();
    if(!text||text===EMPTY_HINT){
      if(text===EMPTY_HINT)status.textContent='';
      status.classList.add('hidden');
    }else{
      status.classList.remove('hidden');
    }
  }
  function install(){
    const modal=document.querySelector('#modal');
    if(!modal||modal.dataset.v4411CedulaCleanup==='1')return;
    modal.dataset.v4411CedulaCleanup='1';
    new MutationObserver(cleanCedulaHint).observe(modal,{childList:true,subtree:true,characterData:true});
    modal.addEventListener('input',()=>setTimeout(cleanCedulaHint,0),true);
    modal.addEventListener('change',()=>setTimeout(cleanCedulaHint,0),true);
    cleanCedulaHint();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install,{once:true});else install();
})();
'''


def main() -> None:
    raw_js = git_bytes(SOURCE_JS)
    if sha256(raw_js) != EXPECTED_JS_SHA256:
        raise SystemExit(f"Fuente app.js 4.4.10 cambió: {sha256(raw_js)}")
    text = raw_js.decode("utf-8-sig")

    start = text.find("function attentionSearch(immediate=false){")
    end = text.find("function attentionWeekKey(", start)
    if start < 0 or end < 0:
        raise SystemExit("No se encontró el bloque attentionSearch de v4.4.10")
    if text.count("function attentionSearch(immediate=false){") != 1:
        raise SystemExit("Cantidad inesperada de attentionSearch")

    final = text[:start] + ATTENTION_SEARCH + text[end:] + CEDULA_HINT_CLEANUP
    if final.count("function attentionSearch(immediate=false){") != 1:
        raise SystemExit("La candidata no tiene exactamente una attentionSearch")
    required = [
        "agenda.classList.toggle('hidden',!!active)",
        "const active=q.length>=2",
        "attentionSearchSeq++",
        "'/api/patients?q='+encodeURIComponent(q)+'&limit=18'",
        "EMPTY_HINT='Ingresa la cédula para validarla localmente.'",
        "status.textContent=''",
        "status.classList.add('hidden')",
    ]
    missing = [x for x in required if x not in final]
    if missing:
        raise SystemExit("Faltan cambios UX: " + ", ".join(missing))

    raw_index = git_bytes(SOURCE_INDEX)
    if sha256(raw_index) != EXPECTED_INDEX_SHA256:
        raise SystemExit(f"Fuente index.html 4.4.10 cambió: {sha256(raw_index)}")
    index = raw_index.decode("utf-8-sig")
    old_cache = '/static/app.js?v=4.4.10'
    new_cache = '/static/app.js?v=4.4.11'
    if index.count(old_cache) != 1:
        raise SystemExit(f"Cache-bust 4.4.10 inesperado: {index.count(old_cache)}")
    index = index.replace(old_cache, new_cache, 1)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "static").mkdir(parents=True, exist_ok=True)
    js_bytes = final.encode("utf-8")
    index_bytes = index.encode("utf-8")
    (OUT / "static" / "app.js").write_bytes(js_bytes)
    (OUT / "static" / "index.html").write_bytes(index_bytes)

    inner = {
        "product": "recepcion-pacientes",
        "version": VERSION,
        "app_version": APP_VERSION,
        "runtime_version": APP_VERSION,
        "launcher_version": "4.3.100-standalone-7",
        "updater_version": "integrado-en-launcher",
        "copy": ["static/app.js", "static/index.html", "update_manifest.json"],
    }
    inner_bytes = (json.dumps(inner, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    (OUT / "update_manifest.json").write_bytes(inner_bytes)

    latest = {
        "product": "recepcion-pacientes",
        "version": VERSION,
        "app_version": APP_VERSION,
        "runtime_version": APP_VERSION,
        "mandatory": True,
        "channel": "files-v3",
        "message": "v4.4.11: al buscar en Nueva atención oculta la Agenda y amplía resultados; al limpiar vuelve la Agenda. Quita el aviso vacío de cédula sin eliminar su validación.",
        "files": [
            {"path":"static/app.js","url":"https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_11_attention_ux/static/app.js","sha256":sha256(js_bytes),"encoding":"utf-8"},
            {"path":"static/index.html","url":"https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_11_attention_ux/static/index.html","sha256":sha256(index_bytes),"encoding":"utf-8"},
            {"path":"update_manifest.json","url":"https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_11_attention_ux/update_manifest.json","sha256":sha256(inner_bytes),"encoding":"utf-8"},
        ],
    }
    (ROOT / "build" / "v4411_attention_ux" / "candidate_latest.json").write_text(
        json.dumps(latest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline=""
    )
    print("V4411_BUILT", sha256(js_bytes), sha256(index_bytes), sha256(inner_bytes))


if __name__ == "__main__":
    main()

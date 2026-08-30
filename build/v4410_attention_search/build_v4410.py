from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSION = "4.4.10"
APP_VERSION = "4.4.9"
SOURCE_JS = "updates/v4_4_9_clean_444/static/app.js"
SOURCE_INDEX = "updates/v4_4_9_clean_444/static/index.html"
OUT = ROOT / "updates" / "v4_4_10_attention_search"
EXPECTED_JS_SHA256 = "ddd63ef3613a375c255ed24a17fcfe52e9aa0088df3663bc973bdae755abf4e0"
EXPECTED_INDEX_SHA256 = "e4f743f38cf5117632ab577d8520c9463fa566d5c984d821cc739baf48d8ec51"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_bytes(rel: str) -> bytes:
    return subprocess.check_output(["git", "show", f"HEAD:{rel}"], cwd=ROOT)


SEARCH_FUNCTION = r'''

/* v4.4.10 — restaura únicamente la lógica del buscador existente de Nueva atención. */
function attentionSearch(immediate=false){
  clearTimeout(attentionSearchTimer);
  const run=async()=>{
    const input=$('#aSearch'),box=$('#aResults');
    if(!input||!box)return;
    const q=String(input.value||'').trim().toUpperCase();
    if(q.length<2){box.innerHTML='';box.classList.add('hidden');return}

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


def main() -> None:
    raw_js = git_bytes(SOURCE_JS)
    got_js = sha256(raw_js)
    if got_js != EXPECTED_JS_SHA256:
        raise SystemExit(f"Fuente app.js 4.4.9 cambió: {got_js}")
    text = raw_js.decode("utf-8-sig")
    marker = "let attentionSearchTimer=null;\nlet attentionSearchSeq=0;"
    if text.count(marker) != 1:
        raise SystemExit(f"Marcador attentionSearch inesperado: {text.count(marker)}")
    if "function attentionSearch(" in text:
        raise SystemExit("La fuente ya contiene attentionSearch; no aplicar doble parche")

    final = text.replace(marker, marker + SEARCH_FUNCTION, 1)
    if final.count("function attentionSearch(") != 1:
        raise SystemExit("La candidata no tiene exactamente una función attentionSearch")
    if "replace(/[^0-9]/g" in SEARCH_FUNCTION or "digitsOnlyInput" in SEARCH_FUNCTION:
        raise SystemExit("REGRESIÓN: el buscador vuelve a restringir a dígitos")
    required = [
        "'/api/patients?q='+encodeURIComponent(q)+'&limit=18'",
        "p.nombre", "p.cedula", "p.celular", "p.correo",
        "attentionFor(", "activateHistoricalPatient(",
    ]
    missing = [x for x in required if x not in SEARCH_FUNCTION]
    if missing:
        raise SystemExit("Faltan capacidades del buscador: " + ", ".join(missing))

    raw_index = git_bytes(SOURCE_INDEX)
    got_index = sha256(raw_index)
    if got_index != EXPECTED_INDEX_SHA256:
        raise SystemExit(f"Fuente index.html 4.4.9 cambió: {got_index}")
    index = raw_index.decode("utf-8-sig")
    old_cache = '/static/app.js?v=4.4.9'
    new_cache = '/static/app.js?v=4.4.10'
    if index.count(old_cache) != 1:
        raise SystemExit(f"Cache-bust 4.4.9 inesperado: {index.count(old_cache)}")
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
        "message": "v4.4.10: corrige únicamente el buscador de Nueva atención para buscar por nombre, cédula, celular o correo. No modifica backend ni otras pantallas.",
        "files": [
            {
                "path": "static/app.js",
                "url": "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_10_attention_search/static/app.js",
                "sha256": sha256(js_bytes),
                "encoding": "utf-8",
            },
            {
                "path": "static/index.html",
                "url": "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_10_attention_search/static/index.html",
                "sha256": sha256(index_bytes),
                "encoding": "utf-8",
            },
            {
                "path": "update_manifest.json",
                "url": "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_10_attention_search/update_manifest.json",
                "sha256": sha256(inner_bytes),
                "encoding": "utf-8",
            },
        ],
    }
    (ROOT / "build" / "v4410_attention_search" / "candidate_latest.json").write_text(
        json.dumps(latest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline=""
    )
    print("V4410_BUILT", sha256(js_bytes), sha256(index_bytes), sha256(inner_bytes))


if __name__ == "__main__":
    main()

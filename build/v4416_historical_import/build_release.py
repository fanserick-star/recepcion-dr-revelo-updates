from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSION = "4.4.16"
APP_SRC = "updates/v4_4_15_historical_all/app.py"
JS_SRC = "updates/v4_4_14_ui_history/static/app.js"
INDEX_SRC = "updates/v4_4_14_ui_history/static/index.html"
OUT = ROOT / "updates/v4_4_16_historical_import"


def git_bytes(path: str) -> bytes:
    return subprocess.check_output(["git", "show", f"HEAD:{path}"], cwd=ROOT)


def text(path: str) -> str:
    return git_bytes(path).decode("utf-8-sig")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


if OUT.exists():
    shutil.rmtree(OUT)
(OUT / "static").mkdir(parents=True, exist_ok=True)

app = text(APP_SRC)
js = text(JS_SRC)
index = text(INDEX_SRC)

assert 'APP_VERSION = "4.4.15"' in app
assert 'const VERSION=' in app and '4.4.15' in app
assert '@app.get("/api/historical/stats")' in app
assert 'if mode == "historical":' in app
assert '/static/app.js?v=4.4.14' in index
assert "async function loadPatientFilter(mode,button=null){" in js

app = app.replace('APP_VERSION = "4.4.15"', 'APP_VERSION = "4.4.16"', 1)
app, n_badge = re.subn(r"(const VERSION=.*?)4\.4\.15(.*?;)", r"\g<1>4.4.16\g<2>", app, count=1)
assert n_badge == 1

endpoint = r'''

@app.post("/api/historical/import")
async def import_historical_registry(
    file: UploadFile = File(...),
    user: User = Depends(current_user),
):
    """Restaura el índice histórico exclusivamente en SQLite local.

    El CSV llega desde el navegador de la PC de Recepción, se valida en memoria y
    no se sube a Neon ni se conserva como archivo dentro del programa. Solo se
    reemplaza la tabla historical_patients cuando el archivo completo ya pasó
    todas las validaciones.
    """
    filename = str(file.filename or "").strip()
    if not filename.lower().endswith(".csv"):
        raise HTTPException(400, "Selecciona el archivo histórico CSV preparado para Recepción.")
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "El archivo histórico está vacío.")
    if len(raw) > 5_000_000:
        raise HTTPException(400, "El archivo histórico supera el tamaño esperado.")
    try:
        content = raw.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content))
    except Exception:
        raise HTTPException(400, "No se pudo leer el archivo histórico como CSV.")

    required = {"source_key", "nombre", "search_text", "first_year", "last_year"}
    fields = {str(x or "").strip() for x in (reader.fieldnames or [])}
    if not required.issubset(fields):
        raise HTTPException(400, "El archivo no corresponde al histórico 2020–2025 de Recepción.")

    parsed = []
    seen = set()
    for row in reader:
        name = " ".join(str(row.get("nombre") or "").split()).upper()
        if not name:
            continue
        source_key = str(row.get("source_key") or "").strip().lower()
        if not re.fullmatch(r"[0-9a-f]{40}", source_key):
            source_key = hashlib.sha1(("HIST2020-2025|" + normalize_lookup_name(name)).encode("utf-8")).hexdigest()
        if source_key in seen:
            continue
        try:
            first_year = int(row.get("first_year") or 2020)
            last_year = int(row.get("last_year") or 2025)
        except Exception:
            continue
        if not (2020 <= first_year <= 2025 and 2020 <= last_year <= 2025 and first_year <= last_year):
            continue
        exact = None
        raw_date = str(row.get("last_visit_date") or "").strip()
        if raw_date:
            try:
                exact = date.fromisoformat(raw_date[:10])
            except Exception:
                exact = None
        try:
            row_count = max(1, int(row.get("row_count") or 1))
        except Exception:
            row_count = 1
        seen.add(source_key)
        parsed.append({
            "source_key": source_key,
            "nombre": name[:240],
            "search_text": str(row.get("search_text") or name).upper(),
            "cedula": str(row.get("cedula") or "").strip()[:30] or None,
            "celular": str(row.get("celular") or "").strip()[:40] or None,
            "correo": str(row.get("correo") or "").strip().lower()[:220] or None,
            "lugar": " ".join(str(row.get("lugar") or "").split()).upper()[:160] or None,
            "first_year": first_year,
            "last_year": last_year,
            "last_visit_date": exact,
            "row_count": row_count,
            "aliases": str(row.get("aliases") or "").strip() or None,
            "phones": str(row.get("phones") or "").strip() or None,
            "emails": str(row.get("emails") or "").strip() or None,
            "cedulas": str(row.get("cedulas") or "").strip() or None,
        })

    # Este índice real contiene miles de fichas. No permitimos reemplazarlo con
    # un CSV equivocado o incompleto que accidentalmente deje la tabla vacía.
    if len(parsed) < 1000:
        raise HTTPException(400, f"El archivo parece incompleto: solo contiene {len(parsed)} pacientes válidos.")

    try:
        with LocalSessionLocal() as ldb:
            ldb.execute(delete(HistoricalPatient))
            ldb.execute(insert(HistoricalPatient), parsed)
            marker = ldb.get(CacheMeta, HISTORICAL_REGISTRY_MARKER)
            if marker:
                marker.value = "1"
            else:
                ldb.add(CacheMeta(key=HISTORICAL_REGISTRY_MARKER, value="1"))
            ldb.commit()
    except Exception as exc:
        raise HTTPException(500, f"No se pudo guardar el histórico local: {str(exc)[:140]}")

    dated = sum(1 for x in parsed if x.get("last_visit_date"))
    return {
        "ok": True,
        "loaded": len(parsed),
        "with_exact_date": dated,
        "first_year": min(x["first_year"] for x in parsed),
        "last_year": max(x["last_year"] for x in parsed),
        "local_only": True,
    }
'''
anchor = '@app.get("/api/historical/stats")'
assert app.count(anchor) == 1
app = app.replace(anchor, endpoint + "\n\n" + anchor, 1)

old_load = """  const lim=activePatientFilter==='review'?80:30;\n  try{const rows=await api('/api/patients?mode='+encodeURIComponent(activePatientFilter)+'&limit='+lim);renderPatientResults(rows,labels[activePatientFilter]||'Pacientes')}catch(e){box.innerHTML=`<div class=\"attention-search-hint err\">${esc(e.message)}</div>`}\n}"""
new_load = """  const lim=activePatientFilter==='review'?80:30;\n  try{\n    const rows=await api('/api/patients?mode='+encodeURIComponent(activePatientFilter)+'&limit='+lim);\n    if(activePatientFilter==='historical'&&!rows.length){renderHistoricalImportPanel();return}\n    renderPatientResults(rows,labels[activePatientFilter]||'Pacientes');\n  }catch(e){box.innerHTML=`<div class=\"attention-search-hint err\">${esc(e.message)}</div>`}\n}"""
assert js.count(old_load) == 1
js = js.replace(old_load, new_load, 1)

insert_anchor = "async function searchPatients(){"
assert js.count(insert_anchor) == 1
import_ui = r'''
function renderHistoricalImportPanel(){
  const box=$('#patientResults');if(!box)return;
  box.className='results patient-results-list';
  box.innerHTML=`<div class="patient-results-heading">Pacientes históricos 2020–2025</div><div class="patients-empty-state small historical-import-empty"><span>↥</span><b>Base histórica no cargada en esta PC</b><p>Selecciona el índice histórico preparado para Recepción. Se guardará únicamente en la copia local de esta computadora.</p><input id="historicalImportFile" type="file" accept=".csv,text/csv" class="hidden" onchange="importHistoricalRegistryFile(this)"><button type="button" class="primary" data-historical-import="1" onclick="document.querySelector('#historicalImportFile')?.click()">Cargar histórico 2020–2025</button></div>`;
}
async function importHistoricalRegistryFile(input){
  const file=input?.files?.[0];if(!file)return;
  const box=$('#patientResults');
  if(box)box.innerHTML='<div class="patients-loading">Validando y cargando el histórico local…</div>';
  try{
    const form=new FormData();form.append('file',file,file.name);
    const r=await fetch('/api/historical/import',{method:'POST',body:form});
    const data=await r.json().catch(()=>({}));
    if(!r.ok)throw Error(data.detail||'No se pudo cargar el histórico.');
    alert(`Histórico recuperado: ${Number(data.loaded||0).toLocaleString('es-EC')} pacientes.`);
    await loadPatientFilter('historical');
  }catch(e){
    if(box)box.innerHTML=`<div class="attention-search-hint err">${esc(e.message||e)}</div>`;
  }finally{if(input)input.value=''}
}

'''
js = js.replace(insert_anchor, import_ui + insert_anchor, 1)

index = index.replace('/static/app.js?v=4.4.14', '/static/app.js?v=4.4.16', 1)

assert 'data-historical-import="1"' in js
assert '/api/historical/import' in js and '/api/historical/import' in app
assert 'FormData()' in js
assert 'historical_patients' in app
assert 'LocalSessionLocal() as ldb' in endpoint
assert '/static/app.js?v=4.4.16' in index
# Nunca empaquetar datos de pacientes en el repo público.
assert 'HISTORICO_PACIENTES_2020_2025.csv' not in [p.name for p in OUT.glob('*')]

app_bytes = app.encode('utf-8')
js_bytes = js.encode('utf-8')
index_bytes = index.encode('utf-8')
(OUT / 'app.py').write_bytes(app_bytes)
(OUT / 'static' / 'app.js').write_bytes(js_bytes)
(OUT / 'static' / 'index.html').write_bytes(index_bytes)

inner = {
    'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,
    'launcher_version':'4.3.100-standalone-7','updater_version':'integrado-en-launcher',
    'copy':['app.py','static/app.js','static/index.html','update_manifest.json'],
}
inner_bytes=(json.dumps(inner,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
(OUT/'update_manifest.json').write_bytes(inner_bytes)

base='https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_16_historical_import/'
latest={
    'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,
    'mandatory':True,'channel':'files-v3',
    'message':'v4.4.16: restaura la carga local y privada del histórico 2020–2025 cuando el índice no está presente. Los datos de pacientes no se publican en GitHub ni se suben a Neon.',
    'files':[
        {'path':'app.py','url':base+'app.py','sha256':sha(app_bytes),'encoding':'utf-8'},
        {'path':'static/app.js','url':base+'static/app.js','sha256':sha(js_bytes),'encoding':'utf-8'},
        {'path':'static/index.html','url':base+'static/index.html','sha256':sha(index_bytes),'encoding':'utf-8'},
        {'path':'update_manifest.json','url':base+'update_manifest.json','sha256':sha(inner_bytes),'encoding':'utf-8'},
    ],
}
(ROOT/'build/v4416_historical_import/candidate_latest.json').write_text(json.dumps(latest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'version':VERSION,'app_sha':sha(app_bytes),'js_sha':sha(js_bytes),'index_sha':sha(index_bytes),'public_patient_data':False},indent=2))

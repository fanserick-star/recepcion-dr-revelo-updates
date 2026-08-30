from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSION = "4.4.17"
APP_SRC = "updates/v4_4_16_historical_import/app.py"
JS_SRC = "updates/v4_4_16_historical_import/static/app.js"
INDEX_SRC = "updates/v4_4_16_historical_import/static/index.html"
OUT = ROOT / "updates/v4_4_17_continue_attention"


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

assert 'APP_VERSION = "4.4.16"' in app
assert "const VERSION=\\'4.4.16\\';" in app
assert "/static/app.js?v=4.4.16" in index
assert "onclick=\"openPatient(${Number(p.id)},'attention-search')\"" in js
assert "async function openPatient(id,source='general'){" in js
assert 'data-historical-import="1"' in js

# Versión real del backend/overlay para que el badge sea correcto.
app = app.replace('APP_VERSION = "4.4.16"', 'APP_VERSION = "4.4.17"', 1)
app = app.replace("const VERSION=\\'4.4.16\\';", "const VERSION=\\'4.4.17\\';", 1)

notes_anchor = "  const notes=String(p.notas||'').trim();\n"
assert js.count(notes_anchor) == 1
context_logic = r'''  const fromAttentionSearch=source==='attention-search';
  const profileActions=fromAttentionSearch
    ? `<button class="patient-edit-btn" onclick="editPatient(${Number(id)},'attention-search')">Editar datos</button>`
    : `<button class="primary" onclick="attentionFor(${Number(id)})">＋ Nueva atención</button><button onclick="openAgendaPatient(${Number(id)})">＋ Agendar cita</button><button class="patient-edit-btn" onclick="editPatient(${Number(id)},'${esc(source)}')">Editar datos</button>${deleteButton}`;
  const continueAttention=fromAttentionSearch
    ? `<div class="v4417-continue-wrap"><button type="button" class="v4417-continue-attention" data-continue-attention="1" onclick="attentionFor(${Number(id)})">CONTINUAR ATENCIÓN</button></div>`
    : '';
'''
js = js.replace(notes_anchor, notes_anchor + context_logic, 1)

old_actions = r'''<div class="v4413-profile-actions"><button class="primary" onclick="attentionFor(${Number(id)})">＋ Nueva atención</button><button onclick="openAgendaPatient(${Number(id)})">＋ Agendar cita</button><button class="patient-edit-btn" onclick="editPatient(${Number(id)},'${esc(source)}')">Editar datos</button>${deleteButton}</div>'''
new_actions = r'''<div class="v4413-profile-actions">${profileActions}</div>'''
assert js.count(old_actions) == 1
js = js.replace(old_actions, new_actions, 1)

old_tail = r'''<section class="hidden" data-profile-panel="facturacion"><div class="v4413-profile-section-title"><h3>Historial de Facturación</h3><span>Registros vinculados a este paciente</span></div>${patientProfileBillingHtml(p)}</section></div></div>'''
new_tail = r'''<section class="hidden" data-profile-panel="facturacion"><div class="v4413-profile-section-title"><h3>Historial de Facturación</h3><span>Registros vinculados a este paciente</span></div>${patientProfileBillingHtml(p)}</section></div>${continueAttention}</div>'''
assert js.count(old_tail) == 1
js = js.replace(old_tail, new_tail, 1)

index = index.replace('/static/app.js?v=4.4.16', '/static/app.js?v=4.4.17', 1)
style = r'''
<style id="v4417-continue-attention-style">
#modal .v4417-continue-wrap{margin-top:18px;padding-top:16px;border-top:1px solid #dbe6f2}
#modal .v4417-continue-attention{display:block;width:100%;min-height:58px;border:0;border-radius:14px;background:#198754;color:#fff;font-size:16px;font-weight:900;letter-spacing:.02em;box-shadow:0 8px 20px rgba(25,135,84,.22);cursor:pointer}
#modal .v4417-continue-attention:hover{filter:brightness(.96)}
#modal .v4417-continue-attention:focus-visible{outline:3px solid rgba(25,135,84,.25);outline-offset:3px}
</style>
'''
assert '</head>' in index
index = index.replace('</head>', style + '</head>', 1)

# Guardas funcionales del flujo solicitado.
assert "source==='attention-search'" in js
assert 'data-continue-attention="1"' in js
assert 'CONTINUAR ATENCIÓN' in js
assert "editPatient(${Number(id)},'attention-search')" in js
assert '${continueAttention}</div>' in js
assert '/static/app.js?v=4.4.17' in index
assert 'v4417-continue-attention-style' in index
# Lo ya recuperado en 4.4.16 debe sobrevivir sin cambios.
assert '@app.post("/api/historical/import")' in app
assert 'data-historical-import="1"' in js

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

base='https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_17_continue_attention/'
latest={
    'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,
    'mandatory':True,'channel':'files-v3',
    'message':'v4.4.17: en la ficha abierta desde Nueva atención se ocultan Nueva atención y Agendar cita; aparece abajo un botón verde CONTINUAR ATENCIÓN. La ficha normal de Pacientes conserva sus acciones.',
    'files':[
        {'path':'app.py','url':base+'app.py','sha256':sha(app_bytes),'encoding':'utf-8'},
        {'path':'static/app.js','url':base+'static/app.js','sha256':sha(js_bytes),'encoding':'utf-8'},
        {'path':'static/index.html','url':base+'static/index.html','sha256':sha(index_bytes),'encoding':'utf-8'},
        {'path':'update_manifest.json','url':base+'update_manifest.json','sha256':sha(inner_bytes),'encoding':'utf-8'},
    ],
}
(ROOT/'build/v4417_continue_attention/candidate_latest.json').write_text(json.dumps(latest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'version':VERSION,'app_sha':sha(app_bytes),'js_sha':sha(js_bytes),'index_sha':sha(index_bytes)},indent=2))

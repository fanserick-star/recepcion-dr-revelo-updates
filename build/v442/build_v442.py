from __future__ import annotations
import hashlib, json, math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / 'updates' / 'v441'
OUT = ROOT / 'updates' / 'v442'
VERSION = '4.4.2'
LAUNCHER_VERSION = '4.3.100-standalone-7'


def joined(prefix: str, n: int) -> str:
    parts = sorted(SRC.glob(prefix + '*'), key=lambda p: int(p.name.replace(prefix, '')))
    if len(parts) != n:
        raise SystemExit(f'{prefix}: se esperaban {n} partes y hay {len(parts)}')
    return ''.join(p.read_text(encoding='utf-8') for p in parts)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_parts(text: str, prefix: str, n: int) -> list[str]:
    OUT.mkdir(parents=True, exist_ok=True)
    for p in OUT.glob(prefix + '*'):
        p.unlink()
    step = math.ceil(len(text) / n)
    names=[]
    for i in range(n):
        name=f'{prefix}{i+1}'
        (OUT/name).write_text(text[i*step:(i+1)*step], encoding='utf-8', newline='')
        names.append(name)
    if ''.join((OUT/x).read_text(encoding='utf-8') for x in names) != text:
        raise SystemExit('reconstrucción inválida '+prefix)
    return names


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count=text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: esperaba 1 coincidencia y encontró {count}')
    return text.replace(old,new,1)


def replace_between(text: str, start: str, end: str, new: str, label: str) -> str:
    a=text.find(start)
    if a < 0: raise SystemExit(label+': inicio no encontrado')
    b=text.find(end,a+len(start))
    if b < 0: raise SystemExit(label+': fin no encontrado')
    # El marcador END se conserva porque text[b:] empieza exactamente ahí.
    return text[:a]+new+text[b:]


NEW_ATTENTION = r'''async function newAttention(){
  currentPatientSource='general';
  attentionWeekAnchor=toISO(new Date());
  openModal(`<div class="new-attention-start-modal attention-agenda-only"><div class="modal-form-heading"><h2>Nueva atención</h2><p>Selecciona una cita para registrar la atención.</p></div><div id="attentionWeekBlock" class="attention-week-block"><div class="attention-week-head"><div><b>Agenda</b><span>Jueves, viernes y sábado</span></div><div class="attention-week-nav"><button type="button" title="Semana anterior" onclick="moveAttentionWeek(-1)">‹</button><button type="button" class="week-today" onclick="currentAttentionWeek()">Esta semana</button><button type="button" title="Semana siguiente" onclick="moveAttentionWeek(1)">›</button></div><div class="attention-week-range"><strong id="attentionWeekLabel"></strong><span id="attentionWeekConflict" class="attention-week-conflict-note hidden"></span></div></div><div id="attentionWeekCalendar" class="attention-week-calendar"><div class="attention-week-loading">Cargando agenda…</div></div></div></div>`);
  loadAttentionWeek(false,attentionWeekAnchor);
}
'''


CLEAN_CSS = r'''/* v4.4.2 — Atender directo desde Agenda */
.attention-agenda-only .modal-form-heading{margin-bottom:12px!important}
.attention-agenda-only .attention-week-block{margin-top:0!important}
'''


def patch_static_app(js: str) -> str:
    # Nueva atención queda dedicada a la agenda. El alta/búsqueda de pacientes
    # continúa disponible en su pantalla propia, sin ocupar el flujo de Atender.
    js=replace_between(js,'async function newAttention(){','function pRow(p){',NEW_ATTENTION,'Nueva atención solo agenda')
    # pRow + attentionSearch eran exclusivos del buscador retirado.
    js=replace_between(js,'function pRow(p){','function procedureByName(name){','', 'retirar buscador de atención')
    required=['async function newAttention()','attention-agenda-only','id="attentionWeekBlock"','Selecciona una cita para registrar la atención.','patient-name-button','Procedimientos y servicios','<span class="service-price">$40.00</span>']
    for token in required:
        if token not in js: raise SystemExit('static app falta '+token)
    forbidden=['new-patient-callout','attention-start-search','id="aSearch"','function attentionSearch()','function pRow(p)']
    for token in forbidden:
        if token in js: raise SystemExit('static app conserva '+token)
    return js


def patch_app(s: str) -> str:
    s=replace_once(s,'APP_VERSION = "4.4.1"','APP_VERSION = "4.4.2"','versión backend')
    s=replace_once(s,"const VERSION=\\'4.4.1\\';","const VERSION=\\'4.4.2\\';",'versión visual')

    # Retirar por completo endpoints ya descartados: ficha rápida y resumen
    # inteligente. Actividad/Papelera continúan en SQLite local; diagnóstico
    # toca Neon únicamente bajo clic explícito del usuario.
    s=replace_between(s,'@app.get("/api/patients/{pid}/quick")','@app.get("/api/ops/diagnostics")','', 'endpoints descartados')

    # Quitar del overlay toda la lógica de drawer + Agenda inteligente.
    s=replace_once(s,'}ensurePatientDrawer();ensureDiagnosticsCard()}','}ensureDiagnosticsCard()}','init sin ficha rápida')
    s=replace_between(s,' function ensurePatientDrawer(){',' function ensureDiagnosticsCard(){','', 'js ficha rápida y agenda inteligente')
    # El resumen diario quedó sin uso desde 4.4.1; se elimina para que no exista
    # ninguna referencia residual al endpoint de Agenda inteligente.
    if ' function maybeDailyBrief(){' in s:
        s=replace_between(s,' function maybeDailyBrief(){','function init(){ensureOpsUI()}','', 'resumen diario muerto')

    # Limpiar CSS muerto de ficha rápida/Agenda inteligente del overlay base.
    if '.patient-quick-drawer-backdrop{' in s and '.ops-diagnostic-panel{' in s:
        s=replace_between(s,'.patient-quick-drawer-backdrop{','.ops-diagnostic-panel{','', 'css ficha rápida y agenda inteligente')
    s=s.replace('.smart-agenda-bottom,.ops-diagnostic-grid{grid-template-columns:1fr}', '.ops-diagnostic-grid{grid-template-columns:1fr}')
    s=s.replace('.pq-kpis{grid-template-columns:1fr 1fr 1fr}', '')
    s=s.replace('.patient-quick-drawer{left:auto!important;right:0!important;bottom:auto!important;max-width:94vw!important;margin:0!important;padding:0!important}\n','')

    overlay_marker='@app.get("/v460/overlay.css")'
    inject='V442_CLEAN_CSS = r"""'+CLEAN_CSS+'"""\nV460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\\n" + V442_CLEAN_CSS\n\n'
    s=replace_between(s,overlay_marker,overlay_marker,inject,'css v442') if False else s
    # Para insertar ANTES del marcador sin duplicarlo usamos replace_once simple.
    s=replace_once(s,overlay_marker,inject+overlay_marker,'css v442')

    compile(s,'app.py','exec')
    required=['APP_VERSION = "4.4.2"','TRASH_RETENTION_DAYS = 7','Actividad local-first estricta','Lectura estrictamente local','Guarda la Papelera únicamente en SQLite local','Resumen de datos y servicios','/api/ops/diagnostics','V442_CLEAN_CSS','V43104_ALERT_JS','Procedimientos y servicios',"price.textContent='$40.00'",'Emitir por lotes']
    for token in required:
        if token not in s: raise SystemExit('app falta '+token)
    forbidden=['/api/patients/{pid}/quick','openPatientQuick','ensurePatientDrawer','patientQuickDrawer','/api/ops/agenda-smart','loadSmartAgenda','maybeDailyBrief','patient-quick-drawer-backdrop','smart-agenda-card','@app.get("/api/ops/diagnostics")@app.get']
    for token in forbidden:
        if token in s: raise SystemExit('app conserva '+token)
    return s


def main() -> None:
    app=patch_app(joined('app.part',7)); launcher=joined('ABRIR_RECEPCION.part',4)
    ap=write_parts(app,'app.part',7); lp=write_parts(launcher,'ABRIR_RECEPCION.part',4)
    (OUT/'static').mkdir(parents=True,exist_ok=True)
    index=(SRC/'static'/'index.html').read_text(encoding='utf-8')
    static_app=patch_static_app((SRC/'static'/'app.js').read_text(encoding='utf-8'))
    (OUT/'static'/'index.html').write_text(index,encoding='utf-8',newline='')
    (OUT/'static'/'app.js').write_text(static_app,encoding='utf-8',newline='')
    ab,lb,ib,jb=app.encode(),launcher.encode(),index.encode(),static_app.encode()
    manifest={'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,'launcher_version':LAUNCHER_VERSION,'updater_version':'integrado-en-launcher','copy':['ABRIR_RECEPCION.py','app.py','static/index.html','static/app.js','update_manifest.json']}
    mb=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode();(OUT/'update_manifest.json').write_bytes(mb)
    base='https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v442/'
    latest={'product':'recepcion-pacientes','version':VERSION,'mandatory':True,'channel':'files-v3','message':'v4.4.2: elimina Ficha rápida y restos de Agenda inteligente; Nueva atención abre directo en la Agenda sin alta ni buscador de pacientes, manteniendo Actividad/Papelera local-first y diagnóstico manual.','files':[{'path':'ABRIR_RECEPCION.py','parts':[base+x for x in lp],'sha256':sha(lb),'encoding':'utf-8'},{'path':'app.py','parts':[base+x for x in ap],'sha256':sha(ab),'encoding':'utf-8'},{'path':'static/index.html','url':base+'static/index.html','sha256':sha(ib),'encoding':'utf-8'},{'path':'static/app.js','url':base+'static/app.js','sha256':sha(jb),'encoding':'utf-8'},{'path':'update_manifest.json','url':base+'update_manifest.json','sha256':sha(mb),'encoding':'utf-8'}]}
    txt=json.dumps(latest,ensure_ascii=False,indent=2)+'\n';(ROOT/'latest.json').write_text(txt,encoding='utf-8',newline='');(ROOT/'latest-v3.json').write_text(txt,encoding='utf-8',newline='')
    print('OK',VERSION,sha(ab),sha(lb),sha(jb))

if __name__=='__main__': main()

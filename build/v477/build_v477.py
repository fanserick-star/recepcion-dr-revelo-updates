from __future__ import annotations
import ast, hashlib, json, math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/'updates'/'v476'
OUT=ROOT/'updates'/'v477'
VERSION='4.3.77'
LAUNCHER_VERSION='4.3.76-standalone-3'


def joined(prefix,n):
    ps=sorted(SRC.glob(prefix+'*'),key=lambda p:int(p.name.replace(prefix,'')))
    if len(ps)!=n: raise SystemExit(f'{prefix}: se esperaban {n} partes y hay {len(ps)}')
    return ''.join(p.read_text(encoding='utf-8') for p in ps)

def sha(b): return hashlib.sha256(b).hexdigest()

def write_parts(text,prefix,n):
    OUT.mkdir(parents=True,exist_ok=True)
    for p in OUT.glob(prefix+'*'): p.unlink()
    step=math.ceil(len(text)/n); names=[]
    for i in range(n):
        name=f'{prefix}{i+1}'
        (OUT/name).write_text(text[i*step:(i+1)*step],encoding='utf-8',newline='')
        names.append(name)
    rebuilt=''.join((OUT/x).read_text(encoding='utf-8') for x in names)
    if rebuilt!=text: raise SystemExit(f'{prefix}: reconstrucción inválida')
    return names

ATTENTION_CSS=r'''
/* v4.3.77 — Remaster de Nueva atención */
.modalbox.modalbox-wide.v477-attention-modalbox{width:min(790px,94vw)!important;max-height:90vh!important;padding:21px 23px 20px!important;border-radius:18px!important}
.v477-attention-remaster{display:grid;gap:12px}
.v477-attention-top{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;padding-right:42px}
.v477-attention-top .modal-form-heading{padding-right:0!important;margin:0!important}
.v477-attention-top .modal-form-heading h2{font-size:22px!important;letter-spacing:-.015em}
.v477-attention-top .modal-form-heading p{margin-top:4px!important;font-size:11px!important}
.v477-new-patient-btn{flex:0 0 auto;min-height:39px;padding:9px 13px!important;border-radius:11px!important;font-size:11px!important;font-weight:850!important;white-space:nowrap}
.v477-attention-remaster .attention-start-search{margin:0!important;gap:4px!important}
.v477-attention-remaster .attention-start-search>label{font-size:11px!important;color:#53647b!important}
.v477-attention-remaster .attention-start-search .search{height:46px!important;padding:10px 13px!important;border-radius:12px!important;background:#fff!important;font-size:14px!important}
.v477-attention-remaster .attention-start-search>small{display:none!important}
.v477-attention-remaster .attention-week-block{margin:0!important;padding:0!important;border:0!important;background:transparent!important}
.v477-today-head{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:11px 13px;margin:1px 0 7px;border:1px solid #dfe7f1;border-radius:12px;background:#f7f9fc}
.v477-today-title{display:grid;gap:2px;min-width:0}
.v477-today-kicker{font-size:8px;font-weight:900;letter-spacing:.12em;color:#6d7d92;text-transform:uppercase}
.v477-today-title b{font-size:13px;color:#1c314f;text-transform:capitalize}
.v477-today-meta{display:flex;align-items:center;gap:7px;flex-wrap:wrap;justify-content:flex-end}
.v477-today-meta strong{font-size:10px;color:#586c85;white-space:nowrap}
.v477-today-meta .attention-week-conflict-note{font-size:8px;padding:3px 6px}
.v477-attention-remaster .attention-week-calendar{display:block!important}
.v477-attention-remaster .attention-week-day{border:1px solid #dce5ef!important;border-radius:13px!important;overflow:hidden!important;box-shadow:none!important;background:#fff!important}
.v477-attention-remaster .attention-week-day>header{padding:8px 11px!important;background:#edf5ff!important;border-bottom:1px solid #dce8f6!important}
.v477-attention-remaster .attention-week-day>header b{font-size:12px!important}
.v477-attention-remaster .attention-week-day>header span{font-size:9px!important}
.v477-attention-remaster .attention-week-day>header strong{min-width:27px!important;height:25px!important;border-radius:8px!important;font-size:10px!important}
.v477-attention-remaster .attention-week-list{display:grid!important;grid-template-columns:repeat(2,minmax(0,1fr))!important;gap:7px!important;padding:8px!important;max-height:330px!important;overflow:auto!important}
.v477-attention-remaster .attention-week-row{grid-template-columns:54px minmax(0,1fr)!important;min-height:49px!important;padding:8px 10px!important;border-radius:10px!important;border:1px solid #e3e9f1!important;background:#fff!important}
.v477-attention-remaster .attention-week-row:hover,.v477-attention-remaster .attention-week-row:focus{background:#f2f7ff!important;border-color:#a9c6ec!important;box-shadow:0 0 0 2px #e2edfb!important}
.v477-attention-remaster .attention-week-time{font-size:12px!important;color:#1d66a7!important}
.v477-attention-remaster .attention-week-person b{font-size:11.5px!important;line-height:1.2!important;-webkit-line-clamp:1!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important;display:block!important}
.v477-attention-remaster .attention-week-person small{font-size:9px!important;color:#738196!important}
.v477-attention-remaster .attention-week-row.confirmafy-unlinked{padding-right:10px!important;padding-bottom:8px!important}
.v477-attention-remaster .attention-week-unlinked-badge{display:none!important}
.v477-attention-remaster .attention-week-empty,.v477-attention-remaster .attention-week-loading{padding:22px 14px!important;border:1px dashed #d6e0eb;border-radius:12px;background:#fbfcfe;font-size:11px!important}
.v477-no-clinic{display:grid;justify-items:center;gap:4px;padding:25px 15px!important}
.v477-no-clinic b{font-size:13px;color:#314762}.v477-no-clinic span{font-size:10px;color:#77869a;text-align:center}
.v477-attention-remaster .attention-results{margin-top:0!important;max-height:390px!important}
@media(max-width:720px){.modalbox.modalbox-wide.v477-attention-modalbox{width:min(94vw,620px)!important;padding:18px!important}.v477-attention-top{padding-right:34px;align-items:stretch;flex-direction:column;gap:9px}.v477-new-patient-btn{align-self:flex-start}.v477-attention-remaster .attention-week-list{grid-template-columns:1fr!important;max-height:none!important}.v477-today-head{align-items:flex-start;flex-direction:column;gap:6px}.v477-today-meta{justify-content:flex-start}}
'''

ATTENTION_JS=r''';(()=>{
  if(window.__v477AttentionRemaster)return;
  window.__v477AttentionRemaster=true;

  const dayName=(d)=>{
    try{return new Intl.DateTimeFormat('es-EC',{weekday:'long',day:'2-digit',month:'long'}).format(d)}catch(_e){return 'Hoy'}
  };
  const applyShell=()=>{
    const modal=document.querySelector('#modal .modalbox');
    if(modal&&modal.querySelector('.v477-attention-remaster'))modal.classList.add('v477-attention-modalbox');
  };

  window.renderAttentionWeek=function(d={}){
    const box=$('#attentionWeekCalendar');if(!box)return;
    const days=d.days||[],today=toISO(new Date());
    const day=days.find(x=>String(x?.date||'').slice(0,10)===today)||null;
    const title=$('#v477TodayTitle'),label=$('#attentionWeekLabel');
    if(title)title.textContent=day?.label?`${day.label} · ${fmtDate(day.date)}`:dayName(new Date());
    if(label)label.textContent=day?`${(day.appointments||[]).length} cita${(day.appointments||[]).length===1?'':'s'}`:'Sin consulta';
    const conflict=$('#attentionWeekConflict');
    if(conflict){
      const n=day?(day.appointments||[]).filter(x=>x?.conflict).length:0;
      conflict.textContent=n?`⚠ ${n} duplicada${n===1?'':'s'}`:'';
      conflict.classList.toggle('hidden',n<=0);
    }
    if(!day){
      box.innerHTML='<div class="attention-week-empty wide v477-no-clinic"><b>Hoy no hay consulta programada</b><span>Puedes buscar un paciente arriba para registrar una atención manualmente.</span></div>';
      return;
    }
    const rows=(day.appointments||[]).map(attentionWeekRow).join('')||'<div class="attention-week-empty">No hay pacientes agendados para hoy.</div>';
    box.innerHTML=`<article class="attention-week-day today v477-today-card"><header><div><b>Pacientes de hoy</b><span>${fmtDate(day.date)}</span></div><strong>${(day.appointments||[]).length}</strong></header><div class="attention-week-list">${rows}</div></article>`;
  };

  window.newAttention=async function(){
    currentPatientSource='general';
    attentionSearchSeq++;
    attentionWeekAnchor=toISO(new Date());
    const todayText=dayName(new Date());
    openModal(`<div class="new-attention-start-modal v477-attention-remaster"><div class="v477-attention-top"><div class="modal-form-heading"><h2>Nueva atención</h2><p>Selecciona al paciente de hoy o búscalo por sus datos.</p></div><button class="primary v477-new-patient-btn" onclick="newPatient(true)">＋ Paciente nuevo</button></div><div class="attention-start-search"><label for="aSearch">Buscar paciente</label><input id="aSearch" class="search uppercase-search" autocomplete="off" autocapitalize="characters" spellcheck="false" placeholder="Cédula, apellidos y nombres, celular o correo" oninput="upperSearchInput(this);attentionSearch()"></div><div id="attentionWeekBlock" class="attention-week-block"><div class="v477-today-head"><div class="v477-today-title"><span class="v477-today-kicker">Agenda de hoy</span><b id="v477TodayTitle">${esc(todayText)}</b></div><div class="v477-today-meta"><strong id="attentionWeekLabel"></strong><span id="attentionWeekConflict" class="attention-week-conflict-note hidden"></span></div></div><div id="attentionWeekCalendar" class="attention-week-calendar"><div class="attention-week-loading">Cargando agenda de hoy…</div></div></div><div id="aResults" class="results attention-results hidden"></div></div>`);
    applyShell();
    loadAttentionWeek(false,attentionWeekAnchor);
    setTimeout(()=>$('#aSearch')?.focus(),0);
  };

  const oldClose=window.closeModal;
  if(typeof oldClose==='function')window.closeModal=function(){
    document.querySelector('#modal .modalbox')?.classList.remove('v477-attention-modalbox');
    return oldClose.apply(this,arguments);
  };
})();'''


def patch_app(s):
    if s.count('APP_VERSION = "4.3.76"')!=1: raise SystemExit('APP_VERSION 4.3.76 no encontrado')
    s=s.replace('APP_VERSION = "4.3.76"','APP_VERSION = "4.3.77"',1)
    visual="const VERSION=\\'4.3.76\\';"
    if visual not in s: raise SystemExit('versión visual 4.3.76 no encontrada')
    s=s.replace(visual,"const VERSION=\\'4.3.77\\';",1)
    marker='@app.get("/v460/overlay.css")'
    if s.count(marker)!=1: raise SystemExit('punto overlay no encontrado')
    injected=(
      'V477_ATTENTION_CSS = r"""'+ATTENTION_CSS+'"""\n'
      'V477_ATTENTION_JS = r"""'+ATTENTION_JS+'"""\n'
      'V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\\n" + V477_ATTENTION_CSS\n'
      'V460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\\n" + V477_ATTENTION_JS\n\n'
      + marker
    )
    return s.replace(marker,injected,1)


def main():
    app=patch_app(joined('app.part',7))
    launcher=joined('ABRIR_RECEPCION.part',4)
    compile(app,'app.py','exec');compile(launcher,'ABRIR_RECEPCION.py','exec')
    tree=ast.parse(app)
    js=None
    for node in tree.body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='V477_ATTENTION_JS' for t in node.targets):
            js=ast.literal_eval(node.value);break
    if not js: raise SystemExit('V477_ATTENTION_JS no encontrado')
    required=['Agenda de hoy','days.find','Paciente nuevo','Buscar paciente','Hoy no hay consulta programada','attentionWeekRow','loadAttentionWeek']
    for token in required:
        if token not in js: raise SystemExit(f'falta {token}')
    if 'days.map' in js: raise SystemExit('el remaster no debe renderizar los tres días')
    if 'moveAttentionWeek' in js or 'currentAttentionWeek' in js: raise SystemExit('el remaster no debe mostrar navegación semanal')
    if 'APP_VERSION = "4.3.77"' not in app or "const VERSION=\\'4.3.77\\';" not in app: raise SystemExit('versiones incorrectas')
    # Facturación v4.3.76 debe permanecer intacta.
    if 'V476_JS' not in app or 'b.estado = "EMITIDA"' not in app or 'doctor_isotype.png' not in launcher:
        raise SystemExit('regresión sobre v4.3.76')

    ap=write_parts(app,'app.part',7);lp=write_parts(launcher,'ABRIR_RECEPCION.part',4)
    ab=app.encode('utf-8');lb=launcher.encode('utf-8')
    manifest={'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,'launcher_version':LAUNCHER_VERSION,'updater_version':'integrado-en-launcher','copy':['ABRIR_RECEPCION.py','app.py','update_manifest.json']}
    mb=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode('utf-8');(OUT/'update_manifest.json').write_bytes(mb)
    base='https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v477/'
    latest={'product':'recepcion-pacientes','version':VERSION,'mandatory':True,'channel':'files-v3','message':'v4.3.77: remasteriza Nueva atención, compacta el modal y muestra únicamente la agenda del día actual.','files':[{'path':'ABRIR_RECEPCION.py','parts':[base+x for x in lp],'sha256':sha(lb),'encoding':'utf-8'},{'path':'app.py','parts':[base+x for x in ap],'sha256':sha(ab),'encoding':'utf-8'},{'path':'update_manifest.json','url':base+'update_manifest.json','sha256':sha(mb),'encoding':'utf-8'}]}
    txt=json.dumps(latest,ensure_ascii=False,indent=2)+'\n';(ROOT/'latest.json').write_text(txt,encoding='utf-8',newline='');(ROOT/'latest-v3.json').write_text(txt,encoding='utf-8',newline='')
    print('OK',VERSION,sha(ab))

if __name__=='__main__': main()

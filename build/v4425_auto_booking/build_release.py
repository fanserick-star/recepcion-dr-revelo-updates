from __future__ import annotations
import hashlib,json,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BASE='updates/v4_4_24_cleanup_old_whatsapp_tests'
OUT=ROOT/'updates/v4_4_25_auto_booking'
VERSION='4.4.25'

def git_text(path:str)->str:
    return subprocess.check_output(['git','show',f'HEAD:{path}'],cwd=ROOT).decode('utf-8-sig')
def write(path:Path,text:str):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8',newline='\n')
def sha(p:Path):return hashlib.sha256(p.read_bytes()).hexdigest()

app=git_text(f'{BASE}/app.py')
js=git_text(f'{BASE}/static/app.js')
html=git_text(f'{BASE}/static/index.html')

assert 'APP_VERSION = "4.4.24"' in app
assert "const VERSION=\\'4.4.24\\';" in app
assert '/static/app.js?v=4.4.24' in html

app=app.replace('APP_VERSION = "4.4.24"','APP_VERSION = "4.4.25"',1)
app=app.replace("const VERSION=\\'4.4.24\\';","const VERSION=\\'4.4.25\\';",1)
html=html.replace('/static/app.js?v=4.4.24','/static/app.js?v=4.4.25',1)

# Endpoint 100% local: no consulta Neon. Devuelve las auto-citas que ya llegaron
# a la copia SQLite mediante la sincronización normal del programa.
endpoint_marker='@app.get("/api/whatsapp-responses/count")\n'
assert endpoint_marker in app
auto_endpoint=r'''
@app.get("/api/auto-bookings/recent")
def auto_bookings_recent_v4425(db: Session = Depends(get_db), user: User = Depends(current_user)):
    try:
        cutoff = date.today() - timedelta(days=1)
        rows = list(db.scalars(
            select(ConfirmafyAgendaItem)
            .where(
                ConfirmafyAgendaItem.source_hash.like("mobile:autoagenda:%"),
                ConfirmafyAgendaItem.fecha >= cutoff,
            )
            .order_by(ConfirmafyAgendaItem.created_at.desc(), ConfirmafyAgendaItem.id.desc())
            .limit(50)
        ))
        return {
            "items": [
                {
                    "id": int(x.id),
                    "source_hash": str(x.source_hash or ""),
                    "nombre": str(x.nombre or "PACIENTE"),
                    "celular": str(x.celular or ""),
                    "fecha": x.fecha.isoformat() if x.fecha else "",
                    "hora": str(x.hora or "")[:5],
                    "created_at": x.created_at.isoformat() if x.created_at else None,
                }
                for x in rows
            ],
            "source": "sqlite-local",
        }
    except Exception as exc:
        return {"items": [], "source": "sqlite-local", "error": str(exc)[:160]}

'''
app=app.replace(endpoint_marker,auto_endpoint+endpoint_marker,1)

# Se ejecuta como último overlay para distinguir las auto-citas y avisar a
# recepción. El sondeo consulta solo el endpoint SQLite anterior.
api_marker='# ---------------------------------------------------------------------------\n# API\n# ---------------------------------------------------------------------------\n'
assert api_marker in app
overlay=r'''
V4425_AUTOBOOK_CSS = r"""
.native-unlinked.native-auto-booked{background:#e8f2ff!important;color:#245c94!important;border:1px solid #bcd5ee!important;font-weight:950!important;letter-spacing:.035em!important}
.native-slot.occupied:has(.native-auto-booked){outline:2px solid #a8caea!important;outline-offset:-2px!important}
"""
V4425_AUTOBOOK_JS = r""";(()=>{
  if(window.__v4425AutoBooking)return;
  window.__v4425AutoBooking=true;
  const PREFIX='mobile:autoagenda:';
  const SEEN_KEY='rp-v4425-auto-bookings-seen';
  const e=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

  function installAgendaBadge(){
    const base=window.nativeAgendaRowCell;
    if(typeof base!=='function'||base.__v4425AutoBooking)return false;
    const wrapped=function(row,date,time){
      let html=base.apply(this,arguments);
      const staged=row?.staged||{};
      const hash=String(staged.source_hash||'');
      if(!hash.startsWith(PREFIX))return html;
      html=html.replace('SIN VINCULAR','AUTOAGENDADA');
      html=html.replace('class="native-unlinked"','class="native-unlinked native-auto-booked"');
      return html;
    };
    wrapped.__v4425AutoBooking=true;
    window.nativeAgendaRowCell=wrapped;
    return true;
  }

  function readSeen(){
    try{const x=JSON.parse(localStorage.getItem(SEEN_KEY)||'[]');return Array.isArray(x)?x:[]}catch{return[]}
  }
  function saveSeen(values){
    try{localStorage.setItem(SEEN_KEY,JSON.stringify(values.slice(-250)))}catch{}
  }
  function localDate(v){
    if(typeof window.fmtDate==='function')try{return window.fmtDate(v)}catch{}
    const m=/^(\d{4})-(\d{2})-(\d{2})/.exec(String(v||''));return m?`${m[3]}/${m[2]}/${m[1]}`:String(v||'');
  }
  function localTime(v){
    if(typeof window.fmtTime==='function')try{return window.fmtTime(v)}catch{}
    return String(v||'').slice(0,5);
  }
  let busy=false;
  async function poll(){
    if(busy||document.hidden)return;
    busy=true;
    try{
      const d=await api('/api/auto-bookings/recent');
      const items=Array.isArray(d?.items)?d.items:[];
      if(!items.length)return;
      const old=readSeen(),seen=new Set(old);
      const fresh=items.filter(x=>x?.source_hash&&String(x.source_hash).startsWith(PREFIX)&&!seen.has(String(x.source_hash)));
      if(!fresh.length)return;
      fresh.forEach(x=>{const h=String(x.source_hash||'');if(h){seen.add(h);old.push(h)}});saveSeen(old);
      const last=fresh[0]||fresh[fresh.length-1];
      const detail=`${String(last?.nombre||'PACIENTE')} · ${localDate(last?.fecha)} · ${localTime(last?.hora)}`;
      const msg=fresh.length===1?`Nueva cita autoagendada: ${detail}`:`${fresh.length} nuevas citas autoagendadas. Última: ${detail}`;
      if(typeof window.rpNotice==='function')window.rpNotice(msg);else alert(msg);
      if(document.querySelector('#agenda:not(.hidden)')&&typeof window.loadAgenda==='function')setTimeout(()=>window.loadAgenda(),250);
    }catch(_e){}
    finally{busy=false}
  }

  let tries=0;
  function boot(){
    if(!installAgendaBadge()&&++tries<15)setTimeout(boot,150);
    setTimeout(poll,900);
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
  setInterval(poll,120000);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)setTimeout(poll,600)});
})();"""
V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\n" + V4425_AUTOBOOK_CSS
V460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\n" + V4425_AUTOBOOK_JS

'''
app=app.replace(api_marker,overlay+api_marker,1)

write(OUT/'app.py',app)
write(OUT/'static/app.js',js)
write(OUT/'static/index.html',html)

manifest={
  'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,
  'launcher_version':'4.3.100-standalone-7','updater_version':'integrado-en-launcher',
  'copy':['app.py','static/app.js','static/index.html','update_manifest.json']
}
write(OUT/'update_manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')

base_url='https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_25_auto_booking/'
files=[]
for rel in ['app.py','static/app.js','static/index.html','update_manifest.json']:
    p=OUT/rel
    files.append({'path':rel,'url':base_url+rel,'sha256':sha(p),'encoding':'utf-8'})
latest={
  'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,
  'mandatory':True,'channel':'files-v3',
  'message':'v4.4.25: integra el autoagendamiento de pacientes. Las citas creadas desde el enlace público aparecen como AUTOAGENDADA y Recepción avisa cuando una nueva auto-cita llega a la copia local. El aviso consulta solo SQLite y no añade sondeos a Neon.',
  'files':files
}
write(ROOT/'build/v4425_auto_booking/candidate_latest.json',json.dumps(latest,ensure_ascii=False,indent=2)+'\n')
print('V4425_BUILD_OK')

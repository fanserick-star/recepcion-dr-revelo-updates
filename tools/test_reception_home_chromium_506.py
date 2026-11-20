"""Real Chromium visual regression for Recepción Inicio at 1600×900.

All visits, appointments and billing figures below are synthetic and local.
No production server, Neon or patient information is accessed.
"""
from __future__ import annotations
import json
import threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "recepcion" / "app"
OUT = ROOT / "reports" / "reception-506-1600x900.png"
OUT.parent.mkdir(parents=True, exist_ok=True)

class StaticHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(APP), **kwargs)
    def log_message(self, *_args):
        return

server = ThreadingHTTPServer(("127.0.0.1", 0), StaticHandler)
threading.Thread(target=server.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{server.server_port}/static/index.html"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width":1600,"height":900}, device_scale_factor=1)
    errors=[]
    page.on("pageerror",lambda exc: errors.append(str(exc)))
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_function("window.__r504PaintHome && typeof applyWeekPayload==='function'",timeout=15000)

    # Install synthetic, read-only API used by the original weekly presentation.
    page.evaluate(r"""() => {
       const visits=[];
       for(let i=1;i<=11;i++){
         visits.push({id:i,patient_id:i,fecha:'2026-11-14',tipo:i%2?'N':'S',
           estado:'ACTIVA',valor:40,procedimiento:'',
           patient:{id:i,nombre:'PACIENTE DE PRUEBA '+i,cedula:'000000000'+i,celular:'0990000000'}});
       }
       visits.push({id:12,patient_id:2,fecha:'2026-11-14',tipo:'S',estado:'ACTIVA',
          valor:30,procedimiento:'ECOGRAFIA',
          patient:{id:2,nombre:'PACIENTE DE PRUEBA 2',cedula:'0000000002'}});
       const week={
         days:[
           {date:'2026-11-11',label:'Miércoles',data:{count:0,total:0,visits:[]}},
           {date:'2026-11-12',label:'Jueves',data:{count:0,total:0,visits:[]}},
           {date:'2026-11-13',label:'Viernes',data:{count:0,total:0,visits:[]}},
           {date:'2026-11-14',label:'Sábado',data:{count:11,total:470,visits}}
         ]
       };
       const agenda={days:[{date:'2026-11-14',appointments:[
         {appointment:{id:1,patient_id:1,hora:'09:00',estado:'CONFIRMADA'},
          patient:{id:1,nombre:'PACIENTE DE PRUEBA 1'}},
         {appointment:{id:2,patient_id:2,hora:'10:20',estado:'PENDIENTE'},
          patient:{id:2,nombre:'PACIENTE DE PRUEBA 2'}},
         {appointment:{id:3,patient_id:3,hora:'16:00',estado:'CONFIRMADA'},
          patient:{id:3,nombre:'PACIENTE DE PRUEBA 3'}}
       ]}]};
       window.api=async (path) => {
         if(String(path).includes('/api/agenda/week')) return agenda;
         if(String(path).includes('/api/ops/today'))return {ok:true,date:'2026-11-14',consultations:11,exam_reviews:0,scheduled_today:3};
         if(String(path).includes('/api/pending-summary'))return {billing:0,agenda:0};
         return {ok:true};
       };
       const app=document.getElementById('app');
       app?.classList.remove('hidden');
       document.getElementById('login')?.classList.add('hidden');
       document.getElementById('inicio')?.classList.remove('hidden');
       applyWeekPayload('2026-11-14',week,'2026-11-14');
       window.__r504HomeEnter?.();
    }""")
    page.wait_for_function(
       "document.querySelectorAll('#todayTable tr[data-v504-patient]').length===11",
       timeout=12000
    )
    page.wait_for_function(
       "(document.querySelector('#v504AgendaList')?.textContent||'').includes('PACIENTE DE PRUEBA 1')",
       timeout=12000
    )
    layout=page.evaluate("""() => {
       const bound=s=>{const e=document.querySelector(s);const r=e?.getBoundingClientRect();return r?{x:r.x,y:r.y,width:r.width,height:r.height}:null};
       return {
         viewport:{width:window.innerWidth,height:window.innerHeight},
         kpis:[...document.querySelectorAll('#r486Metrics .r486-metric')]
           .filter(e=>getComputedStyle(e).display!=='none')
           .map(e=>{const r=e.getBoundingClientRect();return {w:r.width,h:r.height}}),
         table:bound('#todayTable'),
         left:bound('.v504-day-card'),
         sidebar:bound('.v504-side-panel'),
         agenda:bound('#v504AgendaCard'),
         recent:bound('#v504ActivityCard'),
         patients:document.querySelectorAll('#todayTable tr[data-v504-patient]').length,
         agendaNames:(document.querySelector('#v504AgendaList')?.textContent||''),
         activityRows:document.querySelectorAll('#v504ActivityList .v504-activity-entry').length,
         legacyTable:!!document.querySelector('#todayTable .home-patient-table')
       }
    }""")
    print("VISUAL_1600x900",json.dumps(layout,ensure_ascii=False))
    assert layout["viewport"]=={"width":1600,"height":900},layout["viewport"]
    assert len(layout["kpis"])==4,layout
    assert all(85<=x["h"]<=145 for x in layout["kpis"]),layout["kpis"]
    assert layout["patients"]==11,layout
    assert not layout["legacyTable"],"Native original table still won the render"
    assert layout["sidebar"]["x"]>=layout["left"]["x"]+layout["left"]["width"]-4,layout
    assert layout["agenda"]["height"]<430,layout["agenda"]
    assert layout["recent"]["height"]<450,layout["recent"]
    assert layout["recent"]["y"]>=layout["agenda"]["y"]+layout["agenda"]["height"]-2,layout
    assert layout["activityRows"]==4,layout

    # Regression: a legacy repaint or a return through the sidebar must not
    # change the canonical Inicio table. The weekly selector must agree.
    page.evaluate("""() => {
      document.getElementById('todayTable').innerHTML =
        table(weeklyData['2026-11-14'].visits, {home:true});
      document.getElementById('inicio').classList.add('hidden');
      document.getElementById('pacientes').classList.remove('hidden');
      show('inicio');
    }""")
    page.wait_for_function(
      "document.querySelectorAll('#todayTable tr[data-v504-patient]').length===11",
      timeout=12000
    )
    assert not page.locator('#todayTable .home-patient-table').count(),\
      "Returning from sidebar left the legacy table visible"
    page.evaluate("selectHomeDay('2026-11-13');selectHomeDay('2026-11-14')")
    assert page.locator('#todayTable tr[data-v504-patient]').count()==11,\
      "Weekly navigation switched table renderers"
    assert not page.locator('#todayTable .home-patient-table').count(),\
      "Weekly navigation restored the legacy table"
    assert page.locator('#selectedDayTitle .v504-back-today').count()<=1,\
      "Date shortcut was duplicated after navigation"
    page.screenshot(path=str(OUT), full_page=True)
    browser.close()

server.shutdown()
print("RECEPTION_506_CHROMIUM_1600X900_VISUAL_OK",OUT)

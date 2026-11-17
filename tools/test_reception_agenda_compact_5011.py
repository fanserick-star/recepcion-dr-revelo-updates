"""Recepción 5.0.11: synthetic real-Chromium agenda screenshot 1600x900.
No production API, WhatsApp, Neon, booking writes or patient information.
"""
from __future__ import annotations
import json
import threading
from pathlib import Path
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
APP=ROOT/"recepcion"/"app"
OUT=ROOT/"reports"/"reception-agenda-5011-1600x900-synthetic.png"
OUT.parent.mkdir(parents=True,exist_ok=True)

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,directory=str(APP),**kwargs)
    def log_message(self,*args): pass

srv=ThreadingHTTPServer(("127.0.0.1",0),Handler)
threading.Thread(target=srv.serve_forever,daemon=True).start()
try:
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        page=browser.new_page(viewport={"width":1600,"height":900},device_scale_factor=1)
        errors=[]
        page.on("pageerror",lambda e:errors.append(str(e)))
        page.goto(f"http://127.0.0.1:{srv.server_port}/static/index.html",
                  wait_until="domcontentloaded",timeout=30000)
        page.wait_for_function("typeof renderNativeAgenda==='function' && typeof agendaVisibleSlotTimes==='function'")
        page.evaluate(r"""() => {
          const days=[
            {date:'2026-11-18',label:'Miércoles',appointments:[]},
            {date:'2026-11-19',label:'Jueves',appointments:[]},
            {date:'2026-11-20',label:'Viernes',appointments:[]},
            {date:'2026-11-21',label:'Sábado',appointments:[]}
          ];
          const names=['PACIENTE DE EJEMPLO UNO','PACIENTE DE EJEMPLO DOS',
                       'PACIENTE DE EJEMPLO TRES','PACIENTE DE EJEMPLO CUATRO'];
          const slots=agendaVisibleSlotTimes();
          days.forEach((d,i)=>slots.forEach((time,j)=>{
            if((j+i)%4!==0 || (i===0&&time<'10:00'))return;
            d.appointments.push({appointment:{id:1+i*100+j,hora:time,
              fecha:d.date,estado:j%3===0?'CONFIRMADA':'PENDIENTE'},
              patient:{id:1+i*100+j,nombre:names[(i+j)%4]},source_type:'RECEPCION'});
          }));
          window.api=async()=>({days:[]});
          document.querySelector('#app')?.classList.remove('hidden');
          document.querySelector('#login')?.classList.add('hidden');
          document.body.classList.add('v50-ui');
          document.querySelectorAll('main > section').forEach(e=>e.classList.add('hidden'));
          document.querySelector('#agenda').classList.remove('hidden');
          window.agendaNativeWeek={days};
          document.querySelector('#agendaNativeWeekLabel').textContent='18/11/2026 – 21/11/2026';
          document.querySelector('#agendaNativeWeekDate').value='2026-11-18';
          renderNativeAgenda({days});
        }""")
        page.wait_for_selector("#agendaNativeGrid .native-slot")
        layout=page.evaluate(r"""() => {
          const rect=s=>{
            const e=document.querySelector(s),r=e?.getBoundingClientRect();
            return r?{x:r.x,y:r.y,width:r.width,height:r.height,bottom:r.bottom}:null;
          };
          const grid=document.querySelector('#agendaNativeGrid');
          const times=Array.from(grid.querySelectorAll('.native-time:not(.lunch)'));
          return {
            viewport:[innerWidth,innerHeight],
            agenda:rect('#agenda'),title:rect('#agenda .agenda-native-title-row'),
            navigation:rect('#agenda .agenda-native-weekbar'),
            grid:rect('#agendaNativeGrid'),schedule:rect('#agendaNativeGrid .native-schedule'),
            gridScroll: grid.scrollHeight-grid.clientHeight,
            horizontalScroll:grid.scrollWidth-grid.clientWidth,
            fullDaySlots:times.length,
            firstTime:times[0]?.textContent,
            lastTime:times[times.length-1]?.textContent,
            rail:document.querySelector('#v50AgendaRail')
              ?getComputedStyle(document.querySelector('#v50AgendaRail')).display:'absent',
            focus:getComputedStyle(document.querySelector('.agenda-focus-toolbar')).display,
            topDescription:getComputedStyle(document.querySelector('#agenda .section-title-with-brand p')).display,
            firstSlot:rect('#agendaNativeGrid .native-slot'),
            endTime:times[times.length-1]?.getBoundingClientRect().bottom
          };
        }""")
        print("RECEPTION_5011_AGENDA_VISUAL",json.dumps(layout,ensure_ascii=False))
        assert layout["viewport"]==[1600,900]
        assert layout["fullDaySlots"]>=22,layout
        assert "a. m." in layout["firstTime"] and "p. m." in layout["lastTime"],layout
        assert layout["focus"]=="none" and layout["topDescription"]=="none",layout
        assert abs(layout["title"]["y"]-layout["navigation"]["y"])<=5,layout
        assert layout["grid"]["bottom"]<=900,layout
        assert layout["gridScroll"]<=3,"Full clinic day is clipped: "+str(layout)
        assert layout["horizontalScroll"]<=3,"Horizontal agenda overflow: "+str(layout)
        assert layout["endTime"]<=900,layout
        assert layout["rail"] in ("none","absent"),layout
        page.screenshot(path=str(OUT),full_page=False)
        if errors: print("BROWSER_ERRORS",json.dumps(errors[:6],ensure_ascii=False))
        browser.close()
finally:
    srv.shutdown()
print("RECEPTION_5011_AGENDA_1600X900_OK",OUT)

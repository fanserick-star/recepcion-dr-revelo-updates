"""Real Chromium 1600x900 test of the docked patient record in Reception.

Runs only against static files and synthetic demographics. No production login,
real patient data, Neon, billing, WhatsApp or clinical endpoints are called.
"""
from __future__ import annotations
import json
import threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
APP=ROOT/"recepcion"/"app"
OUT=ROOT/"reports"/"reception-514-patients-dossier-1600x900.png"
OUT.parent.mkdir(parents=True,exist_ok=True)

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*a,**kw):
        super().__init__(*a,directory=str(APP),**kw)
    def log_message(self,*_):
        pass

server=ThreadingHTTPServer(("127.0.0.1",0),Handler)
threading.Thread(target=server.serve_forever,daemon=True).start()
url=f"http://127.0.0.1:{server.server_port}/static/index.html"
try:
  with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={"width":1600,"height":900},device_scale_factor=1)
    errors=[]
    page.on("pageerror",lambda exc:errors.append(str(exc)))
    page.goto(url,wait_until="domcontentloaded",timeout=30000)
    page.wait_for_function("typeof openPatient==='function' && window.__reception501",timeout=20000)
    page.evaluate(r"""async () => {
      const patient={
        id:21,nombre:'PACIENTE APELLIDO LARGO SEGUNDO APELLIDO DOS NOMBRES',
        cedula:'0000000001',celular:'0990001234',
        correo:'persona-sintetica-muy-larga@example.invalid',
        fecha_nacimiento:'2002-03-07',lugar:'QUEVEDO',
        notas:'Observaciones para comprobar el panel derecho de la ficha.',
        visitas:[],visits:[],appointments:[],emissions:[],billing:[]
      };
      window.api=async url=>{
        if(String(url).includes('/api/patients/21/profile'))return patient;
        throw new Error('No synthetic endpoint: '+url);
      };
      window.loadClinicalDelivery=()=>{};
      document.querySelector('#app')?.classList.remove('hidden');
      document.querySelector('#login')?.classList.add('hidden');
      for(const section of document.querySelectorAll('#app>main>section'))
        section.classList.add('hidden');
      document.querySelector('#pacientes')?.classList.remove('hidden');
      document.querySelector('#patientResults').innerHTML=
        '<button class="patient-compact-row" type="button"><span class="patient-compact-main"><b class="patient-compact-name">PACIENTE SINTÉTICO</b></span></button>';
      await openPatient(21,'patients');
    }""")
    page.wait_for_function("document.querySelector('#modal.v501-docked-profile.v50-dossier-open .modalbox.v4413-profile-shell')!==null",timeout=12000)
    coords=page.evaluate(r"""() => {
      const rect=s=>{
        const el=document.querySelector(s);const r=el?.getBoundingClientRect();
        return r?{x:r.x,y:r.y,width:r.width,height:r.height,right:r.right,bottom:r.bottom}:null;
      };
      return {
        viewport:window.innerWidth,documentWidth:document.documentElement.scrollWidth,
        dossier:rect('#modal.v501-docked-profile .modalbox.v4413-profile-shell'),
        notes:rect('#modal.v501-docked-profile .v499-profile-note-panel'),
        personal:rect('#modal.v501-docked-profile .v499-personal-panel'),
        actions:rect('#modal.v501-docked-profile .v4413-profile-actions'),
        tabBar:rect('#modal.v501-docked-profile .v4413-profile-tabs'),
        patientList:rect('#patientResults'),
        computedWidth:getComputedStyle(document.querySelector('#modal .modalbox')).width,
        summary:document.querySelector('.v499-personal-panel')?.textContent||''
      };
    }""")
    print("PATIENT_DOCK_1600X900",json.dumps(coords,ensure_ascii=False))
    assert coords["dossier"] and coords["notes"] and coords["personal"] and coords["actions"],coords
    assert coords["dossier"]["x"]>=coords["patientList"]["right"]-10,coords
    for name in ("dossier","notes","personal","actions","tabBar"):
        assert coords[name]["x"]>=0 and coords[name]["right"]<=1592,(name,coords)
    assert coords["notes"]["width"]>=180 and coords["personal"]["width"]>=260,coords
    assert coords["documentWidth"]<=1602,coords
    assert "QUEVEDO" in coords["summary"],coords
    assert not errors,errors
    page.screenshot(path=str(OUT),full_page=False)
    # Inicio: reutiliza la MISMA ficha, pero en el centro; no abre panel lateral.
    page.evaluate(r"""async () => {
      closeModal();
      document.querySelector('#pacientes').classList.add('hidden');
      document.querySelector('#inicio').classList.remove('hidden');
      await openPatient(21,'home');
    }""")
    page.wait_for_function(
      "document.querySelector('#modal.v50-dossier-open:not(.v501-docked-profile) .v5021-dossier')!==null",
      timeout=12000
    )
    page.wait_for_timeout(50)
    home=page.evaluate(r"""() => {
      const m=document.querySelector('#modal'), box=m.querySelector('.modalbox');
      const b=box.getBoundingClientRect();
      return {x:b.x,y:b.y,width:b.width,height:b.height,
        centerX:b.x+b.width/2,centerY:b.y+b.height/2,
        overlay:getComputedStyle(m).display,
        backdrop:getComputedStyle(m).backgroundColor,
        fixed:getComputedStyle(m).position,
        documentWidth:document.documentElement.scrollWidth,
        docked:m.classList.contains('v501-docked-profile')};
    }""")
    print("HOME_PATIENT_MODAL_1600X900",json.dumps(home,ensure_ascii=False))
    assert not home["docked"],home
    assert home["overlay"]=="grid" and home["fixed"]=="fixed",home
    assert abs(home["centerX"]-800)<24 and abs(home["centerY"]-450)<24,home
    assert home["width"]<=1000 and home["height"]<=860,home
    assert home["documentWidth"]<=1602,home
    assert not errors,errors
    browser.close()
finally:
  server.shutdown()
print("RECEPTION_PATIENT_DOCK_NO_RIGHT_CROP_1600X900_OK",OUT)

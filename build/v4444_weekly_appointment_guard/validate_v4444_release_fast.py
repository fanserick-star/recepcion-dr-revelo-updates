from __future__ import annotations

import ast
import hashlib
import json
import pathlib
import subprocess
import sys

from playwright.sync_api import sync_playwright
import validate_v4444 as legacy

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "updates" / "v4_4_44_weekly_appointment_guard"


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise RuntimeError(msg)


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract_string(name: str, app_path: pathlib.Path) -> str:
    tree = ast.parse(app_path.read_text(encoding="utf-8-sig"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            if any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
                return node.value.value
    raise RuntimeError(f"No se encontró {name}")


def browser_phone_guard(app_path: pathlib.Path) -> None:
    js = extract_string("V4444_PHONE_GUARD_JS", app_path)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 900, "height": 700})
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.set_content(r'''
          <div class="form-field"><label>Celular</label><input id="fCel" value="0997225661"></div>
          <script>
          let attentionDraft={stagedId:44,fecha:'2026-09-03'};
          let apiCalls=[],saveCalls=0,used=[],alerts=[];
          const $=s=>document.querySelector(s);
          const esc=s=>String(s??'').replace(/[&<>"']/g,'');
          const toISO=()=> '2026-09-03';
          const formatPhoneValue=v=>String(v||'');
          window.alert=m=>alerts.push(String(m));
          async function api(url,opt){
            apiCalls.push(url);
            if(url.startsWith('/api/identity/phone-owner')){
              const u=new URL('http://local'+url),exclude=Number(u.searchParams.get('exclude_id')||0);
              if(exclude===9)return {duplicate:false,patient:null};
              return {duplicate:true,patient:{id:9,nombre:'PACIENTE EXISTENTE',cedula:'0912345678',celular:'0997225661'}};
            }
            return {};
          }
          async function editPatientFromAttention(id){}
          async function savePatientAndReturnToAttention(id){saveCalls++}
          async function editPatient(id){}
          async function savePatient(id){saveCalls++}
          async function newPatient(){}
          async function saveNewPatient(){saveCalls++}
          async function newPatientFromStaged(itemId,fecha){}
          async function saveNewPatientFromStaged(itemId,fecha){saveCalls++}
          async function saveNewPatientFromConfirmafy(){saveCalls++}
          async function usePatientForStaged(itemId,patientId,fecha){used.push([itemId,patientId,fecha])}
          </script>
        ''')
        page.add_script_tag(content=js)

        # 1) Completar datos: otro paciente posee el teléfono -> aviso visible.
        page.evaluate("editPatientFromAttention(5)")
        page.wait_for_selector('#v4444PhoneDuplicateWarning')
        require('Este celular ya está registrado' in page.locator('#v4444PhoneDuplicateWarning').inner_text(), 'No apareció aviso de celular duplicado al completar datos')
        require('PACIENTE EXISTENTE' in page.locator('#v4444PhoneDuplicateWarning').inner_text(), 'El aviso no identifica la ficha existente')
        require(page.evaluate("apiCalls.some(x=>x.includes('exclude_id=5'))"), 'Completar datos no excluye correctamente la propia ficha')

        # 2) Guardar con ese teléfono debe detenerse antes del PUT estable.
        page.evaluate("savePatientAndReturnToAttention(5)")
        page.wait_for_timeout(40)
        require(page.evaluate("saveCalls===0"), 'Celular duplicado dejó guardar cambios')
        require(page.evaluate("alerts.some(x=>x.includes('Este celular ya está registrado'))"), 'Falta advertencia al intentar guardar celular duplicado')

        # 3) El mismo número del propio paciente NO es duplicado.
        page.evaluate("document.querySelector('#v4444PhoneDuplicateWarning')?.remove(); alerts=[]; apiCalls=[]")
        page.evaluate("editPatientFromAttention(9)")
        page.wait_for_timeout(220)
        require(page.locator('#v4444PhoneDuplicateWarning').count() == 0, 'El propio celular produjo falso positivo')
        page.evaluate("savePatientAndReturnToAttention(9)")
        page.wait_for_timeout(40)
        require(page.evaluate("saveCalls===1"), 'La edición legítima del propio celular quedó bloqueada')
        require(page.evaluate("apiCalls.some(x=>x.includes('exclude_id=9'))"), 'No se consultó exclusión del paciente actual')

        # 4) Cita WhatsApp: teléfono ya viene precargado y debe detectarse sin escribir.
        page.evaluate("saveCalls=0;apiCalls=[];alerts=[];attentionDraft={stagedId:44,fecha:'2026-09-03'}")
        page.evaluate("newPatientFromStaged(44,'2026-09-03')")
        page.wait_for_selector('#v4444PhoneDuplicateWarning')
        require(page.locator('#v4444UseExistingPhoneOwner').count() == 1, 'Cita precargada no ofrece usar la ficha existente')
        page.click('#v4444UseExistingPhoneOwner')
        page.wait_for_timeout(40)
        require(page.evaluate("used.length===1 && used[0][0]===44 && used[0][1]===9 && used[0][2]==='2026-09-03'"), 'Usar ficha existente no conserva la cita staged')

        # 5) Aun sin pulsar el botón, Guardar y continuar no puede crear duplicado.
        page.evaluate("used=[];saveCalls=0")
        page.evaluate("saveNewPatientFromStaged(44,'2026-09-03')")
        page.wait_for_timeout(40)
        require(page.evaluate("saveCalls===0"), 'Cita staged dejó crear paciente con celular duplicado')
        require(not errors, f"Errores JS en guardia de celular: {errors}")
        browser.close()
    print('V4444_BROWSER_PHONE_GUARD_OK')


def main() -> None:
    # 1) Pruebas que sí corresponden a lo modificado: contrato de guardia y
    # browser real del diálogo Cancelar / Agendar de todas formas.
    legacy.build()
    legacy.contract()
    legacy.browser_guard()

    # 2) Generar el artefacto final con puente WhatsApp/Cloud + guardia celular.
    subprocess.run([sys.executable, str(HERE / "build_v4444_cloud_sync.py")], cwd=ROOT, check=True)
    app_path = OUT / "app.py"
    text = app_path.read_text(encoding="utf-8-sig")
    compile(text, str(app_path), "exec")

    for marker in (
        'APP_VERSION = "4.4.44"',
        '/api/agenda/appointments/guarded',
        'Agendar de todas formas',
        '_v4444_sync_cloud_staged_for_dates',
        'v4444_cloud_staged_agenda_catchup',
        'request.url.path == "/api/agenda/week"',
        'core.queue_count() > 0',
        'core.check_cloud(force=False)',
        'core.ConfirmafyAgendaItem.fecha.in_(normalized)',
        'mobile:whatsapp-cloud-test:',
        '/api/identity/phone-owner',
        'V4444_PHONE_GUARD_JS',
        'window.__v4444PhoneDuplicateGuard=true',
        'savePatientAndReturnToAttention',
        'saveNewPatientFromStaged',
        'Este celular ya está registrado',
        'exclude_id=',
    ):
        require(marker in text, f"Falta contrato: {marker}")

    start = text.index('# v4.4.44 — puente seguro Cloud/WhatsApp')
    end = text.index('FEATURE_BOOT_OK = True', start)
    sync = text[start:end]
    require('core.Patient(' not in sync, 'El puente no puede crear Patients')
    require('delete(core.ConfirmafyAgendaItem)' not in sync, 'El puente no puede borrar citas locales')
    require('FORCE_OFFLINE' in sync, 'Falta protección offline')
    require('queue_count() > 0' in sync, 'Falta protección de cola local pendiente')
    require('if ldb.get(core.ConfirmafyAgendaItem, cloud_id) is not None:' in sync, 'Falta protección contra colisión de ID local')

    phone_start = text.index('# v4.4.44 — protección de celular duplicado')
    phone_end = text.index('FEATURE_BOOT_OK = True', phone_start)
    phone_block = text[phone_start:phone_end]
    require('core.normalize_lookup_phone(patient.celular) == normalized' in phone_block, 'Comparación de teléfono no está normalizada')
    require('int(patient.id) == int(exclude_id)' in phone_block, 'Editar no excluye la propia ficha')
    require('core.Patient.celular.is_not(None)' in phone_block, 'Consulta de celular no limita candidatos vacíos')
    require('No se guardó ningún cambio' in phone_block, 'Falta bloqueo explícito antes de guardar')

    # 3) Reproducir en Chromium los bugs de celular, incluido el número precargado.
    browser_phone_guard(app_path)

    # 4) Todo lo que NO debía cambiar debe seguir siendo exactamente el mismo
    # byte que la estable 4.4.43. No hay launcher/base/UI nuevo que pueda romper arranque.
    expected = {
        'app_base_4428.py': 'e5d3d96b9289169aa52524e8cc2f5f0ec9567c8da5e11d482151b12fc8ff85ba',
        'static/app.js': '0657c3b76721df2e28ec812856a2fc25944d2908382b13fbf3f115dad3e18d90',
        'static/index.html': '16d30060a0be19215e612c4ba897e801873dd359712e90d4dc14e32513b25728',
    }
    for rel, digest in expected.items():
        require(sha(OUT / rel) == digest, f"Cambió archivo estable prohibido: {rel}")
    launcher = b''.join((OUT / f'ABRIR_RECEPCION.part{i}').read_bytes() for i in range(1, 5))
    require(hashlib.sha256(launcher).hexdigest() == '39ee0e178c9f86387b220905f2f8612f6c61e721a928fd8ed3ca514a639b007e', 'Cambió launcher estable')
    compile(launcher.decode('utf-8-sig'), 'ABRIR_RECEPCION.py', 'exec')

    candidate = json.loads((OUT / 'candidate_latest.json').read_text(encoding='utf-8'))
    require(candidate.get('version') == '4.4.44' and candidate.get('app_version') == '4.4.44', 'Candidato incorrecto')
    message = str(candidate.get('message') or '')
    require('WhatsApp/Agenda Cloud' in message, 'Mensaje de release no describe sync')
    require('celular' in message.lower() and 'duplicados' in message.lower(), 'Mensaje de release no describe guardia de celular')
    for item in candidate.get('files') or []:
        rel = item['path']
        if rel == 'ABRIR_RECEPCION.py':
            data = launcher
        else:
            data = (OUT / rel).read_bytes()
        require(hashlib.sha256(data).hexdigest() == item['sha256'], f"SHA candidato incorrecto: {rel}")

    print('VALIDATE_V4444_RELEASE_FAST_OK')


if __name__ == '__main__':
    main()

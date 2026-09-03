from __future__ import annotations

import ast
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "updates" / "v4_4_46_phone_guard"
SOURCE_REF = "6fca4c5511054bef790273a81c109f4c05a63717"
SOURCE_PREFIX = "updates/v4_4_45_attention_agenda_identity_fix"
SOURCE_APP_SHA256 = "59d074befb07c7b7b0ffb5ebfc00eed193b8cd367589bf79c12eeeb215d09527"


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_bytes(path: str) -> bytes:
    return subprocess.check_output(["git", "show", f"{SOURCE_REF}:{SOURCE_PREFIX}/{path}"], cwd=ROOT)


def build() -> None:
    subprocess.run([sys.executable, str(HERE / "build_v4446.py")], cwd=ROOT, check=True)


def extract_string(name: str) -> str:
    tree = ast.parse((OUT / "app.py").read_text(encoding="utf-8-sig"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            if any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
                return node.value.value
    raise AssertionError(f"No se encontró {name}")


def contracts() -> None:
    source_app = git_bytes("app.py")
    require(sha(source_app) == SOURCE_APP_SHA256, "Fuente pública v4.4.45 cambió")
    app_path = OUT / "app.py"
    app = app_path.read_text(encoding="utf-8-sig")
    compile(app, "app.py", "exec")
    for marker in (
        'APP_VERSION = "4.4.46"',
        '/api/agenda/appointments/guarded',
        'Agendar de todas formas',
        '_v4445_sync_cloud_agenda_for_dates',
        'window.__v4445StagedIdentityFix',
        'Encontramos una ficha con este celular',
        '/api/identity/phone-owner',
        'window.__v4446PhoneDuplicateGuard',
        'Este celular ya está registrado',
        'savePatientAndReturnToAttention',
        'saveNewPatientFromStaged',
        'v4445CreateDifferentStaged',
        'int(patient.id) == int(exclude_id)',
        'core.normalize_lookup_phone(patient.celular) == normalized',
    ):
        require(marker in app, f"Falta contrato: {marker}")

    start = app.index('# v4.4.46 — guardia de celular')
    end = app.index('FEATURE_BOOT_OK = True', start)
    feature = app[start:end]
    require('CREATE TABLE' not in feature.upper(), 'La 4.4.46 intenta crear tablas')
    require('DROP TABLE' not in feature.upper(), 'La 4.4.46 intenta borrar tablas')
    require('db.delete(' not in feature and 'ldb.delete(' not in feature, 'La 4.4.46 intenta borrar filas')
    require('core.Patient.celular.in_(sorted(variants))' in feature, 'La búsqueda de celular no usa índice/candidatos concretos')
    require('No se guardó ningún cambio' in feature, 'Falta bloqueo explícito antes del guardado')

    manifest = json.loads((OUT / "update_manifest.json").read_text(encoding="utf-8"))
    candidate = json.loads((OUT / "candidate_latest.json").read_text(encoding="utf-8"))
    require(manifest.get('version') == '4.4.46' and candidate.get('version') == '4.4.46', 'Versión incorrecta')
    require(manifest.get('copy') == ['app.py', 'update_manifest.json'], 'La actualización dejó de ser mínima')
    require([x.get('path') for x in candidate.get('files', [])] == ['app.py', 'update_manifest.json'], 'Candidate toca archivos de más')
    require(manifest.get('required_dependencies') == ['app_base_4428.py'], 'Se perdió dependencia base')
    require(manifest.get('required_python_packages') == [{'import': 'pg8000', 'pip': 'pg8000==1.31.2'}], 'Se perdió guardia pg8000')
    by_path = {x['path']: x for x in candidate['files']}
    require(by_path['app.py']['sha256'] == sha(app_path.read_bytes()), 'SHA app.py incorrecto')
    require(by_path['update_manifest.json']['sha256'] == sha((OUT / 'update_manifest.json').read_bytes()), 'SHA manifest incorrecto')
    print('V4446_CONTRACT_OK')


def js_syntax() -> None:
    script = extract_string('V4446_PHONE_GUARD_JS')
    with tempfile.TemporaryDirectory() as td:
        path = pathlib.Path(td) / 'v4446.js'
        path.write_text(script, encoding='utf-8')
        result = subprocess.run(['node', '--check', str(path)], text=True, capture_output=True)
        if result.returncode:
            print(result.stdout); print(result.stderr)
        require(result.returncode == 0, 'JavaScript v4.4.46 no compila')
    print('V4446_JS_SYNTAX_OK')


def browser_phone_guard() -> None:
    script = extract_string('V4446_PHONE_GUARD_JS')
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 900, 'height': 700})
        errors = []
        page.on('pageerror', lambda exc: errors.append(str(exc)))
        page.set_content(r'''
          <div class="form-field"><label>Celular</label><input id="fCel" value="0997225661"></div>
          <script>
          let attentionDraft={stagedId:44,fecha:'2026-09-03'};
          let apiCalls=[],saveCalls=0,used=[],alerts=[],newStagedCalls=0;
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
          async function newPatientFromStaged(itemId,fecha){newStagedCalls++}
          async function saveNewPatientFromStaged(itemId,fecha){saveCalls++}
          async function saveNewPatientFromConfirmafy(){saveCalls++}
          async function usePatientForStaged(itemId,patientId,fecha){used.push([itemId,patientId,fecha])}
          window.v4445CreateDifferentStaged=function(){throw Error('No debe conservar la función capturada antigua')}
          </script>
        ''')
        page.add_script_tag(content=script)

        # Bug exacto: completar datos en editMode con celular de OTRA ficha.
        page.evaluate("editPatientFromAttention(5)")
        page.wait_for_selector('#v4446PhoneDuplicateWarning')
        text = page.locator('#v4446PhoneDuplicateWarning').inner_text()
        require('Este celular ya está registrado' in text and 'PACIENTE EXISTENTE' in text, 'No apareció la advertencia correcta al completar datos')
        require(page.evaluate("apiCalls.some(x=>x.includes('exclude_id=5'))"), 'Completar datos no excluye la ficha actual')
        page.evaluate("savePatientAndReturnToAttention(5)")
        page.wait_for_timeout(50)
        require(page.evaluate('saveCalls===0'), 'Completar datos guardó un celular duplicado')
        require(page.evaluate("alerts.some(x=>x.includes('Este celular ya está registrado'))"), 'Guardar no mostró advertencia final')

        # Mantener el propio celular debe seguir funcionando sin falso positivo.
        page.evaluate("document.querySelector('#v4446PhoneDuplicateWarning')?.remove();apiCalls=[];alerts=[]")
        page.evaluate("editPatientFromAttention(9)")
        page.wait_for_timeout(280)
        require(page.locator('#v4446PhoneDuplicateWarning').count() == 0, 'El propio celular produjo falso positivo')
        page.evaluate("savePatientAndReturnToAttention(9)")
        page.wait_for_timeout(50)
        require(page.evaluate('saveCalls===1'), 'La edición legítima quedó bloqueada')
        require(page.evaluate("apiCalls.some(x=>x.includes('exclude_id=9'))"), 'No se verificó exclusión del propio paciente')

        # El celular staged viene precargado: debe advertirse sin volver a escribirlo.
        page.evaluate("saveCalls=0;apiCalls=[];alerts=[]")
        page.evaluate("newPatientFromStaged(44,'2026-09-03')")
        page.wait_for_selector('#v4446PhoneDuplicateWarning')
        require(page.locator('#v4446UseExistingPhoneOwner').count() == 1, 'Staged precargado no ofrece usar ficha existente')
        page.click('#v4446UseExistingPhoneOwner')
        page.wait_for_timeout(50)
        require(page.evaluate("used.length===1 && used[0][0]===44 && used[0][1]===9 && used[0][2]==='2026-09-03'"), 'Usar ficha existente perdió contexto de la cita')

        # El botón "Es otra persona" de v4.4.45 debe pasar por la nueva guardia.
        page.evaluate("document.querySelector('#v4446PhoneDuplicateWarning')?.remove();used=[];newStagedCalls=0")
        page.evaluate("v4445CreateDifferentStaged(44,'2026-09-03')")
        page.wait_for_selector('#v4446PhoneDuplicateWarning')
        require(page.evaluate('newStagedCalls===1'), 'Es otra persona no fue redirigido por la guardia 4.4.46')

        # Guardar staged con teléfono repetido nunca debe llegar al POST estable.
        page.evaluate("saveCalls=0;alerts=[]")
        page.evaluate("saveNewPatientFromStaged(44,'2026-09-03')")
        page.wait_for_timeout(50)
        require(page.evaluate('saveCalls===0'), 'Staged dejó crear un paciente con celular duplicado')
        require(not errors, f'Errores JS: {errors}')
        browser.close()
    print('V4446_BROWSER_PHONE_GUARD_OK')


def main() -> None:
    build()
    contracts()
    js_syntax()
    browser_phone_guard()
    print('VALIDATE_V4446_OK')


if __name__ == '__main__':
    main()

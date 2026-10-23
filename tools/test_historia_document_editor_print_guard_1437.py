"""Regresión de editores clínicos amplios y prevención de múltiples impresiones.

Todos los datos son sintéticos y se crean en un SQLite temporal.
No se conecta a Neón, Windows ni una impresora real.
"""
import json
import re
import sqlite3
import subprocess
import tempfile
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "historia-clinica" / "app"))
from fastapi import FastAPI
import documentos_clinicos
import informes_clinicos


def route(app, path):
    return next(
        item.endpoint for item in app.routes
        if getattr(item, "path", "") == path and "GET" in (getattr(item, "methods", ()) or ())
    )


def fake_base(title, body, active="inicio"):
    return (
        '<!doctype html><html lang="es"><head><title>' + title + '</title></head>'
        '<body class="cp-remaster-app">'
        '<header class="topbar"><a href="/">INICIO</a><a href="/configuracion">Configuración</a></header>'
        '<main>' + body + '</main>'
        '<footer>Historia Clínica</footer></body></html>'
    )


def main():
    with tempfile.TemporaryDirectory(prefix="historia_editor_1437_") as temp:
        root = Path(temp)
        db_path = root / "clinica.sqlite"
        with sqlite3.connect(db_path) as conn:
            conn.executescript("""
                CREATE TABLE patients (
                    id TEXT PRIMARY KEY,name TEXT,national_id TEXT,birth_date TEXT,
                    sex TEXT,deleted_at TEXT
                );
                CREATE TABLE encounters (
                    id TEXT PRIMARY KEY,patient_id TEXT,queue_id TEXT,
                    note_status TEXT,deleted_at TEXT,diagnosis TEXT,
                    clinical_note TEXT
                );
                INSERT INTO patients(id,name,national_id,birth_date,sex)
                   VALUES('p1','PACIENTE FICTICIO','0000000000','1980-01-01','M');
            """)
        documentos_clinicos.ensure_schema(db_path)
        app = FastAPI()
        context = {"DB_PATH": db_path, "ROOT": root, "base": fake_base}
        documentos_clinicos.install(app, context)
        informes_clinicos.install(app, context)

        forms = {
            "rx": route(app, "/recetas/nueva")("p1").body.decode(),
            "cert": route(app, "/certificados/nuevo")("p1").body.decode(),
            "rest": route(app, "/certificados/reposo/nuevo")("p1").body.decode(),
            "report": route(app, "/informes/nuevo")("p1", "cistoscopia").body.decode(),
        }
        for key, page in forms.items():
            assert '<body class="cp-remaster-app clinical-document-editor">' in page, key
            assert 'body.clinical-document-editor > header.topbar' in page, key
            assert 'body.clinical-document-editor > footer' in page, key
            assert 'max-width:1600px' in page, key
            assert 'id="clinical-document-progress"' in page, key
            assert 'role="status" aria-live="polite"' in page, key
            assert 'REPEAT_WAIT_MS=20000' in page, key
            assert 'if(busy)' in page and 'if(printing&&remaining>0)' in page, key
            assert page.count('window.historiaDocumentAction=(function()') == 1, key
            assert 'paciente' in page.lower() or 'Paciente' in page, key

        assert "['rx-save','rx-preview','rx-print','rx-pdf']" in forms["rx"]
        assert "return await window.historiaNativePrint(j.preview_url,'recipe');" in forms["rx"]
        assert "['cert-save','cert-preview','cert-print','cert-pdf']" in forms["cert"]
        assert "return await window.historiaNativePrint(j.preview_url,'certificate');" in forms["cert"]
        assert "['rest-save','rest-preview','rest-print','rest-pdf']" in forms["rest"]
        assert "return await window.historiaNativePrint(j.preview_url,'certificate');" in forms["rest"]
        assert "['report-save','report-preview','report-print','report-sign']" in forms["report"]
        assert "return await window.historiaNativePrint(data.preview_url,'certificate');" in forms["report"]

        # El listado y la aplicación principal no deben perder su navegación.
        listing = route(app, "/recetas")().body.decode()
        assert '<body class="cp-remaster-app">' in listing
        assert 'clinical-document-editor' not in listing
        assert '<header class="topbar">' in listing
        assert 'INICIO' in listing
        assert documentos_clinicos._document_editor_shell(
            lambda title, body, active: body, "Prueba", "CONTENIDO", "recetas"
        ) == "CONTENIDO"

        # Ejecución real del guard JS con DOM simulado: cinco clics
        # simultáneos deben producir una sola petición. No usa impresora.
        guarded = re.search(
            r"<script>\s*(window\.historiaDocumentAction=\(function\(\)\{.*?\}\)\(\);)\s*</script>",
            forms["rx"], re.S,
        )
        assert guarded, "No se encontró el controlador común de documentos"
        scenario = r"""
const vm=require('node:vm');
const ids=['rx-save','rx-preview','rx-print','rx-pdf'];
const elements={};
for(const id of ids)elements[id]={textContent:id,disabled:false};
elements['rx-state']={textContent:'Sin guardar'};
elements['clinical-document-progress']={textContent:'',dataset:{},hidden:true};
const ctx={
  window:{},document:{getElementById(id){return elements[id]||null;}},
  Date,Math,setTimeout(){return 1;},clearTimeout(){},
};
vm.runInNewContext(ACTION_CODE,ctx);
const action=ctx.window.historiaDocumentAction;
let jobs=0;
async function work(){jobs++;await Promise.resolve();return true;}
async function test(){
  const results=await Promise.all(Array.from({length:5},()=>
    action('print',ids,'rx-state',work)));
  if(jobs!==1 || results.filter(x=>x===true).length!==1)
    throw Error('Cinco clics crearon '+jobs+' solicitudes');
  if(elements['rx-print'].disabled!==true)
    throw Error('La protección de 20 s no bloqueó el botón');
  await action('print',ids,'rx-state',work);
  if(jobs!==1)throw Error('Doble impresión aceptada durante cooldown');
  if(!elements['clinical-document-progress'].textContent.includes('Impresión ya solicitada'))
    throw Error('No se avisó al usuario sobre la impresión previa');
  await action('save',ids,'rx-state',async()=>true);
  if(elements['rx-print'].disabled!==true)
    throw Error('Guardar desbloqueó incorrectamente la reimpresión');
  // El fallo de envío no debe activar un nuevo periodo de bloqueo.
  const elements2={};
  for(const id of ids)elements2[id]={textContent:id,disabled:false};
  elements2['rx-state']={textContent:'Sin guardar'};
  elements2['clinical-document-progress']={textContent:'',dataset:{},hidden:true};
  const ctx2={window:{},document:{getElementById(id){return elements2[id]||null;}},
    Date,Math,setTimeout(){return 1;},clearTimeout(){}};
  vm.runInNewContext(ACTION_CODE,ctx2);
  let retries=0;
  const doAction=ctx2.window.historiaDocumentAction;
  await doAction('print',ids,'rx-state',async()=>{retries++;return false;});
  await doAction('print',ids,'rx-state',async()=>{retries++;return true;});
  if(retries!==2)throw Error('Fallo previo impidió reintentar');
  console.log('HISTORIA_JS_5_CLICS_1_IMPRESION_OK');
}
test().catch(e=>{console.error(e);process.exitCode=1});
""".replace("ACTION_CODE", json.dumps(guarded.group(1)))
        subprocess.run(["node", "-e", scenario], check=True, timeout=15)
        print("HISTORIA_EDITOR_PRINT_GUARD_1437_OK")


if __name__ == "__main__":
    main()

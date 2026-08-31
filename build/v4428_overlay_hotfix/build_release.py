from __future__ import annotations
import hashlib,json,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BASE='updates/v4_4_27_neon_ultra'
OUT=ROOT/'updates/v4_4_28_overlay_hotfix'
VERSION='4.4.28'

def git_text(path:str)->str:
    return subprocess.check_output(['git','show',f'HEAD:{path}'],cwd=ROOT).decode('utf-8-sig')
def write(path:Path,text:str):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8',newline='\n')
def sha(p:Path):return hashlib.sha256(p.read_bytes()).hexdigest()

app=git_text(f'{BASE}/app.py')
js=git_text(f'{BASE}/static/app.js')
html=git_text(f'{BASE}/static/index.html')

assert 'APP_VERSION = "4.4.27"' in app
assert "const VERSION=\\'4.4.27\\';" in app
assert '/static/app.js?v=4.4.27' in html
assert 'V4425_AUTOBOOK_CSS = r"""' in app
assert '# v4.3.60 — visibilidad de versión + estados de Agenda con alto contraste' in app

early='''V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\\n" + V4425_AUTOBOOK_CSS\nV460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\\n" + V4425_AUTOBOOK_JS\n'''
assert app.count(early)==1, app.count(early)
# v4.4.25 añadió AUTOAGENDADA antes de que el overlay base V460 existiera.
# Python compila esa referencia, pero al ejecutar el módulo produce NameError.
# Quitamos esas dos líneas tempranas y las aplicamos al final, después de que
# todos los overlays históricos ya fueron definidos/concatenados.
app=app.replace(early,'',1)
late='''\n\n# v4.4.28 — AUTOAGENDADA se concatena al final, cuando V460 ya existe.\nV460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\\n" + V4425_AUTOBOOK_CSS\nV460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\\n" + V4425_AUTOBOOK_JS\n'''
app=app.rstrip()+late+'\n'

app=app.replace('APP_VERSION = "4.4.27"','APP_VERSION = "4.4.28"',1)
app=app.replace("const VERSION=\\'4.4.27\\';","const VERSION=\\'4.4.28\\';",1)
html=html.replace('/static/app.js?v=4.4.27','/static/app.js?v=4.4.28',1)

# Guardia específica del fallo observado: la definición base debe aparecer antes
# de cualquier concatenación que lea V460 en el lado derecho.
base_pos=app.index('V460_OVERLAY_CSS = r"""')
autobook_pos=app.rindex('V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\\n" + V4425_AUTOBOOK_CSS')
assert base_pos < autobook_pos
assert app[:base_pos].count('V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "")') == 0
assert app[:base_pos].count('V460_OVERLAY_JS = (V460_OVERLAY_JS or "")') == 0

write(OUT/'app.py',app)
write(OUT/'static/app.js',js)
write(OUT/'static/index.html',html)
manifest={
  'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,
  'launcher_version':'4.3.100-standalone-7','updater_version':'integrado-en-launcher',
  'copy':['app.py','static/app.js','static/index.html','update_manifest.json']
}
write(OUT/'update_manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
base_url='https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_28_overlay_hotfix/'
files=[]
for rel in ['app.py','static/app.js','static/index.html','update_manifest.json']:
    p=OUT/rel
    files.append({'path':rel,'url':base_url+rel,'sha256':sha(p),'encoding':'utf-8'})
latest={
  'product':'recepcion-pacientes','version':VERSION,'app_version':VERSION,'runtime_version':VERSION,
  'mandatory':True,'channel':'files-v3',
  'message':'v4.4.28: corrige el arranque de Recepción después de v4.4.27. Reordena de forma segura el overlay AUTOAGENDADA y conserva íntegra la ultra optimización de Neon. No modifica Excel ni bases SQLite locales.',
  'files':files
}
write(ROOT/'build/v4428_overlay_hotfix/candidate_latest.json',json.dumps(latest,ensure_ascii=False,indent=2)+'\n')
print('V4428_OVERLAY_HOTFIX_BUILD_OK')

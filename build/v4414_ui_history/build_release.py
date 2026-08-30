from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = "updates/v4_4_13_patient_profile"
OUT = ROOT / "updates/v4_4_14_ui_history"
VERSION = "4.4.14"


def git_bytes(path: str) -> bytes:
    return subprocess.check_output(["git", "show", f"HEAD:{path}"], cwd=ROOT)


def text(path: str) -> str:
    return git_bytes(path).decode("utf-8-sig")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


if OUT.exists():
    shutil.rmtree(OUT)
(OUT / "static").mkdir(parents=True, exist_ok=True)

app = text(f"{SRC}/app.py")
js = text(f"{SRC}/static/app.js")
index = text(f"{SRC}/static/index.html")

assert 'APP_VERSION = "4.4.13"' in app
assert '/static/app.js?v=4.4.13' in index
assert 'v4413-patient-profile-css' in index
assert 'function historicalLastLabel(p={})' in js
assert 'Última atención histórica:' in js

# Versión real + badge del overlay.
app = app.replace('APP_VERSION = "4.4.13"', 'APP_VERSION = "4.4.14"', 1)
app, n_badge = re.subn(r"(const VERSION=.*?)4\.4\.13(.*?;)", r"\g<1>4.4.14\g<2>", app, count=1)
assert n_badge == 1

# Históricos: mostrar mes/año si hay fecha; si no, al menos el último año conocido.
old_helpers = "function historicalLastDate(p={}){return p.historical_last_visit_date||p.historical?.last_visit_date||null}\nfunction historicalLastLabel(p={}){const d=historicalLastDate(p);return d?`Última atención histórica con fecha disponible: ${fmtDate(d)}`:`Paciente registrado en el histórico ${historicalYears(p)}`}"
new_helpers = "function historicalLastDate(p={}){return p.historical_last_visit_date||p.historical?.last_visit_date||null}\nfunction historicalLastPeriod(p={}){const d=String(historicalLastDate(p)||'');const m=/^(\\d{4})-(\\d{2})/.exec(d);if(m){const months=['enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre'];const i=Number(m[2])-1;if(i>=0&&i<12)return `${months[i]} ${m[1]}`}const y=Number(p.historical_last_year||p.historical?.last_year||0);return y?String(y):''}\nfunction historicalLastLabel(p={}){const period=historicalLastPeriod(p);return period?`Última atención histórica: ${period}`:`Paciente registrado en el histórico ${historicalYears(p)}`}"
assert js.count(old_helpers) == 1
js = js.replace(old_helpers, new_helpers, 1)

old_search = "const last=p.historical_last_visit_date||p.ultima_atencion;\n          const lastText=last?`Última atención histórica: ${fmtDate(last)}`:`Paciente histórico ${years}`;"
new_search = "const period=historicalLastPeriod(p);\n          const lastText=period?`Última atención histórica: ${period}`:`Último registro histórico: ${p.historical_last_year||years}`;"
assert js.count(old_search) == 1
js = js.replace(old_search, new_search, 1)

# Reservar el espacio físico de la X en el encabezado de la ficha.
old_css = ".v4413-profile-head{display:flex;justify-content:space-between;gap:18px;align-items:flex-start}"
new_css = ".v4413-profile-head{display:flex;justify-content:space-between;gap:18px;align-items:flex-start;padding-right:58px}.modalbox.v4413-profile-shell>.x{z-index:8}"
assert index.count(old_css) == 1
index = index.replace(old_css, new_css, 1)
index = index.replace('/static/app.js?v=4.4.13', '/static/app.js?v=4.4.14', 1)

# El layout móvil también conserva hueco para cerrar, pero permite envolver acciones.
old_mobile = "@media(max-width:720px){.v4413-profile-head{display:grid}"
new_mobile = "@media(max-width:720px){.v4413-profile-head{display:grid;padding-right:48px}"
assert index.count(old_mobile) == 1
index = index.replace(old_mobile, new_mobile, 1)

app_b = app.encode('utf-8')
js_b = js.encode('utf-8')
index_b = index.encode('utf-8')

manifest = {
    "product": "recepcion-pacientes",
    "version": VERSION,
    "app_version": VERSION,
    "runtime_version": VERSION,
    "launcher_version": "4.3.100-standalone-7",
    "updater_version": "integrado-en-launcher",
    "copy": ["app.py", "static/app.js", "static/index.html", "update_manifest.json"],
}
manifest_b = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode('utf-8')

(OUT / 'app.py').write_bytes(app_b)
(OUT / 'static' / 'app.js').write_bytes(js_b)
(OUT / 'static' / 'index.html').write_bytes(index_b)
(OUT / 'update_manifest.json').write_bytes(manifest_b)

base_url = "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_14_ui_history"
latest = {
    "product": "recepcion-pacientes",
    "version": VERSION,
    "app_version": VERSION,
    "runtime_version": VERSION,
    "mandatory": True,
    "channel": "files-v3",
    "message": "v4.4.14: evita choque entre Nueva atención y cerrar ficha; históricos muestran mes/año de última atención cuando está disponible.",
    "files": []
}
for rel, data in [
    ('app.py', app_b),
    ('static/app.js', js_b),
    ('static/index.html', index_b),
    ('update_manifest.json', manifest_b),
]:
    latest['files'].append({"path": rel, "url": f"{base_url}/{rel}", "sha256": sha(data), "encoding": "utf-8"})

candidate = ROOT / 'build' / 'v4414_ui_history' / 'candidate_latest.json'
candidate.write_text(json.dumps(latest, ensure_ascii=False, indent=2) + "\n", encoding='utf-8')

# Candados de alcance.
assert 'padding-right:58px' in index
assert 'function historicalLastPeriod' in js
assert "['enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre']" in js
assert '⚠ Datos incompletos' in js
assert 'Historial de Agenda' in js and 'Historial de Facturación' in js
assert 'billingScope.querySelectorAll' in app
assert 'RP_PORT' in app and 'pg8000' in app
print('V4414_BUILD_OK')
print('app', sha(app_b))
print('js', sha(js_b))
print('index', sha(index_b))

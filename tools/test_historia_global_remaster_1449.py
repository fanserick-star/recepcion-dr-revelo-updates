"""Contrato visual del tema unificado v1.4.49; no toca datos clínicos."""
from __future__ import annotations
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "historia-clinica" / "app"
app = (ROOT / "app.py").read_text(encoding="utf-8")
css = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
materials = (ROOT / "material_pacientes.py").read_text(encoding="utf-8")
consent = (ROOT / "consentimiento_informado.py").read_text(encoding="utf-8")
docs = (ROOT / "documentos_clinicos.py").read_text(encoding="utf-8")
reports = (ROOT / "informes_clinicos.py").read_text(encoding="utf-8")

for name, src in (("app",app), ("materials",materials), ("consent",consent), ("documents",docs), ("reports",reports)):
    ast.parse(src,filename=name+".py")

assert "def _global_remaster_sidebar(active: str)" in app
assert app.index("def _global_remaster_sidebar") < app.index("documentos_clinicos.install(app, globals())")
assert app.index("_HC_GLOBAL_SOURCE_BASE = base") < app.index("informes_clinicos.install(app, globals())")
assert "if active != \"inicio\" and '<body class=\"cp-remaster-app\">' in html" in app
assert "if '<main>' in html and 'class=\"hc-g-sidebar\"' not in html:" in app
assert "doctor_turn_call.CALL_SCRIPT" in app
assert "doctor_turn_call.queue_button(r, real_turn, _queue_is_procedure)" in app
assert "class='queue-dismiss-form js-queue-dismiss'" in app
assert "home-queue-count" in app and "hc-b-app" in app

for route in ("/", "/pacientes", "/recetas", "/certificados", "/informes",
              "/macros", "/configuracion", "/material", "/recuperacion/borradores"):
    assert route in app
for key in ("hc-g-sidebar", "hc-g-side-links", "hc-g-side-link", "hc-g-active",
            "clinical-document-editor", "hc-b-app", "hc-global-material",
            "@media print", "Material v1.4.49", "Historia 1.4.49"):
    assert key in css, key
assert css.count("{")==css.count("}")
assert css.count("/*")==css.count("*/")

assert "def _material_remaster_sidebar" in materials
assert "class='hc-global-material'" in materials
assert "{_material_remaster_sidebar()}" in materials
assert "material_index.json" in materials
assert "estos archivos quedan únicamente en esta PC" in materials
assert "DECLARACIÓN DE CONSENTIMIENTO INFORMADO" in consent
assert "NEGATIVA DEL CONSENTIMIENTO INFORMADO" in consent
assert "REVOCATORIA DE CONSENTIMIENTO INFORMADO" in consent
assert "@media print" in consent
assert "<body class=\"cp-remaster-app clinical-document-editor\">" in docs
assert "REPEAT_WAIT_MS=20000" in docs
assert "report_cystoscopy" in reports and "report_ultrasound" in reports


# Regresión real de HTML renderizado, no solo detección de strings.
# En v1.4.49 la clase body arrastraba un espacio y el menú no se montaba,
# aunque el CSS y el test estático anterior existían.
tree = ast.parse(app)
base_nodes = [node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=="base"]
core_base = next(node for node in base_nodes if node.lineno < 1300)
sidebar = next(node for node in tree.body if isinstance(node,ast.FunctionDef)
               and node.name=="_global_remaster_sidebar")
wrapper = next(node for node in base_nodes if 4700 < node.lineno < 4900)
def _load_function(node, ns):
    mini = ast.Module(body=[node],type_ignores=[])
    exec(compile(mini,"isolated_real_base_render.py","exec"),ns)
isolated = {
    "e": lambda x: __import__("html").escape(str(x),quote=True),
    "APP_VERSION": "1.4.50",
    "DOCTOR_NAME": "Dr. Armando Revelo",
    "APP_DIALOG_HTML": "",
}
_load_function(core_base,isolated)
isolated["_HC_GLOBAL_SOURCE_BASE"] = isolated["base"]
_load_function(sidebar,isolated)
_load_function(wrapper,isolated)
patient_page=isolated["base"]("Ficha clínica","<section id='ficha-clinica'></section>","pacientes")
assert '<body class="cp-remaster-app">' in patient_page
assert patient_page.count('class="hc-g-sidebar"')==1, "No se montó el menú lateral en ficha"
assert 'href="/" title="Volver al inicio"' in patient_page, "No existe enlace Inicio"
assert '<span class="hc-g-side-name">Inicio</span>' in patient_page
assert patient_page.index('class="hc-g-sidebar"') < patient_page.index("<main>")
assert "id='ficha-clinica'" in patient_page
consult_page=isolated["base"]("Atención","<div id='consulta'></div>","pacientes")
assert consult_page.count('class="hc-g-sidebar"')==1
doc_page=isolated["base"]("Receta","<div class='docs-wrap'></div>","recetas")
assert doc_page.count('class="hc-g-sidebar"')==1
assert '<body class="cp-remaster-app">' in doc_page, "Document editor cannot detect body marker"
home_page=isolated["base"]("Inicio","<div></div>","inicio")
assert '<body class="cp-remaster-app hc-b-app">' in home_page
assert 'class="hc-g-sidebar"' not in home_page
assert 'display:inline-flex!important' in css and ".brand-home-link" in css
print("HISTORIA_REAL_RENDER_SIDEBAR_VISIBLE_1450_OK")


# Contrato 1.4.51: listado de informes dentro del shell lateral, editor separado.
report_tree=ast.parse(reports)
report_install=next(n for n in report_tree.body if isinstance(n,ast.FunctionDef) and n.name=="install")
list_node=next(n for n in report_install.body if isinstance(n,ast.FunctionDef) and n.name=="list_reports")
returns=[n.value for n in ast.walk(list_node) if isinstance(n,ast.Return)]
assert len(returns)==1
outer=returns[0]
assert isinstance(outer,ast.Call) and isinstance(outer.func,ast.Name) and outer.func.id=="HTMLResponse"
assert len(outer.args)==1
inner=outer.args[0]
assert isinstance(inner,ast.Call) and isinstance(inner.func,ast.Name) and inner.func.id=="base", "Informes ocultó navegación izquierda"
assert [x.value for x in inner.args[::2] if isinstance(x,ast.Constant)][:1]==["Informes médicos"]
assert 'return HTMLResponse(_document_editor_shell(base, "Informes médicos", body + script, "informes"))' in reports, "Editor de informes debe permanecer independiente"
home_right=app.split('<div class="hc-b-shortcut-grid">',1)[1].split('</div>',1)[0]
assert 'data-hc-create="receta"' in home_right
assert 'data-hc-create="certificado"' in home_right
assert 'data-hc-create="informe"' in home_right
assert "Videocistoscopías" not in home_right, "Atajo duplicado en Inicio"
assert 'id="patient-videos-open"' in app, "Se perdió galería de videocistoscopías del paciente"
assert '("videos", "▣", "Videocistoscopías", "/pacientes")' in app, "Se perdió navegador lateral"
assert 'body.cp-remaster-app:not(.hc-b-app):not(.clinical-document-editor):has(.report-list-card) > main' in css
print("HISTORIA_1451_REPORT_LIST_SIDEBAR_HOME_VIDEO_TILE_REMOVED_OK")


# V1.4.52: cola más visible, sin perder navegación ni alterar el llamado.
assert "Inicio B v1.4.52 · jerarquía visual restaurada en lista de espera" in css
assert "body.hc-b-app .hc-b-queue-list .hc-b-wait-card:first-child" in css
assert "body.hc-b-app .hc-b-queue-list .hc-b-wait-card.hc-b-review" in css
assert "body.hc-b-app .hc-b-queue-list .hc-b-wait-card.queue-row-attending" in css
assert "body.hc-b-app .hc-b-queue-list .hc-b-wait-card .hc-b-wait-name strong" in css
assert "font-size:43px!important" in css
assert "overflow-y:auto!important" in css
assert "height:100vh!important;min-height:100vh!important;overflow:hidden!important" in css
assert "overscroll-behavior:contain" in css
assert 'class="hc-b-queue-list"' in app
assert 'class="hc-b-wait-content"' not in app or "hc-b-wait-content" in app
assert 'queue_status_class = "queue-row-waiting" if is_waiting else "queue-row-attending"' in app
assert 'doctor_turn_call.queue_button(r, real_turn, _queue_is_procedure)' in app
assert "href = f\"/cola/{e(r['id'])}/atender\" if can_open else \"#\"" in app
assert "js-queue-dismiss" in app and "hc-b-open" in app
assert "queue_turns.get(str(r[\"id\"]))" in app
print("HISTORIA_1452_PROMINENT_WAITING_CARDS_QUEUE_CONTROLS_PRESERVED_OK")


# v1.4.53: la imagen elegida exige TRES columnas en cada tarjeta,
# no los tres botones en una fila debajo de los datos.
assert "Historia v1.4.53 · sala de espera fiel a referencia visual" in css
assert "grid-template-columns:98px minmax(0,1fr) 166px!important" in css
assert "body.hc-b-app .hc-b-queue-list .hc-b-wait-card .hc-b-wait-content" in css
assert "display:contents!important" in css
assert "grid-column:3!important;grid-row:1!important" in css
assert "display:flex!important;flex-direction:column!important;justify-content:center!important" in css
assert "body.hc-b-app .hc-b-queue-list .hc-b-wait-card .hc-b-wait-tags" in css
assert "background:linear-gradient(180deg,#086ee1,#0556be)!important" in css
assert 'p.national_id AS patient_national_id' in app
assert 'p.phone AS patient_phone' in app
assert 'str(r["patient_phone"] or "").strip()' in app
assert 'str(r["patient_national_id"] or "").strip()' in app
assert 'f"CI: {raw_identification}" if raw_identification else ""' in app
assert "patient_meta = \"  |  \".join(part for part in patient_meta_parts if part)" in app
assert "e(patient_meta)" in app  # HTML escape de datos de la ficha
assert "<div class='hc-b-wait-tags'>" in app
assert "<span class='hc-b-wait-state'>" in app
assert "▤ Revisión de exámenes" in app
assert "f\"<div class='queue-turn-number'><span>Turno</span><b>{real_turn}</b></div>\"" in app
assert "doctor_turn_call.queue_button(r, real_turn, _queue_is_procedure)" in app
assert "class='queue-dismiss-form js-queue-dismiss'" in app
assert "href = f\"/cola/{e(r['id'])}/atender\" if can_open else \"#\"" in app
assert ".hc-b-wait-actions .js-doctor-call" in css
assert ".hc-b-wait-actions .hc-b-open" in css
assert ".hc-b-wait-actions .hc-b-remove" in css
print("HISTORIA_1453_REFERENCIA_FIEL_TARJETAS_TRES_COLUMNAS_OK")


# v1.4.54: pulido de dimensiones sin invertir la distribución.
polish = css.split("/* Historia v1.4.54 · pulido final de las tarjetas de espera", 1)[1]
assert "grid-template-columns:106px minmax(0,1fr) 174px!important" in polish
assert "grid-template-columns:94px minmax(0,1fr) 164px!important" in polish
assert "width:94px!important;min-height:155px!important" in polish
assert "font-size:68px!important" in polish
assert "font-size:22px!important" in polish
assert "font-size:13.5px!important" in polish
assert "font-size:13px!important;min-height:39px!important" in polish
assert "height:47px!important;min-height:47px!important" in polish
assert "gap:5px!important" in polish
assert "display:contents!important" in css
assert "grid-column:3!important;grid-row:1!important" in css
assert "doctor_turn_call.queue_button(r, real_turn, _queue_is_procedure)" in app
assert "class='queue-dismiss-form js-queue-dismiss'" in app
assert "f\"<a class='hc-b-open' href='{href}'>{e(action_label)}</a>\"" in app
assert css.count("{") == css.count("}")
assert css.count("/*") == css.count("*/")
print("HISTORIA_1454_WAITING_CARDS_FINAL_VISUAL_POLISH_OK")


# v1.4.55: turno 1:1, sin deformarse por el alto de la tarjeta.
square=css.split("/* Historia v1.4.55 · turno cuadrado 1:1 y centrado.",1)[1]
assert "--hc-turn-square:106px" in square
assert "--hc-turn-square:94px" in square
assert "--hc-turn-square:71px" in square
for rule in (
  "width:var(--hc-turn-square)!important",
  "height:var(--hc-turn-square)!important",
  "min-height:var(--hc-turn-square)!important",
  "max-height:var(--hc-turn-square)!important",
  "aspect-ratio:1 / 1!important",
  "align-self:center!important",
  "justify-self:center!important",
  "flex:none!important",
  "gap:3px!important",
  "overflow:hidden!important",
):
    assert rule in square, "Falta regla de cuadrado: "+rule
assert "height:100%!important" not in square, "El bloque volvió a estirarse"
assert "grid-column:3!important;grid-row:1!important" in css, "Se movieron los botones"
assert "doctor_turn_call.queue_button(r, real_turn, _queue_is_procedure)" in app
assert "class='queue-dismiss-form js-queue-dismiss'" in app
assert "f\"<a class='hc-b-open' href='{href}'>{e(action_label)}</a>\"" in app
print("HISTORIA_1455_SQUARE_TURN_TILE_OK")

print("HISTORIA_GLOBAL_REMASTER_1449_VISUAL_CONTRACT_OK")

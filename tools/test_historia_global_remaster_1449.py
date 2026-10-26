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

print("HISTORIA_GLOBAL_REMASTER_1449_VISUAL_CONTRACT_OK")

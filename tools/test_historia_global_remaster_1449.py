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

print("HISTORIA_GLOBAL_REMASTER_1449_VISUAL_CONTRACT_OK")

"""Historia 1.4.100 · pruebas sintéticas de ventanas de documentos.

No accede a pacientes, SQLite, Neon, LAN, impresoras ni documentos reales.
"""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "historia-clinica" / "app"
DOCS = APP / "documentos_clinicos.py"
REPORTS = APP / "informes_clinicos.py"

def isolated_function(source_path: Path, function_name: str):
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(source_path))
    function = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == function_name
    )
    isolated = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    env = {}
    exec(compile(isolated, str(source_path), "exec"), env)
    return env[function_name]

def fake_base(title: str, body: str, active: str) -> str:
    assert title and active
    return (
        '<!doctype html><html><head><meta charset="utf-8"></head>'
        '<body class="cp-remaster-app">'
        '<header class="topbar">MAIN APP HEADER</header>'
        '<aside class="hc-g-sidebar">MAIN APP NAV</aside>'
        '<main>' + body + '</main><footer>MAIN APP FOOTER</footer>'
        '</body></html>'
    )

class DocumentWindows14100(unittest.TestCase):
    def test_recipe_certificate_and_rest_layout(self):
        editor = isolated_function(DOCS, "_document_editor_shell")
        html = editor(fake_base, "Receta médica", "<section class='docs-wrap'></section>", "recetas")
        self.assertIn('cp-remaster-app clinical-document-editor', html)
        self.assertIn("grid-template-columns:minmax(0,1fr);gap:14px", html)
        self.assertIn("max-width:970px", html)
        self.assertIn(".docs-card .med-table input", html)
        self.assertIn("width:100%;min-width:0;max-width:100%;box-sizing:border-box", html)
        self.assertIn("body.clinical-document-editor .docs-fields", html)
        self.assertIn("window.historiaDocumentAction=", html)
        self.assertIn("doc-dirty-warning", html)
        self.assertIn("REPEAT_WAIT_MS=20000", html)

    def test_patient_reports_are_focused_without_sidebar(self):
        popup = isolated_function(REPORTS, "_report_patient_popup_shell")
        html = popup(fake_base, "<section class='docs-wrap'>INFORMES SINTÉTICOS</section>")
        self.assertIn('cp-remaster-app clinical-document-editor clinical-report-list-popup', html)
        self.assertIn("body.clinical-report-list-popup > .hc-g-sidebar{display:none!important}", html)
        self.assertIn("body.clinical-report-list-popup > header.topbar", html)
        self.assertIn("min-height:100vh!important;height:auto!important", html)
        self.assertIn("INFORMES SINTÉTICOS", html)
        self.assertNotIn("window.historiaDocumentAction=", html)
        source = REPORTS.read_text(encoding="utf-8")
        self.assertIn("if patient_id:", source)
        self.assertIn("return HTMLResponse(_report_patient_popup_shell(base, body))", source)
        self.assertIn('return HTMLResponse(base("Informes médicos", body, "informes"))', source)
        # La ruta global /informes y la ruta de ficha conservan el mismo listado.
        self.assertIn("@app.get(\"/informes\", response_class=HTMLResponse)", source)
        self.assertIn("report-delete-btn", source)
        self.assertIn("electronic_signatures", source)

    def test_source_is_python_syntax_valid(self):
        for file in (DOCS, REPORTS):
            ast.parse(file.read_text(encoding="utf-8"), filename=str(file))

if __name__ == "__main__":
    unittest.main()

"""Historia 1.4.101: in-app modal document UI, no patient/DB/print activity."""
from __future__ import annotations

import ast
from pathlib import Path
import re
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1] / "historia-clinica" / "app"
APP = ROOT / "app.py"
DOCUMENTS = ROOT / "documentos_clinicos.py"
REPORTS = ROOT / "informes_clinicos.py"


def extract_function(path: Path, name: str):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    item = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    return item


class ClinicalInAppModal14101(unittest.TestCase):
    def test_modal_in_main_application(self):
        app = APP.read_text(encoding="utf-8")
        tree = ast.parse(app)
        assign = next(
            n for n in tree.body
            if isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "APP_DIALOG_HTML" for t in n.targets)
        )
        html = ast.literal_eval(assign.value)
        self.assertIn('id="hcClinicalDocumentDialog"', html)
        self.assertIn("backdrop-filter:blur(5px)", html)
        self.assertIn('id="hcClinicalDocumentFrame"', html)
        self.assertIn("dialog.showModal()", html)
        self.assertIn("historiaEditorHasUnsaved", html)
        self.assertIn("historiaEditorConfirmDiscard", html)
        self.assertIn("url.origin!==location.origin", html)
        self.assertIn("event.origin!==location.origin", html)
        self.assertIn("clinical-document-saved", html)
        self.assertIn("document.addEventListener('click'", html)
        self.assertIn("window.historiaOpenClinicalOverlay?.(documentUrl)", app)
        self.assertIn("window.historiaOpenClinicalOverlay?.(url)", app)
        self.assertIn("window.parent.historiaNativePrint(url,kind)", app)
        self.assertIn("window.open(documentUrl,'_blank')", app)
        scripts = re.findall(r"<script>(.*?)</script>", html, flags=re.S)
        self.assertGreaterEqual(len(scripts), 2)
        if shutil.which("node"):
            for script in scripts:
                subprocess.run(["node", "--check", "-"], input=script, text=True, check=True)
            # These operations are entirely synthetic and cannot call APIs.
            simulation = r"""
const fs = require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(0,'utf8');
const docHandlers={};let dirty=false,confirmed=false,confirmCalls=0,discarded=0;
const dialog={open:false,showModal(){this.open=true},close(){this.open=false},
  addEventListener(name,fn){this[name]=fn}};
const frame={src:'',contentWindow:{
  location:{origin:'http://127.0.0.1:8787'},
  historiaEditorHasUnsaved:()=>dirty,
  historiaEditorConfirmDiscard:()=>{discarded++;dirty=false;}
},removeAttribute(name){if(name==='src')this.src=''}};
const title={textContent:''},btn={focus() {},addEventListener(){}};
const elements={hcClinicalDocumentDialog:dialog,hcClinicalDocumentFrame:frame,
  hcClinicalDocumentTitle:title,hcClinicalDocumentClose:btn};
const document={
 getElementById:id=>elements[id],addEventListener:(name,fn)=>docHandlers[name]=fn,
 activeElement:{focus(){}},body:{classList:{add(){},remove(){}}}};
const location={href:'http://127.0.0.1:8787/paciente/1',origin:'http://127.0.0.1:8787'};
const window={parent:null,confirm:()=>{confirmCalls++;return confirmed;},showAppToast(){}};
window.parent=window;
const sandbox={window,document,location,URL,console};
vm.runInNewContext(source,sandbox);
const open=window.historiaOpenClinicalOverlay,close=window.historiaCloseClinicalOverlay;
assert.equal(open('/recetas/nueva?patient_id=test_1'),true);
assert.equal(dialog.open,true);
assert.equal(title.textContent,'Receta médica');
assert(frame.src.endsWith('/recetas/nueva?patient_id=test_1'));
dirty=true;
assert.equal(close(),false);
assert.equal(dialog.open,true);
confirmed=true;
assert.equal(close(),true);
assert.equal(dialog.open,false);
assert.equal(discarded,1);
assert.equal(open('https://malicious.example/recetas/nueva?patient_id=test'),false);
assert.equal(open('/api/firma/documento/test'),false);
assert.equal(open('/informes?patient_id=test_1'),true);
assert.equal(title.textContent,'Informes médicos');
assert.equal(close(),true);
let prevented=false;
const a={href:'http://127.0.0.1:8787/certificados/nuevo?patient_id=test_1'};
docHandlers.click({button:0,target:{closest:()=>a},defaultPrevented:false,
  ctrlKey:false,metaKey:false,shiftKey:false,altKey:false,
  preventDefault(){prevented=true}});
assert.equal(prevented,true);
assert.equal(title.textContent,'Certificado médico');
assert.equal(close(),true);
console.log('MODAL_SAME_ORIGIN_DIRTY_GUARD_FOCUS_DIALOG_OK');
"""
            modal_script = scripts[-1]
            subprocess.run(["node", "-e", simulation], input=modal_script, text=True, check=True)

    def test_compact_two_column_editor_and_print_guard(self):
        text = DOCUMENTS.read_text(encoding="utf-8")
        tree = ast.parse(text)
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                        and n.name == "_document_editor_shell")
        mod = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
        obj = {}
        exec(compile(mod, str(DOCUMENTS), "exec"), obj)
        base = lambda title, body, active: (
            '<html><head></head><body class="cp-remaster-app">'
            '<main>' + body + '</main><footer></footer></body></html>')
        html = obj["_document_editor_shell"](base, "Receta médica", "<div class='docs-wrap'></div>", "recetas")
        self.assertIn("grid-template-columns:minmax(280px,.88fr) minmax(0,1.45fr)", html)
        self.assertIn("@media(max-width:970px)", html)
        self.assertNotIn("@media(max-width:1260px)", html)
        self.assertNotIn("@media(max-width:1080px)", html)
        self.assertIn("historiaEditorHasUnsaved", html)
        self.assertIn("historiaEditorConfirmDiscard", html)
        self.assertIn("historiaDocumentClose", html)
        self.assertIn("beforeunload", html)
        self.assertIn("REPEAT_WAIT_MS=20000", html)
        self.assertIn("window.historiaDocumentAction", html)
        self.assertIn("window.parent!==window?window.parent:null", text)
        self.assertIn("window.parent!==window?window.parent:null", REPORTS.read_text(encoding="utf-8"))
        ast.parse(REPORTS.read_text(encoding="utf-8"))

if __name__ == "__main__":
    unittest.main()

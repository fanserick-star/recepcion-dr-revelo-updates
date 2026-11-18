"""Regression: 5.0 native consultation total must feed the old payment guard.

Only synthetic data; no Windows printer, clinical patient, Neon or database calls.
"""
from __future__ import annotations
import ast
import json
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAYMENT = ROOT / "recepcion/app/reception_payment_terminal.py"
ATTENTION = ROOT / "recepcion/app/static/app.js"
NATIVE = ROOT / "recepcion/app/static/reception_new_attention_507.js"

module = ast.parse(PAYMENT.read_text(encoding="utf-8"), filename=str(PAYMENT))
embedded = []
for node in ast.walk(module):
    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "V4504_JS" for t in node.targets):
        embedded.append(ast.literal_eval(node.value))
assert len(embedded) == 1, "Exactly one legacy payment overlay JS source must be defined"
js = embedded[0]
start = js.index(" function total(){")
end = js.index("\n\n function discounted()", start)
total_source = js[start:end]
assert "selectedServiceOrder()" in total_source, "Native services must be authoritative"
assert "attentionServiceValues[name]" in total_source, "Native procedure prices must be used"
assert "cards().reduce" in total_source, "Legacy fallback must remain supported"
assert "'#atencion.has-patient #r507VisitSlot:not(.hidden)'" in total_source
assert "Selecciona al menos una atención con valor." in js, "Keep payment validation"
assert "buildPayload();" in js and "stableSave.apply" in js, "Keep payment wrapper"
app = ATTENTION.read_text(encoding="utf-8")
native = NATIVE.read_text(encoding="utf-8")
assert "selectedServices=new Set(draftServices.map(serviceKey).filter(Boolean));" in app
assert "function selectedServiceOrder(){" in app
assert "function toggleService(name){" in app
assert "if(!names.length){if(err)err.textContent='Selecciona al menos una consulta o procedimiento.'" in native

# Execute the *real extracted function* with a minimal synthetic DOM and
# canonical state. The source under test is not reproduced in the fixture.
probe = r"""
"use strict";
const assert = require('node:assert/strict');
const body = process.argv[1];
const total = new Function('document','selectedServiceOrder','attentionServiceValues','cards','cardVal',
  body + ';return total();');
function run(native,names,values,legacy=[]){
  return total(
    {querySelector:()=>native?{}:null},
    ()=>names,
    values,
    ()=>legacy,
    value=>value
  );
}
assert.equal(run(true,['CONSULTA'],{}),40);
assert.equal(run(true,['CONSULTA','CISTOSCOPIA'],{CISTOSCOPIA:'35.50'}),75.50);
assert.equal(run(true,['CISTOSCOPIA'],{CISTOSCOPIA:85}),85);
assert.equal(run(true,['CISTOSCOPIA'],{CISTOSCOPIA:''}),0);
assert.equal(run(true,['CONSULTA','CISTOSCOPIA'],{}),0);
assert.equal(run(true,[],{}),0);
assert.equal(run(false,[],{},[40,15]),55);
console.log('RECEPTION_5017_NATIVE_ATTENTION_PAYMENT_TOTAL_OK');
"""
result = subprocess.run(["node", "-e", probe, total_source], capture_output=True, text=True, check=True, timeout=20)
print(result.stdout.strip())

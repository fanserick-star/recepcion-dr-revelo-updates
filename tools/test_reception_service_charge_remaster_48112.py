"""Recepción 4.8.112 — precios de servicio editados, Bendo estable y revisión visible.

Prueba con datos sintéticos, sin Neon, pacientes, facturación real ni terminal.
"""
from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
APP=ROOT/"recepcion/app"

def embedded_js(filename, marker, next_marker):
    source=(APP/filename).read_text(encoding="utf-8")
    start=source.index(marker)+len(marker)
    stop=source.index(next_marker,start)
    return ast.literal_eval(source[start:stop].strip())

payment=embedded_js(
    "reception_payment_terminal.py",
    "    V4504_JS = ",
    "\n    core.V460_OVERLAY_CSS",
)
bendo=embedded_js(
    "reception_payment_terminal_panel.py",
    "V4525_JS = ",
    "\ncore.V460_OVERLAY_CSS",
)

for script in (payment,bendo):
    check=subprocess.run(
        ["node","--check"],input=script,text=True,
        capture_output=True,check=False
    )
    assert check.returncode==0,check.stderr

# Ejecución real en Node de las funciones de cálculo extraídas del script.
start=payment.index("function editableCardValue(c){")
stop=payment.index("function discounted(){",start)
pricing=payment[start:stop]
node_test=r"""
const assert=require('node:assert/strict');
const vm=require('node:vm');
const pricing=PROCESS_PRICING;
function service(name,label){
 return {dataset:{service:name},querySelector:(sel)=>sel==='.service-price'?{textContent:label}:null};
}
const procedure=service('CISTOSCOPIA','$120.00');
const last=service('ÚLTIMO SERVICIO','Valor editable');
const consultation=service('CONSULTA','$40.00');
const fields=[
 {dataset:{service:'CISTOSCOPIA'},value:'89.50'},
 {dataset:{service:'ÚLTIMO SERVICIO'},value:'12.75'}
];
const modal={querySelectorAll:()=>fields};
const context={
 box:()=>modal,
 norm:v=>String(v||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').trim().toLowerCase(),
 q:(selector,card)=>card?.querySelector?.(selector),
 cards:()=>[procedure,last,consultation]
};
const calc=vm.runInNewContext(pricing+';({cardVal,total})',context);
assert.equal(calc.cardVal(procedure),89.5);
assert.equal(calc.cardVal(last),12.75);
assert.equal(calc.cardVal(consultation),40);
assert.equal(calc.total(),142.25);
fields[1].value='17.99';
assert.equal(calc.total(),147.49);
fields[0].value='0';
assert.equal(calc.cardVal(procedure),0);
assert.equal(calc.total(),57.99);
console.log('RECEPTION_SERVICE_EDITED_PRICE_48112_OK');
""".replace("PROCESS_PRICING",json.dumps(pricing))
result=subprocess.run(["node","-e",node_test],text=True,capture_output=True,check=False)
assert result.returncode==0,result.stderr
assert "RECEPTION_SERVICE_EDITED_PRICE_48112_OK" in result.stdout

# Cambiar el precio nunca vuelve a dibujar todas las opciones de pago.
assert "document.addEventListener('input',event=>" in payment
assert ".procedure-value-input" in payment
assert "renderSummary();" in payment
assert "setTimeout(render,30);" not in payment
assert "setTimeout(render,170);" not in payment
assert "const bendoPanel=q('#v4525Bendo',host);" in payment
assert "options.insertAdjacentElement('afterend',bendoPanel)" in payment
assert "if(state.active){invalidate();render()}" in bendo

# Revisión gratuita se sitúa ANTES de la lista de servicios cobrables.
app=(APP/"static/app.js").read_text(encoding="utf-8")
begin=app.index('openModal(`<div class="attention-form-modal">')
end=app.index('`);',begin)
form=app[begin:end]
assert form.index('exam-review-turn-action') < form.index('service-title enhanced')
assert form.count('exam-review-turn-action')==1
assert form.count('onclick="saveExamReviewTurn(')==1
assert 'Sin cobro ni factura' in form

style=(APP/"reception_payment_terminal_panel.py").read_text(encoding="utf-8")
assert "v4.8.112 · Servicios y cobros" in style
print("RECEPTION_SERVICE_CHARGE_REMASTER_48112_OK")

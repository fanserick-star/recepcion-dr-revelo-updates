"""Regression for AZUR 80mm printer selection. No printer, XML, API or database calls."""
import ast
from pathlib import Path
from types import SimpleNamespace

base=Path(__file__).resolve().parents[1]/"recepcion"/"app"
s=(base/"reception_azur_pos80.py").read_text(encoding="utf-8")
t=ast.parse(s)
def source_fn(name):
    matches=[n for n in t.body if isinstance(n,ast.FunctionDef) and n.name==name]
    assert len(matches)==1,name
    return matches[0]

class Refused(Exception):
    def __init__(self,code,message):
        self.code=code
        super().__init__(message)

prefs={"printer":""}
info={"supported":True,"default_printer":"THERMAL-80","printers":["THERMAL-80","A4"]}
fake=SimpleNamespace(HTTPException=Refused,_app_preferences=lambda:prefs,
                     _windows_printer_info=lambda:info)
ctx={"core":fake}
exec(compile(ast.Module(body=[source_fn("_resolve_pos80_printer")],type_ignores=[]),"<printer resolver>","exec"),ctx)
resolve=ctx["_resolve_pos80_printer"]

assert resolve()==("THERMAL-80","Predeterminada de Windows")
prefs["printer"]="THERMAL-80"
assert resolve()==("THERMAL-80","Configurada en Recepción")
prefs["printer"]="DEVICE DISCONNECTED"
try:resolve()
except Refused as e:assert e.code==409
else:raise AssertionError("Never silently switch from disconnected configured printer to Windows default")

prefs["printer"]=""
info["default_printer"]=""
try:resolve()
except Refused as e:assert e.code==409
else:raise AssertionError("Never guess a printer when Windows has no default")

info["default_printer"]="THERMAL-80"
info["printers"]=[]
try:resolve()
except Refused as e:assert e.code==409
else:raise AssertionError("Printer list cannot be empty")

info["printers"]=["THERMAL-80"]
info["supported"]=False
try:resolve()
except Refused as e:assert e.code==409
else:raise AssertionError("Do not print if Windows cannot enumerate printers")

print("AZUR_POS80_WINDOWS_DEFAULT_PRINTER_FALLBACK_SAFE_4848_OK")

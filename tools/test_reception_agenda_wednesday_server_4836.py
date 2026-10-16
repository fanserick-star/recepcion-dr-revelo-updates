"""Exercise actual appointment validation via AST without launching app or writing to DB."""
import ast
from datetime import date
from pathlib import Path
import re
src=(Path(__file__).resolve().parents[1]/"recepcion/app/core_runtime.py").read_text(encoding="utf-8")
tree=ast.parse(src)
node=next(n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name=="normalize_appointment_payload")
code=ast.get_source_segment(src,node)
class HTTPException(Exception):
    def __init__(self,status_code,detail):
        super().__init__(detail)
        self.status_code=status_code
def minutes(t): return int(t[:2])*60+int(t[3:5])
scope={"re":re,"date":date,"HTTPException":HTTPException,"hhmm_to_minutes":minutes}
exec(code,scope)
check=scope["normalize_appointment_payload"]
for date_,hour in [(date(2026,10,14),"08:00"),(date(2026,10,14),"09:40")]:
    try: check({"fecha":date_,"hora":hour,"nota":""})
    except HTTPException as e:
        assert e.status_code==400 and "miércoles" in str(e).lower(),(date_,hour,str(e))
    else: raise AssertionError(f"Accepted closed Wednesday slot {date_} {hour}")
for date_,hour in [(date(2026,10,14),"10:00"),(date(2026,10,15),"08:00"),
                   (date(2026,10,14),"14:00"),(date(2026,10,15),"17:00")]:
    result=check({"fecha":date_,"hora":hour,"nota":""})
    assert result["hora"]==hour
try: check({"fecha":date(2026,10,15),"hora":"12:20"})
except HTTPException as e: assert e.status_code==400
else: raise AssertionError("Lunch overlap accepted")
print("AGENDA_4836_WEDNESDAY_SERVER_VALIDATION_NO_DB_NO_META_OK")

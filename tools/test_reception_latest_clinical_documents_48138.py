"""Offline regression: selected clinical Neon supplies document metadata on demand.

No production database, private keys, real LAN, patient records, WhatsApp, or PDF bytes.
The authenticated patient's mapped identity must always be checked before the cache.
"""
from __future__ import annotations

import ast
import json
import re
import threading
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / "recepcion/app/clinical_delivery.py").read_text(encoding="utf-8")
bridge = (ROOT / "recepcion/app/historia_bridge.py").read_text(encoding="utf-8")
identity_source = (ROOT / "recepcion/app/reception_history_identity_consolidated.py").read_text(encoding="utf-8")
ui = (ROOT / "recepcion/app/static/clinical_delivery.js").read_text(encoding="utf-8")
tree = ast.parse(source)
chosen = {"_linked_patient", "_documents", "_cloud_documents"}
nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in chosen]
assert len(nodes) == 3

class HTTPException(Exception):
    def __init__(self, status_code, detail):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)

class LocalSession:
    def __enter__(self): return self
    def __exit__(self, *_): return False

class FakeConnection:
    def __init__(self, target):
        self.target = target
        self.calls = []
        self.closed = False
        self.fail_cloud = False
        self.linked = True
        self.patients = []
    def cursor(self): return self
    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        if "FROM public.patient_links" in sql:
            self.current = [("clinical-A",)] if self.linked else []
        elif "FROM public.prescriptions" in sql:
            if self.fail_cloud: raise RuntimeError("synthetic-private-postgres-error")
            self.current = [
                ("rx-current", "2026-11-13T14:10:00", "receta"),
                ("report-current", "2026-11-13T13:10:00", "informe"),
                ("rest-current", "2026-11-13T12:10:00", "reposo"),
                ("medical-current", "2026-11-13T11:10:00", "certificado"),
                ("malformed doc", "2026-11-13T10:00:00", "receta"),
            ]
        else:
            self.current = []
    def fetchone(self): return self.current[0] if self.current else None
    def fetchall(self): return self.current
    def close(self): self.closed = True

chosen_target = SimpleNamespace(value="emergency")
instances = []
def connect():
    conn = FakeConnection(chosen_target.value)
    instances.append(conn)
    return conn
identity = SimpleNamespace(_connect_public=connect,
    historia_bridge=SimpleNamespace(_history_target=lambda: chosen_target.value))
core = SimpleNamespace(HTTPException=HTTPException,
    LocalSessionLocal=lambda: LocalSession())
ns = {
    "re": re, "time": time, "threading":threading, "core":core,
    "identity":identity, "_patient":lambda db,pid:pid,
    "_cloud_reception_id":lambda pid:str(pid),
    "_CLOUD_DOCUMENTS_CACHE":{},
    "_CLOUD_DOCUMENTS_CACHE_LOCK":threading.Lock(),
    "_CLOUD_DOCUMENTS_TTL_SECONDS":8,
    "_CLOUD_DOCUMENTS_CACHE_LIMIT":128,
    "LABELS":{"receta":"Receta médica","informe":"Informe médico",
              "reposo":"Certificado de reposo","certificado":"Certificado médico"}
}
exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])), "selected_neon_docs", "exec"),ns)
documents=ns["_documents"]
docs,rid,cid = documents(42)
assert rid=="42" and cid=="clinical-A"
assert [d["id"] for d in docs]==["rx-current","report-current","rest-current","medical-current"]
assert len(instances)==1 and instances[0].closed
statements=[x[0] for x in instances[0].calls]
assert statements[0]=="SET TRANSACTION READ ONLY"
assert "FROM public.patient_links" in statements[1]
assert "FROM public.prescriptions" in statements[2]
assert "FROM public.certificates" in statements[2]
assert "ORDER BY issued_at DESC LIMIT 100" in statements[2]
assert "deleted_at IS NULL" in statements[2]
assert instances[0].calls[1][1]==("42",)
assert instances[0].calls[2][1]==("clinical-A","clinical-A")
assert all("bytes" not in str(x).lower() for x in docs)
# Same link must still be authorized on every request, while the list reuses cache.
docs2,_,_=documents(42)
assert docs2==docs
assert len([x for x in instances[1].calls if "FROM public.prescriptions" in x[0]])==0
assert len([x for x in instances[1].calls if "FROM public.patient_links" in x[0]])==1
documents(42,refresh=True)
assert len([x for x in instances[2].calls if "FROM public.prescriptions" in x[0]])==1
# Selection of the other Neon must never consume the old project's cache.
chosen_target.value="official"
documents(42)
assert len([x for x in instances[3].calls if "FROM public.prescriptions" in x[0]])==1
# A missing verified mapping must refuse, even if the patient's documents are cached.
def denied(): 
    conn=FakeConnection(chosen_target.value);conn.linked=False;instances.append(conn);return conn
identity._connect_public=denied
try:documents(42)
except HTTPException as ex:assert ex.status_code==409
else:raise AssertionError("Cached data bypassed current verified link")
# Fail closed on Neon failure: never silently read a previous Neon or LAN.
identity._connect_public=connect
ns["_CLOUD_DOCUMENTS_CACHE"].clear()
def unavailable():
    conn=FakeConnection(chosen_target.value);conn.fail_cloud=True;instances.append(conn);return conn
identity._connect_public=unavailable
try:documents(42)
except HTTPException as ex:
    assert ex.status_code==503
    assert "Neon de Historia seleccionado" in ex.detail
    assert "synthetic-private" not in ex.detail
else:raise AssertionError("Cloud error must not silently fall back")
assert "_cloud_documents(conn, clinical_id, refresh=refresh)" in source
assert "_lan_documents(rid, clinical_id)" not in source.split("def _documents(",1)[1].split("def _lan_pdf_failure(",1)[0]
assert "docs, rid, clinical_id = _documents(pid, refresh=True)" in source
assert "def delivery_documents(pid:int,refresh:bool=False" in source
assert "refresh?'?refresh=true':''" in ui
assert "load(state.pid,state.phone,state.name,true)" in ui
assert "_database_url_for_target(_history_target())" in bridge
assert "selected = historia_bridge._history_target()" in identity_source
assert '"HISTORIA_EMERGENCY_DATABASE_URL"' in bridge
print("RECEPTION_LATEST_CLINICAL_DOCUMENTS_SELECTED_NEON_48146_OK")

"""Offline security regression for Historia LAN signed-original lookup (1.4.24).

No patient data, network, cloud or real private keys are used.
"""
import ast
import hashlib
import hmac
import os
import re
import sqlite3
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

root=Path(__file__).resolve().parents[1]
source=(root/"historia-clinica/app/lan_bridge.py").read_text(encoding="utf-8")
tree=ast.parse(source)
cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=="LanService")
methods=[n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name in
         {"signed_document_for_reception","_valid_delivery_proof"}]
assert len(methods)==2
module=ast.fix_missing_locations(ast.Module(body=methods,type_ignores=[]))
ns={"sqlite3":sqlite3,"hashlib":hashlib,"hmac":hmac,"os":os,"re":re,"time":time,"Path":Path,
    "_clean":lambda x,n=400:str(x or "").strip()[:n]}
exec(compile(module,"historia_lan_verified_offline","exec"),ns)
lookup=ns["signed_document_for_reception"]
proof=ns["_valid_delivery_proof"]
secret="synthetic-key-do-not-use-in-production-123456789"
sys.modules["cloud_sync"]=SimpleNamespace(_load_env=lambda _:{"CLINICAL_DELIVERY_LAN_SECRET":secret})
try:
    with tempfile.TemporaryDirectory(prefix="historia_lan_1424_") as folder:
        home=Path(folder)
        archive=home/"data"/"documentos_firmados"
        archive.mkdir(parents=True)
        original=b"%PDF-1.4\nsynthetic signed document for testing only\n%%EOF"
        pdf=archive/"synthetic.pdf"
        pdf.write_bytes(original)
        db=home/"clinic.sqlite"
        with sqlite3.connect(db) as conn:
            conn.executescript("""
            CREATE TABLE patient_links(reception_patient_id TEXT,clinical_patient_id TEXT,verified INTEGER);
            CREATE TABLE certificates(id TEXT PRIMARY KEY,patient_id TEXT,certificate_type TEXT,deleted_at TEXT);
            CREATE TABLE prescriptions(id TEXT PRIMARY KEY,patient_id TEXT,deleted_at TEXT);
            CREATE TABLE electronic_signatures(id INTEGER PRIMARY KEY,document_type TEXT,
                document_id TEXT,relative_path TEXT,pdf_sha256 TEXT);
            """)
            conn.execute("INSERT INTO certificates VALUES('document-1','clinical-1','medical',NULL)")
            conn.execute("INSERT INTO certificates VALUES('document-2','clinical-2','medical',NULL)")
            for n in (1,2):
                conn.execute("INSERT INTO electronic_signatures VALUES(?,?,?,?,?)",
                    (n,"certificado",f"document-{n}","data/documentos_firmados/synthetic.pdf",
                     hashlib.sha256(original).hexdigest()))
        svc=SimpleNamespace(root=home,db_path=db)
        stamp=str(int(time.time()))
        material=f"reception-1|clinical-1|certificado|document-1|{stamp}"
        digest=hmac.new(secret.encode(),material.encode(),hashlib.sha256).hexdigest()
        assert proof(svc,"reception-1","certificado","document-1",stamp,digest,"clinical-1")
        assert not proof(svc,"reception-1","certificado","document-1",stamp,digest,"clinical-2")
        assert not proof(svc,"reception-1","certificado","document-1",stamp,digest,"")
        assert not proof(svc,"reception-1","certificado","document-1",str(int(stamp)-90),digest,"clinical-1")
        # Missing local link: verified cloud HMAC ID + exact local ownership permits read-only.
        assert lookup(svc,"reception-1","certificado","document-1","clinical-1")==original
        def rejects(exc, *args):
            try: lookup(svc,*args)
            except exc: return
            raise AssertionError(f"Expected {exc.__name__}")
        rejects(PermissionError,"reception-1","certificado","document-2","clinical-1")
        rejects(PermissionError,"reception-1","certificado","document-1","clinical-2")
        rejects(PermissionError,"reception-1","certificado","document-1","")
        rejects(FileNotFoundError,"reception-1","certificado","missing-document","clinical-1")
        with sqlite3.connect(db) as conn:
            conn.execute("INSERT INTO patient_links VALUES('reception-1','clinical-2',1)")
        rejects(PermissionError,"reception-1","certificado","document-1","clinical-1")
        with sqlite3.connect(db) as conn:
            conn.execute("UPDATE patient_links SET clinical_patient_id='clinical-1' WHERE reception_patient_id='reception-1'")
        assert lookup(svc,"reception-1","certificado","document-1","clinical-1")==original
        with sqlite3.connect(db) as conn:
            assert conn.execute("SELECT COUNT(*) FROM certificates").fetchone()[0]==2
            assert conn.execute("SELECT COUNT(*) FROM patient_links").fetchone()[0]==1
        assert pdf.read_bytes()==original
finally:
    sys.modules.pop("cloud_sync",None)
assert "val(\"clinical_patient_id\")" in source
assert "service._valid_token(self.remote_ip, token)" in source
assert "service._valid_delivery_proof(" in source
assert "hmac.compare_digest" in source
print("HISTORIA_1424_SIGNED_LAN_VERIFIED_LINK_READ_ONLY_SECURITY_OK")

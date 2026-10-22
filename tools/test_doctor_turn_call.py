"""Contrato de llamados doctor->LAN->Recepción TV. Sin pacientes reales ni Neón."""
import ast
import json
import sqlite3
import tempfile
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from fastapi import FastAPI, HTTPException

import doctor_turn_call as call


class FakeRequest:
    base_url = "http://127.0.0.1:8000/"
    def __init__(self, headers=None, host="127.0.0.1"):
        self.client = SimpleNamespace(host=host)
        self.headers = headers or {"x-historia-doctor-call":"1","origin":"http://127.0.0.1:8000"}


def response(response):
    return json.loads(response.body.decode("utf-8"))


def test_local_event():
    with tempfile.TemporaryDirectory(prefix="doctor_turn_call_") as temp:
        root = Path(temp)
        dbpath = root / "db.sqlite"
        today = datetime.now().isoformat(timespec="seconds")
        with sqlite3.connect(dbpath) as db:
            db.execute("""CREATE TABLE waiting_queue(
                id TEXT PRIMARY KEY,status TEXT,queued_at TEXT,
                attention_type TEXT,clinical_patient_id TEXT,reception_turn INTEGER
            )""")
            db.executemany(
                "INSERT INTO waiting_queue VALUES(?,?,?,?,?,?)",
                [
                    ("q1","waiting",today,"Consulta","patient-1",8),
                    ("q2","waiting",today,"REVISIÓN DE EXÁMENES","patient-2",9),
                    ("q3","waiting",today,"Procedimiento","patient-3",10),
                    ("q4","completed",today,"Consulta","patient-4",11),
                    ("q5","waiting","2026-01-01T09:00:00","Consulta","patient-5",12),
                ],
            )
        app=FastAPI()
        def connection():
            db=sqlite3.connect(dbpath);db.row_factory=sqlite3.Row;return db
        def turn(conn,qid):
            row=conn.execute("SELECT reception_turn FROM waiting_queue WHERE id=?",(qid,)).fetchone()
            return row[0] if row else None
        def procedure(row):return str(row["attention_type"])=="Procedimiento"
        call.install(app,connection,root,turn,procedure)
        endpoint=next(r.endpoint for r in app.routes if getattr(r,"path","")=="/api/doctor-turn-call/{queue_id}")
        assert 'href="/"' in (Path(__file__).resolve().parents[1]/"historia-clinica/app/app.py").read_text(encoding="utf-8"), "El Inicio no puede desaparecer"
        ok=response(endpoint("q1",FakeRequest()))
        assert ok["ok"] and ok["turn"]==8
        event=call.latest(root)
        assert event["turn"]==8 and event["queue_id"]=="q1"
        assert set(event)=={"event_id","queue_id","turn","exam_review","at_epoch"}
        raw=call._event_path(root).read_text(encoding="utf-8")
        assert "patient-" not in raw and "nombre" not in raw
        assert endpoint("q1",FakeRequest()).status_code==429
        assert endpoint("q3",FakeRequest()).status_code==409
        assert endpoint("q4",FakeRequest()).status_code==409
        assert endpoint("q5",FakeRequest()).status_code==409
        with sqlite3.connect(dbpath) as db:
            assert db.execute("SELECT status FROM waiting_queue WHERE id='q1'").fetchone()[0]=="waiting"
            assert db.execute("SELECT COUNT(*) FROM waiting_queue").fetchone()[0]==5
        review=response(endpoint("q2",FakeRequest()))
        assert review["turn"]==9 and review["exam_review"]
        assert call.latest(root)["exam_review"]
        try:
            endpoint("q2",FakeRequest(host="192.168.1.9"))
            raise AssertionError("Remote request should be rejected")
        except HTTPException as e:
            assert e.status_code==403
        try:
            endpoint("q2",FakeRequest(headers={"origin":"https://evil.invalid","x-historia-doctor-call":"1"}))
            raise AssertionError("Foreign origin should be rejected")
        except HTTPException as e:
            assert e.status_code==403
        stale=call.latest(root)
        stale["at_epoch"]-=call.MAX_EVENT_AGE_SECONDS+1
        call._event_path(root).write_text(json.dumps(stale),encoding="utf-8")
        assert call.latest(root) is None
    print("DOCTOR_TURN_HISTORY_LOCAL_OK")


def test_tv_dedup_and_display():
    # Ejecuta el método REAL de Recepción sin importar su runtime pesado.
    path=Path(__file__).resolve().parents[1]/"recepcion/app/reception_tv_turns.py"
    program=ast.parse(path.read_text(encoding="utf-8"))
    cls=next(n for n in program.body if isinstance(n,ast.ClassDef) and n.name=="ClinicTVTurnService")
    method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=="_consume_doctor_call")
    node=ast.ClassDef(name="Harness", bases=[],keywords=[],body=[method],decorator_list=[])
    ns={"_epoch":time.time,"_now_iso":lambda:datetime.now().isoformat(timespec="seconds")}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),str(path),"exec"),ns)
    service=ns["Harness"]()
    service.lock=threading.RLock()
    service.live={"mode":"attending","event_id":18,"current_queue_id":"qOld","turn":7}
    now=time.time()
    def payload(event_id,queue_id="q1",turn=8,age=0,exam_review=False):
        return {"doctor_call":{"event_id":event_id,"queue_id":queue_id,"turn":turn,
                 "exam_review":exam_review,"at_epoch":now-age},
                "current":{"queue_id":"qOld","turn":7},
                "waiting":[{"queue_id":"q1","turn":8},{"queue_id":"q2","turn":9}]}
    e1=str(uuid.uuid4())
    service._consume_doctor_call(payload(e1))
    assert service.live["mode"]=="calling" and service.live["turn"]==8
    assert service.live["event_id"]==19
    service._consume_doctor_call(payload(e1))
    assert service.live["event_id"]==19, "Polling must not ring twice"
    service._consume_doctor_call(payload(str(uuid.uuid4()),"qNo",33))
    assert service.live["event_id"]==19, "Unknown queue must not be announced"
    service._consume_doctor_call(payload(str(uuid.uuid4()),"q2",9,age=26))
    assert service.live["event_id"]==19, "Stale call must not ring"
    service._consume_doctor_call(payload(str(uuid.uuid4()),"q2",9,exam_review=True))
    assert service.live["event_id"]==20 and service.live["exam_review"]
    assert service.live["current_queue_id"]=="qOld", "Calling must not change clinical attention"
    print("DOCTOR_TURN_TV_DEDUP_OK")


def main():
    test_local_event()
    test_tv_dedup_and_display()

if __name__=="__main__":
    main()

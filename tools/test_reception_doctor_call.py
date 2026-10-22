"""Contrato de evento manual de Historia en la TV, sin dependencias ni pacientes."""
import ast
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path


def main():
    src=(Path(__file__).resolve().parents[1]/"recepcion/app/reception_tv_turns.py").read_text("utf-8")
    p=ast.parse(src)
    cls=next(x for x in p.body if isinstance(x,ast.ClassDef) and x.name=="ClinicTVTurnService")
    method=next(x for x in cls.body if isinstance(x,ast.FunctionDef) and x.name=="_consume_doctor_call")
    namespace={"_epoch":time.time,"_now_iso":lambda:datetime.now().isoformat(timespec="seconds")}
    new=ast.ClassDef(name="Harness",bases=[],keywords=[],body=[method],decorator_list=[])
    exec(compile(ast.fix_missing_locations(ast.Module(body=[new],type_ignores=[])),"<doctor-tv>","exec"),namespace)
    svc=namespace["Harness"]()
    svc.lock=threading.RLock()
    svc.live={"mode":"attending","event_id":10,"current_queue_id":"ongoing","turn":7}
    now=time.time()
    def payload(id, qid="wait",num=8,age=0,review=False):
        return {"doctor_call":{"event_id":id,"queue_id":qid,"turn":num,"at_epoch":now-age,"exam_review":review},
                "current":{"queue_id":"ongoing","turn":7},
                "waiting":[{"queue_id":"wait","turn":8},{"queue_id":"review","turn":9}]}
    same=str(uuid.uuid4())
    svc._consume_doctor_call(payload(same))
    assert svc.live["mode"]=="calling" and svc.live["turn"]==8
    assert svc.live["event_id"]==11
    for _ in range(4):
        svc._consume_doctor_call(payload(same))
    assert svc.live["event_id"]==11, "La misma señal no puede hacer sonar la TV repetidamente"
    svc._consume_doctor_call(payload(str(uuid.uuid4()),"nonexistent",100))
    assert svc.live["event_id"]==11
    svc._consume_doctor_call(payload(str(uuid.uuid4()),"review",9,age=26))
    assert svc.live["event_id"]==11
    svc._consume_doctor_call(payload(str(uuid.uuid4()),"review",9,review=True))
    assert svc.live["event_id"]==12 and svc.live["exam_review"] is True
    assert svc.live["current_queue_id"]=="ongoing", "El llamado jamás altera la atención actual"
    assert "def _apply_history_without_doctor_call" in src
    assert 'self._apply_history_without_doctor_call(payload)' in src
    print("RECEPTION_TV_DOCTOR_CALL_DEDUP_OK")


if __name__=="__main__":
    main()

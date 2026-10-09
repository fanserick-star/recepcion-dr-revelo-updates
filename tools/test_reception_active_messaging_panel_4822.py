"""Actual appointment messaging window: offline, no Meta calls, no Neon writes."""
import ast
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
guard=(ROOT/"recepcion/app/reception_messaging_runtime_guard.py").read_text(encoding="utf-8")
runtime=(ROOT/"recepcion/app/reception_messaging_runtime.py").read_text(encoding="utf-8")
tree=ast.parse(guard)

def make_func(name,ns):
    nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name]
    assert len(nodes)==1,name
    exec(compile(ast.Module(body=nodes,type_ignores=[]),"<isolated>", "exec"),ns)
    return ns[name]

ec=timezone(timedelta(hours=-5))
now=datetime.now(ec)
def local(template,due):
    return {"direction":"outbound","template":template,"status":"PENDING",
            "due_at":due.isoformat(),"timestamp":(due+timedelta(hours=5)).replace(tzinfo=None).isoformat(),
            "label":"Cita agendada","status_label":"Programado","tone":"planned",
            "local_fallback":True}

def test_overdue_unconfirmed():
    classify=make_func("_local_intention_state",{"datetime":datetime,"timedelta":timedelta,"timezone":timezone})
    out=classify(local("cita_agendada",now-timedelta(hours=2)),cloud_available=True)
    assert out["status"]=="NO_CLOUD_EVENT" and out["status_label"]=="Sin constancia de envío"
    assert not out["due_at"] and "Meta Cloud" in out["error"]
    # The right-side timestamp is no longer the UTC creation time (+5 hours).
    assert out["timestamp"].startswith((now-timedelta(hours=2)).date().isoformat())
    assert out["timestamp"]!=local("cita_agendada",now-timedelta(hours=2))["timestamp"]
    upcoming=classify(local("recordatorio_cita",now+timedelta(days=6)),cloud_available=True)
    assert upcoming["status"]=="SCHEDULED_LOCAL" and upcoming["status_label"]=="Programado"
    missing=classify(local("cita_agendada",now-timedelta(hours=2)),cloud_available=False)
    assert missing["status"]=="UNVERIFIED" and missing["status_label"]=="No verificable"

def test_combined_cloud_and_local():
    ns={"datetime":datetime,"timedelta":timedelta,"timezone":timezone,"date":date}
    ns["_cloud_history"]=lambda **kw:([{"direction":"outbound","template":"recordatorio_hoy",
                                             "status":"DELIVERED","status_label":"Entregado",
                                             "timestamp":now.isoformat()}],"")
    ns["messaging"]=SimpleNamespace(_local_outbox_history=lambda *_:[
            local("cita_agendada",now-timedelta(hours=2)),
            local("recordatorio_hoy",now-timedelta(hours=1))])
    ns["_local_intention_state"]=make_func("_local_intention_state",ns)
    ns["_pending_signal_safe"]=lambda:False
    history=make_func("_history_payload",ns)
    d=history(source_type="appointment",source_id=107,fecha=datetime(2026,10,16).date(),
              hora="17:00",patient_name="PACIENTE DEMOSTRACION")
    assert len(d["events"])==2
    assert {e["status_label"] for e in d["events"]}=={"Sin constancia de envío","Entregado"}
    assert d["cloud_available"] and d["active_messaging_panel"]=="4.8.22"
    ns["_cloud_history"]=lambda **kw:([],"Conexión no disponible")
    d=history(source_type="appointment",source_id=107,fecha=datetime(2026,10,16).date(),
              hora="17:00",patient_name="PACIENTE DEMOSTRACION")
    assert d["events"][0]["status_label"]=="No verificable"

def test_real_override_and_no_dispatch():
    assert "Mensajería WhatsApp" in runtime
    assert "/api/messaging/appointments/" in runtime
    assert "messaging.install = install" in guard
    for forbidden in ("sendMeta(", "send_whatsapp(", "runScheduler("):
        assert forbidden not in ast.get_source_segment(guard,next(n for n in tree.body
                          if isinstance(n,ast.FunctionDef) and n.name=="_history_payload"))
if __name__=="__main__":
    test_overdue_unconfirmed()
    test_combined_cloud_and_local()
    test_real_override_and_no_dispatch()
    print("ACTIVE_MESSAGING_PANEL_REAL_ROUTE_NO_PHANTOM_DELIVERY_NO_SEND_OK")

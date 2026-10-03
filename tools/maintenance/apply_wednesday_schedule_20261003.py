from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def write(rel: str, text: str) -> None:
    (ROOT / rel).write_text(text, encoding="utf-8")


def replace_exact(text: str, old: str, new: str, *, label: str, count: int = 1) -> str:
    actual = text.count(old)
    if actual != count:
        raise RuntimeError(f"{label}: esperaba {count} coincidencia(s), encontré {actual}")
    return text.replace(old, new)


def patch_core_runtime() -> None:
    rel = "recepcion/app/core_runtime.py"
    s = read(rel)
    s = replace_exact(
        s,
        '''    defs = [\n        ("Jueves", monday + timedelta(days=3)),\n        ("Viernes", monday + timedelta(days=4)),\n        ("Sábado", monday + timedelta(days=5)),\n    ]''',
        '''    defs = [\n        ("Miércoles", monday + timedelta(days=2)),\n        ("Jueves", monday + timedelta(days=3)),\n        ("Viernes", monday + timedelta(days=4)),\n        ("Sábado", monday + timedelta(days=5)),\n    ]''',
        label="home_week Wednesday",
    )
    s = replace_exact(
        s,
        '''    day_defs = [\n        ("Jueves", monday + timedelta(days=3)),\n        ("Viernes", monday + timedelta(days=4)),\n        ("Sábado", monday + timedelta(days=5)),\n    ]''',
        '''    day_defs = [\n        ("Miércoles", monday + timedelta(days=2)),\n        ("Jueves", monday + timedelta(days=3)),\n        ("Viernes", monday + timedelta(days=4)),\n        ("Sábado", monday + timedelta(days=5)),\n    ]''',
        label="agenda_week Wednesday",
    )
    s = replace_exact(
        s,
        '''    for minute in range(8 * 60, 17 * 60 + 1, 20):\n        end_minute = minute + 20''',
        '''    # Miércoles el doctor inicia a las 10:00; jueves, viernes y sábado\n    # conservan el horario que ya tenían. Todos mantienen 12:30–14:00.\n    start_minute = 10 * 60 if fecha.weekday() == 2 else 8 * 60\n    for minute in range(start_minute, 17 * 60 + 1, 20):\n        end_minute = minute + 20''',
        label="agenda slots Wednesday start",
    )
    write(rel, s)


def patch_reception_frontend() -> None:
    rel = "recepcion/app/static/app.js"
    s = read(rel)
    s = replace_exact(
        s,
        '''  // Próximo día de consultorio: jueves, viernes o sábado.\n  // Si hoy ya es uno de esos días, usamos hoy para que Reagendar pueda''',
        '''  // Próximo día de consultorio: miércoles, jueves, viernes o sábado.\n  // Si hoy ya es uno de esos días, usamos hoy para que Reagendar pueda''',
        label="next clinic comment",
    )
    s = replace_exact(s, "if([4,5,6].includes(d.getDay()))return toISO(d);", "if([3,4,5,6].includes(d.getDay()))return toISO(d);", label="next clinic days")
    s = replace_exact(
        s,
        '''  return [\n    {label:'Jueves',date:new Date(monday.getFullYear(),monday.getMonth(),monday.getDate()+3)},\n    {label:'Viernes',date:new Date(monday.getFullYear(),monday.getMonth(),monday.getDate()+4)},\n    {label:'Sábado',date:new Date(monday.getFullYear(),monday.getMonth(),monday.getDate()+5)},\n  ].map(x=>({...x,iso:toISO(x.date)}));''',
        '''  return [\n    {label:'Miércoles',date:new Date(monday.getFullYear(),monday.getMonth(),monday.getDate()+2)},\n    {label:'Jueves',date:new Date(monday.getFullYear(),monday.getMonth(),monday.getDate()+3)},\n    {label:'Viernes',date:new Date(monday.getFullYear(),monday.getMonth(),monday.getDate()+4)},\n    {label:'Sábado',date:new Date(monday.getFullYear(),monday.getMonth(),monday.getDate()+5)},\n  ].map(x=>({...x,iso:toISO(x.date)}));''',
        label="week cards days",
    )
    s = replace_exact(
        s,
        '''  if(dow===0)return days[2].iso;\n  if(dow<=3)return days[0].iso;\n  return days[2].iso;''',
        '''  if(dow===0)return days[3].iso;\n  return days[0].iso;''',
        label="week default selection",
    )
    s = replace_exact(s, "const last=days?.[2]?.iso?fmtDate(days[2].iso):'';", "const last=days?.[3]?.iso?fmtDate(days[3].iso):'';", label="week nav last day")
    s = replace_exact(
        s,
        '''const label=d.label||weeklyData[iso]?.label||(['4','5','6'].includes(String(parseISO(iso).getDay()))?['','','','','Jueves','Viernes','Sábado'][parseISO(iso).getDay()]:'Día');''',
        '''const label=d.label||weeklyData[iso]?.label||(['3','4','5','6'].includes(String(parseISO(iso).getDay()))?['','','','Miércoles','Jueves','Viernes','Sábado'][parseISO(iso).getDay()]:'Día');''',
        label="home day fallback label",
    )
    write(rel, s)

    rel = "recepcion/app/static/style.css"
    s = read(rel)
    s = replace_exact(
        s,
        ".week-cards{display:grid;grid-template-columns:repeat(3,minmax(180px,1fr));",
        ".week-cards{display:grid;grid-template-columns:repeat(4,minmax(160px,1fr));",
        label="week cards four columns",
    )
    write(rel, s)


def patch_doctor_web() -> None:
    rel = "agenda/index.html"
    s = read(rel)
    s = replace_exact(s, ".grid{min-width:720px;display:grid;grid-template-columns:74px repeat(3,1fr)}", ".grid{min-width:860px;display:grid;grid-template-columns:74px repeat(4,1fr)}", label="doctor grid")
    s = replace_exact(s, ".lunch{grid-column:span 3;", ".lunch{grid-column:span 4;", label="doctor lunch span")
    s = replace_exact(s, ".grid{min-width:0;width:100%;grid-template-columns:42px repeat(3,minmax(0,1fr))}", ".grid{min-width:0;width:100%;grid-template-columns:42px repeat(4,minmax(0,1fr))}", label="doctor mobile grid")
    s = replace_exact(
        s,
        '''<div id="dayPicker" class="day-picker" style="display:none"><button data-pick-day="0" class="active" type="button">JUE</button><button data-pick-day="1" type="button">VIE</button><button data-pick-day="2" type="button">SÁB</button></div>''',
        '''<div id="dayPicker" class="day-picker" style="display:none"><button data-pick-day="0" class="active" type="button">MIÉ</button><button data-pick-day="1" type="button">JUE</button><button data-pick-day="2" type="button">VIE</button><button data-pick-day="3" type="button">SÁB</button></div>''',
        label="doctor day picker",
    )
    s = replace_exact(s, "const from=iso(add(state.mon,3)),to=iso(add(state.mon,5));", "const from=iso(add(state.mon,2)),to=iso(add(state.mon,5));", label="doctor query range")
    s = replace_exact(s, "Math.max(0,Math.min(2,Number(state.dayIndex)||0))", "Math.max(0,Math.min(3,Number(state.dayIndex)||0))", label="doctor day clamps", count=2)
    old_render = '''function render(){const days=[add(state.mon,3),add(state.mon,4),add(state.mon,5)],dates=days.map(iso),maps=dates.map(d=>new Map(state.rows.filter(r=>String(r.fecha).slice(0,10)===d).map(r=>[String(r.hora).slice(0,5),r])));$('#week').textContent=`${fmt(days[0])} – ${fmtFull(days[2])}`;let h='<div class="corner">HORA</div>';['JUEVES','VIERNES','SÁBADO'].forEach((n,i)=>h+=`<div class="day" data-day="${i}"><b>${n}</b><span>${fmt(days[i])}</span></div>`);let lunch=false;for(const time of SLOTS){if(!lunch&&time==='14:00'){h+='<div class="time lunch-time"><b>12:30</b><small></small></div><div class="lunch">ALMUERZO · 12:30 – 14:00</div>';lunch=true}const z=tp(time);h+=`<div class="time"><b>${z.t}</b><small>${z.p}</small></div>`;dates.forEach((d,i)=>{const r=maps[i].get(time);h+=r?appt(r,i):free(d,time,i)})}$('#grid').innerHTML=h;document.querySelectorAll('[data-free]').forEach(e=>e.onclick=()=>freeClick(e.dataset.date,e.dataset.time));document.querySelectorAll('[data-row]').forEach(e=>e.onclick=()=>detail(Number(e.dataset.row)));applyAgendaView();const total=3*SLOTS.length;$('#s1').textContent=state.rows.length;$('#s2').textContent=Math.max(0,total-state.rows.length);const mh=$('#moveHint');if(state.move){mh.style.display='block';mh.innerHTML=`Reagendando <b>${esc(state.move.patient_name)}</b>. Toca un horario disponible para mover la cita. <button id="cancelMove" class="secondary" style="border:0;border-radius:8px;padding:5px 8px;margin-left:6px">Cancelar</button>`;$('#cancelMove').onclick=()=>{state.move=null;render()}}else mh.style.display='none'}'''
    new_render = '''function slotAllowed(d,t){const dow=new Date(d+'T12:00:00').getDay();return dow!==3||String(t)>='10:00'}\nfunction closed(dayIndex=0){return `<div class="slot closed-slot" data-day="${dayIndex}"><div><b>—</b><span>No atiende</span></div></div>`}\nfunction render(){const days=[add(state.mon,2),add(state.mon,3),add(state.mon,4),add(state.mon,5)],dates=days.map(iso),maps=dates.map(d=>new Map(state.rows.filter(r=>String(r.fecha).slice(0,10)===d).map(r=>[String(r.hora).slice(0,5),r])));$('#week').textContent=`${fmt(days[0])} – ${fmtFull(days[3])}`;let h='<div class="corner">HORA</div>';['MIÉRCOLES','JUEVES','VIERNES','SÁBADO'].forEach((n,i)=>h+=`<div class="day" data-day="${i}"><b>${n}</b><span>${fmt(days[i])}</span></div>`);let lunch=false;for(const time of SLOTS){if(!lunch&&time==='14:00'){h+='<div class="time lunch-time"><b>12:30</b><small></small></div><div class="lunch">ALMUERZO · 12:30 – 14:00</div>';lunch=true}const z=tp(time);h+=`<div class="time"><b>${z.t}</b><small>${z.p}</small></div>`;dates.forEach((d,i)=>{if(!slotAllowed(d,time)){h+=closed(i);return}const r=maps[i].get(time);h+=r?appt(r,i):free(d,time,i)})}$('#grid').innerHTML=h;document.querySelectorAll('[data-free]').forEach(e=>e.onclick=()=>freeClick(e.dataset.date,e.dataset.time));document.querySelectorAll('[data-row]').forEach(e=>e.onclick=()=>detail(Number(e.dataset.row)));applyAgendaView();const total=dates.reduce((sum,d)=>sum+SLOTS.filter(t=>slotAllowed(d,t)).length,0),used=state.rows.filter(r=>slotAllowed(String(r.fecha).slice(0,10),String(r.hora).slice(0,5))).length;$('#s1').textContent=state.rows.length;$('#s2').textContent=Math.max(0,total-used);const mh=$('#moveHint');if(state.move){mh.style.display='block';mh.innerHTML=`Reagendando <b>${esc(state.move.patient_name)}</b>. Toca un horario disponible para mover la cita. <button id="cancelMove" class="secondary" style="border:0;border-radius:8px;padding:5px 8px;margin-left:6px">Cancelar</button>`;$('#cancelMove').onclick=()=>{state.move=null;render()}}else mh.style.display='none'}'''
    s = replace_exact(s, old_render, new_render, label="doctor render four days")
    s = replace_exact(s, ".free:hover{background:#f0f7ff}", ".free:hover{background:#f0f7ff}.closed-slot{display:flex;align-items:center;justify-content:center;background:#f3f5f7;color:#9aa4b1;text-align:center}.closed-slot b{display:block;font-size:11px}.closed-slot span{font-size:9px}", label="doctor closed slot css")
    write(rel, s)


def patch_public_booking() -> None:
    rel = "agenda/agendar.html"
    s = read(rel)
    s = replace_exact(s, "<div class=\"sub\">Atención jueves, viernes y sábado.</div>", "<div class=\"sub\">Atención miércoles, jueves, viernes y sábado. Los miércoles desde las 10:00.</div>", label="public booking subtitle")
    s = replace_exact(
        s,
        '''function occupiedSet(){return new Set((state.data?.occupied||[]).map(x=>`${x.date}|${x.time}`))}\nfunction availableCount(date){const occ=occupiedSet();return (state.data?.times||[]).filter(t=>!occ.has(`${date}|${t}`)).length}\nfunction validDates(){const today=parse(state.data?.today||iso(new Date())),out=[];for(let i=0;i<=Number(state.data?.max_days||45);i++){const d=add(today,i),day=d.getDay();if([4,5,6].includes(day))out.push(iso(d))}return out}''',
        '''function occupiedSet(){return new Set((state.data?.occupied||[]).map(x=>`${x.date}|${x.time}`))}\nfunction timesForDate(date){const dow=parse(date).getDay(),byDay=state.data?.times_by_day||{},specific=byDay[String(dow)];if(Array.isArray(specific))return specific;return (state.data?.times||[]).filter(t=>dow!==3||String(t)>='10:00')}\nfunction availableCount(date){const occ=occupiedSet();return timesForDate(date).filter(t=>!occ.has(`${date}|${t}`)).length}\nfunction validDates(){const today=parse(state.data?.today||iso(new Date())),out=[];for(let i=0;i<=Number(state.data?.max_days||45);i++){const d=add(today,i),day=d.getDay();if([3,4,5,6].includes(day))out.push(iso(d))}return out}''',
        label="public booking Wednesday dates",
    )
    s = replace_exact(
        s,
        '''function renderTimes(){const host=$('#times'),occ=occupiedSet();$('#selectedDateText').textContent=fmtDate(state.date);host.innerHTML=(state.data?.times||[]).map(t=>`<button class="time${state.time===t?' active':''}" data-time="${t}" ${occ.has(`${state.date}|${t}`)?'disabled':''}>${fmtTime(t)}</button>`).join('');host.querySelectorAll('[data-time]').forEach(b=>b.onclick=()=>selectTime(b.dataset.time))}''',
        '''function renderTimes(){const host=$('#times'),occ=occupiedSet();$('#selectedDateText').textContent=fmtDate(state.date);host.innerHTML=timesForDate(state.date).map(t=>`<button class="time${state.time===t?' active':''}" data-time="${t}" ${occ.has(`${state.date}|${t}`)?'disabled':''}>${fmtTime(t)}</button>`).join('');host.querySelectorAll('[data-time]').forEach(b=>b.onclick=()=>selectTime(b.dataset.time))}''',
        label="public booking Wednesday times",
    )
    write(rel, s)


def patch_whatsapp_worker() -> None:
    rel = "cloudflare/whatsapp_worker.js"
    s = read(rel)
    valid_old = "return !!d2 && [4, 5, 6].includes(d2.getUTCDay());"
    count = s.count(valid_old)
    if count < 1:
        raise RuntimeError("worker bookingValidDay no encontrado")
    s = s.replace(valid_old, "return !!d2 && [3, 4, 5, 6].includes(d2.getUTCDay());")

    marker = "var BOOKING_TIMES = new Set(bookingTimes());"
    marker_count = s.count(marker)
    if marker_count < 1:
        raise RuntimeError("worker BOOKING_TIMES no encontrado")
    helper = marker + '''\nfunction bookingTimeAllowed(date, time) {\n  const d2 = bookingDateObj(date);\n  if (!d2 || !BOOKING_TIMES.has(String(time || ""))) return false;\n  return d2.getUTCDay() !== 3 || String(time || "") >= "10:00";\n}'''
    s = s.replace(marker, helper)

    old_validation = '''!bookingValidDay(date) || !bookingDateWithinHorizon(date) || !BOOKING_TIMES.has(time)'''
    validation_count = s.count(old_validation)
    if validation_count < 2:
        raise RuntimeError(f"worker validaciones esperadas: encontré {validation_count}")
    s = s.replace(old_validation, '''!bookingValidDay(date) || !bookingDateWithinHorizon(date) || !bookingTimeAllowed(date, time)''')

    old_payload = '''days: [4, 5, 6], times: bookingTimes(), occupied'''
    payload_count = s.count(old_payload)
    if payload_count < 1:
        raise RuntimeError("worker availability payload no encontrado")
    new_payload = '''days: [3, 4, 5, 6], times: bookingTimes(), times_by_day: { "3": bookingTimes().filter((t) => t >= "10:00"), "4": bookingTimes(), "5": bookingTimes(), "6": bookingTimes() }, schedule: "wed_10_17_break_1230_1400_v1", occupied'''
    s = s.replace(old_payload, new_payload)

    version_count = s.count('worker_version: "2.6.23"')
    if version_count != 1:
        raise RuntimeError(f"worker_version marker esperado 1, encontré {version_count}")
    s = s.replace('worker_version: "2.6.23"', 'worker_version: "2.6.24", booking_schedule: "wed_10_17_break_1230_1400_v1"')
    write(rel, s)


def patch_manifest() -> None:
    rel = "recepcion/app/update_manifest.json"
    doc = json.loads(read(rel))
    doc["version"] = "4.6.48"
    doc["app_version"] = "4.6.48"
    doc["runtime_version"] = "4.6.48"
    notes = doc.setdefault("notes", {})
    notes["purpose"] = (
        "Recepción 4.6.48: habilita miércoles como día de atención en Agenda, de 10:00 a 17:00, "
        "con el mismo descanso 12:30–14:00. Alinea Inicio/Agenda de Recepción, Agenda web 24/7 del doctor, "
        "autoagendamiento público y comandos de autoagenda por WhatsApp. Jueves, viernes y sábado conservan "
        "sus horarios existentes. No cambia pacientes, facturación, impresión, Historia Clínica ni turnos/TV."
    )
    notes["previous_version"] = "4.6.47"
    notes["agenda_days"] = ["MIERCOLES", "JUEVES", "VIERNES", "SABADO"]
    notes["agenda_wednesday_hours"] = "10:00-17:00"
    notes["agenda_break"] = "12:30-14:00"
    notes["agenda_web_doctor_updated"] = True
    notes["agenda_public_booking_updated"] = True
    notes["agenda_whatsapp_autoagenda_updated"] = True
    notes["agenda_other_days_preserved"] = True
    notes["database_schema_changes"] = False
    notes["patient_data_changes"] = False
    notes["billing_logic_changes"] = False
    notes["printing_changes"] = False
    notes["procedure_logic_changes"] = False
    write(rel, json.dumps(doc, ensure_ascii=False, indent=2) + "\n")


def validate() -> None:
    core = read("recepcion/app/core_runtime.py")
    assert '("Miércoles", monday + timedelta(days=2))' in core
    assert 'start_minute = 10 * 60 if fecha.weekday() == 2 else 8 * 60' in core

    appjs = read("recepcion/app/static/app.js")
    assert "{label:'Miércoles'" in appjs
    assert "[3,4,5,6].includes(d.getDay())" in appjs

    doctor = read("agenda/index.html")
    assert "['MIÉRCOLES','JUEVES','VIERNES','SÁBADO']" in doctor
    assert "dow!==3||String(t)>='10:00'" in doctor

    public = read("agenda/agendar.html")
    assert "[3,4,5,6].includes(day)" in public
    assert "timesForDate" in public

    worker = read("cloudflare/whatsapp_worker.js")
    assert '[3, 4, 5, 6].includes(d2.getUTCDay())' in worker
    assert 'bookingTimeAllowed(date, time)' in worker
    assert 'worker_version: "2.6.24"' in worker
    assert 'wed_10_17_break_1230_1400_v1' in worker


if __name__ == "__main__":
    patch_core_runtime()
    patch_reception_frontend()
    patch_doctor_web()
    patch_public_booking()
    patch_whatsapp_worker()
    patch_manifest()
    validate()
    print("WEDNESDAY_SCHEDULE_MIGRATION_OK")

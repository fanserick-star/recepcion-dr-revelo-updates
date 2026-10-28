"""Recepción 4.8.106 — iniciar atención buscando paciente, no desde Agenda.
No accede a pacientes ni realiza llamadas externas.
"""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]/"recepcion/app"
app=(ROOT/"static/app.js").read_text(encoding="utf-8")
core=(ROOT/"core_runtime.py").read_text(encoding="utf-8")
html=(ROOT/"static/index.html").read_text(encoding="utf-8")
css=(ROOT/"static/home_remaster_4886.css").read_text(encoding="utf-8")
m=json.loads((ROOT/"update_manifest.json").read_text(encoding="utf-8"))
v=json.loads((ROOT/"recepcion-version.json").read_text(encoding="utf-8"))["version"]
assert v==m["version"]==m["runtime_version"]==m["app_version"]=="4.8.106"
assert '/static/app.js?v=4.8.106' in html
assert '/static/home_remaster_4886.css?v=4.8.106' in html
start=app.index("function newAttention(){")
stop=app.index("function procedureByName(",start)
flow=app[start:stop]
assert 'new-attention-start-modal' in flow
assert 'v477-attention-remaster attention-search-only' in flow
assert 'id="aSearch"' in flow
assert 'id="aResults"' in flow
assert 'attentionSearch()' in flow
assert 'newPatient(true)' in flow
assert 'attentionSearchSeq++' in flow
assert "document.querySelector('#aSearch')?.focus()" in flow
for forbidden in ("attentionWeekBlock","attentionWeekCalendar","loadAttentionWeek(",
                  "/api/agenda/week","agenda-only","Agenda de hoy","moveAttentionWeek"):
    assert forbidden not in flow,forbidden
assert "function attentionSearch(immediate=false)" in app
assert "const active=q.length>=2" in app
assert "api('/api/patients?q='+encodeURIComponent(q)+'&limit=18')" in app
assert "if(seq!==attentionSearchSeq)return" in app
assert "openPatient(${Number(p.id)},'attention-search')" in app
assert "openHistoricalPatientProfile(${Number(p.historical_id)})" in app
assert "Sin coincidencias. Revisa nombres" in app
assert "function newPatient(continueToAttention=false,agendaSlot=null)" in app
assert 'onclick="saveNewPatient(true)"' in app
assert "if(clinical.linked===true)await attentionFor(p.id)" in app
assert "if(data.clinical_registration_kind==='S')" in app
assert "async function attentionFor(id,draft=null)" in app
assert "selectedServices=new Set(draftServices.map(serviceKey).filter(Boolean))" in app
assert "async function saveExamReviewTurn(id)" in app
assert "if(fecha!==toISO(new Date()))" in app
assert "Number.isFinite(valor)" in app

# Source-of-truth: no second HTML implementation of Nueva atención injected at runtime.
beg=core.index('V477_ATTENTION_JS = r"""')
end=core.index('V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\\n" + V477_ATTENTION_CSS',beg)
injected=core[beg:end]
assert 'window.newAttention=function(){' in injected
assert 'mainNewAttention.apply(this,arguments)' in injected
assert 'v477-attention-modalbox' in injected
for forbidden in ("window.newAttention=async function","id=\"attentionWeekBlock\"",
                  "loadAttentionWeek(false","Agenda de hoy","window.renderAttentionWeek=function"):
    assert forbidden not in injected,forbidden
# The old v4.3.78 remix is still in the served overlay for Home.
# It must NEVER replace the canonical newAttention entry point.
remix_start=core.index('V478_REMIX_JS = r"""')
remix_end=core.index('V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\\n" + V478_REMIX_CSS',remix_start)
remix=core[remix_start:remix_end]
assert 'window.newAttention=async function' not in remix
assert 'id="attentionWeekBlock"' not in remix
assert 'loadAttentionWeek(false,attentionWeekAnchor)' not in remix
assert 'window.renderHomeDayPayload=function' in remix
assert core.count('window.newAttention=function(){') == 1
assert core.count('window.newAttention=async function(){') == 0

# Functional regression: execute the actual source + ordered runtime overlays.
import subprocess
subprocess.run(['node','tools/test_reception_new_attention_runtime_48106.mjs'],check=True)

assert 'attention-search-only' in css
assert 'attention-search-hint' in css

# Do not touch the main Agenda, Confirmafy handling, clinical linkage or fiscal flows.
assert 'id="agendaNativeGrid"' in html
assert 'data-section="agenda"' in html
for symbol in ("async function attendFromAgenda(","async function attendConfirmafyStaged(",
               "async function saveAttention(","async function saveExamReviewTurn(",
               "async function refreshAttentionClinicalHistory("):
    assert symbol in app,symbol
assert "if(!serviceNames.length)throw Error('Selecciona al menos una atención.')" in app
assert "api('/api/visits/batch',{method:'POST'" in app
print("RECEPTION_SEARCH_FIRST_NEW_ATTENTION_48102_OK")

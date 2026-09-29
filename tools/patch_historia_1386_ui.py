from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "historia-clinica/app/app.py"
CSS = ROOT / "historia-clinica/app/static/style.css"
VER = ROOT / "historia-clinica/app/historia-version.json"
MAN = ROOT / "historia-clinica/app/update_manifest.json"

app = APP.read_text(encoding="utf-8-sig")

# ---------------------------------------------------------------------------
# Global professional dialog used instead of browser/WebView confirm/alert.
# ---------------------------------------------------------------------------
marker = 'def base(title: str, body: str, active: str = "inicio", extra_head: str = "", extra_script: str = "") -> str:\n'
assert marker in app, "base() marker not found"
assert "APP_DIALOG_HTML =" not in app, "dialog already installed"

dialog = r'''APP_DIALOG_HTML = r"""
<div id="appDialogBackdrop" class="app-dialog-backdrop" hidden aria-hidden="true">
  <section class="app-dialog" role="dialog" aria-modal="true" aria-labelledby="appDialogTitle" aria-describedby="appDialogMessage">
    <div class="app-dialog-icon" aria-hidden="true">i</div>
    <div class="app-dialog-copy">
      <h3 id="appDialogTitle">Confirmar acción</h3>
      <p id="appDialogMessage"></p>
    </div>
    <div class="app-dialog-actions">
      <button type="button" class="secondary" id="appDialogCancel">Cancelar</button>
      <button type="button" class="primary" id="appDialogConfirm">Continuar</button>
    </div>
  </section>
</div>
<script>
(()=>{
  if(window.__historiaProfessionalDialog)return;
  window.__historiaProfessionalDialog=true;
  const backdrop=document.getElementById('appDialogBackdrop');
  const title=document.getElementById('appDialogTitle');
  const message=document.getElementById('appDialogMessage');
  const cancel=document.getElementById('appDialogCancel');
  const confirmBtn=document.getElementById('appDialogConfirm');
  let finish=null;

  function close(value){
    if(!finish)return;
    const done=finish;
    finish=null;
    backdrop.hidden=true;
    backdrop.setAttribute('aria-hidden','true');
    document.body.classList.remove('app-dialog-open');
    confirmBtn.classList.remove('danger');
    done(Boolean(value));
  }

  window.appConfirm=(text,options={})=>new Promise(resolve=>{
    if(finish)close(false);
    finish=resolve;
    title.textContent=String(options.title||'Confirmar acción');
    message.textContent=String(text||'');
    confirmBtn.textContent=String(options.confirmText||'Continuar');
    cancel.textContent=String(options.cancelText||'Cancelar');
    cancel.hidden=options.cancelText===null;
    confirmBtn.classList.toggle('danger',Boolean(options.danger));
    backdrop.hidden=false;
    backdrop.setAttribute('aria-hidden','false');
    document.body.classList.add('app-dialog-open');
    setTimeout(()=>confirmBtn.focus(),0);
  });
  window.appNotice=(text,options={})=>window.appConfirm(text,{
    ...options,
    confirmText:options.confirmText||'Aceptar',
    cancelText:null
  });

  cancel.addEventListener('click',()=>close(false));
  confirmBtn.addEventListener('click',()=>close(true));
  backdrop.addEventListener('click',ev=>{if(ev.target===backdrop && !cancel.hidden)close(false)});
  document.addEventListener('keydown',ev=>{
    if(backdrop.hidden)return;
    if(ev.key==='Escape' && !cancel.hidden){ev.preventDefault();close(false)}
  });

  document.addEventListener('submit',async ev=>{
    const form=ev.target.closest?.('.js-queue-dismiss');
    if(!form || form.dataset.confirmed==='1')return;
    ev.preventDefault();
    const ok=await window.appConfirm(
      'Se quitará esta atención de Pacientes en espera. La ficha y la historia clínica se conservarán.',
      {title:'Quitar de espera',confirmText:'Quitar',danger:true}
    );
    if(ok){form.dataset.confirmed='1';form.submit()}
  });
})();
</script>
"""

'''
app = app.replace(marker, dialog + marker, 1)

old_end = "{extra_script}</body></html>\"\"\""
new_end = "{APP_DIALOG_HTML}{extra_script}</body></html>\"\"\""
assert app.count(old_end) == 1, app.count(old_end)
app = app.replace(old_end, new_end, 1)

# ---------------------------------------------------------------------------
# Waiting-room cards: keep consultation turn, remove initial avatar and PROC box.
# ---------------------------------------------------------------------------
old_turn = '''            turn_badge = (\n                f"<div class='queue-turn-number'><span>TURNO</span><b>#{real_turn}</b></div>"\n                if not is_procedure and real_turn is not None\n                else "<div class='queue-turn-number queue-turn-procedure'><span>ATENCIÓN</span><b>PROC.</b></div>"\n            )'''
new_turn = '''            turn_badge = (\n                f"<div class='queue-turn-number'><span>TURNO</span><b>#{real_turn}</b></div>"\n                if not is_procedure and real_turn is not None\n                else ""\n            )'''
assert app.count(old_turn) == 1, app.count(old_turn)
app = app.replace(old_turn, new_turn, 1)

avatar_line = '''                f"<div class='queue-avatar'>{e((r['display_name'] or '?')[:1])}</div>"\n'''
assert app.count(avatar_line) == 1, app.count(avatar_line)
app = app.replace(avatar_line, "", 1)

old_form = '''                f"<form class='queue-dismiss-form' method='post' action='/cola/{e(r['id'])}/descartar' "\n                f"onsubmit=\\"return confirm('¿Quitar este turno de Pacientes en espera? No se eliminará la ficha ni la historia clínica.')\\">"'''
new_form = '''                f"<form class='queue-dismiss-form js-queue-dismiss' method='post' action='/cola/{e(r['id'])}/descartar'>"'''
assert app.count(old_form) == 1, app.count(old_form)
app = app.replace(old_form, new_form, 1)

# ---------------------------------------------------------------------------
# Replace native browser confirmations throughout patient history flows.
# ---------------------------------------------------------------------------
old_reopen = "if(!confirm('¿Abrir esta historia para continuar editándola? Se conservará una revisión interna del texto anterior.'))return;"
new_reopen = "if(!await window.appConfirm('Se abrirá esta historia para continuar editándola. Antes de modificarla se conservará una revisión interna del texto anterior.',{title:'Continuar edición',confirmText:'Continuar edición'}))return;"
assert app.count(old_reopen) == 1, app.count(old_reopen)
app = app.replace(old_reopen, new_reopen, 1)

old_delete = "if(!confirm(msg))return;"
new_delete = "if(!await window.appConfirm(msg,{title:'Eliminar historia',confirmText:'Eliminar',danger:true}))return;"
assert app.count(old_delete) == 1, app.count(old_delete)
app = app.replace(old_delete, new_delete, 1)

old_alert = "else alert(err&&err.message?err.message:'No se pudo imprimir.');"
new_alert = "else if(window.appNotice)window.appNotice(err&&err.message?err.message:'No se pudo imprimir.',{title:'Impresión'});"
assert app.count(old_alert) == 1, app.count(old_alert)
app = app.replace(old_alert, new_alert, 1)

assert "if(!confirm(" not in app
assert "return confirm(" not in app
assert "else alert(" not in app
assert "PROC.</b>" not in app
assert "class='queue-avatar'" not in app
assert "<span>TURNO</span>" in app
APP.write_text(app, encoding="utf-8", newline="\n")

# ---------------------------------------------------------------------------
# CSS: professional modal + queue layout without avatar/PROC placeholder.
# ---------------------------------------------------------------------------
css = CSS.read_text(encoding="utf-8-sig")
css_marker = "/* v1.3.86 · diálogos profesionales + cola sin avatar/PROC */"
assert css_marker not in css
css += r'''

/* v1.3.86 · diálogos profesionales + cola sin avatar/PROC */
body.app-dialog-open{overflow:hidden}
.app-dialog-backdrop[hidden]{display:none!important}
.app-dialog-backdrop{
  position:fixed;inset:0;z-index:10000;display:flex;align-items:center;justify-content:center;
  padding:24px;background:rgba(17,31,48,.36);backdrop-filter:blur(4px)
}
.app-dialog{
  width:min(520px,calc(100vw - 36px));display:grid;grid-template-columns:44px minmax(0,1fr);
  gap:0 15px;background:#fff;border:1px solid #d9e1e9;border-radius:15px;
  box-shadow:0 24px 70px rgba(19,37,58,.24);padding:22px 22px 18px
}
.app-dialog-icon{
  width:42px;height:42px;border-radius:12px;display:grid;place-items:center;
  background:#e9f2f8;color:#0f4c78;font-size:20px;font-weight:900;font-family:Georgia,serif
}
.app-dialog-copy{min-width:0;padding-top:1px}
.app-dialog-copy h3{margin:0;color:#17212f;font-size:18px;line-height:1.2;letter-spacing:-.015em}
.app-dialog-copy p{margin:8px 0 0;color:#5c6878;font-size:13.5px;line-height:1.55;white-space:pre-line}
.app-dialog-actions{grid-column:1/-1;display:flex;justify-content:flex-end;gap:9px;margin-top:20px;padding-top:15px;border-top:1px solid #edf0f3}
.app-dialog-actions .primary,.app-dialog-actions .secondary{height:40px;min-width:104px;padding:0 17px}
.app-dialog-actions .primary.danger{background:#a93842}
.app-dialog-actions .primary.danger:hover{background:#8e2f38}

/* Consultas conservan TURNO #n; procedimientos no muestran cajón artificial. */
.home-queue-v107 .queue-avatar{display:none!important}
.home-queue-v107 .queue-row-main{
  grid-template-columns:76px minmax(0,1fr) auto!important;
  grid-template-areas:'turn patient time' 'turn patient action'!important;
  column-gap:16px!important
}
.home-queue-v107 .queue-row-procedure .queue-row-main{
  grid-template-columns:minmax(0,1fr) auto!important;
  grid-template-areas:'patient time' 'patient action'!important;
  padding-left:22px!important
}
.home-queue-v107 .queue-row-procedure .queue-patient-copy{padding-left:2px}
.home-queue-v107 .queue-row-procedure .queue-procedure-chip{margin-top:2px}
@media(max-width:720px){
  .home-queue-v107 .queue-row-main{
    grid-template-columns:64px minmax(0,1fr)!important;
    grid-template-areas:'turn patient' 'time action'!important
  }
  .home-queue-v107 .queue-row-procedure .queue-row-main{
    grid-template-columns:minmax(0,1fr)!important;
    grid-template-areas:'patient' 'time' 'action'!important;
    padding-left:14px!important
  }
}
'''
CSS.write_text(css, encoding="utf-8", newline="\n")

# ---------------------------------------------------------------------------
# Version + manifest.
# ---------------------------------------------------------------------------
ver = json.loads(VER.read_text(encoding="utf-8-sig"))
assert ver.get("version") == "1.3.85", ver
ver["version"] = "1.3.86"
VER.write_text(json.dumps(ver, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")

man = json.loads(MAN.read_text(encoding="utf-8-sig"))
for key in ("version", "app_version", "runtime_version"):
    man[key] = "1.3.86"
notes = man.setdefault("notes", {})
notes.update({
    "purpose": "Refina Pacientes en espera: conserva turnos de consultas, elimina avatar/PROC de procedimientos y reemplaza confirmaciones nativas por modales profesionales.",
    "previous_version": "1.3.85",
    "functional_changes": False,
    "ui_only_release": True,
    "waiting_room_queue_logic_unchanged": True,
    "waiting_queue_unchanged": True,
    "waiting_room_turn_prominent": True,
    "consultation_turn_number_preserved": True,
    "procedure_turn_consumption": False,
    "procedure_proc_block_removed": True,
    "waiting_room_initial_avatar_removed": True,
    "professional_app_dialogs": True,
    "native_browser_confirm_removed": True,
    "native_browser_alert_fallback_removed": True,
    "database_schema_changes": False,
    "clinical_data_changes": False,
    "patient_data_destructive_changes": False,
    "lan_logic_changes": False,
    "cloud_logic_changes": False,
    "printing_changes": False,
})
MAN.write_text(json.dumps(man, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

print("PATCH_OK Historia 1.3.86")

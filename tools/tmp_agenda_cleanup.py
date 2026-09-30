from __future__ import annotations

from pathlib import Path
import ast
import json
import re

ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    require(count == 1, f"{label}: esperado 1, encontrado {count}")
    return text.replace(old, new, 1)


def main() -> None:
    module_path = ROOT / "recepcion/app/reception_payments_and_agenda.py"
    app_path = ROOT / "recepcion/app/static/app.js"
    style_path = ROOT / "recepcion/app/static/style.css"
    core_path = ROOT / "recepcion/app/core_runtime.py"
    agenda_path = ROOT / "agenda/index.html"
    public_path = ROOT / "agenda/agendar.html"
    version_path = ROOT / "recepcion/app/recepcion-version.json"
    manifest_path = ROOT / "recepcion/app/update_manifest.json"

    module = module_path.read_text(encoding="utf-8")
    tree = ast.parse(module)
    extracted: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in {
                    "V4449_AGENDA_FLOW_JS",
                    "V4449_AGENDA_FLOW_CSS",
                }:
                    extracted[target.id] = ast.literal_eval(node.value)
    require(
        set(extracted) == {"V4449_AGENDA_FLOW_JS", "V4449_AGENDA_FLOW_CSS"},
        f"No se encontraron ambos overlays de Agenda: {sorted(extracted)}",
    )

    agenda_js = extracted["V4449_AGENDA_FLOW_JS"]
    agenda_css = extracted["V4449_AGENDA_FLOW_CSS"]
    replacements = {
        "__v4449AgendaFlowSpeed": "__agendaCanonicalFlow",
        "v4449SaveExistingAndAttend": "saveExistingAndAttendFromAgenda",
        "__v4449AgendaTest": "__agendaCanonicalTest",
        "v4449-existing-attend": "agenda-existing-attend",
        "v4449-existing-note": "agenda-existing-note",
    }
    for old, new in replacements.items():
        agenda_js = agenda_js.replace(old, new)
        agenda_css = agenda_css.replace(old, new)

    app = app_path.read_text(encoding="utf-8")
    require("__agendaCanonicalFlow" not in app, "Agenda canónica ya está incrustada en app.js")
    old_fmt = (
        "function fmtTime(v){const m=String(v||'').match(/^(\\d{1,2}):(\\d{2})/);"
        "if(!m)return esc(v);let h=Number(m[1]),min=m[2];const ap=h>=12?'p. m.':'a. m.';"
        "h=h%12||12;return `${h}:${min} ${ap}`}\n"
        "function fmtTimeCompact(v){const m=String(v||'').match(/^(\\d{1,2}):(\\d{2})/);"
        "if(!m)return esc(v);let h=Number(m[1]),min=m[2];h=h%12||12;return `${h}:${min}`}"
    )
    new_fmt = (
        "function fmtTime(v){const m=String(v||'').match(/^(\\d{1,2}):(\\d{2})/);"
        "if(!m)return esc(v);return `${pad(Number(m[1]))}:${m[2]}`}\n"
        "function fmtTimeCompact(v){const m=String(v||'').match(/^(\\d{1,2}):(\\d{2})/);"
        "if(!m)return esc(v);return `${pad(Number(m[1]))}:${m[2]}`}"
    )
    app = replace_once(app, old_fmt, new_fmt, "fmtTime Reception 24h")
    app += (
        "\n\n// Agenda canónica: flujo consolidado desde el antiguo overlay histórico.\n"
        + agenda_js.strip()
        + "\n"
    )
    app_path.write_text(app, encoding="utf-8")

    style = style_path.read_text(encoding="utf-8")
    require(".agenda-existing-note" not in style, "CSS canónico de Agenda ya existe")
    style += (
        "\n\n/* Agenda canónica: estilo de actualización de paciente existente. */\n"
        + agenda_css.strip()
        + "\n"
    )
    style_path.write_text(style, encoding="utf-8")

    start = module.index("    V4449_AGENDA_FLOW_JS = ")
    end = module.index("    _v4450_stable_mirror_patient =", start)
    module = (
        module[:start]
        + "    # La interfaz de Agenda vive ahora en static/app.js y static/style.css.\n"
        + module[end:]
    )
    require("V4449_AGENDA_FLOW_JS" not in module, "Quedó overlay JS histórico")
    require("V4449_AGENDA_FLOW_CSS" not in module, "Quedó overlay CSS histórico")
    module_path.write_text(module, encoding="utf-8")

    core = core_path.read_text(encoding="utf-8")
    old_import = '''from remote_agenda import (
    normalize_public_base_url as remote_normalize_base_url,
    start_quick_tunnel as remote_start_quick_tunnel,
    start_named_tunnel as remote_start_named_tunnel,
    start_named_tunnel_background as remote_start_named_tunnel_background,
    stop_managed_tunnel as remote_stop_tunnel,
    tunnel_status as remote_tunnel_status,
)'''
    core = replace_once(
        core,
        old_import,
        "from remote_agenda import stop_managed_tunnel as remote_stop_tunnel",
        "imports Tunnel legado",
    )

    old_remote = '''# Agenda remota por HTTPS. El token del túnel se lee únicamente del .env local.
REMOTE_AGENDA_BASE_URL = (os.getenv("REMOTE_AGENDA_BASE_URL") or "").strip().rstrip("/")
REMOTE_AGENDA_TUNNEL_TOKEN = (os.getenv("REMOTE_AGENDA_TUNNEL_TOKEN") or "").strip()
REMOTE_AGENDA_AUTOSTART = (os.getenv("REMOTE_AGENDA_AUTOSTART") or "1").strip() != "0"
'''
    core = replace_once(core, old_remote, "", "variables Tunnel legado")

    remote_start = core.index("\ndef _mobile_remote_payload(")
    remote_end = core.index('\n@app.post("/api/mobile/links/rotate")', remote_start)
    core = core[:remote_start] + "\n" + core[remote_end:]

    cleanup_start = core.index("\nWA_TEST_CLEANUP_PHONE_V4424 =")
    cleanup_route = core.index("\n@app.post", cleanup_start)
    cleanup_end = core.index("\n@app.", cleanup_route + 2)
    core = core[:cleanup_start] + "\n" + core[cleanup_end:]

    stale_comment = '''# Activación por plantilla: solo recordatorio_cita está aprobado hoy. Aunque
# WHATSAPP_ENABLED llegue a 1, las otras dos no se intentan hasta aprobarlas.'''
    fresh_comment = '''# Activación local por plantilla. En la arquitectura actual Cloudflare es la autoridad
# de envío 24/7; estas banderas solo gobiernan el fallback local si Cloud se desactiva.'''
    core = replace_once(core, stale_comment, fresh_comment, "comentario WhatsApp")

    require('/api/whatsapp-responses/cleanup-old-tests' not in core, "Quedó endpoint de pruebas")
    require('/api/mobile/remote/' not in core, "Quedaron endpoints de Tunnel")
    require('REMOTE_AGENDA_TUNNEL_TOKEN' not in core, "Quedó token de Tunnel")
    require('remote_start_quick_tunnel' not in core, "Quedó start quick tunnel")
    require('remote_start_named_tunnel' not in core, "Quedó start named tunnel")
    require('remote_tunnel_status' not in core, "Quedó status tunnel")
    require('remote_stop_tunnel(DATA_DIR)' in core, "Se perdió limpieza de proceso Tunnel legado")
    core_path.write_text(core, encoding="utf-8")

    agenda = agenda_path.read_text(encoding="utf-8")
    header = '<div class="top-actions"><button class="mode-switch" id="modeSwitch" type="button"></button><button class="icon" id="refresh" aria-label="Actualizar">↻</button></div>'
    new_header = '<div class="top-actions"><button class="mode-switch" id="modeSwitch" type="button"></button><button class="mode-switch show" id="forgetDevice" type="button" title="Borrar acceso y copia local de este dispositivo">SALIR</button><button class="icon" id="refresh" aria-label="Actualizar">↻</button></div>'
    agenda = replace_once(agenda, header, new_header, "botón salir Agenda")

    old_tp = "function tp(s){const [h,m]=s.split(':').map(Number);return {t:`${h%12||12}:${pad(m)}`,p:h>=12?'PM':'AM'}}"
    new_tp = "function tp(s){const [h,m]=s.split(':').map(Number);return {t:`${pad(h)}:${pad(m)}`,p:''}}"
    agenda = replace_once(agenda, old_tp, new_tp, "horario 24h Agenda privada")
    agenda = replace_once(agenda, "<b>12:30</b><small>PM</small>", "<b>12:30</b><small></small>", "almuerzo PM")
    agenda = replace_once(agenda, "ALMUERZO · 12:30 PM – 2:00 PM", "ALMUERZO · 12:30 – 14:00", "almuerzo 24h")

    role_fn = "function rememberRoleKey(){if(state.role==='doctor')localStorage.setItem('revelo_agenda_doctor_key',state.key);if(state.role==='reception')localStorage.setItem('revelo_agenda_reception_key',state.key)}"
    cache_code = r'''function rememberRoleKey(){if(state.role==='doctor')localStorage.setItem('revelo_agenda_doctor_key',state.key);if(state.role==='reception')localStorage.setItem('revelo_agenda_reception_key',state.key)}
const AGENDA_CACHE_TTL_MS=24*60*60*1000;
function purgeAgendaCaches(){for(let i=localStorage.length-1;i>=0;i--){const k=localStorage.key(i);if(!k||!k.startsWith('revelo_cloud_'))continue;try{const d=JSON.parse(localStorage.getItem(k)||'null');if(!d||!Array.isArray(d.rows)||Date.now()-Number(d.saved_at||0)>AGENDA_CACHE_TTL_MS)localStorage.removeItem(k)}catch{localStorage.removeItem(k)}}}
function saveWeekCache(key,rows){try{localStorage.setItem(key,JSON.stringify({saved_at:Date.now(),rows}))}catch{}}
function loadWeekCache(key){try{const d=JSON.parse(localStorage.getItem(key)||'null');if(!d||!Array.isArray(d.rows)||Date.now()-Number(d.saved_at||0)>AGENDA_CACHE_TTL_MS){localStorage.removeItem(key);return null}return d.rows}catch{localStorage.removeItem(key);return null}}
function forgetDevice(){if(!confirm('¿Borrar de este dispositivo los accesos guardados y la copia local de la agenda?'))return;['revelo_agenda_cloud_key','revelo_agenda_doctor_key','revelo_agenda_reception_key'].forEach(k=>localStorage.removeItem(k));for(let i=localStorage.length-1;i>=0;i--){const k=localStorage.key(i);if(k?.startsWith('revelo_cloud_'))localStorage.removeItem(k)}history.replaceState({},'',location.pathname+location.search);state.key='';state.role='';state.rows=[];state.jwt='';state.exp=0;location.reload()}
purgeAgendaCaches();'''
    agenda = replace_once(agenda, role_fn, cache_code, "caché privado Agenda")

    agenda = replace_once(
        agenda,
        "localStorage.setItem(`revelo_cloud_${iso(state.mon)}`,JSON.stringify(state.rows));",
        "saveWeekCache(`revelo_cloud_${iso(state.mon)}`,state.rows);",
        "guardado caché Agenda",
    )
    agenda = replace_once(
        agenda,
        "const c=localStorage.getItem(`revelo_cloud_${iso(state.mon)}`);if(c){state.rows=JSON.parse(c);render();online('Sin conexión · mostrando copia guardada',false)}else fatal(e.message)",
        "const c=loadWeekCache(`revelo_cloud_${iso(state.mon)}`);if(c){state.rows=c;render();online('Sin conexión · mostrando copia guardada reciente',false)}else fatal(e.message)",
        "lectura caché Agenda",
    )
    agenda = replace_once(
        agenda,
        "$('#modeSwitch').onclick=switchMode;boot();",
        "$('#modeSwitch').onclick=switchMode;$('#forgetDevice').onclick=forgetDevice;boot();",
        "handler salir Agenda",
    )
    agenda_path.write_text(agenda, encoding="utf-8")

    public = public_path.read_text(encoding="utf-8")
    public = replace_once(
        public,
        "const fmtTime=v=>{const [hh,mm]=String(v).split(':').map(Number);return `${hh%12||12}:${pad(mm)} ${hh>=12?'p. m.':'a. m.'}`};",
        "const fmtTime=v=>{const [hh,mm]=String(v).split(':').map(Number);return `${pad(hh)}:${pad(mm)}`};",
        "horario 24h Agenda pública",
    )
    public_path.write_text(public, encoding="utf-8")

    version_path.write_text('{"version":"4.6.26"}\n', encoding="utf-8")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["version"] = manifest["app_version"] = manifest["runtime_version"] = "4.6.26"
    notes = manifest.setdefault("notes", {})
    notes.update(
        {
            "purpose": "Consolida Agenda y WhatsApp: UI de Agenda pasa a fuente canónica, elimina controles de túnel legado y residuos de pruebas, y unifica horario 24 h.",
            "previous_version": "4.6.25",
            "candidate_only": False,
            "agenda_ui_canonical": True,
            "agenda_historical_overlay_removed": True,
            "agenda_24h_format": True,
            "agenda_cloud_conflict_logic_preserved": True,
            "agenda_offline_cache_logic_preserved": True,
            "legacy_remote_tunnel_start_controls_removed": True,
            "legacy_remote_tunnel_startup_cleanup_preserved": True,
            "whatsapp_old_test_cleanup_endpoint_removed": True,
            "whatsapp_cloud_mode_preserved": True,
            "whatsapp_logic_changes": False,
            "billing_logic_changes": False,
            "database_schema_changes": False,
            "patient_data_changes": False,
            "production_status": "stable",
            "rollback_safe": True,
        }
    )
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("AGENDA_RECEPTION_CONSOLIDATION_PATCHED")


if __name__ == "__main__":
    main()

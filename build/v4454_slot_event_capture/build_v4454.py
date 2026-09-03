from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "updates" / "v4_4_53_slot_capture_fix"
OUT = ROOT / "updates" / "v4_4_54_slot_event_capture"
VERSION = "4.4.54"


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise RuntimeError(msg)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dump(obj: dict) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


PATCH = r'''
    # -----------------------------------------------------------------------
    # v4.4.54 — capturar fecha/hora en el MISMO clic del horario libre.
    # -----------------------------------------------------------------------
    # La cuadrícula estable invoca openAgendaSlotPicker(fecha, hora). Guardamos
    # esos argumentos antes de abrir la ventana de selección, evitando depender
    # del DOM/interiores del modal para reconstruir el horario.
    V4454_SLOT_EVENT_JS = r"""
;(()=>{
  if(window.__v4454SlotEventCapture)return;
  window.__v4454SlotEventCapture=true;

  function normalizeSlot(fecha,hora){
    const f=String(fecha||'').slice(0,10),h=String(hora||'').slice(0,5);
    if(!/^\d{4}-\d{2}-\d{2}$/.test(f)||!/^\d{2}:\d{2}$/.test(h))return null;
    return {fecha:f,hora:h,ts:Date.now()};
  }
  function remember(fecha,hora){
    const slot=normalizeSlot(fecha,hora);
    if(slot)window.__v4454SelectedAgendaSlot=slot;
    return slot;
  }
  function installWrapper(){
    const current=window.openAgendaSlotPicker;
    if(typeof current!=='function'||current.__v4454Wrapped)return;
    const wrapped=function(fecha,hora){remember(fecha,hora);return current.apply(this,arguments)};
    wrapped.__v4454Wrapped=true;
    wrapped.__v4454Original=current;
    window.openAgendaSlotPicker=wrapped;
  }

  // Captura en fase capture, antes de que ejecute el onclick inline del horario.
  document.addEventListener('click',e=>{
    const btn=e.target?.closest?.('[onclick*="openAgendaSlotPicker"]');
    if(!btn)return;
    const raw=String(btn.getAttribute('onclick')||'');
    const m=/openAgendaSlotPicker\(\s*['"](\d{4}-\d{2}-\d{2})['"]\s*,\s*['"](\d{2}:\d{2})['"]\s*\)/.exec(raw);
    if(m)remember(m[1],m[2]);
  },true);

  installWrapper();
  setTimeout(installWrapper,0);
  setTimeout(installWrapper,120);
  setTimeout(installWrapper,500);
  document.addEventListener('click',()=>setTimeout(installWrapper,0),true);

  window.__v4454SlotCaptureTest={normalizeSlot,remember,installWrapper,get:()=>window.__v4454SelectedAgendaSlot||null};
})();
"""
    core.V460_OVERLAY_JS = (core.V460_OVERLAY_JS or "") + "\n" + V4454_SLOT_EVENT_JS
'''


def main() -> None:
    app_text = (SOURCE / "app.py").read_text(encoding="utf-8-sig")
    require('APP_VERSION = "4.4.53"' in app_text, "La base app no es 4.4.53")
    app_text = app_text.replace('APP_VERSION = "4.4.53"', 'APP_VERSION = "4.4.54"', 1)
    app_text = app_text.replace("const VERSION='4.4.53';", "const VERSION='4.4.54';")

    old = "    const slot=slotFromModal(source);"
    new = "    const remembered=window.__v4454SelectedAgendaSlot;\n    const slot=(remembered&&Date.now()-Number(remembered.ts||0)<300000?remembered:null)||slotFromModal(source);"
    require(old in app_text, "No se encontró apertura rápida v4.4.53")
    app_text = app_text.replace(old, new, 1)

    require("    FEATURE_BOOT_OK = True\n" in app_text, "No se encontró punto de inserción")
    app_text = app_text.replace("    FEATURE_BOOT_OK = True\n", PATCH + "\n    FEATURE_BOOT_OK = True\n", 1)
    compile(app_text, "app.py", "exec")

    app = app_text.encode("utf-8")
    app_base = (SOURCE / "app_base_4428.py").read_text(encoding="utf-8-sig").replace("\r\n", "\n").encode("utf-8")
    launcher_parts = [(SOURCE / f"ABRIR_RECEPCION.part{i}").read_bytes() for i in range(1, 5)]
    launcher = b"".join(launcher_parts)
    compile(app_base.decode("utf-8-sig"), "app_base_4428.py", "exec")
    compile(launcher.decode("utf-8-sig"), "ABRIR_RECEPCION.py", "exec")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "app.py").write_bytes(app)
    (OUT / "app_base_4428.py").write_bytes(app_base)
    for i, data in enumerate(launcher_parts, 1):
        (OUT / f"ABRIR_RECEPCION.part{i}").write_bytes(data)

    manifest = {
        "product": "recepcion-pacientes",
        "version": VERSION,
        "app_version": VERSION,
        "runtime_version": VERSION,
        "launcher_version": "4.4.48-update-before-focus-dependency-safe-1",
        "updater_version": "integrado-en-launcher-update-before-focus",
        "required_dependencies": ["app_base_4428.py"],
        "required_python_packages": [{"import": "pg8000", "pip": "pg8000==1.31.2"}],
        "copy": ["app.py", "app_base_4428.py", "ABRIR_RECEPCION.py", "update_manifest.json"],
    }
    manifest_bytes = dump(manifest)
    (OUT / "update_manifest.json").write_bytes(manifest_bytes)

    raw = "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_54_slot_event_capture/"
    candidate = {
        "product": "recepcion-pacientes",
        "version": VERSION,
        "app_version": VERSION,
        "runtime_version": VERSION,
        "mandatory": True,
        "channel": "files-v3",
        "message": "v4.4.54: Crear cita nueva conserva la fecha y hora directamente desde el clic del horario libre, sin depender del contenido del modal. Conserva todos los arreglos de v4.4.53.",
        "files": [
            {"path": "app.py", "url": raw + "app.py", "sha256": sha(app), "encoding": "utf-8"},
            {"path": "app_base_4428.py", "url": raw + "app_base_4428.py", "sha256": sha(app_base), "encoding": "utf-8"},
            {"path": "ABRIR_RECEPCION.py", "parts": [raw + f"ABRIR_RECEPCION.part{i}" for i in range(1, 5)], "sha256": sha(launcher), "encoding": "utf-8"},
            {"path": "update_manifest.json", "url": raw + "update_manifest.json", "sha256": sha(manifest_bytes), "encoding": "utf-8"},
        ],
    }
    (OUT / "candidate_latest.json").write_bytes(dump(candidate))
    print("BUILD_V4454_OK", sha(app), sha(app_base), sha(launcher))


if __name__ == "__main__":
    main()

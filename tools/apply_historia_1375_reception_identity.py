from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "historia-clinica" / "app" / "app.py"
VERSION = ROOT / "historia-clinica" / "app" / "historia-version.json"
MANIFEST = ROOT / "historia-clinica" / "app" / "update_manifest.json"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise RuntimeError(f"No se encontró bloque esperado: {label}")
    return text.replace(old, new, 1)


def apply() -> None:
    s = APP.read_text(encoding="utf-8")
    s = replace_once(
        s,
        '''            elif is_new:\n                action_label = "Revisar ficha"\n            else:\n                action_label = "Vincular ficha"\n''',
        '''            elif is_new:\n                action_label = "Revisar ficha"\n            else:\n                action_label = "Esperando Recepción"\n''',
        "acción de cola",
    )
    s = replace_once(
        s,
        '''            href = f"/cola/{e(r['id'])}/atender"\n''',
        '''            can_open = bool(r["clinical_patient_id"]) or is_new or r["status"] == "in_consultation"\n            href = f"/cola/{e(r['id'])}/atender" if can_open else "#"\n''',
        "enlace de cola",
    )
    s = replace_once(
        s,
        '''    next_row = next((r for r in queue if r["status"] == "waiting"), None)\n    if next_row is None:\n        next_row = next((r for r in queue), None)\n''',
        '''    eligible_queue = [\n        r for r in queue\n        if r["status"] == "in_consultation"\n        or bool(r["clinical_patient_id"])\n        or _queue_display_type(r) == "Nuevo"\n    ]\n    next_row = next((r for r in eligible_queue if r["status"] == "waiting"), None)\n    if next_row is None:\n        next_row = next((r for r in eligible_queue), None)\n''',
        "siguiente paciente",
    )
    s = replace_once(
        s,
        'APP_VERSION = "1.3.74"',
        'APP_VERSION = "1.3.75"',
        "versión app",
    )
    APP.write_text(s, encoding="utf-8")

    version = json.loads(VERSION.read_text(encoding="utf-8-sig"))
    version["version"] = "1.3.75"
    VERSION.write_text(json.dumps(version, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
    manifest["version"] = "1.3.75"
    manifest["app_version"] = "1.3.75"
    manifest["runtime_version"] = "1.3.75"
    notes = manifest.setdefault("notes", {})
    notes.update({
        "purpose": "Recepción pasa a resolver la identidad antes de enviar subsecuentes; Historia deja la vinculación manual fuera del flujo normal del doctor.",
        "previous_version": "1.3.74",
        "reception_identity_authority": True,
        "doctor_manual_link_normal_flow": False,
        "doctor_manual_link_emergency_fallback": True,
        "unlinked_subsequent_doctor_action_disabled": True,
        "next_patient_skips_unlinked_subsequent": True,
        "clinical_data_changes": False,
        "cloud_logic_changes": False,
        "printing_changes": False,
        "database_schema_changes": False,
        "patient_data_destructive_changes": False,
    })
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def verify() -> None:
    s = APP.read_text(encoding="utf-8")
    version = json.loads(VERSION.read_text(encoding="utf-8-sig"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
    assert 'APP_VERSION = "1.3.75"' in s
    assert 'action_label = "Esperando Recepción"' in s
    assert 'can_open = bool(r["clinical_patient_id"]) or is_new or r["status"] == "in_consultation"' in s
    assert 'eligible_queue = [' in s
    assert 'or _queue_display_type(r) == "Nuevo"' in s
    assert version["version"] == "1.3.75"
    assert manifest["version"] == manifest["app_version"] == manifest["runtime_version"] == "1.3.75"
    assert manifest["notes"]["reception_identity_authority"] is True
    assert manifest["notes"]["doctor_manual_link_normal_flow"] is False
    assert manifest["notes"]["doctor_manual_link_emergency_fallback"] is True
    assert manifest["notes"]["patient_data_destructive_changes"] is False
    assert '@app.get("/cola/{queue_id}/vincular/{patient_id}")' in s
    print("HISTORIA_1375_RECEPTION_IDENTITY_OK")


if __name__ == "__main__":
    apply()
    verify()

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "updates" / "v4_4_56_patient_validation_origin_fix"
OUT = ROOT / "updates" / "v4_4_57_consultation_turns"
VERSION = "4.4.57"


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise RuntimeError(msg)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dump(obj: dict) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


PY_HELPERS = '''\n\ndef _v4457_counts_as_medical_turn(v) -> bool:\n    """Un turno corresponde a una consulta médica, no a un procedimiento aislado."""\n    return not str(getattr(v, "procedimiento", None) or "").strip()\n\n\ndef _v4457_consultation_turns(patient_days: dict) -> dict:\n    """Numera solo paciente/día que tenga al menos una consulta médica."""\n    turns = {}\n    by_date = {}\n    for key, items in patient_days.items():\n        fecha, pid = key\n        consultation_ids = [\n            int(v.id) for v, _p in items\n            if _v4457_counts_as_medical_turn(v)\n        ]\n        if not consultation_ids:\n            turns[(fecha, pid)] = None\n            continue\n        by_date.setdefault(fecha, []).append((min(consultation_ids), pid))\n    for fecha, items in by_date.items():\n        for n, (_first_id, pid) in enumerate(sorted(items), 1):\n            turns[(fecha, pid)] = n\n    return turns\n'''

JS_HELPER = '''  function v4457ConsultationTurnMap(groups){\n    const map=new Map();let turn=0;\n    [...(groups||[])].reverse().forEach(g=>{\n      if((g?.visits||[]).some(v=>!String(v?.procedimiento||'').trim()))map.set(g,++turn);\n    });\n    return map;\n  }\n'''


def main() -> None:
    app_text = (SOURCE / "app.py").read_text(encoding="utf-8-sig")
    require('APP_VERSION = "4.4.56"' in app_text, "La base app no es 4.4.56")
    app_text = app_text.replace('APP_VERSION = "4.4.56"', 'APP_VERSION = "4.4.57"', 1)
    app_text = app_text.replace("const VERSION='4.4.56';", "const VERSION='4.4.57';")
    compile(app_text, "app.py", "exec")

    base_text = (SOURCE / "app_base_4428.py").read_text(encoding="utf-8-sig").replace("\r\n", "\n")

    # Backend/reportes: construir la numeración únicamente con consultas médicas.
    report_marker = '\n\ndef build_report_data(rows):\n'
    require(base_text.count(report_marker) == 1, "No se encontró exactamente un build_report_data")
    base_text = base_text.replace(report_marker, PY_HELPERS + report_marker, 1)

    old_turn_block = '''    turns = {}\n    by_date = {}\n    for key, items in patient_days.items():\n        fecha, pid = key\n        first_id = min(v.id for v, _ in items)\n        by_date.setdefault(fecha, []).append((first_id, pid))\n    for fecha, items in by_date.items():\n        for n, (_, pid) in enumerate(sorted(items), 1):\n            turns[(fecha, pid)] = n\n'''
    require(base_text.count(old_turn_block) == 1, "No se encontró el bloque estable de numeración de turnos")
    base_text = base_text.replace(old_turn_block, '    turns = _v4457_consultation_turns(patient_days)\n', 1)

    # Inicio: mantener todos los pacientes/procedimientos visibles, pero el N.º
    # se calcula solo para grupos que contienen al menos una consulta.
    ui_marker = '  function remasterHomeTable(rows){\n'
    require(base_text.count(ui_marker) == 1, "No se encontró remasterHomeTable")
    base_text = base_text.replace(ui_marker, JS_HELPER + ui_marker, 1)

    old_groups = "    const groups=groupHomeVisits(rows);const head='<tr><th class=\"number-col\">N.º</th><th>Paciente</th><th>Atención</th><th>Valor</th><th class=\"home-actions-col\">Acciones</th></tr>';"
    new_groups = "    const groups=groupHomeVisits(rows),turnMap=v4457ConsultationTurnMap(groups);const head='<tr><th class=\"number-col\">N.º</th><th>Paciente</th><th>Atención</th><th>Valor</th><th class=\"home-actions-col\">Acciones</th></tr>';"
    require(base_text.count(old_groups) == 1, "No se encontró cabecera estable de la tabla Inicio")
    base_text = base_text.replace(old_groups, new_groups, 1)

    require(base_text.count('num=groups.length-index,fecha=') == 1, "No se encontró cálculo visual de turno anterior")
    base_text = base_text.replace('num=groups.length-index,fecha=', 'num=turnMap.get(g)||null,fecha=', 1)

    old_num = '<td class="row-number" rowspan="${1+extras.length}">${num}.</td>'
    new_num = '<td class="row-number" rowspan="${1+extras.length}">${num?num+\'.\':\'—\'}</td>'
    require(base_text.count(old_num) == 1, "No se encontró celda visual de N.º")
    base_text = base_text.replace(old_num, new_num, 1)

    # Mantener la corrección 4.4.56: fecha de nacimiento llega como texto antes
    # del normalizador y el resto de la base permanece idéntico salvo el turno.
    require('fecha_nacimiento: Optional[str] = None' in base_text, "Se perdió PatientIn robusto de 4.4.56")
    require('values["fecha_nacimiento"] = date.fromisoformat' in base_text, "Se perdió conversión final de nacimiento")
    compile(base_text, "app_base_4428.py", "exec")

    app = app_text.encode("utf-8")
    app_base = base_text.encode("utf-8")
    launcher_parts = [(SOURCE / f"ABRIR_RECEPCION.part{i}").read_bytes() for i in range(1, 5)]
    launcher = b"".join(launcher_parts)
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

    raw = "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_57_consultation_turns/"
    candidate = {
        "product": "recepcion-pacientes",
        "version": VERSION,
        "app_version": VERSION,
        "runtime_version": VERSION,
        "mandatory": True,
        "channel": "files-v3",
        "message": "v4.4.57: los turnos se numeran solo por consultas médicas. Los procedimientos aislados siguen visibles pero no consumen N.º; consulta + procedimientos cuenta un único turno. Reportes usan la misma regla. Conserva todo v4.4.56.",
        "files": [
            {"path": "app.py", "url": raw + "app.py", "sha256": sha(app), "encoding": "utf-8"},
            {"path": "app_base_4428.py", "url": raw + "app_base_4428.py", "sha256": sha(app_base), "encoding": "utf-8"},
            {"path": "ABRIR_RECEPCION.py", "parts": [raw + f"ABRIR_RECEPCION.part{i}" for i in range(1, 5)], "sha256": sha(launcher), "encoding": "utf-8"},
            {"path": "update_manifest.json", "url": raw + "update_manifest.json", "sha256": sha(manifest_bytes), "encoding": "utf-8"},
        ],
    }
    (OUT / "candidate_latest.json").write_bytes(dump(candidate))
    print("BUILD_V4457_OK", sha(app), sha(app_base), sha(launcher))


if __name__ == "__main__":
    main()

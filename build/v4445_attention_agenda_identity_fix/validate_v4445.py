from __future__ import annotations

import ast
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "updates" / "v4_4_45_attention_agenda_identity_fix"
SOURCE_REF = "5789f783702ce69769e139b63ecfeacdd0849605"
SOURCE_PREFIX = "updates/v4_4_43_daily_emitted_whatsapp_schedule"
STABLE = {
    "ABRIR_RECEPCION.py": "39ee0e178c9f86387b220905f2f8612f6c61e721a928fd8ed3ca514a639b007e",
    "app_base_4428.py": "e5d3d96b9289169aa52524e8cc2f5f0ec9567c8da5e11d482151b12fc8ff85ba",
    "static/app.js": "0657c3b76721df2e28ec812856a2fc25944d2908382b13fbf3f115dad3e18d90",
    "static/index.html": "16d30060a0be19215e612c4ba897e801873dd359712e90d4dc14e32513b25728",
}


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_bytes(path: str) -> bytes:
    return subprocess.check_output(["git", "show", f"{SOURCE_REF}:{SOURCE_PREFIX}/{path}"], cwd=ROOT)


def build() -> None:
    subprocess.run([sys.executable, str(HERE / "build_v4445.py")], cwd=ROOT, check=True)


def stable_scope() -> None:
    # Demuestra que la actualización parte de los mismos bytes estables y que el
    # canal 4.4.45 ni siquiera intenta reemplazarlos.
    launcher = b"".join(git_bytes(f"ABRIR_RECEPCION.part{i}") for i in range(1, 5))
    require(sha(launcher) == STABLE["ABRIR_RECEPCION.py"], "Launcher estable cambió")
    for path in ("app_base_4428.py", "static/app.js", "static/index.html"):
        require(sha(git_bytes(path)) == STABLE[path], f"Fuente estable cambió: {path}")

    candidate = json.loads((OUT / "candidate_latest.json").read_text(encoding="utf-8"))
    paths = [x.get("path") for x in candidate.get("files", [])]
    require(paths == ["app.py", "update_manifest.json"], f"Alcance no mínimo: {paths}")
    forbidden = {"ABRIR_RECEPCION.py", "app_base_4428.py", "static/app.js", "static/index.html", ".env"}
    require(not (forbidden & set(paths)), f"La actualización intenta tocar archivos estables: {forbidden & set(paths)}")
    print("V4445_STABLE_SCOPE_OK", paths)


def contracts() -> None:
    app_path = OUT / "app.py"
    app = app_path.read_text(encoding="utf-8")
    compile(app, "app.py", "exec")
    for marker in (
        'APP_VERSION = "4.4.45"',
        '/api/agenda/appointments/guarded',
        'Agendar de todas formas',
        '_v4445_sync_cloud_agenda_for_dates',
        'core.queue_count() > 0',
        'core.mirror_patient_to_local(patient)',
        'core.mirror_appointment_to_local(appointment)',
        'core.ConfirmafyAgendaItem.source_hash == source_hash',
        'window.__v4445StagedIdentityFix',
        'Encontramos una ficha con este celular',
        'Usar esta ficha',
        'usePatientForStaged',
        'v4445CreateDifferentStaged',
    ):
        require(marker in app, f"Falta contrato: {marker}")

    # El bloque nuevo no puede incluir DDL ni mecanismos de borrado de pacientes.
    feature_start = app.index("# v4.4.45 — Agenda Cloud completa")
    feature_end = app.index("FEATURE_BOOT_OK = True", feature_start)
    feature = app[feature_start:feature_end]
    require("CREATE TABLE" not in feature.upper(), "El parche intenta crear tablas")
    require("DROP TABLE" not in feature.upper(), "El parche intenta borrar tablas")
    require("db.delete(" not in feature and "ldb.delete(" not in feature, "El parche intenta borrar filas")

    manifest = json.loads((OUT / "update_manifest.json").read_text(encoding="utf-8"))
    candidate = json.loads((OUT / "candidate_latest.json").read_text(encoding="utf-8"))
    require(manifest.get("version") == "4.4.45", "Manifest con versión incorrecta")
    require(candidate.get("version") == "4.4.45", "Candidate con versión incorrecta")
    require(manifest.get("copy") == ["app.py", "update_manifest.json"], "Manifest toca archivos de más")
    require(manifest.get("required_dependencies") == ["app_base_4428.py"], "Se perdió dependencia base")
    require(manifest.get("required_python_packages") == [{"import": "pg8000", "pip": "pg8000==1.31.2"}], "Se perdió guardia pg8000")

    by_path = {x["path"]: x for x in candidate["files"]}
    require(by_path["app.py"]["sha256"] == sha(app_path.read_bytes()), "SHA app.py incorrecto")
    require(by_path["update_manifest.json"]["sha256"] == sha((OUT / "update_manifest.json").read_bytes()), "SHA manifest incorrecto")
    print("V4445_CONTRACT_OK")


def js_syntax() -> None:
    tree = ast.parse((OUT / "app.py").read_text(encoding="utf-8"))
    script = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            if any(isinstance(t, ast.Name) and t.id == "V4445_STAGED_IDENTITY_JS" for t in node.targets):
                script = node.value.value
                break
    require(bool(script), "No se encontró V4445_STAGED_IDENTITY_JS")
    with tempfile.TemporaryDirectory() as td:
        js = pathlib.Path(td) / "v4445.js"
        js.write_text(script, encoding="utf-8")
        result = subprocess.run(["node", "--check", str(js)], text=True, capture_output=True)
        if result.returncode:
            print(result.stdout)
            print(result.stderr)
        require(result.returncode == 0, "JavaScript v4.4.45 no compila")
    print("V4445_JS_SYNTAX_OK")


def main() -> None:
    build()
    stable_scope()
    contracts()
    js_syntax()
    print("VALIDATE_V4445_OK")


if __name__ == "__main__":
    main()

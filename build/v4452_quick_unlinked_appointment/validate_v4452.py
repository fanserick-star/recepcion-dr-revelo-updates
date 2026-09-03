from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "updates" / "v4_4_52_quick_unlinked_appointment"
SOURCE = ROOT / "updates" / "v4_4_51_payment_source_of_truth"
VERSION = "4.4.52"

sys.path.insert(0, str(ROOT / "build" / "v4449_agenda_flow_speed"))
import validate_v4449 as legacy_helpers


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def launcher_bytes(folder: pathlib.Path) -> bytes:
    return b"".join((folder / f"ABRIR_RECEPCION.part{i}").read_bytes() for i in range(1, 5))


def build() -> None:
    subprocess.run([sys.executable, str(HERE / "build_v4452.py")], cwd=ROOT, check=True)


def contracts() -> None:
    app = (OUT / "app.py").read_text(encoding="utf-8-sig")
    base = (OUT / "app_base_4428.py").read_text(encoding="utf-8-sig")
    launcher = launcher_bytes(OUT).decode("utf-8-sig")
    compile(app, "app.py", "exec")
    compile(base, "app_base_4428.py", "exec")
    compile(launcher, "ABRIR_RECEPCION.py", "exec")

    markers = (
        'APP_VERSION = "4.4.52"',
        'class V4452QuickAppointmentIn',
        '/api/agenda/unlinked/guarded',
        'crear_cita_rapida_sin_ficha',
        'confirmafy_staged.create',
        'pc:quick:',
        '_v4444_same_week_conflict',
        'appointment_conflicts',
        'window.__v4452QuickUnlinkedAppointment',
        '＋ Crear cita nueva',
        'no crea una ficha de paciente',
        'v4452SaveQuickAppointment',
        'window.__v4451PaymentSourceOfTruth',
        'window.__v4450PatientCacheIdentity',
        '/api/agenda/appointments/guarded',
    )
    for marker in markers:
        require(marker in app, f"Falta contrato v4.4.52: {marker}")

    # El endpoint nuevo no debe crear Patient: solo ConfirmafyAgendaItem.
    start = app.index('class V4452QuickAppointmentIn')
    end = app.index('V4452_QUICK_APPOINTMENT_JS = r"""', start)
    backend_patch = app[start:end]
    require('core.ConfirmafyAgendaItem(' in backend_patch, "No se crea cita staged")
    require('core.Patient(' not in backend_patch, "Nueva cita no debe crear ficha Patient")
    require('core.add_queue(' in backend_patch and 'confirmafy_staged.create' in backend_patch, "Falta cola offline staged")
    require('core.schedule_whatsapp_for_contact(' in backend_patch, "Falta flujo WhatsApp para cita staged")

    # Sintaxis del JS nuevo.
    js_start = app.index('V4452_QUICK_APPOINTMENT_JS = r"""') + len('V4452_QUICK_APPOINTMENT_JS = r"""')
    js_end = app.index('\n"""\n\n    V4452_QUICK_APPOINTMENT_CSS', js_start)
    js = app[js_start:js_end]
    with tempfile.TemporaryDirectory() as td:
        path = pathlib.Path(td) / "v4452.js"
        path.write_text(js, encoding="utf-8", newline="")
        proc = subprocess.run(["node", "--check", str(path)], text=True, capture_output=True)
        require(proc.returncode == 0, f"JS v4.4.52 inválido: {proc.stderr}")

    manifest = json.loads((OUT / "update_manifest.json").read_text(encoding="utf-8"))
    candidate = json.loads((OUT / "candidate_latest.json").read_text(encoding="utf-8"))
    expected = ["app.py", "app_base_4428.py", "ABRIR_RECEPCION.py", "update_manifest.json"]
    require(manifest.get("version") == VERSION, "Manifest incorrecto")
    require(manifest.get("required_dependencies") == ["app_base_4428.py"], "Dependencia obligatoria incompleta")
    require(manifest.get("copy") == expected, "Manifest copy incompleto")
    require([x.get("path") for x in candidate.get("files", [])] == expected, "Candidate incompleto")

    # Base y launcher deben seguir exactamente los de 4.4.51.
    source_base = (SOURCE / "app_base_4428.py").read_text(encoding="utf-8-sig").replace("\r\n", "\n").encode("utf-8")
    require((OUT / "app_base_4428.py").read_bytes() == source_base, "La base estable cambió")
    require(launcher_bytes(OUT) == launcher_bytes(SOURCE), "El launcher cambió")
    print("V4452_CONTRACT_OK")


def legacy_acceptance() -> None:
    candidate = json.loads((OUT / "candidate_latest.json").read_text(encoding="utf-8"))
    server, base = legacy_helpers.start_server()
    try:
        server.RequestHandlerClass.files = legacy_helpers.localize_candidate(candidate, OUT, base)
        with tempfile.TemporaryDirectory() as td:
            temp = pathlib.Path(td)
            install = temp / "install"
            sentinels = legacy_helpers.seed_legacy_install(install)
            legacy = legacy_helpers.legacy_module(temp)
            result = legacy.check_and_apply_update(
                install, base + "/manifest", attempts=1, timeout=8, allow_test_sources=True
            )
            require(result.get("ok") and result.get("updated"), f"Updater 4.4.43 rechazó v4.4.52: {result}")
            require(legacy._local_package_version(install) == VERSION, "Manifest final incorrecto")
            require(legacy._installed_app_version(install) == VERSION, "app final incorrecta")
            require(legacy._installation_consistent(install), "Instalación incoherente")
            for path, data in sentinels.items():
                require(path.read_bytes() == data, f"Se alteró archivo protegido: {path.name}")
    finally:
        server.shutdown()
        server.server_close()
    print("V4452_ACCEPTED_BY_LEGACY_443")


def launcher_selftests() -> None:
    with tempfile.TemporaryDirectory() as td:
        path = pathlib.Path(td) / "ABRIR_RECEPCION.py"
        path.write_bytes(launcher_bytes(OUT))
        proc = subprocess.run(
            [sys.executable, str(path), "--self-test-core"],
            cwd=td, text=True, capture_output=True, timeout=100,
        )
        require(proc.returncode == 0, f"Launcher self-test falló: {proc.stdout}\n{proc.stderr}")
        require("SELFTEST OK:" in proc.stdout, "Launcher no reportó SELFTEST OK")
    print("V4452_LAUNCHER_SELFTESTS_OK")


def main() -> None:
    build()
    contracts()
    legacy_acceptance()
    launcher_selftests()
    print("VALIDATE_V4452_OK")


if __name__ == "__main__":
    main()

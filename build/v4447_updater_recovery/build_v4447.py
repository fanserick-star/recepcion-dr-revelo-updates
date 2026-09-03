from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "updates" / "v4_4_46_phone_guard"
LAUNCHER_SOURCE = ROOT / "updates" / "v4_4_43_daily_emitted_whatsapp_schedule"
OUT = ROOT / "updates" / "v4_4_47_updater_recovery"
VERSION = "4.4.47"
LAUNCHER_VERSION = "4.4.47-update-before-focus-1"


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise RuntimeError(msg)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dump(obj: dict) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def split_text(text: str, count: int = 4) -> list[str]:
    n = len(text)
    cuts = [round(n * i / count) for i in range(count + 1)]
    return [text[cuts[i]:cuts[i + 1]] for i in range(count)]


def build_app() -> bytes:
    text = (SOURCE / "app.py").read_text(encoding="utf-8-sig")
    require('APP_VERSION = "4.4.46"' in text, "La base app no es 4.4.46")
    text = text.replace('APP_VERSION = "4.4.46"', 'APP_VERSION = "4.4.47"', 1)
    text = text.replace("const VERSION='4.4.46';", "const VERSION='4.4.47';")
    compile(text, "app.py", "exec")
    for marker in (
        '/api/agenda/appointments/guarded',
        'window.__v4445StagedIdentityFix',
        '/api/identity/phone-owner',
        'window.__v4446PhoneDuplicateGuard',
        'stopIfDuplicate',
        'Este celular ya está registrado',
    ):
        require(marker in text, f"Se perdió arreglo acumulativo: {marker}")
    return text.encode("utf-8")


def build_launcher() -> bytes:
    parts = [(LAUNCHER_SOURCE / f"ABRIR_RECEPCION.part{i}").read_text(encoding="utf-8-sig") for i in range(1, 5)]
    text = "".join(parts)
    require('LAUNCHER_VERSION = "4.4.42-dynamic-port-file-python-dependency-guard-1"' in text, "Launcher base inesperado")
    text = text.replace(
        'LAUNCHER_VERSION = "4.4.42-dynamic-port-file-python-dependency-guard-1"',
        f'LAUNCHER_VERSION = "{LAUNCHER_VERSION}"',
        1,
    )

    old = '''def main() -> None:\n    _set_windows_identity()\n    _choose_app_port()\n\n    # Protección doble: mutex mientras el launcher/WebView está vivo y detección\n    # de ventana para el caso excepcional de fallback Edge.\n    if _running_version(timeout=0.45) is not None and _focus_existing_window():\n        return\n\n    handle, already = _acquire_mutex()\n    if already:\n        _focus_existing_window()\n        _release_mutex(handle)\n        return\n\n    splash = Splash()\n'''
    new = '''def main() -> None:\n    _set_windows_identity()\n    _choose_app_port()\n\n    # v4.4.47: el mutex sigue evitando dos launchers simultáneos, pero YA NO\n    # reutilizamos/focalizamos una ventana antes de comprobar actualizaciones.\n    # El backend queda vivo al cerrar WebView; el atajo antiguo podía encontrar\n    # esa sesión 4.4.43 y salir antes de consultar latest-v3.json, dejando la PC\n    # atrapada indefinidamente en una versión vieja.\n    handle, already = _acquire_mutex()\n    if already:\n        _focus_existing_window()\n        _release_mutex(handle)\n        return\n\n    splash = Splash()\n'''
    require(old in text, "No se encontró el atajo viejo antes del actualizador")
    text = text.replace(old, new, 1)

    old_expected = '''        expected = _expected_app_version(ROOT)\n        current = _running_version()\n        if current != expected:\n'''
    new_expected = '''        expected = _expected_app_version(ROOT)\n        current = _running_version()\n\n        # Reutilizar una ventana existente sigue siendo válido, pero únicamente\n        # DESPUÉS de consultar/aplicar el canal. Así una sesión vieja nunca puede\n        # impedir que se instale una versión más nueva.\n        if current == expected and _focus_existing_window():\n            return\n\n        if current != expected:\n'''
    require(old_expected in text, "No se encontró el bloque expected/current")
    text = text.replace(old_expected, new_expected, 1)

    compile(text, "ABRIR_RECEPCION.py", "exec")
    main = text[text.index("def main() -> None:"):text.index("\ndef _selftest_mutex_holder", text.index("def main() -> None:"))]
    require(main.index("result = check_and_apply_update(ROOT)") < main.index("if current == expected and _focus_existing_window()"), "El foco sigue antes del update")
    before_update = main[:main.index("result = check_and_apply_update(ROOT)")]
    require("_focus_existing_window()" not in before_update.split("if already:", 1)[-1], "Hay un foco prematuro después de adquirir mutex")
    return text.encode("utf-8")


def main() -> None:
    app = build_app()
    launcher = build_launcher()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "app.py").write_bytes(app)

    launch_text = launcher.decode("utf-8")
    parts = split_text(launch_text, 4)
    for i, part in enumerate(parts, 1):
        (OUT / f"ABRIR_RECEPCION.part{i}").write_text(part, encoding="utf-8", newline="")
    rebuilt = b"".join((OUT / f"ABRIR_RECEPCION.part{i}").read_bytes() for i in range(1, 5))
    require(rebuilt == launcher, "Las partes no reconstruyen exactamente el launcher")

    manifest = {
        "product": "recepcion-pacientes",
        "version": VERSION,
        "app_version": VERSION,
        "runtime_version": VERSION,
        "launcher_version": LAUNCHER_VERSION,
        "updater_version": "integrado-en-launcher-update-before-focus",
        "required_dependencies": ["app_base_4428.py"],
        "required_python_packages": [{"import": "pg8000", "pip": "pg8000==1.31.2"}],
        "copy": ["app.py", "ABRIR_RECEPCION.py", "update_manifest.json"],
    }
    manifest_bytes = dump(manifest)
    (OUT / "update_manifest.json").write_bytes(manifest_bytes)

    raw = "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_47_updater_recovery/"
    candidate = {
        "product": "recepcion-pacientes",
        "version": VERSION,
        "app_version": VERSION,
        "runtime_version": VERSION,
        "mandatory": True,
        "channel": "files-v3",
        "message": (
            "v4.4.47: corrige el actualizador que podía quedarse atrapado en 4.4.43 cuando el backend anterior seguía vivo. "
            "Ahora siempre comprueba y aplica la actualización antes de reutilizar una ventana existente. Conserva todos los arreglos 4.4.46 de Agenda Cloud/WhatsApp, identidad por celular y protección semanal. "
            "No modifica .env, data, SQLite, Excel ni la base estable."
        ),
        "files": [
            {"path": "app.py", "url": raw + "app.py", "sha256": sha(app), "encoding": "utf-8"},
            {
                "path": "ABRIR_RECEPCION.py",
                "parts": [raw + f"ABRIR_RECEPCION.part{i}" for i in range(1, 5)],
                "sha256": sha(launcher),
                "encoding": "utf-8",
            },
            {"path": "update_manifest.json", "url": raw + "update_manifest.json", "sha256": sha(manifest_bytes), "encoding": "utf-8"},
        ],
    }
    (OUT / "candidate_latest.json").write_bytes(dump(candidate))
    print("BUILD_V4447_OK", sha(app), sha(launcher))


if __name__ == "__main__":
    main()

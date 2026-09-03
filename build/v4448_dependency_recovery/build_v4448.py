from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "updates" / "v4_4_47_updater_recovery"
LEGACY = ROOT / "updates" / "v4_4_43_daily_emitted_whatsapp_schedule"
OUT = ROOT / "updates" / "v4_4_48_dependency_recovery"
VERSION = "4.4.48"
LAUNCHER_VERSION = "4.4.48-update-before-focus-dependency-safe-1"


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
    require('APP_VERSION = "4.4.47"' in text, "La base app no es 4.4.47")
    text = text.replace('APP_VERSION = "4.4.47"', 'APP_VERSION = "4.4.48"', 1)
    text = text.replace("const VERSION='4.4.47';", "const VERSION='4.4.48';")
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
    text = "".join(
        (SOURCE / f"ABRIR_RECEPCION.part{i}").read_text(encoding="utf-8-sig")
        for i in range(1, 5)
    )
    require(
        'LAUNCHER_VERSION = "4.4.47-update-before-focus-1"' in text,
        "Launcher base 4.4.47 inesperado",
    )
    text = text.replace(
        'LAUNCHER_VERSION = "4.4.47-update-before-focus-1"',
        f'LAUNCHER_VERSION = "{LAUNCHER_VERSION}"',
        1,
    )
    compile(text, "ABRIR_RECEPCION.py", "exec")
    main = text[
        text.index("def main() -> None:"):
        text.index("\ndef _selftest_mutex_holder", text.index("def main() -> None:"))
    ]
    require(
        main.index("result = check_and_apply_update(ROOT)")
        < main.index("if current == expected and _focus_existing_window()"),
        "Se perdió update-before-focus",
    )
    return text.encode("utf-8")


def main() -> None:
    app = build_app()
    launcher = build_launcher()
    app_base = (LEGACY / "app_base_4428.py").read_bytes()
    compile(app_base.decode("utf-8-sig"), "app_base_4428.py", "exec")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "app.py").write_bytes(app)
    (OUT / "app_base_4428.py").write_bytes(app_base)

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
        "copy": ["app.py", "app_base_4428.py", "ABRIR_RECEPCION.py", "update_manifest.json"],
    }
    manifest_bytes = dump(manifest)
    (OUT / "update_manifest.json").write_bytes(manifest_bytes)

    raw = "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_48_dependency_recovery/"
    candidate = {
        "product": "recepcion-pacientes",
        "version": VERSION,
        "app_version": VERSION,
        "runtime_version": VERSION,
        "mandatory": True,
        "channel": "files-v3",
        "message": (
            "v4.4.48: paquete de recuperación compatible con el actualizador 4.4.43. "
            "Incluye explícitamente app_base_4428.py junto con app.py, el launcher reparado y el manifest, "
            "porque el actualizador antiguo rechaza cualquier app.py cuya dependencia local no venga en el mismo paquete. "
            "Conserva todos los arreglos funcionales de 4.4.47 y no modifica .env, data, SQLite ni Excel."
        ),
        "files": [
            {"path": "app.py", "url": raw + "app.py", "sha256": sha(app), "encoding": "utf-8"},
            {"path": "app_base_4428.py", "url": raw + "app_base_4428.py", "sha256": sha(app_base), "encoding": "utf-8"},
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
    print("BUILD_V4448_OK", sha(app), sha(app_base), sha(launcher))


if __name__ == "__main__":
    main()

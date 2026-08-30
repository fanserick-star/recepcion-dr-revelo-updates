from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSION = "4.4.6"
STABLE_VERSION = "4.3.64"
STABLE_SHA256 = "33ba932ef73ae28722c5f8f1a75d439a82cfb4a67adb78d837430522b786f9a8"
PART_SIZE = 70000
OUT = ROOT / "updates" / "v4_4_6_recovery"
BASE_ZIP = ROOT / "installer_clean" / "base" / "clean_base_resources.zip"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stable_app_bytes() -> bytes:
    src = ROOT / "updates" / "v464"
    parts = sorted(src.glob("app.part*"), key=lambda p: int(p.name.split("part")[-1]))
    if len(parts) != 7:
        raise SystemExit(f"v4.3.64 incompleta: se esperaban 7 partes y hay {len(parts)}")
    raw = b"".join(p.read_bytes() for p in parts)
    got = hashlib.sha256(raw).hexdigest()
    if got != STABLE_SHA256:
        raise SystemExit(f"La v4.3.64 estable cambió: {got}")
    return raw


def bump_only_version(raw: bytes) -> bytes:
    s = raw.decode("utf-8")

    # APP_VERSION es el único identificador imprescindible para el backend y el
    # actualizador. Los demás identificadores visuales pueden tener espacios o
    # comillas distintas según la etapa de build, por eso se cambian por patrón.
    s, n_app = re.subn(r'APP_VERSION\s*=\s*["\']4\.3\.64["\']', 'APP_VERSION = "4.4.6"', s, count=1)
    if n_app != 1:
        raise SystemExit(f"APP_VERSION 4.3.64 aparece {n_app} veces")

    s, n_badge = re.subn(
        r'(const\s+VERSION\s*=\s*)["\']4\.3\.64["\']',
        r"\1'4.4.6'",
        s,
        count=1,
    )
    s = s.replace('/v460/overlay.css?v=4.3.64', '/v460/overlay.css?v=4.4.6')
    s = s.replace('/v460/overlay.js?v=4.3.64', '/v460/overlay.js?v=4.4.6')
    print('VERSION_PATCH', {'app': n_app, 'badge': n_badge})

    # No se permite arrastrar la limpieza 4.4.3 que originó las regresiones.
    forbidden = ["attention-agenda-only", "V443_CLEANUP_JS", "V443_CLEANUP_CSS"]
    for token in forbidden:
        if token in s:
            raise SystemExit(f"La recuperación contiene un marcador 4.4.3 prohibido: {token}")

    # Señales de la rama funcional que el usuario había probado.
    required = ["V459_SETTINGS_JS", "whatsapp", "agenda", "openLinkedAgendaDetail"]
    low = s.lower()
    for token in required:
        if token.lower() not in low:
            raise SystemExit(f"La v4.3.64 estable no contiene la función esperada: {token}")
    return s.encode("utf-8")


def find_pristine_static() -> tuple[Path, Path, Path]:
    if not BASE_ZIP.exists():
        raise SystemExit("No existe clean_base_resources.zip")
    temp = Path(tempfile.mkdtemp(prefix="rp_recovery_"))
    with zipfile.ZipFile(BASE_ZIP) as z:
        z.extractall(temp)

    indexes = sorted(temp.rglob("static/index.html"), key=lambda p: (len(p.parts), str(p)))
    scripts = sorted(temp.rglob("static/app.js"), key=lambda p: (len(p.parts), str(p)))
    if not indexes or not scripts:
        listing = "\n".join(str(p.relative_to(temp)) for p in temp.rglob("*") if p.is_file())
        raise SystemExit("El ZIP base no contiene static/index.html y static/app.js.\n" + listing[:5000])
    return temp, indexes[0], scripts[0]


def write_parts(data: bytes) -> list[Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("app.part*"):
        old.unlink()
    paths = []
    for n, start in enumerate(range(0, len(data), PART_SIZE), 1):
        p = OUT / f"app.part{n}"
        p.write_bytes(data[start:start + PART_SIZE])
        paths.append(p)
    return paths


def file_entry(path: str, local: Path) -> dict:
    return {
        "path": path,
        "url": f"https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_6_recovery/{local.relative_to(OUT).as_posix()}",
        "sha256": sha256(local),
        "encoding": "utf-8",
    }


def main() -> None:
    raw = stable_app_bytes()
    recovered = bump_only_version(raw)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "static").mkdir(parents=True, exist_ok=True)
    parts = write_parts(recovered)

    temp, pristine_index, pristine_js = find_pristine_static()
    try:
        shutil.copy2(pristine_index, OUT / "static" / "index.html")
        shutil.copy2(pristine_js, OUT / "static" / "app.js")
    finally:
        shutil.rmtree(temp, ignore_errors=True)

    # app_base.js fue introducido por los hotfix 4.4.x. Se sobrescribe con un
    # archivo inerte para impedir que una referencia residual ejecute otra UI.
    (OUT / "static" / "app_base.js").write_text(
        "// v4.4.6 recovery: archivo legado neutralizado; la interfaz usa /static/app.js.\n",
        encoding="utf-8",
    )

    manifest = {
        "product": "recepcion-pacientes",
        "version": VERSION,
        "app_version": VERSION,
        "runtime_version": VERSION,
        "launcher_version": "4.3.100-standalone-7",
        "updater_version": "integrado-en-launcher",
        "copy": [
            "ABRIR_RECEPCION.py",
            "app.py",
            "static/index.html",
            "static/app.js",
            "static/app_base.js",
            "update_manifest.json",
        ],
    }
    manifest_path = OUT / "update_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    current = json.loads((ROOT / "latest-v3.json").read_text(encoding="utf-8"))
    launcher = next((x for x in current.get("files", []) if x.get("path") == "ABRIR_RECEPCION.py"), None)
    if not launcher:
        raise SystemExit("El canal actual no contiene launcher; recuperación detenida")

    app_entry = {
        "path": "app.py",
        "parts": [
            f"https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_6_recovery/{p.name}"
            for p in parts
        ],
        "sha256": hashlib.sha256(recovered).hexdigest(),
        "encoding": "utf-8",
    }
    files = [
        launcher,
        app_entry,
        file_entry("static/index.html", OUT / "static" / "index.html"),
        file_entry("static/app.js", OUT / "static" / "app.js"),
        file_entry("static/app_base.js", OUT / "static" / "app_base.js"),
        file_entry("update_manifest.json", manifest_path),
    ]

    latest = {
        "product": "recepcion-pacientes",
        "version": VERSION,
        "app_version": VERSION,
        "runtime_version": VERSION,
        "mandatory": True,
        "channel": "files-v3",
        "message": "v4.4.6 recuperación limpia: restaura la base estable v4.3.64 y los archivos visuales originales para eliminar la mezcla de versiones en Atención, Agenda y WhatsApp.",
        "files": files,
    }
    payload = json.dumps(latest, ensure_ascii=False, indent=2) + "\n"
    (ROOT / "latest-v3.json").write_text(payload, encoding="utf-8")
    (ROOT / "latest.json").write_text(payload, encoding="utf-8")

    meta = {
        "version": VERSION,
        "source_version": STABLE_VERSION,
        "source_sha256": STABLE_SHA256,
        "recovered_app_sha256": hashlib.sha256(recovered).hexdigest(),
        "parts_count": len(parts),
        "pristine_index_sha256": sha256(OUT / "static" / "index.html"),
        "pristine_app_js_sha256": sha256(OUT / "static" / "app.js"),
    }
    (OUT / "recovery_meta.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("RECOVERY_V446_BUILT", json.dumps(meta, sort_keys=True))


if __name__ == "__main__":
    main()

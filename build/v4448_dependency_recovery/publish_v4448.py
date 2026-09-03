from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "updates" / "v4_4_48_dependency_recovery"
VERSION = "4.4.48"

sys.path.insert(0, str(HERE))
import validate_v4448 as validation


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise RuntimeError(msg)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def version_tuple(value: object) -> tuple[int, ...]:
    out = []
    for part in str(value or "0").split("."):
        try:
            out.append(int(part))
        except Exception:
            out.append(0)
    return tuple((out + [0, 0, 0, 0])[:4])


def git(*args: str) -> None:
    subprocess.run(["git", *args], cwd=ROOT, check=True)


def fetch(url: str, attempts: int = 4, timeout: float = 25.0) -> bytes:
    last = None
    for i in range(max(1, attempts)):
        try:
            sep = "&" if "?" in url else "?"
            req = urllib.request.Request(
                url + sep + "rp=" + str(time.time_ns()),
                headers={
                    "Cache-Control": "no-cache",
                    "Pragma": "no-cache",
                    "User-Agent": "v4448-legacy-recovery-release",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as r:
                require(getattr(r, "status", 200) == 200, f"HTTP {getattr(r, 'status', '?')}")
                return r.read()
        except Exception as exc:
            last = exc
            if i + 1 < attempts:
                time.sleep(min(4.0, 0.6 + i * 0.6))
    raise RuntimeError(f"No se pudo descargar {url}: {last}")


def wait_payload(item: dict, attempts: int = 50) -> bytes:
    last = None
    for i in range(attempts):
        try:
            urls = item.get("parts") or [item.get("url")]
            data = b"".join(fetch(str(u), attempts=1) for u in urls if u)
            if sha(data) == str(item.get("sha256") or ""):
                return data
            last = f"sha {sha(data)}"
        except Exception as exc:
            last = exc
        time.sleep(min(5.0, 0.8 + i * 0.18))
    raise RuntimeError(f"Payload Raw no propagó {item.get('path')}: {last}")


def raw_legacy_acceptance(candidate: dict) -> None:
    # Esta es la barrera que faltaba en publicaciones anteriores: usa el código
    # del updater 4.4.43 real contra los bytes Raw reales que recibirá la PC.
    with tempfile.TemporaryDirectory() as td:
        temp = pathlib.Path(td)
        install = temp / "install"
        sentinels = validation.seed_legacy_install(install)
        legacy = validation.load_legacy_module(temp)
        result = legacy._apply_remote(candidate, install, attempts=3, timeout=25, allow_test_sources=False)
        require(legacy._local_package_version(install) == VERSION, "Updater 4.4.43 no dejó manifest 4.4.48")
        require(legacy._installed_app_version(install) == VERSION, "Updater 4.4.43 no dejó app 4.4.48")
        require(legacy._installation_consistent(install), "Updater 4.4.43 dejó instalación incoherente")
        launcher = (install / "ABRIR_RECEPCION.py").read_text(encoding="utf-8-sig")
        require(
            'LAUNCHER_VERSION = "4.4.48-update-before-focus-dependency-safe-1"' in launcher,
            "Updater 4.4.43 no reemplazó el launcher",
        )
        require(
            sha((install / "app_base_4428.py").read_bytes())
            == sha((validation.LEGACY / "app_base_4428.py").read_bytes()),
            "Updater 4.4.43 alteró la dependencia estable",
        )
        for path, data in sentinels.items():
            require(path.read_bytes() == data, f"Updater tocó archivo protegido: {path.name}")
        require("app_base_4428.py" in (result.get("paths") or []), "La actualización real no incluyó app_base_4428.py")
    print("RAW_LEGACY_443_ACCEPTANCE_OK")


def wait_latest(version: str, attempts: int = 40) -> dict:
    last = None
    url = "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/latest-v3.json"
    for i in range(attempts):
        try:
            data = json.loads(fetch(url, attempts=1).decode("utf-8-sig"))
            last = data
            if str(data.get("version") or "") == version:
                return data
        except Exception as exc:
            last = exc
        time.sleep(min(4.0, 0.7 + i * 0.15))
    raise RuntimeError(f"latest-v3 Raw no propagó {version}: {last}")


def main() -> None:
    subprocess.run([sys.executable, str(HERE / "validate_v4448.py")], cwd=ROOT, check=True)
    candidate = json.loads((OUT / "candidate_latest.json").read_text(encoding="utf-8"))
    require(candidate.get("version") == VERSION, "Versión candidata incorrecta")
    require(
        [x.get("path") for x in candidate.get("files", [])]
        == ["app.py", "app_base_4428.py", "ABRIR_RECEPCION.py", "update_manifest.json"],
        "El candidato no trae la dependencia requerida por 4.4.43",
    )

    current = json.loads(
        fetch("https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/latest-v3.json").decode("utf-8-sig")
    )
    require(
        version_tuple(current.get("version")) <= version_tuple(VERSION),
        f"El canal ya tiene una versión más nueva: {current.get('version')}",
    )

    git("config", "user.name", "github-actions[bot]")
    git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")

    # 1) Publicamos SOLO payload. latest-v3 sigue apuntando a la versión anterior.
    git("add", "updates/v4_4_48_dependency_recovery")
    staged = subprocess.check_output(["git", "diff", "--cached", "--name-only"], cwd=ROOT, text=True).strip()
    if staged:
        git("commit", "-m", "release: payload v4.4.48 compatible con updater 4.4.43")
        git("pull", "--rebase", "origin", "main")
        git("push", "origin", "HEAD:main")

    # 2) Comprobamos SHA de TODOS los bytes Raw, incluida app_base_4428.py.
    for item in candidate["files"]:
        data = wait_payload(item)
        if item["path"] == "app.py":
            require('APP_VERSION = "4.4.48"' in data.decode("utf-8-sig"), "Raw app incorrecta")
        elif item["path"] == "app_base_4428.py":
            require(sha(data) == sha((validation.LEGACY / "app_base_4428.py").read_bytes()), "Raw app_base no es la estable")
        elif item["path"] == "ABRIR_RECEPCION.py":
            text = data.decode("utf-8-sig")
            require(
                'LAUNCHER_VERSION = "4.4.48-update-before-focus-dependency-safe-1"' in text,
                "Raw launcher incorrecto",
            )

    # 3) Antes de tocar el canal, el updater REAL 4.4.43 debe instalar esos Raw
    #    bytes en una copia 4.4.43 y conservar todos los datos protegidos.
    raw_legacy_acceptance(candidate)

    # 4) Recién ahora se mueve el canal estable.
    latest_bytes = (json.dumps(candidate, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    (ROOT / "latest-v3.json").write_bytes(latest_bytes)
    (ROOT / "latest.json").write_bytes(latest_bytes)
    git("add", "latest-v3.json", "latest.json")
    staged = subprocess.check_output(["git", "diff", "--cached", "--name-only"], cwd=ROOT, text=True).strip()
    if staged:
        git("commit", "-m", "release: publicar v4.4.48 recuperación definitiva")
        git("pull", "--rebase", "origin", "main")
        git("push", "origin", "HEAD:main")

    propagated = wait_latest(VERSION)
    require(any(x.get("path") == "app_base_4428.py" for x in propagated.get("files", [])), "latest-v3 Raw perdió app_base")
    print("PUBLISH_V4448_OK")


if __name__ == "__main__":
    main()

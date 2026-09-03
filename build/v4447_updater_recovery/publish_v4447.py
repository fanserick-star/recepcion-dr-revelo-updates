from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "updates" / "v4_4_47_updater_recovery"
VERSION = "4.4.47"


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise RuntimeError(msg)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def version_tuple(value: object) -> tuple[int, ...]:
    out = []
    for part in str(value or "0").split("."):
        try: out.append(int(part))
        except Exception: out.append(0)
    return tuple((out + [0, 0, 0, 0])[:4])


def git(*args: str) -> None:
    subprocess.run(["git", *args], cwd=ROOT, check=True)


def fetch(url: str, attempts: int = 3, timeout: float = 20.0) -> bytes:
    last = None
    for i in range(max(1, attempts)):
        try:
            sep = "&" if "?" in url else "?"
            req = urllib.request.Request(
                url + sep + "rp=" + str(time.time_ns()),
                headers={"Cache-Control": "no-cache", "Pragma": "no-cache", "User-Agent": "v4447-safe-release"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as r:
                require(getattr(r, "status", 200) == 200, f"HTTP {getattr(r, 'status', '?')}")
                return r.read()
        except Exception as exc:
            last = exc
            if i + 1 < attempts:
                time.sleep(min(4.0, 0.5 + i * 0.5))
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
        time.sleep(min(5.0, 0.8 + i * 0.15))
    raise RuntimeError(f"Payload Raw no propagó {item.get('path')}: {last}")


def main() -> None:
    subprocess.run([sys.executable, str(HERE / "validate_v4447.py")], cwd=ROOT, check=True)
    candidate = json.loads((OUT / "candidate_latest.json").read_text(encoding="utf-8"))
    require(candidate.get("version") == VERSION, "Versión candidata incorrecta")

    current = json.loads(fetch("https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/latest-v3.json", attempts=4).decode("utf-8-sig"))
    require(version_tuple(current.get("version")) <= version_tuple(VERSION), f"El canal ya tiene una versión más nueva: {current.get('version')}")

    git("config", "user.name", "github-actions[bot]")
    git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")

    # Publicar primero el payload. El canal estable todavía no se mueve.
    git("add", "updates/v4_4_47_updater_recovery")
    staged = subprocess.check_output(["git", "diff", "--cached", "--name-only"], cwd=ROOT, text=True).strip()
    if staged:
        git("commit", "-m", "release: payload v4.4.47 recuperación del actualizador")
        git("pull", "--rebase", "origin", "main")
        git("push", "origin", "HEAD:main")

    # El launcher antiguo consume Raw GitHub. No publicamos latest hasta que los
    # bytes reales del payload estén disponibles y tengan el SHA esperado.
    for item in candidate["files"]:
        data = wait_payload(item)
        if item["path"] == "ABRIR_RECEPCION.py":
            text = data.decode("utf-8-sig")
            require('LAUNCHER_VERSION = "4.4.47-update-before-focus-1"' in text, "Raw launcher incorrecto")
            main_block = text[text.index("def main() -> None:"):text.index("\ndef _selftest_mutex_holder", text.index("def main() -> None:"))]
            require(main_block.index("result = check_and_apply_update(ROOT)") < main_block.index("if current == expected and _focus_existing_window()"), "Raw launcher conserva orden incorrecto")
        if item["path"] == "app.py":
            require('APP_VERSION = "4.4.47"' in data.decode("utf-8-sig"), "Raw app incorrecta")

    latest_bytes = (json.dumps(candidate, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    (ROOT / "latest-v3.json").write_bytes(latest_bytes)
    (ROOT / "latest.json").write_bytes(latest_bytes)
    git("add", "latest-v3.json", "latest.json")
    staged = subprocess.check_output(["git", "diff", "--cached", "--name-only"], cwd=ROOT, text=True).strip()
    if staged:
        git("commit", "-m", "release: publicar v4.4.47 recuperación del actualizador")
        git("pull", "--rebase", "origin", "main")
        git("push", "origin", "HEAD:main")

    # Verificación del contenido en la rama (Raw puede tardar algunos segundos
    # adicionales; no convertimos esa propagación de CDN en un falso fallo del job).
    branch_latest = json.loads((ROOT / "latest-v3.json").read_text(encoding="utf-8"))
    require(branch_latest.get("version") == VERSION, "latest-v3 local no quedó en 4.4.47")
    require(any(x.get("path") == "ABRIR_RECEPCION.py" for x in branch_latest.get("files", [])), "El canal no incluye el launcher reparado")
    print("PUBLISH_V4447_OK")


if __name__ == "__main__":
    main()

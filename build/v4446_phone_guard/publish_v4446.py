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
OUT = ROOT / "updates" / "v4_4_46_phone_guard"
VERSION = "4.4.46"


def require(cond: bool, msg: str) -> None:
    if not cond:
        raise RuntimeError(msg)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(*args: str) -> None:
    subprocess.run(["git", *args], cwd=ROOT, check=True)


def fetch(url: str, attempts: int = 18) -> bytes:
    last = None
    for i in range(attempts):
        try:
            sep = "&" if "?" in url else "?"
            req = urllib.request.Request(
                url + sep + "v=" + str(time.time_ns()),
                headers={"Cache-Control": "no-cache", "User-Agent": "v4446-safe-release"},
            )
            with urllib.request.urlopen(req, timeout=20) as r:
                require(getattr(r, "status", 200) == 200, f"HTTP {getattr(r, 'status', '?')}")
                return r.read()
        except Exception as exc:
            last = exc
            time.sleep(min(4.0, 0.5 + i * 0.4))
    raise RuntimeError(f"Raw GitHub no propagó {url}: {last}")


def wait_latest(expected: str, attempts: int = 24) -> dict:
    url = "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/latest.json"
    last = None
    for i in range(attempts):
        try:
            data = json.loads(fetch(url, attempts=2).decode("utf-8-sig"))
            last = data
            if data.get("version") == expected and data.get("app_version") == expected:
                return data
        except Exception as exc:
            last = exc
        time.sleep(min(3.0, 0.6 + i * 0.25))
    raise RuntimeError(f"latest.json no propagó {expected}: {last!r}")


def version_tuple(value: object) -> tuple[int, ...]:
    out = []
    for part in str(value or "0").split("."):
        try: out.append(int(part))
        except Exception: out.append(0)
    return tuple(out)


def current_latest() -> dict:
    return json.loads(fetch("https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/latest.json").decode("utf-8-sig"))


def main() -> None:
    subprocess.run([sys.executable, str(HERE / "validate_v4446.py")], cwd=ROOT, check=True)
    candidate = json.loads((OUT / "candidate_latest.json").read_text(encoding="utf-8"))
    require(candidate.get("version") == VERSION, "Versión candidata incorrecta")
    require([x.get("path") for x in candidate.get("files", [])] == ["app.py", "update_manifest.json"], "La publicación dejó de ser mínima")

    before = current_latest()
    require(version_tuple(before.get("version")) <= version_tuple(VERSION), f"El canal ya tiene una versión más nueva: {before.get('version')}")

    git("config", "user.name", "github-actions[bot]")
    git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")

    # 1) Publicar payload sin mover el canal estable.
    git("add", "updates/v4_4_46_phone_guard")
    staged = subprocess.check_output(["git", "diff", "--cached", "--name-only"], cwd=ROOT, text=True).strip()
    if staged:
        git("commit", "-m", "release: payload v4.4.46 guardia de celular")
        git("pull", "--rebase", "origin", "main")
        git("push", "origin", "HEAD:main")

    # 2) Verificar bytes reales en Raw GitHub.
    for item in candidate["files"]:
        data = fetch(item["url"])
        require(sha(data) == item["sha256"], f"SHA Raw incorrecto: {item['path']}")
    remote_app = fetch(next(x["url"] for x in candidate["files"] if x["path"] == "app.py")).decode("utf-8-sig")
    for marker in (
        'APP_VERSION = "4.4.46"',
        '/api/agenda/appointments/guarded',
        '_v4445_sync_cloud_agenda_for_dates',
        'window.__v4445StagedIdentityFix',
        '/api/identity/phone-owner',
        'window.__v4446PhoneDuplicateGuard',
        'Este celular ya está registrado',
    ):
        require(marker in remote_app, f"Raw app perdió marcador: {marker}")

    # Volver a comprobar versión después del push de payload; nunca pisar una más nueva.
    before_channel = current_latest()
    require(version_tuple(before_channel.get("version")) <= version_tuple(VERSION), f"Apareció una versión más nueva durante las pruebas: {before_channel.get('version')}")

    # 3) Solo después mover latest.json/latest-v3.json.
    latest_bytes = (json.dumps(candidate, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    (ROOT / "latest-v3.json").write_bytes(latest_bytes)
    (ROOT / "latest.json").write_bytes(latest_bytes)
    git("add", "latest-v3.json", "latest.json")
    staged = subprocess.check_output(["git", "diff", "--cached", "--name-only"], cwd=ROOT, text=True).strip()
    if staged:
        git("commit", "-m", "release: publicar v4.4.46 guardia de celular")
        git("pull", "--rebase", "origin", "main")
        git("push", "origin", "HEAD:main")

    # 4) Verificación final.
    remote_latest = wait_latest(VERSION)
    message = str(remote_latest.get("message") or "")
    require("Completar datos" in message and "celular" in message.lower(), "El mensaje publicado no describe el bug corregido")
    require([x.get("path") for x in remote_latest.get("files", [])] == ["app.py", "update_manifest.json"], "Canal toca archivos de más")
    remote_app_hash = next(x["sha256"] for x in remote_latest["files"] if x["path"] == "app.py")
    local_app_hash = next(x["sha256"] for x in candidate["files"] if x["path"] == "app.py")
    require(remote_app_hash == local_app_hash, "Hash app.py del canal no coincide")
    print("PUBLISH_V4446_OK")


if __name__ == "__main__":
    main()

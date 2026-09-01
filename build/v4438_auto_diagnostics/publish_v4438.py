from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "updates" / "v4_4_38_auto_diagnostics"
LATEST = ROOT / "latest-v3.json"
LATEST_LEGACY = ROOT / "latest.json"


def run(*args: str) -> None:
    subprocess.run(list(args), cwd=ROOT, check=True)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def get(url: str, timeout: int = 12) -> bytes:
    sep = "&" if "?" in url else "?"
    req = urllib.request.Request(
        url + sep + "rp_ts=" + str(time.time_ns()),
        headers={"Cache-Control": "no-cache", "Pragma": "no-cache", "User-Agent": "Recepcion-v4438-release"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def commit_and_push(paths: list[str], message: str) -> None:
    run("git", "config", "user.name", "github-actions[bot]")
    run("git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    run("git", "add", *paths)
    diff = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT)
    if diff.returncode != 0:
        run("git", "commit", "-m", message)
        run("git", "pull", "--rebase", "origin", "main")
        run("git", "push", "origin", "main")


def verify_raw_payload(candidate: dict) -> None:
    last = None
    for _ in range(90):
        try:
            for item in candidate["files"]:
                if item["path"] == "ABRIR_RECEPCION.py":
                    data = b"".join(get(url) for url in item["parts"])
                else:
                    data = get(item["url"])
                got = sha(data)
                if got != item["sha256"]:
                    raise RuntimeError(f"SHA Raw incorrecto {item['path']}: {got}")
                if item["path"].endswith(".py"):
                    compile(data.decode("utf-8-sig"), item["path"], "exec")
            print("RAW_PAYLOAD_V4438_OK")
            return
        except Exception as exc:
            last = exc
            time.sleep(1)
    raise RuntimeError(f"Payload 4.4.38 no propagó íntegro: {last}")


def verify_channel() -> None:
    url = "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/latest-v3.json"
    expected = ["ABRIR_RECEPCION.py", "app_base_4428.py", "app.py", "static/app.js", "static/index.html", "update_manifest.json"]
    last = None
    for _ in range(90):
        try:
            data = json.loads(get(url, 10).decode("utf-8-sig"))
            paths = [x.get("path") for x in data.get("files", [])]
            if data.get("version") == "4.4.38" and data.get("app_version") == "4.4.36" and paths == expected:
                print("CHANNEL_V4438_OK")
                return
            last = (data.get("version"), data.get("app_version"), paths)
        except Exception as exc:
            last = exc
        time.sleep(1)
    raise RuntimeError(f"Canal 4.4.38 no propagó correctamente: {last}")


def main() -> None:
    if os.getenv("GITHUB_ACTIONS", "").lower() != "true":
        raise SystemExit("Este publicador solo puede ejecutarse dentro de GitHub Actions")
    candidate_text = (OUT / "candidate_latest.json").read_text(encoding="utf-8")
    candidate = json.loads(candidate_text)
    expected = ["ABRIR_RECEPCION.py", "app_base_4428.py", "app.py", "static/app.js", "static/index.html", "update_manifest.json"]
    if candidate.get("version") != "4.4.38" or candidate.get("app_version") != "4.4.36":
        raise RuntimeError("Candidato 4.4.38 inválido")
    if [x.get("path") for x in candidate.get("files", [])] != expected:
        raise RuntimeError("Candidato 4.4.38 no es acumulativo")

    # 1. Primero persiste el payload ya validado, SIN mover el canal.
    commit_and_push(["updates/v4_4_38_auto_diagnostics"], "payload: v4.4.38 diagnóstico privado validado")
    run("git", "pull", "--rebase", "origin", "main")
    verify_raw_payload(candidate)

    # 2. Solo después de verificar GitHub Raw se permite mover el canal.
    current = json.loads(LATEST.read_text(encoding="utf-8"))
    if current.get("version") not in {"4.4.37", "4.4.38"}:
        raise RuntimeError(f"Canal cambió inesperadamente: {current.get('version')}")
    LATEST.write_text(candidate_text, encoding="utf-8")
    LATEST_LEGACY.write_text(candidate_text, encoding="utf-8")
    commit_and_push(["latest-v3.json", "latest.json"], "release: v4.4.38 diagnóstico automático privado tras validación")
    verify_channel()
    print("PUBLISH_V4438_COMPLETE")


if __name__ == "__main__":
    main()

from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "updates" / "v4_4_44_weekly_appointment_guard"


def require(cond, msg):
    if not cond:
        raise RuntimeError(msg)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(*args):
    subprocess.run(["git", *args], cwd=ROOT, check=True)


def fetch(url: str, attempts: int = 12) -> bytes:
    last = None
    for i in range(attempts):
        try:
            sep = "&" if "?" in url else "?"
            req = urllib.request.Request(
                url + sep + "ts=" + str(time.time_ns()),
                headers={"Cache-Control": "no-cache", "User-Agent": "v4444-publisher"},
            )
            with urllib.request.urlopen(req, timeout=20) as response:
                if getattr(response, "status", 200) != 200:
                    raise RuntimeError("HTTP " + str(getattr(response, "status", "?")))
                return response.read()
        except Exception as exc:
            last = exc
            time.sleep(min(5, 0.8 + i * 0.6))
    raise RuntimeError("Raw no propagó: " + url + ": " + str(last))


def main():
    # El canal nunca se mueve si la construcción, browser smoke o updater smoke fallan.
    subprocess.run(
        [sys.executable, str(ROOT / "build" / "v4444_weekly_appointment_guard" / "validate_v4444.py")],
        cwd=ROOT,
        check=True,
    )
    candidate = json.loads((OUT / "candidate_latest.json").read_text(encoding="utf-8"))
    require(candidate.get("version") == "4.4.44" and candidate.get("app_version") == "4.4.44", "Candidato incorrecto")

    git("config", "user.name", "github-actions[bot]")
    git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    git("add", "updates/v4_4_44_weekly_appointment_guard")
    staged = subprocess.check_output(["git", "diff", "--cached", "--name-only"], cwd=ROOT, text=True).strip()
    if staged:
        git("commit", "-m", "release: payload v4.4.44 guardia semanal de citas")
        git("push", "origin", "HEAD:main")

    # Verifica que cada byte publicado por Raw coincida con el candidato antes
    # de modificar latest.json/latest-v3.json.
    for item in candidate["files"]:
        data = b"".join(fetch(u) for u in item["parts"]) if item.get("parts") else fetch(item["url"])
        require(sha(data) == item["sha256"], "SHA Raw incorrecto: " + item["path"])

    latest = (json.dumps(candidate, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    (ROOT / "latest-v3.json").write_bytes(latest)
    (ROOT / "latest.json").write_bytes(latest)
    git("add", "latest-v3.json", "latest.json")
    git("commit", "-m", "release: v4.4.44 guardia semanal de citas")
    git("push", "origin", "HEAD:main")

    remote = json.loads(
        fetch("https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/latest-v3.json").decode("utf-8-sig")
    )
    require(remote.get("version") == "4.4.44" and remote.get("app_version") == "4.4.44", "Canal no propagó 4.4.44")
    require(remote["files"][0]["sha256"] == candidate["files"][0]["sha256"], "Launcher propagado incorrecto")
    require(remote["files"][2]["sha256"] == candidate["files"][2]["sha256"], "app.py propagado incorrecto")
    print("PUBLISH_V4444_OK")


if __name__ == "__main__":
    main()

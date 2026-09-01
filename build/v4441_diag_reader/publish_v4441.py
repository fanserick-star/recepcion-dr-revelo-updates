from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "updates" / "v4_4_41_diag_reader"
WORKER = ROOT / "cloudflare" / "WHATSAPP_WORKER_v2_6_15_DIAGNOSTICS_STANDALONE.js"


def require(cond, msg):
    if not cond:
        raise RuntimeError(msg)


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(*args):
    subprocess.run(["git", *args], cwd=ROOT, check=True)


def fetch(url: str, attempts: int = 10) -> bytes:
    last = None
    for i in range(attempts):
        try:
            sep = "&" if "?" in url else "?"
            req = urllib.request.Request(url + sep + "ts=" + str(time.time_ns()), headers={"Cache-Control":"no-cache","User-Agent":"v4441-publisher"})
            with urllib.request.urlopen(req, timeout=15) as r:
                if getattr(r, "status", 200) != 200:
                    raise RuntimeError(f"HTTP {getattr(r,'status','?')}")
                return r.read()
        except Exception as exc:
            last = exc
            time.sleep(min(5, 0.8 + i * 0.6))
    raise RuntimeError(f"Raw no propagó: {url}: {last}")


def main():
    subprocess.run([sys.executable, str(ROOT / "build" / "v4441_diag_reader" / "validate_v4441.py")], cwd=ROOT, check=True)
    candidate = json.loads((OUT / "candidate_latest.json").read_text(encoding="utf-8"))
    require(candidate.get("version") == "4.4.41", "Candidato incorrecto")
    require(WORKER.is_file(), "Falta Worker generado")

    git("config", "user.name", "github-actions[bot]")
    git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    git("add", "updates/v4_4_41_diag_reader", "cloudflare/WHATSAPP_WORKER_v2_6_15_DIAGNOSTICS_STANDALONE.js")
    staged = subprocess.check_output(["git","diff","--cached","--name-only"], cwd=ROOT, text=True).strip()
    if staged:
        git("commit", "-m", "release: payload v4.4.41 y Worker diagnóstico 2.6.15")
        git("push", "origin", "HEAD:main")

    # Verificar cada payload directamente desde GitHub Raw antes de mover el canal.
    for item in candidate["files"]:
        if item.get("parts"):
            data = b"".join(fetch(u) for u in item["parts"])
        else:
            data = fetch(item["url"])
        require(sha_bytes(data) == item["sha256"], f"SHA Raw incorrecto: {item['path']}")

    worker_url = "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/cloudflare/WHATSAPP_WORKER_v2_6_15_DIAGNOSTICS_STANDALONE.js"
    worker_remote = fetch(worker_url)
    require(sha_bytes(worker_remote) == sha_bytes(WORKER.read_bytes()), "Worker Raw no coincide")
    require(b'worker_version: "2.6.15"' in worker_remote and b'/diagnostics/' in worker_remote, "Worker Raw incompleto")

    latest_bytes = (json.dumps(candidate, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    (ROOT / "latest-v3.json").write_bytes(latest_bytes)
    (ROOT / "latest.json").write_bytes(latest_bytes)
    git("add", "latest-v3.json", "latest.json")
    git("commit", "-m", "release: v4.4.41 códigos privados de diagnóstico")
    git("push", "origin", "HEAD:main")

    raw_latest = fetch("https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/latest-v3.json")
    remote = json.loads(raw_latest.decode("utf-8-sig"))
    require(remote.get("version") == "4.4.41", "Canal no propagó 4.4.41")
    require(remote["files"][0]["sha256"] == candidate["files"][0]["sha256"], "Canal propagó launcher incorrecto")
    print("PUBLISH_V4441_OK")
    print("WORKER_SHA", sha_bytes(WORKER.read_bytes()))


if __name__ == "__main__":
    main()

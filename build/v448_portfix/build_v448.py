from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSION = "4.4.8"
SOURCE_DIR = ROOT / "updates" / "v4_4_7_recovery"
SOURCE_SHA256 = "a54ddd8958acddc13ca7df4d028d0d04f33bc9d25662d551a23758f7fbdf2bc7"
OUT = ROOT / "updates" / "v4_4_8_portfix"
PART_SIZE = 70000


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_app() -> str:
    parts = sorted(SOURCE_DIR.glob("app.part*"), key=lambda p: int(p.name.split("part")[-1]))
    raw = b"".join(p.read_bytes() for p in parts)
    got = sha256_bytes(raw)
    if got != SOURCE_SHA256:
        raise SystemExit(f"Fuente 4.4.7 cambió: {got}")
    return raw.decode("utf-8-sig")


def patch(text: str) -> str:
    old_version = 'APP_VERSION = "4.4.7"'
    if text.count(old_version) != 1:
        raise SystemExit("No se encontró APP_VERSION 4.4.7 de forma única")
    text = text.replace(old_version, 'APP_VERSION = "4.4.8"', 1)
    old_run = 'uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False, access_log=False, log_level="warning", workers=1)'
    new_run = 'uvicorn.run("app:app", host="0.0.0.0", port=int(os.getenv("RP_PORT", "8000")), reload=False, access_log=False, log_level="warning", workers=1)'
    if text.count(old_run) != 1:
        raise SystemExit(f"Esperaba 1 uvicorn fijo y encontré {text.count(old_run)}")
    text = text.replace(old_run, new_run, 1)
    if 'port=8000' in text:
        raise SystemExit("Quedó un port=8000 fijo")
    if 'os.getenv("RP_PORT", "8000")' not in text:
        raise SystemExit("No quedó aplicado RP_PORT")
    compile(text, "app.py", "exec")
    return text


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    text = patch(source_app())
    raw = text.encode("utf-8")
    for p in OUT.glob("app.part*"):
        p.unlink()
    parts=[]
    for n,start in enumerate(range(0,len(raw),PART_SIZE),1):
        p=OUT/f"app.part{n}"
        p.write_bytes(raw[start:start+PART_SIZE])
        parts.append(p)

    manifest={
        "product":"recepcion-pacientes",
        "version":VERSION,
        "app_version":VERSION,
        "runtime_version":VERSION,
        "launcher_version":"4.3.100-standalone-7",
        "updater_version":"integrado-en-launcher",
        "copy":["app.py","update_manifest.json"],
    }
    mp=OUT/"update_manifest.json"
    mp.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    latest={
        "product":"recepcion-pacientes",
        "version":VERSION,
        "app_version":VERSION,
        "runtime_version":VERSION,
        "mandatory":True,
        "channel":"files-v3",
        "message":"v4.4.8 corrección mínima: el backend respeta el puerto libre elegido por el launcher mediante RP_PORT; no toca interfaz ni datos.",
        "files":[
            {
                "path":"app.py",
                "parts":[f"https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_8_portfix/{p.name}" for p in parts],
                "sha256":sha256_bytes(raw),
                "encoding":"utf-8",
            },
            {
                "path":"update_manifest.json",
                "url":"https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_8_portfix/update_manifest.json",
                "sha256":sha256_bytes(mp.read_bytes()),
                "encoding":"utf-8",
            },
        ],
    }
    payload=json.dumps(latest,ensure_ascii=False,indent=2)+"\n"
    (ROOT/"latest-v3.json").write_text(payload,encoding="utf-8")
    (ROOT/"latest.json").write_text(payload,encoding="utf-8")
    print(json.dumps({"version":VERSION,"app_sha256":sha256_bytes(raw),"parts":len(parts)},sort_keys=True))


if __name__ == "__main__":
    main()

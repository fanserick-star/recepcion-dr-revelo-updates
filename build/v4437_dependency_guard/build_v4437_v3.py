from __future__ import annotations

import ast
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "updates" / "v4_4_37_dependency_guard"
OUT.mkdir(parents=True, exist_ok=True)

BASE_REF = "6aeeea848159d9890824722518418fdaaaf3127d"
BASE_PREFIX = "updates/v4_4_28_overlay_hotfix"
LAUNCHER_REF = "5661754088197cafc7a9381156c193f22130ced7"
LAUNCHER_PREFIX = "updates/v4_4_32_launcher_port_patch"
APP_REF = "fc0f123c0d5fe92001a5979d5dfa8afa533b93ec"
APP_PATH = "updates/v4_4_36_default_cash/app.py"
VERSION = "4.4.37"
APP_VERSION = "4.4.36"


def sha(data: bytes) -> str: return hashlib.sha256(data).hexdigest()
def dump(obj: dict) -> bytes: return (json.dumps(obj, ensure_ascii=False, indent=2)+"\n").encode("utf-8")
def require(cond: bool, msg: str) -> None:
    if not cond: raise RuntimeError(msg)
def git_bytes(ref: str, path: str) -> bytes:
    return subprocess.check_output(["git","show",f"{ref}:{path}"],cwd=ROOT)


GUARD = r'''

# ---------------------------------------------------------------------------
# v4.4.37 — guardia permanente de dependencias del runtime
# ---------------------------------------------------------------------------
# Parche mínimo sobre el launcher dinámico 4.4.32. No cambia selección de
# puertos, RP_PORT, mutex, WebView/Edge ni el flujo de arranque.
_RP_V4437_OLD_INSTALLATION_CONSISTENT = _installation_consistent
_RP_V4437_OLD_STAGE_UPDATE = _stage_update


def _rp_v4437_required_files(root: Path = ROOT) -> list[str]:
    try: manifest = _local_manifest(root)
    except Exception: manifest = {}
    values = manifest.get("required_dependencies") or []
    if not isinstance(values, list): return []
    out=[]
    for value in values:
        rel=str(value or "").replace("\\","/").lstrip("/")
        if rel and rel not in out: out.append(rel)
    return out


def _rp_v4437_app_local_imports(app_path: Path) -> set[str]:
    try:
        tree=ast.parse(app_path.read_text(encoding="utf-8-sig"),filename=str(app_path))
    except Exception:
        return set()
    result=set()
    for node in ast.walk(tree):
        if isinstance(node,ast.Import):
            for alias in node.names:
                name=str(alias.name or "").split(".",1)[0]
                if name.startswith("app_"): result.add(name+".py")
        elif isinstance(node,ast.ImportFrom) and node.module:
            name=str(node.module).split(".",1)[0]
            if name.startswith("app_"): result.add(name+".py")
    return result


def _rp_v4437_dependency_file_ok(path: Path) -> bool:
    if not path.is_file(): return False
    if path.suffix.lower()==".py":
        try: compile(path.read_text(encoding="utf-8-sig"),str(path),"exec")
        except Exception: return False
    return True


def _installation_consistent(root: Path = ROOT) -> bool:
    if not _RP_V4437_OLD_INSTALLATION_CONSISTENT(root): return False
    required=set(_rp_v4437_required_files(root))
    required.update(_rp_v4437_app_local_imports(root/"app.py"))
    for rel in required:
        try: target=_safe_target(root,rel)
        except Exception: return False
        if not _rp_v4437_dependency_file_ok(target):
            _log(f"Dependencia obligatoria ausente o dañada: {rel}",root)
            return False
    return True


def _stage_update(remote: dict, root: Path = ROOT, *, attempts: int = 3,
                  timeout: float = 10.0, allow_test_sources: bool = False):
    stage,staged=_RP_V4437_OLD_STAGE_UPDATE(remote,root,attempts=attempts,timeout=timeout,
                                            allow_test_sources=allow_test_sources)
    try:
        paths={str(x.get("rel") or "").replace("\\","/") for x in staged}
        staged_app=stage/"app.py"
        if staged_app.is_file():
            imports=_rp_v4437_app_local_imports(staged_app)
            missing=sorted(rel for rel in imports if rel not in paths)
            if missing:
                raise RuntimeError("Actualización incompleta: app.py requiere archivo(s) no incluidos en el manifiesto: "+", ".join(missing))
        inner=stage/"update_manifest.json"
        if inner.is_file():
            data=json.loads(inner.read_text(encoding="utf-8-sig"));req=data.get("required_dependencies") or []
            if not isinstance(req,list): raise RuntimeError("required_dependencies debe ser una lista")
            absent=[]
            for value in req:
                rel=str(value or "").replace("\\","/").lstrip("/")
                if rel and rel not in paths: absent.append(rel)
            if absent:
                raise RuntimeError("Manifest de actualización incompleto; faltan dependencias obligatorias: "+", ".join(sorted(set(absent))))
        return stage,staged
    except Exception:
        shutil.rmtree(stage,ignore_errors=True)
        raise

'''


def build() -> None:
    base=git_bytes(BASE_REF,f"{BASE_PREFIX}/app.py")
    static_app=git_bytes(BASE_REF,f"{BASE_PREFIX}/static/app.js")
    static_index=git_bytes(BASE_REF,f"{BASE_PREFIX}/static/index.html")
    app=git_bytes(APP_REF,APP_PATH)
    old_parts=[git_bytes(LAUNCHER_REF,f"{LAUNCHER_PREFIX}/ABRIR_RECEPCION.part{i}") for i in range(1,5)]

    require(sha(base)=="e5d3d96b9289169aa52524e8cc2f5f0ec9567c8da5e11d482151b12fc8ff85ba","Base publicada 4.4.28 no coincide")
    require(sha(static_app)=="0657c3b76721df2e28ec812856a2fc25944d2908382b13fbf3f115dad3e18d90","JS publicado 4.4.28 no coincide")
    require(sha(static_index)=="16d30060a0be19215e612c4ba897e801873dd359712e90d4dc14e32513b25728","Index publicado 4.4.28 no coincide")
    require(sha(app)=="2d8c6bac37a603c911b9fca6848e839b00b6b7975cf13fd9c3088c4542e4508e","App publicada 4.4.36 no coincide")
    require(sha(b"".join(old_parts))=="3ce0fae2ede2665a88f935c48fb9d4a221f59639d9c796f45662344b9e678a2a","Launcher publicado 4.4.32 no coincide")

    app_text=app.decode("utf-8-sig");require('APP_VERSION = "4.4.36"' in app_text,"App fijada no declara 4.4.36")
    imports={a.name.split(".",1)[0] for n in ast.walk(ast.parse(app_text)) if isinstance(n,ast.Import) for a in n.names}
    require("app_base_4428" in imports,"App 4.4.36 fijada no requiere app_base_4428")

    p4=old_parts[3].decode("utf-8-sig");anchor='\nif __name__ == "__main__":\n'
    require(p4.count(anchor)==1,"Cambió ancla histórica del launcher")
    patched4=p4.replace(anchor,GUARD+anchor,1).encode("utf-8")
    launcher=b"".join(old_parts[:3]+[patched4]);text=launcher.decode("utf-8-sig")
    compile(text,"ABRIR_RECEPCION.py","exec")
    require('LAUNCHER_VERSION = "4.4.32-dynamic-port-patch-1"' in text,"No conserva launcher dinámico")
    require("_choose_app_port" in text and 'env["RP_PORT"] = str(APP_PORT)' in text,"No conserva RP_PORT/puertos")
    require("_rp_v4437_required_files" in text,"Guardia no insertada")

    for i,data in enumerate(old_parts[:3],1):(OUT/f"ABRIR_RECEPCION.part{i}").write_bytes(data)
    (OUT/"ABRIR_RECEPCION.part4").write_bytes(patched4)
    (OUT/"app_base_4428.py").write_bytes(base);(OUT/"app.py").write_bytes(app)
    (OUT/"static").mkdir(parents=True,exist_ok=True)
    (OUT/"static"/"app.js").write_bytes(static_app);(OUT/"static"/"index.html").write_bytes(static_index)

    paths=["ABRIR_RECEPCION.py","app_base_4428.py","app.py","static/app.js","static/index.html","update_manifest.json"]
    inner={"product":"recepcion-pacientes","version":VERSION,"app_version":APP_VERSION,"runtime_version":APP_VERSION,
           "launcher_version":"4.4.32-dynamic-port-patch-1+dependency-guard-v4437","updater_version":"integrado-en-launcher",
           "required_dependencies":["app_base_4428.py"],"copy":paths}
    inner_bytes=dump(inner);(OUT/"update_manifest.json").write_bytes(inner_bytes)
    raw="https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/updates/v4_4_37_dependency_guard/"
    files=[
      {"path":"ABRIR_RECEPCION.py","parts":[raw+f"ABRIR_RECEPCION.part{i}" for i in range(1,5)],"sha256":sha(launcher),"encoding":"utf-8"},
      {"path":"app_base_4428.py","url":raw+"app_base_4428.py","sha256":sha(base),"encoding":"utf-8"},
      {"path":"app.py","url":raw+"app.py","sha256":sha(app),"encoding":"utf-8"},
      {"path":"static/app.js","url":raw+"static/app.js","sha256":sha(static_app),"encoding":"utf-8"},
      {"path":"static/index.html","url":raw+"static/index.html","sha256":sha(static_index),"encoding":"utf-8"},
      {"path":"update_manifest.json","url":raw+"update_manifest.json","sha256":sha(inner_bytes),"encoding":"utf-8"},
    ]
    candidate={"product":"recepcion-pacientes","version":VERSION,"app_version":APP_VERSION,"runtime_version":APP_VERSION,
      "mandatory":True,"channel":"files-v3",
      "message":"v4.4.37: reparación acumulativa y guardia permanente de dependencias. Recupera instalaciones que saltaron desde versiones antiguas y quedaron sin app_base_4428.py. El release fija sus propios bytes desde los commits publicados de 4.4.28, 4.4.32 y 4.4.36; conserva el launcher dinámico de puertos/RP_PORT y rechaza antes de instalar un app.py que requiera módulos app_* ausentes. Una dependencia obligatoria faltante o corrupta se detecta y se autorepara incluso en la misma versión. No modifica .env, data, pacientes, citas, facturas ni bases de datos.",
      "files":files}
    (OUT/"candidate_latest.json").write_bytes(dump(candidate))
    require([x["path"] for x in files]==paths,"Release no acumulativo")
    print("BUILD_V4437_V3_OK");print("LAUNCHER_SHA",sha(launcher));print("BASE_SHA",sha(base));print("APP_SHA",sha(app))


if __name__=="__main__": build()

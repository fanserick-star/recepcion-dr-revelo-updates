from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.parse
import urllib.request
import webbrowser
import zipfile
from pathlib import Path

LAUNCHER_VERSION = "2.0.1-transactional-2"
PRODUCT = "historia-clinica-dr-revelo"
TITLE = "Historia Clínica - Dr. Armando Revelo"
ROOT = Path(__file__).resolve().parent
DEFAULT_PORT = 8787
DEFAULT_MANIFEST_URL = "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/latest-historia-runtime.json"
OFFICIAL_RAW_PREFIX = "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/"
PROTECTED_TOP = {"data", ".venv"}
PROTECTED_FILES = {".env"}
MUTEX_NAME = "DrArmandoRevelo_HistoriaClinica_Launcher_v4"
APP_USER_MODEL_ID = "DrArmandoRevelo.HistoriaClinica"
SHORTCUT_NAME = "Historia Clínica - Dr. Armando Revelo.lnk"


def _data_dir() -> Path:
    p = ROOT / "data"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _log(message: str) -> None:
    try:
        p = _data_dir() / "launcher.log"
        with p.open("a", encoding="utf-8") as fh:
            fh.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
        if p.stat().st_size > 900_000:
            lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()[-1400:]
            p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception:
        pass


def _state_path() -> Path:
    return _data_dir() / "launcher_state.json"


def _load_state() -> dict:
    try:
        p = _state_path()
        data = json.loads(p.read_text(encoding="utf-8-sig")) if p.is_file() else {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_state(**values) -> None:
    try:
        old = _load_state()
        old.update(values)
        old["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        p = _state_path()
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(old, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, p)
    except Exception:
        pass


def _message(text: str, error: bool = False) -> None:
    if os.name == "nt":
        try:
            ctypes.windll.user32.MessageBoxW(None, str(text), TITLE, 0x10 if error else 0x40)
            return
        except Exception:
            pass
    print(text, file=sys.stderr if error else sys.stdout)


def _set_windows_identity() -> None:
    """Identidad estable de Windows para que la barra de tareas use el icono del programa."""
    if os.name != "nt":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception as exc:
        _log("AppUserModelID no disponible: " + repr(exc))


def _ensure_brand_icon() -> Path | None:
    """Reconstruye el icono oficial desde una fuente de texto actualizable si hace falta."""
    icon = ROOT / "static" / "doctor_icon.ico"
    source = ROOT / "static" / "doctor_icon.b64"
    try:
        if source.is_file():
            raw = base64.b64decode(source.read_text(encoding="ascii").strip(), validate=True)
            wanted = hashlib.sha256(raw).hexdigest()
            current = hashlib.sha256(icon.read_bytes()).hexdigest() if icon.is_file() else ""
            if current != wanted:
                icon.parent.mkdir(parents=True, exist_ok=True)
                temp = icon.with_suffix(".ico.new")
                temp.write_bytes(raw)
                os.replace(temp, icon)
        return icon if icon.is_file() else None
    except Exception as exc:
        _log("No se pudo preparar el icono: " + repr(exc))
        return icon if icon.is_file() else None




def _ensure_native_launcher() -> Path | None:
    """Reconstruye el launcher EXE con icono embebido desde el payload actualizable."""
    target = ROOT / "HistoriaClinica_Dr_Revelo.exe"
    source = ROOT / "static" / "HistoriaClinica_Dr_Revelo.exe.b64"
    try:
        if not source.is_file():
            return target if target.is_file() else None
        raw = base64.b64decode(source.read_text(encoding="ascii").strip(), validate=True)
        if len(raw) < 20000 or raw[:2] != b"MZ":
            raise RuntimeError("payload nativo inválido")
        current_hash = hashlib.sha256(target.read_bytes()).hexdigest() if target.is_file() else ""
        wanted_hash = hashlib.sha256(raw).hexdigest()
        if current_hash != wanted_hash:
            tmp = target.with_suffix(".exe.new")
            tmp.write_bytes(raw)
            os.replace(tmp, target)
        return target
    except Exception as exc:
        _log("No se pudo preparar launcher nativo: " + repr(exc))
        return target if target.is_file() else None


def _ensure_windows_shortcuts() -> None:
    """Autorrepara accesos con el launcher nativo; conserva fallback a INICIAR.bat."""
    if os.name != "nt":
        return
    native = _ensure_native_launcher()
    if native and native.is_file():
        try:
            proc = subprocess.run(
                [str(native), "--repair-shortcut"], cwd=str(ROOT),
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=20, check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if proc.returncode == 0:
                _write_state(shortcut_target=native.name, shortcut_branding_ok=True, taskbar_branding="native-appid")
                return
            _log(f"Launcher nativo devolvió {proc.returncode}; usando fallback")
        except Exception as exc:
            _log("No se pudo usar launcher nativo: " + repr(exc))

    iniciar = ROOT / "INICIAR.bat"
    icon = _ensure_brand_icon()
    if not iniciar.is_file():
        _log("No se pudo reparar acceso directo: falta INICIAR.bat")
        return
    try:
        ps = f"""
$ErrorActionPreference = 'Stop'
$ws = New-Object -ComObject WScript.Shell
$name = '{SHORTCUT_NAME.replace("'", "''")}'
$target = '{str(iniciar).replace("'", "''")}'
$work = '{str(ROOT).replace("'", "''")}'
$icon = '{str(icon or iniciar).replace("'", "''")},0'
$dirs = @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))
foreach ($dir in $dirs) {{
  if ([string]::IsNullOrWhiteSpace($dir)) {{ continue }}
  if (-not (Test-Path -LiteralPath $dir)) {{ continue }}
  $path = Join-Path $dir $name
  $s = $ws.CreateShortcut($path)
  $s.TargetPath = $target
  $s.WorkingDirectory = $work
  $s.IconLocation = $icon
  $s.Description = 'Historia Clínica - Dr. Armando Revelo'
  $s.WindowStyle = 1
  $s.Save()
}}
"""
        encoded = base64.b64encode(ps.encode("utf-16le")).decode("ascii")
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
            cwd=str(ROOT), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=20, check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if proc.returncode == 0:
            try: ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)
            except Exception: pass
            _write_state(shortcut_target="INICIAR.bat-fallback", shortcut_branding_ok=True)
    except Exception as exc:
        _log("No se pudo autorreparar el acceso directo: " + repr(exc))


def _tail(path: Path, lines: int = 80) -> str:
    try:
        return "\n".join(path.read_text(encoding="utf-8", errors="ignore").splitlines()[-lines:])
    except Exception:
        return ""


def _show_failure(title: str, detail: str) -> None:
    diag = detail.strip()
    if not diag:
        diag = "No hay más detalle disponible."
    try:
        import tkinter as tk
        root = tk.Tk()
        root.title(TITLE)
        try:
            _ico = _ensure_brand_icon()
            if _ico: root.iconbitmap(str(_ico))
        except Exception: pass
        root.attributes("-topmost", True)
        root.resizable(False, False)
        root.configure(bg="#111d33")
        w, h = 620, 390
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(f"{w}x{h}+{max(0,(sw-w)//2)}+{max(0,(sh-h)//2)}")
        outer = tk.Frame(root, bg="#111d33", padx=24, pady=22)
        outer.pack(fill="both", expand=True)
        tk.Label(outer, text=title, font=("Segoe UI", 15, "bold"), fg="white", bg="#111d33").pack(anchor="w")
        tk.Label(outer, text="Historia Clínica no fue modificada si la actualización falló.", font=("Segoe UI", 9), fg="#ffca76", bg="#111d33").pack(anchor="w", pady=(5,10))
        box = tk.Text(outer, height=13, wrap="word", font=("Consolas", 9), bg="#182842", fg="#d8e2f0", relief="flat", padx=10, pady=9)
        box.pack(fill="both", expand=True)
        box.insert("1.0", diag)
        box.config(state="disabled")
        row = tk.Frame(outer, bg="#111d33")
        row.pack(fill="x", pady=(12,0))
        status = tk.Label(row, text="", font=("Segoe UI", 8), fg="#86d5a2", bg="#111d33")
        status.pack(side="left")
        def copy_diag():
            try:
                root.clipboard_clear(); root.clipboard_append(diag); root.update(); status.config(text="Diagnóstico copiado")
            except Exception:
                status.config(text="No se pudo copiar")
        tk.Button(row, text="Copiar diagnóstico", command=copy_diag).pack(side="right", padx=(8,0))
        tk.Button(row, text="Cerrar", command=root.destroy).pack(side="right")
        root.mainloop()
    except Exception:
        _message(title + "\n\n" + diag, error=True)


class Splash:
    def __init__(self):
        self.root = None; self.bar = None; self.title = None; self.detail = None; self.elapsed = None
        self.stage = 1; self.started = time.monotonic()
        try:
            import tkinter as tk
            self.tk = tk
            root = tk.Tk(); root.title(TITLE); root.resizable(False, False); root.attributes("-topmost", True); root.configure(bg="#f4efe5")
            try:
                _ico = _ensure_brand_icon()
                if _ico: root.iconbitmap(str(_ico))
            except Exception: pass
            w,h=540,250; sw,sh=root.winfo_screenwidth(),root.winfo_screenheight(); root.geometry(f"{w}x{h}+{max(0,(sw-w)//2)}+{max(0,(sh-h)//2)}")
            root.protocol("WM_DELETE_WINDOW", lambda: None)
            outer=tk.Frame(root,bg="#f4efe5",highlightthickness=1,highlightbackground="#b8aa94"); outer.pack(fill="both",expand=True)
            head=tk.Frame(outer,bg="#123f73",height=72); head.pack(fill="x"); head.pack_propagate(False)
            logo=ROOT/"static"/"doctor_logo.png"
            if logo.is_file():
                try:
                    img=tk.PhotoImage(file=str(logo)); factor=max(1,int(max(img.width()/54,img.height()/54))); img=img.subsample(factor,factor) if factor>1 else img
                    self._logo=img; tk.Label(head,image=img,bg="#123f73").pack(side="left",padx=(20,10),pady=8)
                except Exception as exc: _log("Splash logo: "+repr(exc))
            brand=tk.Frame(head,bg="#123f73"); brand.pack(side="left",fill="y",pady=10)
            tk.Label(brand,text="Historia Clínica",font=("Segoe UI",15,"bold"),fg="white",bg="#123f73").pack(anchor="w")
            tk.Label(brand,text="Dr. Armando Revelo",font=("Segoe UI",9),fg="#dce8f5",bg="#123f73").pack(anchor="w")
            body=tk.Frame(outer,bg="#f4efe5",padx=26,pady=17); body.pack(fill="both",expand=True)
            self.title=tk.Label(body,text="Preparando Historia Clínica…",font=("Segoe UI",13,"bold"),fg="#173b66",bg="#f4efe5"); self.title.pack(anchor="w")
            self.detail=tk.Label(body,text="Comprobando el sistema",font=("Segoe UI",9),fg="#655d52",bg="#f4efe5"); self.detail.pack(anchor="w",pady=(4,13))
            track=tk.Frame(body,bg="#ded6c9",height=8); track.pack(fill="x"); track.pack_propagate(False)
            self.bar=tk.Frame(track,bg="#2b6aa7",height=8); self.bar.place(relx=0,rely=0,relheight=1,relwidth=.08)
            self.elapsed=tk.Label(body,text="Etapa 1 de 4",font=("Segoe UI",8),fg="#847b70",bg="#f4efe5"); self.elapsed.pack(anchor="e",pady=(8,0))
            self.root=root; root.update_idletasks(); root.update()
        except Exception as exc:
            _log("Splash no disponible: "+repr(exc)); self.root=None
    def set(self, stage:int, title:str, detail:str=""):
        self.stage=max(1,min(4,int(stage)))
        if not self.root: return
        try:
            self.title.config(text=title); self.detail.config(text=detail); self.bar.place_configure(relwidth=max(.08,self.stage/4)); self.pump()
        except Exception as exc: _log("Splash set: "+repr(exc))
    def pump(self):
        if not self.root:return
        try:
            secs=max(0,int(time.monotonic()-self.started)); self.elapsed.config(text=f"{secs} s · etapa {self.stage} de 4" if secs>=2 else f"Etapa {self.stage} de 4")
            self.root.update_idletasks(); self.root.update()
        except Exception: pass
    def close(self):
        try:
            if self.root:self.root.destroy()
        except Exception:pass
        self.root=None


def _vtuple(v: str) -> tuple[int,...]:
    out=[]
    for part in str(v or "0").split("."):
        m=re.match(r"^(\d+)",part); out.append(int(m.group(1)) if m else 0)
    return tuple((out+[0,0,0,0])[:4])


def _load_json(path: Path) -> dict:
    data=json.loads(path.read_text(encoding="utf-8-sig"));
    if not isinstance(data,dict): raise RuntimeError(f"JSON inválido: {path.name}")
    return data


def _local_manifest() -> dict:
    p=ROOT/"update_manifest.json"; return _load_json(p) if p.is_file() else {}


def _local_package_version() -> str:
    return str(_local_manifest().get("version") or _installed_app_version() or "0.0.0").strip()


def _installed_app_version(root: Path = ROOT) -> str:
    try:
        text=(root/"app.py").read_text(encoding="utf-8-sig",errors="ignore")
        m=re.search(r'(?m)^\s*APP_VERSION\s*=\s*["\']([^"\']+)',text)
        return m.group(1).strip() if m else ""
    except Exception:return ""


def _expected_app_version(manifest: dict | None = None) -> str:
    m=manifest or _local_manifest(); return str(m.get("app_version") or m.get("runtime_version") or m.get("version") or "").strip()


def _cache_bust(url:str)->str:
    p=urllib.parse.urlsplit(url); q=urllib.parse.parse_qsl(p.query,keep_blank_values=True); q.append(("hc_ts",str(time.time_ns())))
    return urllib.parse.urlunsplit((p.scheme,p.netloc,p.path,urllib.parse.urlencode(q),p.fragment))


def _fetch_bytes(url:str, attempts:int=3, timeout:float=9)->bytes:
    last=None
    for i in range(max(1,attempts)):
        try:
            req=urllib.request.Request(_cache_bust(url),headers={"User-Agent":f"HistoriaClinicaDrRevelo/{LAUNCHER_VERSION}","Cache-Control":"no-cache","Pragma":"no-cache"})
            with urllib.request.urlopen(req,timeout=timeout) as r:
                if getattr(r,"status",200)!=200: raise RuntimeError(f"HTTP {getattr(r,'status','?')}")
                return r.read()
        except Exception as exc:
            last=exc
            if i+1<attempts: time.sleep(.4*(i+1))
    raise RuntimeError(f"No se pudo descargar {url}: {last}")


def _fetch_manifest() -> dict:
    data=json.loads(_fetch_bytes(DEFAULT_MANIFEST_URL,attempts=3,timeout=8).decode("utf-8-sig"))
    if not isinstance(data,dict) or data.get("product")!=PRODUCT: raise RuntimeError("Canal de actualización inválido")
    if not data.get("version") or not isinstance(data.get("files"),list) or not data.get("files"): raise RuntimeError("Canal de actualización incompleto")
    return data


def _safe_target(relative:str, root:Path=ROOT)->Path:
    rel=str(relative or "").replace("\\","/").lstrip("/"); parts=[x for x in rel.split("/") if x]
    if not parts or any(x in {".",".."} for x in parts): raise RuntimeError("Ruta de actualización inválida")
    if root.resolve()==ROOT.resolve():
        if parts[0].lower() in {x.lower() for x in PROTECTED_TOP}: raise RuntimeError(f"Ruta protegida: {rel}")
        if len(parts)==1 and parts[0].lower() in {x.lower() for x in PROTECTED_FILES}: raise RuntimeError(f"Archivo protegido: {rel}")
    dest=(root/Path(*parts)).resolve(); rr=root.resolve()
    if dest!=rr and rr not in dest.parents: raise RuntimeError("Ruta fuera de la instalación")
    return dest


def _payload_urls(item:dict)->list[str]:
    urls=item.get("parts") or ([item.get("url")] if item.get("url") else [])
    urls=[str(x or "").strip() for x in urls if str(x or "").strip()]
    if not urls: raise RuntimeError(f"{item.get('path')}: sin URL")
    for u in urls:
        if not u.startswith(OFFICIAL_RAW_PREFIX): raise RuntimeError(f"Fuente no autorizada: {u}")
    return urls


def _download_item(item:dict)->bytes:
    payload=b"".join(_fetch_bytes(u) for u in _payload_urls(item)); expected=str(item.get("sha256") or "").lower().strip(); got=hashlib.sha256(payload).hexdigest()
    if not expected or got!=expected: raise RuntimeError(f"SHA inválido para {item.get('path')}")
    return payload


def _required_files(manifest:dict)->list[str]:
    values=manifest.get("required_dependencies") or []
    return [str(v).replace("\\","/").lstrip("/") for v in values if str(v or "").strip()]


def _installation_consistent() -> bool:
    try:
        m=_local_manifest(); expected=_expected_app_version(m)
        if expected and _installed_app_version()!=expected:return False
        for rel in _required_files(m):
            p=_safe_target(rel)
            if not p.is_file():return False
            if p.suffix.lower()==".py": compile(p.read_text(encoding="utf-8-sig"),str(p),"exec")
        return (ROOT/"app.py").is_file() and (ROOT/"cloud_sync.py").is_file()
    except Exception:return False


def _candidate_fingerprint(remote:dict)->str:
    rows=[[str(i.get("path") or ""),str(i.get("sha256") or "")] for i in remote.get("files") or []]
    raw=json.dumps({"version":str(remote.get("version") or ""),"files":rows},sort_keys=True,separators=(",",":")).encode()
    return hashlib.sha256(raw).hexdigest()[:20]


def _candidate_failure_count(remote:dict)->int:
    s=_load_state()
    if s.get("failed_candidate_version")!=str(remote.get("version") or ""):return 0
    if s.get("failed_candidate_fingerprint")!=_candidate_fingerprint(remote):return 0
    try:return int(s.get("failed_candidate_count") or 0)
    except Exception:return 0


def _mark_candidate_failure(remote:dict, exc:BaseException)->int:
    count=_candidate_failure_count(remote)+1
    _write_state(failed_candidate_version=str(remote.get("version") or ""),failed_candidate_fingerprint=_candidate_fingerprint(remote),failed_candidate_count=count,candidate_quarantined=count>=2,candidate_last_error=str(exc)[:1200])
    return count


def _clear_candidate_failure():
    _write_state(failed_candidate_version="",failed_candidate_fingerprint="",failed_candidate_count=0,candidate_quarantined=False,candidate_last_error="")


def _stage_update(remote:dict, splash:Splash|None=None):
    stage=Path(tempfile.mkdtemp(prefix="hc_stage_",dir=str(_data_dir()))); entries=[]
    try:
        files=list(remote.get("files") or []); total=max(1,len(files))
        for idx,item in enumerate(files,1):
            rel=str(item.get("path") or "").replace("\\","/").lstrip("/"); dest=_safe_target(rel); expected=str(item.get("sha256") or "").lower().strip()
            if splash:splash.set(2,"Descargando actualización segura…",f"Archivo {idx} de {total}")
            if dest.is_file() and expected:
                try:
                    if hashlib.sha256(dest.read_bytes()).hexdigest()==expected: continue
                except Exception:pass
            payload=_download_item(item)
            if rel.lower().endswith(".py"): compile(payload.decode("utf-8-sig"),rel,"exec")
            sp=stage/rel; sp.parent.mkdir(parents=True,exist_ok=True); sp.write_bytes(payload)
            entries.append({"rel":rel,"stage":sp,"sha":expected})
        return stage,entries
    except Exception:
        shutil.rmtree(stage,ignore_errors=True); raise


def _sqlite_backup(src:Path,dst:Path):
    dst.parent.mkdir(parents=True,exist_ok=True)
    s=sqlite3.connect(src); d=sqlite3.connect(dst)
    try:s.backup(d)
    finally:d.close();s.close()


def _free_port(prefer:int=DEFAULT_PORT)->int:
    def available(port:int)->bool:
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
            try:s.bind(("127.0.0.1",port));return True
            except OSError:return False
    if available(prefer):return prefer
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1",0));return int(s.getsockname()[1])


def _probe(port:int, timeout:float=.6)->dict:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/version?t={time.time_ns()}",timeout=timeout) as r:
            d=json.loads(r.read().decode("utf-8")); return d if isinstance(d,dict) else {}
    except Exception:return {}


def _python_exe(windowless:bool=False)->Path:
    if os.name=="nt":return ROOT/".venv"/"Scripts"/("pythonw.exe" if windowless else "python.exe")
    return ROOT/".venv"/"bin"/"python"


def _create_venv():
    if _python_exe(False).is_file():return
    subprocess.run([sys.executable,"-m","venv",str(ROOT/".venv")],cwd=str(ROOT),check=True)


def _requirements_hash()->str:
    p=ROOT/"requirements.txt"; return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else ""


def _import_ok(py:Path,module:str)->bool:
    try:return subprocess.run([str(py),"-c",f"import {module}"],cwd=str(ROOT),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0) if os.name=="nt" else 0).returncode==0
    except Exception:return False


def _ensure_dependencies(manifest:dict|None=None, force:bool=False, splash:Splash|None=None):
    """Repara dependencias una por una y deja log útil. WebView es obligatorio."""
    if splash:splash.set(1,"Preparando Historia Clínica…","Comprobando Python y WebView2")
    _create_venv()
    py=_python_exe(False)
    wanted=_requirements_hash()
    marker=_data_dir()/"requirements_state.json"
    logp=_data_dir()/"dependencies_install.log"
    try:old=json.loads(marker.read_text(encoding="utf-8")) if marker.is_file() else {}
    except Exception:old={}
    required=(manifest or _local_manifest()).get("required_python_packages") or []
    need=force or old.get("sha256")!=wanted
    for item in required:
        module=str(item.get("import") or "").strip()
        if module and not _import_ok(py,module): need=True
    if not need:return
    if splash:splash.set(1,"Preparando componentes…","Instalando dependencias de forma segura")
    try:
        with logp.open("a",encoding="utf-8") as log:
            log.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Reparación de dependencias\n")
            for item in required:
                module=str(item.get("import") or "").strip()
                spec=str(item.get("pip") or "").strip()
                if not module or not spec:continue
                if not force and _import_ok(py,module):
                    log.write(f"OK existente: {module}\n");log.flush();continue
                log.write(f"Instalando: {spec}\n");log.flush()
                proc=subprocess.run(
                    [str(py),"-m","pip","install","--disable-pip-version-check","--no-input",
                     "--retries","4","--timeout","60",spec],
                    cwd=str(ROOT),stdin=subprocess.DEVNULL,stdout=log,stderr=log,
                    timeout=420,check=False,
                    creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0) if os.name=="nt" else 0
                )
                if proc.returncode!=0 or not _import_ok(py,module):
                    raise RuntimeError(
                        f"No se pudo instalar el componente obligatorio {spec}. "
                        f"Revisa data\\dependencies_install.log."
                    )
                log.write(f"OK instalado: {module}\n");log.flush()
        marker.write_text(json.dumps({"sha256":wanted,"installed_at":time.time()},indent=2),encoding="utf-8")
    except Exception:
        raise

def _trial_runtime(remote:dict, stage:Path, entries:list[dict], splash:Splash|None=None):
    runtime_changed=any(e["rel"].lower().endswith(".py") and e["rel"].lower()!="abrir_historia_clinica.py" for e in entries)
    if not runtime_changed:return {"tested":False,"reason":"no_runtime_change"}
    trial=Path(tempfile.mkdtemp(prefix="hc_trial_",dir=str(_data_dir()))); proc=None
    try:
        for p in ROOT.glob("*.py"):
            if p.name.lower()=="abrir_historia_clinica.py":continue
            shutil.copy2(p,trial/p.name)
        if (ROOT/"static").is_dir():shutil.copytree(ROOT/"static",trial/"static",dirs_exist_ok=True)
        if (ROOT/"requirements.txt").is_file():shutil.copy2(ROOT/"requirements.txt",trial/"requirements.txt")
        (trial/"data").mkdir(parents=True,exist_ok=True)
        srcdb=ROOT/"data"/"historia_clinica.db"
        if not srcdb.is_file():raise RuntimeError("No existe la base local para la prueba aislada")
        _sqlite_backup(srcdb,trial/"data"/"historia_clinica.db")
        for e in entries:
            rel=e["rel"]
            if rel.lower()=="abrir_historia_clinica.py":continue
            dest=trial/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(e["stage"],dest)
        expected=_expected_app_version(remote); port=_free_port(0); log=trial/"trial_startup.log"
        env=os.environ.copy(); env.pop("HISTORIA_DATABASE_URL",None); env.pop("DATABASE_URL",None); env["HC_PREFLIGHT"]="1";env["PYTHONDONTWRITEBYTECODE"]="1"
        if splash:splash.set(2,"Probando actualización antes de instalar…","Copia aislada · tus historias reales no se tocan")
        with log.open("w",encoding="utf-8") as fh:
            proc=subprocess.Popen([str(_python_exe(False)),"-m","uvicorn","app:app","--host","127.0.0.1","--port",str(port),"--no-access-log","--log-level","warning"],cwd=str(trial),env=env,stdin=subprocess.DEVNULL,stdout=fh,stderr=fh,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0) if os.name=="nt" else 0)
        deadline=time.time()+24
        while time.time()<deadline:
            if proc.poll() is not None:raise RuntimeError("La copia de prueba terminó antes de iniciar.\n"+_tail(log,60))
            d=_probe(port,.45)
            if d.get("version")==expected:return {"tested":True,"ok":True}
            if splash:splash.pump()
            time.sleep(.18)
        raise RuntimeError("La copia de prueba no respondió a tiempo.\n"+_tail(log,60))
    finally:
        if proc is not None and proc.poll() is None:
            try:proc.terminate();proc.wait(timeout=3)
            except Exception:
                try:proc.kill()
                except Exception:pass
        shutil.rmtree(trial,ignore_errors=True)


def _backup_before_update(entries:list[dict],version:str):
    backups=_data_dir()/"update_backups";backups.mkdir(parents=True,exist_ok=True)
    target=backups/f"antes_v{version.replace('.','_')}_{time.strftime('%Y%m%d_%H%M%S')}.zip";existed=set()
    with zipfile.ZipFile(target,"w",zipfile.ZIP_DEFLATED) as z:
        for e in entries:
            rel=e["rel"];p=_safe_target(rel)
            if p.is_file():z.write(p,rel);existed.add(rel)
    old=sorted(backups.glob("antes_v*.zip"),key=lambda p:p.stat().st_mtime,reverse=True)
    for p in old[3:]:
        try:p.unlink()
        except Exception:pass
    return target,existed


def _rollback(backup:Path, entries:list[dict], existed:set[str]):
    for e in entries:
        rel=e["rel"]
        if rel not in existed:
            try:
                p=_safe_target(rel)
                if p.is_file():p.unlink()
            except Exception:pass
    if backup.is_file():
        with zipfile.ZipFile(backup,"r") as z:
            for name in z.namelist():
                dest=_safe_target(name);dest.parent.mkdir(parents=True,exist_ok=True);tmp=dest.with_name(dest.name+".rollback")
                tmp.write_bytes(z.read(name));os.replace(tmp,dest)


def _apply_staged(remote:dict, stage:Path, entries:list[dict]):
    if not entries:return {"updated":False,"paths":[]}
    backup,existed=_backup_before_update(entries,str(remote.get("version") or "update"))
    try:
        for e in entries:
            dest=_safe_target(e["rel"]);dest.parent.mkdir(parents=True,exist_ok=True);tmp=dest.with_name(dest.name+".new")
            shutil.copy2(e["stage"],tmp);os.replace(tmp,dest)
            if hashlib.sha256(dest.read_bytes()).hexdigest()!=e["sha"]:raise RuntimeError(f"Verificación local falló: {e['rel']}")
        return {"updated":True,"paths":[e["rel"] for e in entries],"backup":str(backup),"existed":list(existed)}
    except Exception:
        _rollback(backup,entries,existed);raise


def _check_and_apply_update(remote:dict|None,splash:Splash|None=None):
    """
    Actualizador transaccional v2.

    La antigua copia aislada podía rechazar una actualización válida antes
    de instalarla. Ahora la seguridad se basa en:
      1) SHA-256 de todos los archivos descargados.
      2) compile() de cada archivo Python antes de tocar la instalación.
      3) backup ZIP de todo archivo que será reemplazado.
      4) reemplazo atómico archivo por archivo.
      5) verificación SHA-256 ya instalado.
      6) prueba REAL de arranque; main() hace rollback si falla.

    De este modo nunca se anuncia "descargada" para después descartarla por
    una prueba paralela que no representa la instalación real.
    """
    local=_local_package_version()
    coherent=_installation_consistent()
    if remote is None:
        return {"updated":False,"deferred":True,"local":local}

    rv=str(remote.get("version") or "")
    should=_vtuple(rv)>_vtuple(local) or (rv==local and not coherent)
    if not should:
        return {"updated":False,"version":local}

    failures=_candidate_failure_count(remote)
    if coherent and failures>=2:
        msg=f"La actualización {rv} quedó en cuarentena después de dos fallos. Se conserva la última versión estable."
        _write_state(candidate_quarantined=True,candidate_last_error=msg,last_update_ok=False)
        _log(msg)
        return {"updated":False,"deferred":True,"candidate_quarantined":True,"version":local,"error":msg}

    stage=None
    entries=[]
    try:
        if splash:
            splash.set(2,"Descargando actualización…","Verificando integridad archivo por archivo")
        stage,entries=_stage_update(remote,splash)
        if not entries:
            _clear_candidate_failure()
            return {"updated":False,"version":rv or local}

        if splash:
            splash.set(3,"Instalando actualización…","Respaldo automático y reemplazo verificado")
        result=_apply_staged(remote,stage,entries)
        result["version"]=rv
        result["entries"]=[{"rel":e["rel"]} for e in entries]
        _clear_candidate_failure()
        _write_state(
            last_update_version=rv,
            last_update_ok=True,
            updater_mode="transactional-v2",
            candidate_quarantined=False,
            candidate_last_error="",
        )
        _log(f"Actualización transaccional aplicada: {local} -> {rv}; archivos={len(entries)}")
        return result
    except Exception as exc:
        count=_mark_candidate_failure(remote,exc)
        _write_state(last_update_ok=False,updater_mode="transactional-v2",last_apply_error=str(exc)[:1200])
        _log(f"Actualización {rv} falló durante descarga/aplicación #{count}: {exc}")
        return {
            "updated":False,
            "candidate_failed":True,
            "error":str(exc),
            "version":local,
        }
    finally:
        if stage is not None:
            shutil.rmtree(stage,ignore_errors=True)

def _pid_for_port(port:int)->int|None:
    if os.name!="nt":return None
    try:
        out=subprocess.check_output(["netstat","-ano","-p","tcp"],text=True,errors="ignore",creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        needle=f":{int(port)}"
        for line in out.splitlines():
            if "LISTENING" not in line.upper() or needle not in line:continue
            parts=line.split()
            if len(parts)>=5:
                try:return int(parts[-1])
                except Exception:pass
    except Exception:pass
    return None


def _stop_backend(port:int|None=None,pid:int|None=None):
    target=pid or (_pid_for_port(port) if port else None)
    if target and os.name=="nt":
        try:subprocess.run(["taskkill","/PID",str(target),"/T","/F"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=8,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        except Exception:pass
    if port:
        deadline=time.time()+6
        while time.time()<deadline:
            if not _probe(port,.2):break
            time.sleep(.15)


def _find_running_backend():
    s=_load_state(); ports=[]
    for p in [s.get("active_port"),DEFAULT_PORT]:
        try:p=int(p)
        except Exception:continue
        if p not in ports:ports.append(p)
    for port in ports:
        d=_probe(port,.35)
        if d and (d.get("product")==PRODUCT or str(d.get("version") or "").startswith("1.")):
            return port,d
    return None,{}


def _start_server(port:int,splash:Splash|None=None):
    if splash:splash.set(3,"Iniciando Historia Clínica…","Abriendo base local y sincronización")
    logp=_data_dir()/"backend_startup.log"; fh=logp.open("a",encoding="utf-8")
    proc=subprocess.Popen([str(_python_exe(False)),"-m","uvicorn","app:app","--host","127.0.0.1","--port",str(port),"--no-access-log","--log-level","warning"],cwd=str(ROOT),stdin=subprocess.DEVNULL,stdout=fh,stderr=fh,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0) if os.name=="nt" else 0)
    expected=_expected_app_version(); deadline=time.time()+30
    while time.time()<deadline:
        if proc.poll() is not None:
            raise RuntimeError("El backend terminó antes de iniciar.\n"+_tail(logp,80))
        d=_probe(port,.5)
        if d.get("version")==expected:
            _write_state(active_port=port,backend_pid=proc.pid,startup_verified_version=expected,last_known_good_version=expected,last_start_ok=True)
            return proc
        if splash:splash.pump()
        time.sleep(.2)
    try:proc.terminate()
    except Exception:pass
    raise RuntimeError("Historia Clínica tardó demasiado en iniciar.\n"+_tail(logp,80))


def _edge_exe()->Path|None:
    if os.name!="nt":return None
    for p in [Path(os.environ.get("PROGRAMFILES(X86)",""))/"Microsoft/Edge/Application/msedge.exe",Path(os.environ.get("PROGRAMFILES", ""))/"Microsoft/Edge/Application/msedge.exe",Path(os.environ.get("LOCALAPPDATA", ""))/"Microsoft/Edge/Application/msedge.exe"]:
        if p.is_file():return p
    return None


def _open_ui(port:int)->bool:
    """Abre EXCLUSIVAMENTE dentro de WebView2. Nunca usa navegador."""
    url=f"http://127.0.0.1:{port}"
    try:
        import webview
    except Exception as exc:
        _log("pywebview obligatorio no disponible: "+repr(exc))
        raise RuntimeError(
            "No está disponible el componente WebView de Historia Clínica. "
            "Ejecuta el reparador Full WebView. No se abrirá ningún navegador."
        ) from exc
    kwargs={"gui":"edgechromium","debug":False,"private_mode":False,
            "storage_path":str(_data_dir()/"webview_profile")}
    icon=ROOT/"static"/"doctor_icon.ico"
    if icon.is_file():kwargs["icon"]=str(icon)
    try:
        try:
            window=webview.create_window(
                TITLE,url,width=1440,height=900,min_size=(1050,700),
                resizable=True,text_select=True,maximized=True
            )
            maximize=False
        except TypeError:
            window=webview.create_window(
                TITLE,url,width=1440,height=900,min_size=(1050,700),
                resizable=True,text_select=True
            )
            maximize=True
        if maximize:
            def on_start():
                try:window.maximize()
                except Exception:pass
            webview.start(on_start,**kwargs)
        else:
            webview.start(**kwargs)
        return True
    except Exception as exc:
        _log("WebView2 obligatorio falló: "+repr(exc)+" | "+traceback.format_exc(limit=4).replace("\n"," | "))
        raise RuntimeError(
            "WebView2 no pudo iniciar. Historia Clínica no abrirá Edge ni otro navegador. "
            "Ejecuta el reparador Full WebView y revisa data\\launcher.log."
        ) from exc

def _relaunch():
    pyw=_python_exe(True); py=pyw if pyw.is_file() else _python_exe(False); flags=getattr(subprocess,"CREATE_NO_WINDOW",0) if os.name=="nt" else 0
    if os.name=="nt":flags|=getattr(subprocess,"CREATE_NEW_PROCESS_GROUP",0)
    subprocess.Popen([str(py),str(ROOT/"ABRIR_HISTORIA_CLINICA.py")],cwd=str(ROOT),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=flags)


def _acquire_mutex():
    if os.name!="nt":return None,False
    h=ctypes.windll.kernel32.CreateMutexW(None,False,MUTEX_NAME); already=ctypes.windll.kernel32.GetLastError()==183
    return h,already


def _release_mutex(h):
    if os.name=="nt" and h:
        try:ctypes.windll.kernel32.ReleaseMutex(h);ctypes.windll.kernel32.CloseHandle(h)
        except Exception:pass


def prepare()->int:
    _set_windows_identity()
    _ensure_brand_icon()
    _ensure_windows_shortcuts()
    splash=Splash()
    try:
        _ensure_dependencies(_local_manifest(),splash=splash)
        if not _installation_consistent():raise RuntimeError("La instalación no quedó coherente después de preparar dependencias")
        splash.set(4,"Todo listo","Historia Clínica quedó preparada");time.sleep(.3);return 0
    except Exception as exc:
        _log("Prepare falló: "+repr(exc));_show_failure("No se pudo preparar Historia Clínica",str(exc));return 2
    finally:splash.close()


def self_test()->int:
    assert _vtuple("1.10.0")>_vtuple("1.9.9")
    for rel in ("data/x",".env"):
        try:_safe_target(rel);raise AssertionError(rel)
        except RuntimeError:pass
    for rel in ("app.py","cloud_sync.py"):
        compile((ROOT/rel).read_text(encoding="utf-8"),rel,"exec")
    print("SELF_TEST_OK");return 0


def main():
    _set_windows_identity()
    _ensure_brand_icon()
    _ensure_windows_shortcuts()
    _log(f"Launcher {LAUNCHER_VERSION} iniciado")
    splash=Splash(); handle=None; server=None; update_result={}
    try:
        handle,already=_acquire_mutex()
        if already:
            port,d=_find_running_backend()
            if port:
                splash.set(4,"Historia Clínica ya está abierta","Mostrando el programa");time.sleep(.15);splash.close();_open_ui(port);return
            deadline=time.time()+8
            while time.time()<deadline:
                port,d=_find_running_backend()
                if port:splash.close();_open_ui(port);return
                splash.pump();time.sleep(.25)
            splash.close();_message("Historia Clínica parece estar iniciándose en otra ventana. Si no aparece en unos segundos, vuelve a abrir el acceso directo.")
            return

        remote=None
        try:
            splash.set(1,"Verificando actualización…","Comprobando versión y seguridad del paquete")
            remote=_fetch_manifest()
        except Exception as exc:
            _log("No se pudo consultar el canal: "+repr(exc))

        port,d=_find_running_backend()
        local=_local_package_version(); remote_v=str((remote or {}).get("version") or "")
        mandatory=bool((remote or {}).get("mandatory")) and remote_v and _vtuple(remote_v)>_vtuple(local)
        if port and not mandatory:
            splash.set(4,"Historia Clínica ya está abierta","Mostrando el programa");time.sleep(.15);splash.close();_open_ui(port);return
        if port and mandatory:
            _log(f"Cerrando backend {d.get('version')} para actualización obligatoria {remote_v}")
            _stop_backend(port,int(_load_state().get("backend_pid") or 0) or None)

        _ensure_dependencies(remote or _local_manifest(),splash=splash)
        update_result=_check_and_apply_update(remote,splash)
        if update_result.get("candidate_failed"):
            err=str(update_result.get("error") or "Error desconocido")
            splash.set(2,"No se pudo instalar la actualización","Se abrirá la versión anterior · el error quedó registrado")
            _log("Actualización no aplicada: "+err);time.sleep(.65)

        paths={str(x).replace("\\","/").lower() for x in update_result.get("paths",[])}
        if update_result.get("updated") and "abrir_historia_clinica.py" in paths:
            splash.set(3,"Aplicando launcher blindado…","Reinicio seguro");time.sleep(.25);splash.close();_release_mutex(handle);handle=None;_relaunch();return

        _ensure_dependencies(_local_manifest(),force=bool(update_result.get("updated") and "requirements.txt" in paths),splash=splash)
        if not _installation_consistent():raise RuntimeError("La instalación local no es coherente. El launcher no iniciará una versión incompleta.")
        port=_free_port(DEFAULT_PORT)
        try:
            server=_start_server(port,splash)
        except Exception as start_exc:
            if update_result.get("updated") and update_result.get("backup"):
                _log("Startup post-update falló; rollback automático: "+repr(start_exc))
                # Reconstruir entradas mínimas desde paths para restaurar.
                entries=[{"rel":rel} for rel in update_result.get("paths",[])]
                _rollback(Path(update_result["backup"]),entries,set(update_result.get("existed") or []))
                fail_count=_mark_candidate_failure(remote,start_exc) if remote else 1
                _write_state(
                    last_update_ok=False,
                    rollback_after_startup=True,
                    last_start_error=str(start_exc)[:1200],
                    candidate_quarantined=fail_count>=2,
                )
                splash.set(3,"Recuperando versión estable…","La actualización falló al arrancar; revirtiendo cambios")
                time.sleep(.4);splash.close();_release_mutex(handle);handle=None;_relaunch();return
            raise

        splash.set(4,"Todo listo","Abriendo Historia Clínica");time.sleep(.2);splash.close()
        _open_ui(port)
    except Exception as exc:
        splash.close();_write_state(last_start_ok=False,last_start_error=str(exc)[:1400])
        diag=str(exc)+"\n\n--- launcher.log ---\n"+_tail(_data_dir()/"launcher.log",60)+"\n\n--- backend_startup.log ---\n"+_tail(_data_dir()/"backend_startup.log",80)
        _log("Fallo fatal: "+repr(exc)+" | "+traceback.format_exc(limit=8).replace("\n"," | "))
        _show_failure("No se pudo abrir Historia Clínica",diag)
    finally:
        splash.close()
        if server is not None and server.poll() is None:
            try:server.terminate();server.wait(timeout=4)
            except Exception:
                try:server.kill()
                except Exception:pass
        if server is not None:_write_state(active_port=None,backend_pid=None)
        _release_mutex(handle)


if __name__=="__main__":
    if "--prepare" in sys.argv:raise SystemExit(prepare())
    if "--self-test" in sys.argv:raise SystemExit(self_test())
    main()
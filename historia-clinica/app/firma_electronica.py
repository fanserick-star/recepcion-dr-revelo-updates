from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse


_LOCK = threading.RLock()
_SESSION = {
    "passphrase": None,
    "expires_at": 0.0,
    "subject": "",
    "serial": "",
    "not_after": "",
}
_DEFAULT_SESSION_SECONDS = 8 * 60 * 60


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _is_local_request(request: Request) -> bool:
    host = str(getattr(getattr(request, "client", None), "host", "") or "").strip().lower()
    return host in {"127.0.0.1", "::1", "localhost"}


def _require_local(request: Request) -> None:
    if not _is_local_request(request):
        raise HTTPException(status_code=403, detail="La firma electrónica solo se administra desde esta PC.")


def _paths(root: Path) -> dict[str, Path]:
    root = Path(root)
    firma_dir = root / "data" / "firma_electronica"
    signed_dir = root / "data" / "documentos_firmados"
    return {
        "firma_dir": firma_dir,
        "signed_dir": signed_dir,
        "config": firma_dir / "config.json",
        "certificate": firma_dir / "certificado_doctor.p12",
    }


def _load_config(root: Path) -> dict:
    paths = _paths(root)
    defaults = {
        "certificate_path": str(paths["certificate"]),
        "doctor_name": "Dr. Armando Revelo",
        "enabled": True,
    }
    try:
        data = json.loads(paths["config"].read_text(encoding="utf-8"))
        if isinstance(data, dict):
            defaults.update(data)
    except Exception:
        pass
    return defaults


def _save_config(root: Path, config: dict) -> None:
    paths = _paths(root)
    paths["firma_dir"].mkdir(parents=True, exist_ok=True)
    safe = {
        "certificate_path": str(config.get("certificate_path") or paths["certificate"]),
        "doctor_name": str(config.get("doctor_name") or "Dr. Armando Revelo"),
        "enabled": bool(config.get("enabled", True)),
        "updated_at": _now_iso(),
    }
    tmp = paths["config"].with_suffix(".tmp")
    tmp.write_text(json.dumps(safe, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, paths["config"])


def _certificate_path(root: Path) -> Path:
    config = _load_config(root)
    raw = str(config.get("certificate_path") or "").strip()
    return Path(raw) if raw else _paths(root)["certificate"]


def _session_clear() -> None:
    with _LOCK:
        _SESSION["passphrase"] = None
        _SESSION["expires_at"] = 0.0
        _SESSION["subject"] = ""
        _SESSION["serial"] = ""
        _SESSION["not_after"] = ""


def _session_passphrase() -> bytes | None:
    with _LOCK:
        if not _SESSION.get("passphrase"):
            return None
        if time.time() >= float(_SESSION.get("expires_at") or 0):
            _session_clear()
            return None
        value = _SESSION.get("passphrase")
        return bytes(value) if isinstance(value, (bytes, bytearray)) else None


def _certificate_metadata(signer) -> dict:
    cert = getattr(signer, "signing_cert", None)
    if cert is None:
        return {"subject": "", "serial": "", "not_after": ""}
    try:
        subject = str(cert.subject.human_friendly or "")
    except Exception:
        subject = ""
    try:
        serial = str(cert.serial_number)
    except Exception:
        serial = ""
    try:
        not_after = cert.not_valid_after.native.isoformat()
    except Exception:
        try:
            not_after = str(cert.not_valid_after.native)
        except Exception:
            not_after = ""
    return {"subject": subject, "serial": serial, "not_after": not_after}


def _load_signer(root: Path, passphrase: bytes | None = None):
    try:
        from pyhanko.sign import signers
    except Exception as exc:
        raise RuntimeError(
            "Falta el componente de firma electrónica. Reabra Historia Clínica para completar la actualización."
        ) from exc
    cert_path = _certificate_path(root)
    if not cert_path.is_file():
        raise FileNotFoundError("No hay un certificado electrónico configurado en esta PC.")
    signer = signers.SimpleSigner.load_pkcs12(
        pfx_file=str(cert_path),
        passphrase=passphrase,
    )
    if signer is None:
        raise ValueError("No se pudo abrir el certificado. Verifique el archivo y la contraseña.")
    return signer


def _unlock(root: Path, password: str, ttl_seconds: int = _DEFAULT_SESSION_SECONDS) -> dict:
    raw = str(password or "")
    if not raw:
        raise ValueError("Ingrese la contraseña del certificado electrónico.")
    passphrase = raw.encode("utf-8")
    signer = _load_signer(root, passphrase)
    meta = _certificate_metadata(signer)
    ttl = max(15 * 60, min(int(ttl_seconds or _DEFAULT_SESSION_SECONDS), 12 * 60 * 60))
    with _LOCK:
        _SESSION["passphrase"] = passphrase
        _SESSION["expires_at"] = time.time() + ttl
        _SESSION["subject"] = meta["subject"]
        _SESSION["serial"] = meta["serial"]
        _SESSION["not_after"] = meta["not_after"]
    return meta


def _status(root: Path) -> dict:
    cert_path = _certificate_path(root)
    passphrase = _session_passphrase()
    with _LOCK:
        expires_at = float(_SESSION.get("expires_at") or 0)
        meta = {
            "subject": str(_SESSION.get("subject") or ""),
            "serial": str(_SESSION.get("serial") or ""),
            "not_after": str(_SESSION.get("not_after") or ""),
        }
    return {
        "configured": cert_path.is_file(),
        "unlocked": passphrase is not None,
        "certificate_name": cert_path.name if cert_path.is_file() else "",
        "certificate_path": str(cert_path) if cert_path.is_file() else "",
        "expires_in_seconds": max(0, int(expires_at - time.time())) if passphrase else 0,
        **meta,
    }


def _select_certificate_windows() -> str:
    if os.name != "nt":
        raise RuntimeError("La selección automática del certificado está disponible solo en Windows.")
    ps = r"""
Add-Type -AssemblyName System.Windows.Forms
$dlg = New-Object System.Windows.Forms.OpenFileDialog
$dlg.Filter = 'Certificado PKCS#12 (*.p12;*.pfx)|*.p12;*.pfx|Todos los archivos (*.*)|*.*'
$dlg.Title = 'Seleccione la firma electrónica del doctor'
$dlg.Multiselect = $false
if ($dlg.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
  [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
  Write-Output $dlg.FileName
}
"""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-STA", "-Command", ps],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        creationflags=flags,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or "No se pudo abrir el selector de certificados.").strip())
    return (proc.stdout or "").strip().splitlines()[-1].strip() if (proc.stdout or "").strip() else ""


def _install_certificate(root: Path, source: Path) -> Path:
    source = Path(source)
    if not source.is_file() or source.suffix.lower() not in {".p12", ".pfx"}:
        raise ValueError("Seleccione un certificado .p12 o .pfx válido.")
    paths = _paths(root)
    paths["firma_dir"].mkdir(parents=True, exist_ok=True)
    target = paths["certificate"]
    tmp = target.with_suffix(target.suffix + ".tmp")
    shutil.copy2(source, tmp)
    os.replace(tmp, target)
    config = _load_config(root)
    config["certificate_path"] = str(target)
    _save_config(root, config)
    _session_clear()
    return target


def _find_edge() -> Path:
    candidates = []
    for env_name in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        base = os.environ.get(env_name)
        if not base:
            continue
        candidates.extend([
            Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
            Path(base) / "Microsoft" / "Edge Beta" / "Application" / "msedge.exe",
        ])
    for path in candidates:
        if path.is_file():
            return path
    found = shutil.which("msedge") or shutil.which("msedge.exe")
    if found:
        return Path(found)
    raise FileNotFoundError("Microsoft Edge no está disponible para generar el PDF firmado.")


def _render_pdf_from_url(url: str, output: Path) -> None:
    edge = _find_edge()
    output.parent.mkdir(parents=True, exist_ok=True)
    profile_dir = Path(tempfile.mkdtemp(prefix="historia_firma_edge_"))
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    variants = ["--headless=new", "--headless"]
    last_error = ""
    try:
        for headless in variants:
            try:
                if output.exists():
                    output.unlink()
            except Exception:
                pass
            cmd = [
                str(edge),
                headless,
                "--disable-gpu",
                "--no-first-run",
                "--disable-extensions",
                "--no-pdf-header-footer",
                "--print-to-pdf-no-header",
                f"--user-data-dir={profile_dir}",
                f"--print-to-pdf={output}",
                url,
            ]
            proc = subprocess.run(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=60,
                check=False,
                creationflags=flags,
            )
            if proc.returncode == 0 and output.is_file() and output.stat().st_size > 500:
                return
            last_error = (proc.stderr or proc.stdout or b"").decode("utf-8", errors="replace").strip()
        raise RuntimeError(last_error or "Edge no pudo generar el PDF del documento.")
    finally:
        shutil.rmtree(profile_dir, ignore_errors=True)


def _sign_pdf(root: Path, source_pdf: Path, signed_pdf: Path, doctor_name: str) -> dict:
    passphrase = _session_passphrase()
    if passphrase is None:
        raise PermissionError("La firma electrónica está bloqueada. Ingrese la contraseña en Configuración.")
    signer = _load_signer(root, passphrase)
    meta = _certificate_metadata(signer)
    try:
        from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
        from pyhanko.sign import signers
        from pyhanko.sign.fields import SigSeedSubFilter
    except Exception as exc:
        raise RuntimeError("No se pudo cargar el componente PAdES de firma electrónica.") from exc

    signature_meta = signers.PdfSignatureMetadata(
        field_name="FirmaElectronicaDoctor",
        md_algorithm="sha256",
        subfilter=SigSeedSubFilter.PADES,
        reason="Documento clínico emitido por el consultorio",
        location="Quevedo, Ecuador",
        name=str(doctor_name or "Dr. Armando Revelo"),
    )
    signed_pdf.parent.mkdir(parents=True, exist_ok=True)
    with source_pdf.open("rb") as inf, signed_pdf.open("wb") as outf:
        writer = IncrementalPdfFileWriter(inf)
        signers.PdfSigner(signature_meta=signature_meta, signer=signer).sign_pdf(writer, output=outf)
    if not signed_pdf.is_file() or signed_pdf.stat().st_size <= source_pdf.stat().st_size:
        raise RuntimeError("No se pudo completar la firma criptográfica del PDF.")
    return meta


def _safe_doc_id(value: str) -> str:
    raw = str(value or "").strip()
    if not raw or len(raw) > 100 or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for ch in raw):
        raise ValueError("Identificador de documento inválido.")
    return raw


def _ensure_audit_schema(db_path: Path) -> None:
    conn = sqlite3.connect(db_path, timeout=15)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS electronic_signatures(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              document_type TEXT NOT NULL,
              document_id TEXT NOT NULL,
              signed_at TEXT NOT NULL,
              certificate_subject TEXT,
              certificate_serial TEXT,
              pdf_sha256 TEXT NOT NULL,
              relative_path TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_electronic_signatures_doc ON electronic_signatures(document_type,document_id,signed_at DESC)"
        )
        conn.commit()
    finally:
        conn.close()


def _document_exists(db_path: Path, kind: str, doc_id: str) -> bool:
    conn = sqlite3.connect(db_path, timeout=15)
    try:
        if kind == "receta":
            row = conn.execute(
                "SELECT 1 FROM prescriptions WHERE id=? AND COALESCE(deleted_at,'')='' LIMIT 1",
                (doc_id,),
            ).fetchone()
        elif kind == "reposo":
            row = conn.execute(
                """SELECT 1 FROM certificates
                   WHERE id=? AND COALESCE(deleted_at,'')=''
                     AND COALESCE(certificate_type,'medical')='rest_isolation'
                   LIMIT 1""",
                (doc_id,),
            ).fetchone()
        else:
            row = conn.execute(
                """SELECT 1 FROM certificates
                   WHERE id=? AND COALESCE(deleted_at,'')=''
                     AND COALESCE(certificate_type,'medical')<>'rest_isolation'
                   LIMIT 1""",
                (doc_id,),
            ).fetchone()
        return bool(row)
    finally:
        conn.close()


def _audit_signature(db_path: Path, root: Path, kind: str, doc_id: str, pdf_path: Path, meta: dict) -> None:
    digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    try:
        relative = str(pdf_path.relative_to(root))
    except Exception:
        relative = str(pdf_path)
    conn = sqlite3.connect(db_path, timeout=15)
    try:
        conn.execute(
            """INSERT INTO electronic_signatures(
                 document_type,document_id,signed_at,certificate_subject,certificate_serial,pdf_sha256,relative_path
               ) VALUES(?,?,?,?,?,?,?)""",
            (
                kind,
                doc_id,
                _now_iso(),
                str(meta.get("subject") or ""),
                str(meta.get("serial") or ""),
                digest,
                relative,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _page_html(base, status: dict) -> str:
    configured = bool(status.get("configured"))
    unlocked = bool(status.get("unlocked"))
    state_title = "Lista para firmar" if unlocked else ("Certificado configurado · bloqueado" if configured else "Sin configurar")
    state_detail = (
        "La contraseña está activa solo durante esta sesión de Historia Clínica."
        if unlocked
        else "La contraseña nunca se guarda en disco, Neon ni .env."
    )
    body = f"""
<section class='page-head'>
  <span class='eyebrow'>SEGURIDAD LOCAL</span>
  <h1>Firma electrónica</h1>
  <p class='muted'>Firma PAdES para recetas y certificados. El certificado queda únicamente en esta PC.</p>
</section>
<section class='panel' style='max-width:900px;margin:0 auto;padding:18px'>
  <div style='display:grid;grid-template-columns:1fr 1fr;gap:14px'>
    <div style='border:1px solid #d8e1ea;border-radius:14px;padding:16px'>
      <strong style='display:block;font-size:16px'>{state_title}</strong>
      <span style='display:block;color:#64748b;margin-top:5px'>{state_detail}</span>
      <div id='firma-cert' style='margin-top:12px;font-size:13px;color:#334155'>
        {('Archivo: '+str(status.get('certificate_name') or '')) if configured else 'Seleccione el archivo .p12 o .pfx del doctor.'}
      </div>
      <button id='firma-select' class='secondary' style='margin-top:12px'>Seleccionar certificado</button>
    </div>
    <div style='border:1px solid #d8e1ea;border-radius:14px;padding:16px'>
      <label style='display:block;font-weight:800'>Contraseña del certificado
        <input id='firma-password' type='password' autocomplete='off' style='width:100%;margin-top:7px'>
      </label>
      <div style='display:flex;gap:8px;flex-wrap:wrap;margin-top:12px'>
        <button id='firma-unlock' class='primary'>Activar firma</button>
        <button id='firma-lock' class='secondary'>Bloquear</button>
      </div>
      <small style='display:block;color:#64748b;margin-top:10px'>Se desbloquea por hasta 8 horas o hasta cerrar Historia Clínica.</small>
    </div>
  </div>
  <div id='firma-result' style='margin-top:14px;border-radius:12px;padding:12px;background:#f8fafc;color:#334155'>Cargando estado…</div>
</section>
<script>
async function firmaStatus(){
  const r=await fetch('/api/firma/status?t='+Date.now(),{cache:'no-store'}); const s=await r.json();
  const box=document.getElementById('firma-result');
  const mins=Math.max(0,Math.ceil(Number(s.expires_in_seconds||0)/60));
  box.innerHTML=(s.unlocked?'<b>✓ Firma activa</b> · '+mins+' min restantes':'<b>'+ (s.configured?'Certificado cargado, firma bloqueada':'Firma sin configurar') +'</b>')
    +(s.subject?'<br><small>'+String(s.subject).replace(/[<>]/g,'')+'</small>':'');
}
document.getElementById('firma-select').onclick=async()=>{
  const r=await fetch('/api/firma/seleccionar-certificado',{method:'POST'}); const j=await r.json();
  if(!r.ok||!j.ok)alert(j.error||'No se pudo seleccionar el certificado'); else firmaStatus();
};
document.getElementById('firma-unlock').onclick=async()=>{
  const password=document.getElementById('firma-password').value;
  const r=await fetch('/api/firma/desbloquear',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password})}); const j=await r.json();
  document.getElementById('firma-password').value='';
  if(!r.ok||!j.ok)alert(j.error||'No se pudo activar la firma'); else firmaStatus();
};
document.getElementById('firma-lock').onclick=async()=>{await fetch('/api/firma/bloquear',{method:'POST'}); firmaStatus();};
firmaStatus();
</script>
"""
    return base("Firma electrónica", body, "configuracion")


def install(app, context: dict) -> None:
    root = Path(context["ROOT"])
    db_path = Path(context["DB_PATH"])
    base = context["base"]
    doctor_name = str(context.get("DOCTOR_NAME") or "Dr. Armando Revelo")
    _paths(root)["firma_dir"].mkdir(parents=True, exist_ok=True)
    _paths(root)["signed_dir"].mkdir(parents=True, exist_ok=True)
    _ensure_audit_schema(db_path)

    @app.get("/firma-electronica", response_class=HTMLResponse)
    def firma_page(request: Request):
        _require_local(request)
        return HTMLResponse(_page_html(base, _status(root)))

    @app.get("/api/firma/status")
    def firma_status(request: Request):
        _require_local(request)
        return JSONResponse({"ok": True, **_status(root)})

    @app.post("/api/firma/seleccionar-certificado")
    def firma_select(request: Request):
        _require_local(request)
        try:
            selected = _select_certificate_windows()
            if not selected:
                return JSONResponse({"ok": False, "error": "Selección cancelada."}, status_code=400)
            target = _install_certificate(root, Path(selected))
            return JSONResponse({"ok": True, "certificate_name": target.name})
        except Exception as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    @app.post("/api/firma/desbloquear")
    async def firma_unlock(request: Request):
        _require_local(request)
        try:
            payload = await request.json()
            meta = _unlock(root, str(payload.get("password") or ""), _DEFAULT_SESSION_SECONDS)
            return JSONResponse({"ok": True, **meta, **_status(root)})
        except Exception as exc:
            _session_clear()
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    @app.post("/api/firma/bloquear")
    def firma_lock(request: Request):
        _require_local(request)
        _session_clear()
        return JSONResponse({"ok": True})

    @app.get("/api/firma/documento/{kind}/{doc_id}")
    def firma_document(request: Request, kind: str, doc_id: str):
        _require_local(request)
        kind = str(kind or "").strip().lower()
        if kind not in {"receta", "certificado", "reposo"}:
            raise HTTPException(status_code=404, detail="Tipo de documento no soportado.")
        try:
            doc_id = _safe_doc_id(doc_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not _document_exists(db_path, kind, doc_id):
            raise HTTPException(status_code=404, detail="Documento no encontrado.")
        if _session_passphrase() is None:
            return JSONResponse(
                {"ok": False, "error": "Firma electrónica bloqueada. Abra Configuración > Firma electrónica e ingrese la contraseña."},
                status_code=423,
            )

        if kind == "receta":
            preview_path = f"/recetas/{quote(doc_id)}/vista"
        elif kind == "reposo":
            preview_path = f"/certificados/reposo/{quote(doc_id)}/vista"
        else:
            preview_path = f"/certificados/{quote(doc_id)}/vista"
        base_url = str(request.base_url).rstrip("/")
        preview_url = base_url + preview_path
        now = datetime.now()
        dest_dir = _paths(root)["signed_dir"] / now.strftime("%Y") / now.strftime("%m")
        final_pdf = dest_dir / f"{kind}_{doc_id}_{now.strftime('%Y%m%d_%H%M%S')}_firmado.pdf"
        temp_fd, temp_name = tempfile.mkstemp(prefix="historia_unsigned_", suffix=".pdf")
        os.close(temp_fd)
        temp_pdf = Path(temp_name)
        try:
            _render_pdf_from_url(preview_url, temp_pdf)
            meta = _sign_pdf(root, temp_pdf, final_pdf, doctor_name)
            _audit_signature(db_path, root, kind, doc_id, final_pdf, meta)
        except PermissionError as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=423)
        except Exception as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
        finally:
            try:
                temp_pdf.unlink(missing_ok=True)
            except Exception:
                pass

        filename = (
            "Receta_firmada.pdf"
            if kind == "receta"
            else ("Certificado_reposo_firmado.pdf" if kind == "reposo" else "Certificado_firmado.pdf")
        )
        return FileResponse(
            final_pdf,
            media_type="application/pdf",
            filename=filename,
            headers={"Cache-Control": "no-store"},
            content_disposition_type="inline",
        )

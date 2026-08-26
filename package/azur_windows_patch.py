from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from urllib.parse import urlparse


def _origin(value: str) -> str:
    raw = (value or "").strip()
    if "://" not in raw:
        raw = "https://" + raw
    p = urlparse(raw)
    host = (p.hostname or "").lower().strip(".")
    if p.scheme.lower() != "https" or not (host == "azur.com.ec" or host.endswith(".azur.com.ec")):
        raise ValueError("La dirección debe pertenecer a https://azur.com.ec")
    return f"https://{host}"


def _curl_post(url: str, payload: dict, timeout: int, secret: str) -> tuple[int, object, str]:
    curl = shutil.which("curl.exe") or shutil.which("curl")
    if not curl:
        raise RuntimeError("Windows no encontró curl.exe")

    fd, temp_path = tempfile.mkstemp(prefix="azur_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False)
        marker = "\n__HTTP__:%{http_code}"
        cmd = [
            curl, "--silent", "--show-error", "--location",
            "--connect-timeout", "8", "--max-time", str(max(10, timeout)),
            "--request", "POST",
            "--header", "Content-Type: application/json",
            "--header", "Accept: application/json",
            "--data-binary", "@" + temp_path,
            "--write-out", marker,
            url,
        ]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(14, timeout + 4),
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        out = proc.stdout or ""
        err = (proc.stderr or "").strip()
        tag = "__HTTP__:"
        if tag not in out:
            raise RuntimeError((err or f"curl terminó con código {proc.returncode}")[:600])
        body, code = out.rsplit(tag, 1)
        status = int(code.strip() or 0)
        safe = body.replace(secret, "[API_KEY_OCULTA]")[:4000] if secret else body[:4000]
        try:
            data = json.loads(safe) if safe.strip() else {}
        except Exception:
            data = None
        return status, data, safe
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("tiempo de espera agotado al conectar con AZUR") from exc
    finally:
        try:
            os.unlink(temp_path)
        except Exception:
            pass


def install(core) -> None:
    def test_connection(base_url: str, api_key: str, timeout: int = 12):
        key = (api_key or "").strip()
        if not key:
            raise core.AzurError("La API key de AZUR no está configurada")
        try:
            base = _origin(base_url)
        except Exception as exc:
            raise core.AzurError(str(exc)) from exc

        url = base + "/plataforma/api/v2/consulta/comprobante"
        payload = {
            "api_key": key,
            "claveacceso": "0" * 49,
            "clave_acceso": "0" * 49,
        }
        try:
            status, data, text = _curl_post(url, payload, timeout, key)
        except Exception as exc:
            raise core.AzurError("AZUR no devolvió respuesta HTTP: " + str(exc)) from exc

        flat = (json.dumps(data, ensure_ascii=False) if isinstance(data, (dict, list)) else text).lower()
        if status in (401, 403) or any(x in flat for x in ("api key invál", "api_key invál", "api key invalid", "unauthorized", "forbidden")):
            return {
                "ok": False,
                "reachable": True,
                "api_key_valid": False,
                "endpoint": url,
                "status": status,
                "message": "AZUR respondió, pero rechazó la API key.",
            }
        if status in (404, 405) and (not isinstance(data, (dict, list))):
            url2 = base + "/api/v2/consulta/comprobante"
            try:
                status, data, text = _curl_post(url2, payload, timeout, key)
                url = url2
            except Exception as exc:
                raise core.AzurError("AZUR respondió en el dominio, pero no en la ruta API: " + str(exc)) from exc
            flat = (json.dumps(data, ensure_ascii=False) if isinstance(data, (dict, list)) else text).lower()
            if status in (401, 403):
                return {"ok": False, "reachable": True, "api_key_valid": False, "endpoint": url, "status": status, "message": "AZUR respondió, pero rechazó la API key."}

        if status > 0 and status < 500:
            return {
                "ok": True,
                "reachable": True,
                "api_key_valid": True if status not in (401, 403) else False,
                "endpoint": url,
                "status": status,
                "message": "Conexión con AZUR confirmada. No se emitió ningún comprobante.",
            }
        raise core.AzurError(f"AZUR respondió con HTTP {status}")

    core.azur_test_connection = test_connection

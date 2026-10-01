from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.parse

from reception_tv_common import CONFIG_PATH, DATA_DIR, FIREWALL_RULE, PORT, ROOT, VIDEOS_DIR, _clean_name, _is_video_name


class TVMediaMixin:
    def _load_config(self) -> dict:
        default = {
            "videos_enabled": True,
            "video_volume": 0.20,
            "video_order": [],
            "display_mode": "live",
        }
        if not CONFIG_PATH.is_file():
            return default
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
            if not isinstance(data, dict):
                return default
            enabled = bool(data.get("videos_enabled", True))
            volume = max(0.0, min(1.0, float(data.get("video_volume", 0.20))))
            order = [str(x) for x in (data.get("video_order") or []) if isinstance(x, str)]
            display_mode = str(data.get("display_mode") or "live").strip().lower()
            if display_mode not in {"live", "test"}:
                display_mode = "live"
            return {
                "videos_enabled": enabled,
                "video_volume": volume,
                "video_order": order,
                "display_mode": display_mode,
            }
        except Exception:
            return default

    def _save_config(self) -> None:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            tmp = CONFIG_PATH.with_suffix(".json.new")
            tmp.write_text(json.dumps(self.config, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, CONFIG_PATH)
        except Exception:
            pass

    def video_items(self) -> list[dict]:
        files = {p.name: p for p in VIDEOS_DIR.iterdir() if p.is_file() and _is_video_name(p.name)}
        order = []
        for name in list(self.config.get("video_order") or []):
            if name in files and name not in order:
                order.append(name)
        for name in sorted(files):
            if name not in order:
                order.append(name)
        if order != list(self.config.get("video_order") or []):
            self.config["video_order"] = order
            self._save_config()
        return [
            {
                "name": name,
                "size": int(files[name].stat().st_size),
                "url": "/media/" + urllib.parse.quote(name),
            }
            for name in order
        ]

    def video_config(self) -> dict:
        items = self.video_items()
        return {
            "enabled": bool(self.config.get("videos_enabled", True)),
            "volume": float(self.config.get("video_volume", 0.20)),
            "items": items,
        }

    def _advertising_allowed(self, state: dict) -> bool:
        return bool(
            state.get("mode") == "attending"
            and int(state.get("waiting_count") or 0) > 0
            and self.config.get("videos_enabled", True)
            and self.video_items()
        )

    def firewall_repair(self) -> dict:
        if os.name != "nt":
            return {"ok": False, "message": "Disponible solo en Windows."}
        helper = DATA_DIR / "REPARAR_PANTALLA_TV.cmd"
        helper.write_text(
            "@echo off\r\n"
            f'netsh advfirewall firewall delete rule name="{FIREWALL_RULE}" >nul 2>&1\r\n'
            f'netsh advfirewall firewall add rule name="{FIREWALL_RULE}" dir=in action=allow protocol=TCP localport={PORT} profile=private remoteip=localsubnet\r\n',
            encoding="utf-8",
        )
        escaped = str(helper).replace("'", "''")
        command = f"Start-Process -FilePath '{escaped}' -Verb RunAs -Wait"
        try:
            subprocess.Popen(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                cwd=str(ROOT),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return {"ok": True, "message": "Windows pedirá permiso para habilitar la Pantalla TV en la red privada."}
        except Exception as exc:
            return {"ok": False, "message": f"No se pudo abrir el permiso: {type(exc).__name__}"}

    def _save_upload(self, handler, name: str) -> dict:
        safe = _clean_name(name)
        if not safe or not _is_video_name(safe):
            raise ValueError("Formato de video no admitido")
        length = int(handler.headers.get("Content-Length") or 0)
        if length <= 0 or length > 2 * 1024 * 1024 * 1024:
            raise ValueError("El archivo debe medir entre 1 byte y 2 GB")
        target = VIDEOS_DIR / safe
        remaining = length
        with target.open("wb") as out:
            while remaining > 0:
                chunk = handler.rfile.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise IOError("Carga incompleta")
                out.write(chunk)
                remaining -= len(chunk)
        with self.lock:
            order = [x for x in self.config.get("video_order", []) if x != safe]
            order.append(safe)
            self.config["video_order"] = order
            self._save_config()
        return {"ok": True, "name": safe}

    def _serve_media(self, handler, name: str) -> None:
        safe = _clean_name(urllib.parse.unquote(name))
        if not safe or not _is_video_name(safe):
            return handler._send_text(400, "Video inválido")
        path = VIDEOS_DIR / safe
        if not path.is_file():
            return handler._send_text(404, "Video no encontrado")
        total = path.stat().st_size
        start, end, status = 0, total - 1, 200
        header = handler.headers.get("Range") or ""
        match = re.match(r"bytes=(\d*)-(\d*)", header)
        if match:
            if match.group(1):
                start = int(match.group(1))
            if match.group(2):
                end = min(total - 1, int(match.group(2)))
            if start < 0 or start >= total or end < start:
                handler.send_response(416)
                handler.send_header("Content-Range", f"bytes */{total}")
                handler.end_headers()
                return
            status = 206
        length = end - start + 1
        ctype = "video/webm" if path.suffix.lower() == ".webm" else "video/mp4"
        handler.send_response(status)
        handler.send_header("Content-Type", ctype)
        handler.send_header("Accept-Ranges", "bytes")
        handler.send_header("Cache-Control", "public, max-age=3600")
        handler.send_header("Content-Length", str(length))
        if status == 206:
            handler.send_header("Content-Range", f"bytes {start}-{end}/{total}")
        handler.end_headers()
        try:
            with path.open("rb") as inp:
                inp.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = inp.read(min(65536, remaining))
                    if not chunk:
                        break
                    handler.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass

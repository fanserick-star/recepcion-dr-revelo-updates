from __future__ import annotations

import core_runtime
from reception_tv_common import _epoch, _now_iso
from reception_tv_service import APP_VERSION, TVTurnService


class ClinicTVTurnService(TVTurnService):
    """Blindaje del cambio de turno cuando Historia finaliza una consulta.

    Historia actualiza la cola y Recepción la consulta por LAN cada ~0.9 s. En Windows
    puede existir una lectura intermedia donde el turno actual ya desapareció pero el
    registro reciente todavía no muestra su estado terminal. El runtime anterior tomaba
    ese instante como si fuera una cancelación, pasaba a PRÓXIMO TURNO sin crear evento
    de llamado y por eso no sonaba. Conservamos brevemente el turno actual hasta poder
    distinguir completed de cancelled y, si fue completed, aseguramos un único llamado
    del siguiente turno. Cancelar/eliminar continúa sin llamar a nadie.
    """

    FINALIZE_GRACE_SECONDS = 2.8

    def __init__(self):
        super().__init__()
        self.tv_voice_capabilities: list[dict] = []
        self.tv_voice_supported = False
        self.tv_voice_reported_epoch = 0.0
        self.voice_test_id = 0
        self.voice_test_turn = 6

    @staticmethod
    def _valid_waiting(payload: dict) -> list[dict]:
        return [
            item
            for item in (payload.get("waiting") or [])
            if isinstance(item, dict) and item.get("turn") not in (None, "")
        ]

    @staticmethod
    def _has_current_turn(payload: dict) -> bool:
        current = payload.get("current")
        return bool(isinstance(current, dict) and current.get("turn") not in (None, ""))

    @staticmethod
    def _recent_terminal_status(payload: dict, queue_id: str) -> str:
        if not queue_id:
            return ""
        for item in payload.get("recent") or []:
            if not isinstance(item, dict):
                continue
            if str(item.get("queue_id") or "") != str(queue_id):
                continue
            status = str(item.get("status") or "").strip().lower()
            if status == "cancelled":
                return "cancelled"
            if status == "completed" or str(item.get("completed_at") or "").strip():
                return "completed"
            return status
        return ""

    def _clear_finish_pending(self) -> None:
        self._finish_pending_id = ""
        self._finish_pending_since = 0.0

    def _ensure_next_called(self, waiting: list[dict]) -> None:
        if not waiting:
            return
        nxt = waiting[0]
        next_id = str(nxt.get("queue_id") or "")
        next_turn = int(nxt["turn"])
        with self.lock:
            if self.live.get("mode") == "calling" and str(self.live.get("called_queue_id") or "") == next_id:
                return
            self.live["mode"] = "calling"
            self.live["turn"] = next_turn
            self.live["current_queue_id"] = ""
            self.live["called_queue_id"] = next_id
            self.live["call_before_attending_id"] = ""
            self.live["attention_started_epoch"] = 0.0
            self.live["calling_started_epoch"] = _epoch()
            self.live["sound_test"] = False
            self.live["event_id"] = int(self.live.get("event_id") or 0) + 1
            self.live["last_change"] = _now_iso()

    def apply_history(self, payload: dict) -> None:
        waiting = self._valid_waiting(payload)
        has_current = self._has_current_turn(payload)
        with self.lock:
            prev_current_id = str(self.live.get("current_queue_id") or "")
            prev_turn = self.live.get("turn")
            prev_mode = str(self.live.get("mode") or "")

        terminal = self._recent_terminal_status(payload, prev_current_id) if prev_current_id and not has_current else ""
        now = _epoch()

        if prev_current_id and not has_current and waiting and terminal not in {"completed", "cancelled"}:
            if str(getattr(self, "_finish_pending_id", "") or "") != prev_current_id:
                self._finish_pending_id = prev_current_id
                self._finish_pending_since = now
        elif has_current or terminal in {"completed", "cancelled"} or not waiting:
            self._clear_finish_pending()

        super().apply_history(payload)

        if prev_current_id and not has_current and waiting:
            if terminal == "completed":
                self._ensure_next_called(waiting)
                self._clear_finish_pending()
                return
            if terminal == "cancelled":
                self._clear_finish_pending()
                return

            pending_id = str(getattr(self, "_finish_pending_id", "") or "")
            pending_since = float(getattr(self, "_finish_pending_since", 0.0) or 0.0)
            if pending_id == prev_current_id and pending_since and now - pending_since < self.FINALIZE_GRACE_SECONDS:
                with self.lock:
                    self.live["current_queue_id"] = prev_current_id
                    self.live["turn"] = prev_turn
                    self.live["called_queue_id"] = ""
                    self.live["call_before_attending_id"] = ""
                    self.live["mode"] = prev_mode if prev_mode in {"attending", "calling"} else "attending"
                    if self.live["mode"] == "attending":
                        self.live["calling_started_epoch"] = 0.0
                return
            self._clear_finish_pending()

    def _voice_config(self) -> dict:
        return {
            "voice_uri": str(self.config.get("voice_uri") or ""),
            "voice_name": str(self.config.get("voice_name") or ""),
            "voice_lang": str(self.config.get("voice_lang") or ""),
            "rate": float(self.config.get("voice_rate", 0.90)),
            "pitch": float(self.config.get("voice_pitch", 1.00)),
        }

    def report_tv_voices(self, payload: dict) -> dict:
        raw = payload.get("voices") or []
        voices = []
        seen = set()
        for item in raw[:64] if isinstance(raw, list) else []:
            if not isinstance(item, dict):
                continue
            uri = str(item.get("voiceURI") or item.get("name") or "")[:240]
            name = str(item.get("name") or "")[:180]
            lang = str(item.get("lang") or "")[:40]
            if not uri and not name:
                continue
            key = (uri, name, lang)
            if key in seen:
                continue
            seen.add(key)
            voices.append({
                "voiceURI": uri,
                "name": name,
                "lang": lang,
                "default": bool(item.get("default")),
                "localService": bool(item.get("localService")),
            })
        with self.lock:
            self.tv_voice_capabilities = voices
            self.tv_voice_supported = bool(payload.get("supported"))
            self.tv_voice_reported_epoch = _epoch()
        return {"ok": True, "count": len(voices)}

    def voice_settings(self) -> dict:
        with self.lock:
            return {
                "ok": True,
                "config": self._voice_config(),
                "voices": list(self.tv_voice_capabilities),
                "tv_voice_supported": bool(self.tv_voice_supported),
                "tv_voice_reported": bool(self.tv_voice_reported_epoch),
                "tv_voice_age_seconds": max(0.0, _epoch() - self.tv_voice_reported_epoch) if self.tv_voice_reported_epoch else None,
            }

    def set_voice_settings(self, payload: dict) -> dict:
        uri = str(payload.get("voice_uri") or "")[:240]
        rate = max(0.60, min(1.30, float(payload.get("rate", self.config.get("voice_rate", 0.90)))))
        pitch = max(0.70, min(1.30, float(payload.get("pitch", self.config.get("voice_pitch", 1.00)))))
        chosen = None
        with self.lock:
            if uri:
                for item in self.tv_voice_capabilities:
                    if str(item.get("voiceURI") or "") == uri:
                        chosen = item
                        break
                if self.tv_voice_capabilities and chosen is None:
                    raise ValueError("La voz escogida ya no está disponible en el televisor")
            self.config["voice_uri"] = uri if chosen or not uri else ""
            self.config["voice_name"] = str((chosen or {}).get("name") or "")
            self.config["voice_lang"] = str((chosen or {}).get("lang") or "")
            self.config["voice_rate"] = rate
            self.config["voice_pitch"] = pitch
            self._save_config()
        return self.voice_settings()

    def trigger_voice_test(self, payload: dict) -> dict:
        try:
            turn = int(payload.get("turn") or 6)
        except (TypeError, ValueError):
            turn = 6
        turn = max(1, min(999, turn))
        with self.lock:
            self.voice_test_id += 1
            self.voice_test_turn = turn
            return {"ok": True, "voice_test_id": self.voice_test_id, "turn": turn}

    def display_snapshot(self, *, touch_tv: bool = False) -> dict:
        out = super().display_snapshot(touch_tv=touch_tv)
        with self.lock:
            out["voice"] = self._voice_config()
            out["voice_test_id"] = int(self.voice_test_id)
            out["voice_test_turn"] = int(self.voice_test_turn)
        return out


SERVICE = ClinicTVTurnService()

TV_OVERLAY_CSS = r"""
#tvOfficialShortcut{position:fixed;right:18px;bottom:18px;z-index:2147482000;border:1px solid rgba(255,255,255,.22);background:#173a52;color:#fff;border-radius:12px;padding:10px 13px;font:800 12px/1.1 system-ui,-apple-system,Segoe UI,sans-serif;box-shadow:0 8px 24px rgba(0,0,0,.2);cursor:pointer}#tvOfficialShortcut:hover{background:#245877}
#tvOfficialModal{position:fixed;inset:0;z-index:2147483000;display:none;align-items:stretch;justify-content:center;background:rgba(4,13,20,.76);backdrop-filter:blur(3px);padding:18px}#tvOfficialModal.tv-open{display:flex}#tvOfficialShell{width:min(1220px,98vw);height:calc(100vh - 36px);background:#0b1821;border:1px solid rgba(255,255,255,.22);border-radius:18px;overflow:hidden;box-shadow:0 24px 70px rgba(0,0,0,.42);display:flex;flex-direction:column}#tvOfficialBar{height:48px;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:0 12px 0 16px;background:#112a36;border-bottom:1px solid rgba(255,255,255,.12);color:#fff;font:800 13px/1 system-ui,-apple-system,Segoe UI,sans-serif}#tvOfficialClose{border:0;background:#294a58;color:#fff;border-radius:9px;padding:8px 12px;font-weight:900;cursor:pointer}#tvOfficialFrame{width:100%;flex:1;border:0;background:#0b1821}
"""
TV_OVERLAY_JS = r"""
;(()=>{if(window.__tvOfficialInstalled)return;window.__tvOfficialInstalled=true;function closeTV(){const m=document.getElementById('tvOfficialModal');if(m)m.classList.remove('tv-open')}async function openTV(){try{const r=await fetch('/api/tv-turnos/health?t='+Date.now(),{cache:'no-store'});const d=await r.json();if(!d.ok){alert('Pantalla TV no inició. '+(d.error||'Revise el puerto 8899.'));return}}catch(_e){}const m=document.getElementById('tvOfficialModal'),f=document.getElementById('tvOfficialFrame');if(!m||!f)return;if(!f.src||f.src==='about:blank')f.src='http://127.0.0.1:8899/control?embedded=1';m.classList.add('tv-open')}function boot(){if(document.getElementById('tvOfficialShortcut'))return;const b=document.createElement('button');b.id='tvOfficialShortcut';b.type='button';b.textContent='📺 Pantalla TV';b.title='Abrir En vivo / Pruebas dentro de Recepción';b.addEventListener('click',openTV);document.body.appendChild(b);const m=document.createElement('div');m.id='tvOfficialModal';m.innerHTML='<div id="tvOfficialShell"><div id="tvOfficialBar"><span>📺 Pantalla TV · Recepción</span><button id="tvOfficialClose" type="button">Cerrar</button></div><iframe id="tvOfficialFrame" src="about:blank" title="Pantalla TV"></iframe></div>';m.addEventListener('click',e=>{if(e.target===m)closeTV()});document.body.appendChild(m);document.getElementById('tvOfficialClose').addEventListener('click',closeTV);document.addEventListener('keydown',e=>{if(e.key==='Escape')closeTV()})}if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot()})();
"""
core_runtime.V460_OVERLAY_CSS = (getattr(core_runtime, "V460_OVERLAY_CSS", "") or "") + "\n" + TV_OVERLAY_CSS
core_runtime.V460_OVERLAY_JS = (getattr(core_runtime, "V460_OVERLAY_JS", "") or "") + "\n" + TV_OVERLAY_JS

app = core_runtime.app


@app.on_event("startup")
def _start_official_tv_turn_service():
    SERVICE.start()


@app.get("/api/tv-turnos/health")
def tv_turnos_health(user=core_runtime.Depends(core_runtime.current_user)):
    out = SERVICE.status()
    out["finish_calls_next_with_sound"] = True
    out["finish_transition_grace_seconds"] = ClinicTVTurnService.FINALIZE_GRACE_SECONDS
    out["cancel_never_calls_next"] = True
    return out


PATCH_BOOT_OK = True

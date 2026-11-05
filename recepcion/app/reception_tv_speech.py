"""Offline Windows SAPI WAV voice for the local waiting-room TV.

No internet service is used. Optional first-two-surname announcements are resolved
privately from the local Reception LAN outbox, only for an exact active queue ID.
No surnames appear in TV markup, JSON, query parameters or persistent WAV files.
Selectable voice, speed and pitch work on legacy Fully Kiosk.
"""
from __future__ import annotations

import base64
import json
import os
import re
import sqlite3
import uuid
from datetime import date
import subprocess
import tempfile
import threading
from functools import lru_cache
from pathlib import Path

_speech_lock = threading.Lock()


def _ps_escape(value: str) -> str:
    return str(value).replace("'", "''")


def _run_powershell(script: str, timeout: int = 12) -> subprocess.CompletedProcess:
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    return subprocess.run(
        ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=timeout, check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


@lru_cache(maxsize=1)
def windows_voices() -> list[dict]:
    """List installed SAPI voices on Reception (not voices on the TV box)."""
    if os.name != "nt":
        return []
    script = (
        "$ErrorActionPreference='Stop'\n"
        "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8\n"
        "Add-Type -AssemblyName System.Speech\n"
        "$speaker=New-Object System.Speech.Synthesis.SpeechSynthesizer\n"
        "try {\n"
        "  $list=@($speaker.GetInstalledVoices() | Where-Object { $_.Enabled } | "
        "ForEach-Object { [pscustomobject]@{ name=[string]$_.VoiceInfo.Name; "
        "lang=[string]$_.VoiceInfo.Culture.Name } })\n"
        "  ConvertTo-Json -InputObject $list -Depth 3 -Compress\n"
        "} finally { $speaker.Dispose() }\n"
    )
    try:
        result = _run_powershell(script, timeout=12)
        if result.returncode != 0:
            return []
        value = json.loads(result.stdout.decode("utf-8-sig", errors="replace").strip())
        if isinstance(value, dict):
            value = [value]
        if not isinstance(value, list):
            return []
        return [
            {"name": str(item.get("name") or "")[:180],
             "lang": str(item.get("lang") or "")[:40]}
            for item in value[:64]
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        ]
    except (OSError, subprocess.SubprocessError, ValueError, UnicodeError):
        return []


def _synthesize(turn: int, voice_name: str, rate: float, pitch: float, surnames: str = "") -> bytes | None:
    if os.name != "nt":
        return None
    handle, filename = tempfile.mkstemp(prefix="dr_revelo_turn_", suffix=".wav")
    os.close(handle)
    path = Path(filename)
    try:
        # Same announcement for a consultation and an exam-review turn.
        phrase = f"Turno número {turn}, {surnames}, por favor pasar a consulta." if surnames else f"Turno número {turn}, por favor pasar a consulta."
        speed = max(-10, min(10, round((float(rate) - 1.0) * 10)))
        pitch_pct = max(-30, min(30, round((float(pitch) - 1.0) * 100)))
        pitch_label = f"{pitch_pct:+d}%"
        voice_command = (
            f"  $speaker.SelectVoice('{_ps_escape(voice_name)}')\n"
            if voice_name else
            "  $spanish=@($speaker.GetInstalledVoices() | Where-Object { "
            "$_.Enabled -and $_.VoiceInfo.Culture.Name -like 'es-*' })\n"
            "  if ($spanish.Count -gt 0) { $speaker.SelectVoice($spanish[0].VoiceInfo.Name) }\n"
        )
        script = (
            "$ErrorActionPreference='Stop'\n"
            "Add-Type -AssemblyName System.Speech\n"
            "$speaker=New-Object System.Speech.Synthesis.SpeechSynthesizer\n"
            "try {\n"
            + voice_command
            + f"  $speaker.Rate={speed}\n"
            + f"  $speaker.SetOutputToWaveFile('{_ps_escape(str(path))}')\n"
            + f"  $words='{_ps_escape(phrase)}'\n"
            + (f"  try {{\n"
               f"    $text=[System.Security.SecurityElement]::Escape($words)\n"
               f"    $ssml='<speak version=\"1.0\" xmlns=\"http://www.w3.org/2001/10/synthesis\" xml:lang=\"es-EC\"><prosody pitch=\"{pitch_label}\">'+$text+'</prosody></speak>'\n"
               f"    $speaker.SpeakSsml($ssml)\n"
               f"  }} catch {{ $speaker.Speak($words) }}\n"
               if pitch_pct else
               "  $speaker.Speak($words)\n")
            + "  $speaker.SetOutputToNull()\n"
            + "} finally { $speaker.Dispose() }\n"
        )
        result = _run_powershell(script, timeout=12)
        if result.returncode != 0:
            return None
        data = path.read_bytes()
        if len(data) < 1000 or not data.startswith(b"RIFF") or data[8:12] != b"WAVE":
            return None
        return data
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    finally:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def _first_two_surnames(display_name: str) -> str:
    """Conservatively select two leading words from 'Apellidos y nombres'.

    Unclear names and placeholders fall back to the number-only announcement.
    """
    raw = str(display_name or "").strip()
    if not raw or len(raw) > 260:
        return ""
    words = [w.strip(",.;:") for w in raw.split() if w.strip(",.;:")]
    if len(words) < 3 or any(not re.fullmatch(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ'’-]{2,45}", w) for w in words[:2]):
        return ""
    if words[0].casefold() in {"paciente", "sin", "desconocido", "anónimo", "anonimo"}:
        return ""
    return " ".join(words[:2])


def surnames_for_queue(queue_id: str) -> str:
    """Exact Historia queue UUIDv5 -> Reception outbox event; never match by turn.

    Read only recently delivered, noncancelled records for the current local day.
    Missing, ambiguous, malformed or outdated data produces no surname.
    """
    candidate = str(queue_id or "").strip()
    try:
        if str(uuid.UUID(candidate)) != candidate.lower():
            return ""
    except (ValueError, AttributeError):
        return ""
    # Reuse the canonical path, including paths configured by tests.
    try:
        import historia_lan_transport
        path = historia_lan_transport.LAN_OUTBOX_DB
        if not path.is_file():
            return ""
        today = date.today().isoformat()
        with sqlite3.connect(path, timeout=1) as conn:
            conn.execute("PRAGMA query_only=ON")
            rows = conn.execute(
                "SELECT event_id,payload_json FROM events "
                "WHERE created_at >= ? AND created_at < ? AND sent_at IS NOT NULL "
                "AND cancelled=0 ORDER BY created_at DESC LIMIT 3000",
                (today, today + "~"),
            ).fetchall()
        for event_id, payload_json in rows:
            if str(uuid.uuid5(uuid.NAMESPACE_URL, "historia-queue:" + str(event_id))) != candidate:
                continue
            payload = json.loads(payload_json)
            if not isinstance(payload, dict) or str(payload.get("event_id") or "") != str(event_id):
                return ""
            return _first_two_surnames(payload.get("display_name"))
    except (OSError, sqlite3.DatabaseError, ValueError, TypeError):
        return ""
    return ""


@lru_cache(maxsize=192)
def _turn_only_audio(turn: int, voice_name: str, rate: float, pitch: float) -> bytes | None:
    return _synthesize(turn, voice_name, rate, pitch)


def turn_voice_wav(
    turn: int, exam_review: bool = False, voice_name: str = "",
    rate: float = 0.90, pitch: float = 1.00, surnames: str = "",
) -> bytes | None:
    """Public announcements always retain the consultation wording."""
    if not 1 <= turn <= 999:
        return None
    _ = exam_review
    chosen = str(surnames or "").strip()
    if chosen:
        parts = chosen.split()
        if len(parts) != 2 or any(not re.fullmatch(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ'’-]{2,45}", w) for w in parts):
            chosen = ""
    with _speech_lock:
        if chosen:
            # Do not retain identifiable announcements in an LRU audio cache.
            return _synthesize(int(turn), str(voice_name or "")[:180], round(float(rate), 2),
                               round(float(pitch), 2), chosen)
        return _turn_only_audio(int(turn), str(voice_name or "")[:180],
                                round(float(rate), 2), round(float(pitch), 2))

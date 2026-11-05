"""Offline Windows SAPI WAV voice for the local waiting-room TV.

No internet service and no patient identity is ever used. Selectable voice, speed,
and pitch apply to legacy Fully Kiosk that cannot enumerate Android voices.
"""
from __future__ import annotations

import base64
import json
import os
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


@lru_cache(maxsize=192)
def _synthesize(turn: int, voice_name: str, rate: float, pitch: float) -> bytes | None:
    if os.name != "nt":
        return None
    handle, filename = tempfile.mkstemp(prefix="dr_revelo_turn_", suffix=".wav")
    os.close(handle)
    path = Path(filename)
    try:
        # Same announcement for a consultation and an exam-review turn.
        phrase = f"Turno número {turn}, por favor pasar a consulta."
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


def turn_voice_wav(
    turn: int, exam_review: bool = False, voice_name: str = "",
    rate: float = 0.90, pitch: float = 1.00,
) -> bytes | None:
    """Speech settings change voice/speed, not events or turn numbering."""
    if not 1 <= turn <= 999:
        return None
    # Reviews intentionally share consultation wording; the clinical type stays unchanged.
    _ = exam_review
    with _speech_lock:
        return _synthesize(int(turn), str(voice_name or "")[:180], round(float(rate), 2),
                           round(float(pitch), 2))

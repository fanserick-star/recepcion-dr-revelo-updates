from __future__ import annotations

import base64
import os
import shutil
import subprocess
import threading
from pathlib import Path

from reception_tv_common import DATA_DIR


VOICE_DIR = DATA_DIR / "voice"
_VOICE_LOCK = threading.RLock()


def _turn_number(value: object) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError("Turno inválido")
    if number < 1 or number > 999:
        raise ValueError("Turno fuera de rango")
    return number


def _powershell() -> str:
    return shutil.which("powershell.exe") or shutil.which("powershell") or "powershell.exe"


def _ps_quote(value: str) -> str:
    return str(value).replace("'", "''")


def turn_voice_wav(turn: object) -> bytes:
    """Genera/cacha en Recepción la voz del turno y devuelve WAV para la TV.

    La síntesis ocurre en Windows, no en el navegador del televisor. Así la TV solo
    necesita reproducir audio WAV, igual que ya hace con el ding. No usa Internet,
    APIs ni modifica el estado de turnos.
    """

    number = _turn_number(turn)
    VOICE_DIR.mkdir(parents=True, exist_ok=True)
    target = VOICE_DIR / f"turn-{number:03d}.wav"

    with _VOICE_LOCK:
        if target.is_file():
            data = target.read_bytes()
            if len(data) > 44 and data[:4] == b"RIFF":
                return data
            try:
                target.unlink()
            except OSError:
                pass

        phrase = f"Turno número {number}, por favor pasar a consulta."
        path = _ps_quote(str(target.resolve()))
        text = _ps_quote(phrase)
        script = f"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {{
    $voice = $synth.GetInstalledVoices() | Where-Object {{
        $_.Enabled -and $_.VoiceInfo.Culture.Name -like 'es-*'
    }} | Select-Object -First 1
    if ($voice) {{ $synth.SelectVoice($voice.VoiceInfo.Name) }}
    $synth.Rate = -1
    $synth.Volume = 100
    $synth.SetOutputToWaveFile('{path}')
    $synth.Speak('{text}')
}} finally {{
    try {{ $synth.SetOutputToDefaultAudioDevice() }} catch {{}}
    $synth.Dispose()
}}
""".strip()
        encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        result = subprocess.run(
            [_powershell(), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
            creationflags=flags,
            check=False,
        )
        if result.returncode != 0 or not target.is_file():
            try:
                target.unlink()
            except OSError:
                pass
            detail = (result.stderr or result.stdout).decode("utf-8", errors="ignore").strip()
            raise RuntimeError(detail[:220] or "Windows no pudo generar la voz del turno")

        data = target.read_bytes()
        if len(data) <= 44 or data[:4] != b"RIFF":
            try:
                target.unlink()
            except OSError:
                pass
            raise RuntimeError("Windows generó un audio de voz inválido")
        return data

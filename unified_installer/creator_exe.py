import os
import sys
import shutil
import tempfile
import subprocess
import urllib.request
from pathlib import Path

COMMIT = "542b85d06fe20365a251246fffec99707d18f601"
BASE = f"https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/{COMMIT}/unified_installer"
FILES = ["build_private_master.ps1", "ConsultorioDrRevelo.iss"]
FINAL_NAME = "INSTALAR_CONSULTORIO_DR_REVELO_MAESTRO.exe"

def fail(msg):
    print("\nERROR:", msg)
    input("\nPresiona Enter para cerrar...")
    sys.exit(1)

def download(url, dest):
    print(f"Descargando {dest.name}...")
    req = urllib.request.Request(url, headers={"User-Agent":"DrRevelo-MasterCreator/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)

def bundled_iscc():
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    iscc = base / "inno_runtime" / "ISCC.exe"
    if not iscc.is_file():
        fail("El creador no contiene su compilador Inno Setup portátil. Descarga nuevamente el EXE oficial.")
    return iscc

def is_reception_root(path):
    try:
        path = Path(path)
        required = [
            path / ".env",
            path / "ABRIR_RECEPCION.py",
            path / "app.py",
            path / ".venv" / "Scripts" / "pythonw.exe",
        ]
        return all(p.is_file() for p in required)
    except Exception:
        return False

def shortcut_candidates():
    ps = r"""
$ErrorActionPreference = 'SilentlyContinue'
$ws = New-Object -ComObject WScript.Shell
$dirs = @(
  [Environment]::GetFolderPath('Desktop'),
  [Environment]::GetFolderPath('CommonDesktopDirectory'),
  [Environment]::GetFolderPath('Programs'),
  [Environment]::GetFolderPath('CommonPrograms')
) | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -Unique
foreach ($d in $dirs) {
  Get-ChildItem -LiteralPath $d -Filter *.lnk -Recurse -ErrorAction SilentlyContinue | ForEach-Object {
    try {
      $s = $ws.CreateShortcut($_.FullName)
      $text = (($s.TargetPath + ' ' + $s.Arguments + ' ' + $s.WorkingDirectory)).ToLowerInvariant()
      if ($text -match 'abrir_recepcion\.py' -or $text -match 'recepci[oó]n') {
        if ($s.WorkingDirectory) { [Console]::WriteLine($s.WorkingDirectory) }
      }
    } catch {}
  }
}
"""
    try:
        encoded = __import__("base64").b64encode(ps.encode("utf-16le")).decode("ascii")
        out = subprocess.check_output(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
            text=True, encoding="utf-8", errors="ignore",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        for line in out.splitlines():
            line = line.strip().strip('"')
            if line:
                yield Path(line)
    except Exception:
        return

def choose_reception_folder():
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        messagebox.showinfo(
            "Instalador Maestro - Dr. Revelo",
            "No encontré Recepción automáticamente.\n\n"
            "Selecciona la carpeta donde está instalado el programa de Recepción.",
            parent=root,
        )
        selected = filedialog.askdirectory(
            title="Selecciona la carpeta de Recepción",
            parent=root,
            mustexist=True,
        )
        root.destroy()
        if selected:
            return Path(selected)
    except Exception:
        pass
    return None

def detect_reception():
    env_root = os.environ.get("DR_REVELO_RECEPTION_ROOT", "").strip()
    candidates = []
    if env_root:
        candidates.append(Path(env_root))

    candidates.extend([
        Path(r"C:\Recepcion Dr Revelo"),
        Path(r"C:\Recepción Dr Revelo"),
        Path(r"C:\Recepcion Dr. Revelo"),
        Path(r"C:\Recepción Dr. Revelo"),
        Path(r"C:\Recepcion Pacientes Dr Revelo"),
        Path(r"C:\Recepción Pacientes Dr Revelo"),
        Path(r"C:\Recepcion Pacientes"),
        Path(r"C:\Recepción Pacientes"),
    ])

    candidates.extend(shortcut_candidates())

    try:
        for child in Path("C:/").iterdir():
            if child.is_dir() and ("recep" in child.name.lower() or "revelo" in child.name.lower()):
                candidates.append(child)
    except Exception:
        pass

    seen = set()
    for candidate in candidates:
        try:
            candidate = candidate.resolve()
        except Exception:
            candidate = Path(candidate)
        key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        if is_reception_root(candidate):
            return candidate

    selected = choose_reception_folder()
    if selected and is_reception_root(selected):
        return selected

    if selected:
        fail(
            "La carpeta seleccionada no parece ser la instalación de Recepción.\n\n"
            "Debe contener .env, ABRIR_RECEPCION.py, app.py y .venv\\Scripts\\pythonw.exe."
        )

    fail(
        "No pude localizar Recepción automáticamente.\n"
        "Abre Recepción normalmente y vuelve a ejecutar este creador."
    )

def main():
    if os.name != "nt":
        fail("Este creador solo funciona en Windows.")

    try:
        os.system("chcp 65001 >nul")
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    reception = detect_reception()
    print(f"\nRecepción encontrada automáticamente en:\n{reception}")

    if "--detect-only" in sys.argv:
        print("RECEPTION_DETECTION_OK")
        return

    desktop = Path.home() / "Desktop"
    if not desktop.exists():
        desktop = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"
    desktop.mkdir(parents=True, exist_ok=True)

    tmp = Path(tempfile.mkdtemp(prefix="dr_revelo_creator_"))
    try:
        for name in FILES:
            download(f"{BASE}/{name}", tmp / name)

        print("\nPreparando el instalador maestro privado...")
        print("No necesitas escribir API, key, Neon, AZUR ni WhatsApp.")
        ps1 = tmp / "build_private_master.ps1"
        cmd = [
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(ps1),
            "-ReceptionRoot", str(reception),
            "-OutputDir", str(desktop),
        ]
        env = os.environ.copy()
        env["DR_REVELO_ISCC"] = str(bundled_iscc())
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        rc = subprocess.call(cmd, env=env)
        if rc != 0:
            fail(f"El creador terminó con código {rc}.")

        final = desktop / FINAL_NAME
        if not final.exists():
            fail("El proceso terminó, pero no encuentro el EXE maestro en el Escritorio.")

        print("\n==============================================================")
        print("  LISTO - INSTALADOR MAESTRO CREADO")
        print("==============================================================")
        print(f"\n{final}")
        print("\nEse es el único EXE que debes guardar como respaldo privado.")
        print("Contiene la configuración privada del consultorio, pero no las bases clínicas.")
        try:
            subprocess.Popen(["explorer.exe", "/select,", str(final)])
        except Exception:
            pass
        if os.environ.get("DR_REVELO_NONINTERACTIVE") != "1":
            input("\nPresiona Enter para cerrar...")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

if __name__ == "__main__":
    main()

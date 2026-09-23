import os
import sys
import shutil
import tempfile
import subprocess
import urllib.request
from pathlib import Path

COMMIT = "a672c6ed6cdc01b4a09a02ca99de11972559a53e"
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

def main():
    if os.name != "nt":
        fail("Este creador solo funciona en Windows.")

    try:
        os.system("chcp 65001 >nul")
    except Exception:
        pass

    reception = Path(r"C:\Recepcion Dr Revelo")
    required = [
        reception / ".env",
        reception / "ABRIR_RECEPCION.py",
        reception / "app.py",
        reception / ".venv" / "Scripts" / "pythonw.exe",
    ]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        fail("No encuentro la instalación estable de Recepción. Falta:\n" + "\n".join(missing))

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
        input("\nPresiona Enter para cerrar...")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

if __name__ == "__main__":
    main()

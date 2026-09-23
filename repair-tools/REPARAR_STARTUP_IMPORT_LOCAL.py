from __future__ import annotations

import base64
import ctypes
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

TITLE = "Reparar STARTUP-IMPORT - Recepción Dr. Revelo"
PIN = "542b85d06fe20365a251246fffec99707d18f601"
RAW = f"https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/{PIN}/"

SOURCES = {
    "app_patch_4519.py": "updates/v4_5_19_sidebar_real_version/app_patch_4519.py",
    "app_patch_4518.py": "updates/v4_5_18_real_version/app_patch_4518.py",
    "app_patch_4517.py": "updates/v4_5_17_historia_link_status/app_patch_4517.py",
    "app_patch_4511.py": "updates/v4_5_11_shortcut_branding/app_patch_4511.py",
    "app_patch_4510.py": "updates/v4_5_10_auto_recovery/app_patch_4510.py",
    "app_patch_4509.py": "updates/v4_5_09_historia_bridge_stable/app_patch_4509.py",
    "app_patch_4508.py": "updates/v4_5_08_historia_bridge/app_patch_4508.py",
    "app_patch_4507.py": "updates/v4_5_07_bendo_manual_flow/app_patch_4507.py",
    "app_patch_4506.py": "updates/v4_5_06_bendo_config/app_patch_4506.py",
    "app_patch_4505.py": "updates/v4_5_05_dataphone_visual/app_patch_4505.py",
    "app_patch_4504.py": "updates/v4_5_04_dataphone_ready/app_patch_4504.py",
    "app_patch_4502.py": "updates/v4_5_02_couple_discount/app_patch_4502.py",
    "app_patch_4501.py": "updates/v4_5_01_stable_maintenance/app_patch_4501.py",
    "app_patch_4491.py": "updates/v4_4_91_billing_form_no_lines/app_patch_4491.py",
    "app_patch_4490.py": "updates/v4_4_90_billing_form_compact/app_patch_4490.py",
    "app_patch_4489.py": "updates/v4_4_89_billing_data_form/app_patch_4489.py",
    "app_patch_4488.py": "updates/v4_4_88_payment_proof_compact/app_patch_4488.py",
    "app_patch_4487.py": "updates/v4_4_87_payment_proof_safe_right/app_patch_4487.py",
    "app_patch_4486.py": "updates/v4_4_86_single_print_menu/app_patch_4486.py",
    "app_patch_4485.py": "updates/v4_4_85_payment_proof/app_patch_4485.py",
    "app_patch_4484.py": "updates/v4_4_84_optional_billing_email/app_patch_4484.py",
    "app_patch_4483.py": "updates/v4_4_83_mandatory_update_gate/app_patch_4483.py",
    "app_patch_4482.py": "updates/v4_4_82_updater_repair/app_patch_4482.py",
    "app_patch_4481.py": "updates/v4_4_81_remove_facturero_modal/app_patch_4481.py",
    "app_patch_4480.py": "updates/v4_4_80_billing_emitidas_hotfix/app_patch_4480.py",
    "app_patch_4479.py": "updates/v4_4_79_cleanup_obsolete_ui/app_patch_4479.py",
    "app_patch_4478.py": "updates/v4_4_78_visible_discard_stable_version/app_patch_4478.py",
    "app_patch_4477.py": "updates/v4_4_77_discard_pending_billing/app_patch_4477.py",
    "app_patch_4476.py": "updates/v4_4_76_billing_services_coherence/app_patch_4476.py",
    "app_patch_4475.py": "updates/v4_4_75_fast_save_services/app_patch_4475.py",
    "app_patch_4474.py": "updates/v4_4_74_async_print_stable/app_patch_4474.py",
    "app_patch_4473.py": "updates/v4_4_73_stable_recovery/app_patch_4473.py",
    "app_patch_4470.py": "updates/v4_4_70_workflow_fixes/app_patch_4470.py",
    "app_patch_4469.py": "updates/v4_4_69_receipt_left_wide/app_patch_4469.py",
    "app_patch_4468.py": "updates/v4_4_68_receipt_large_long/app_patch_4468.py",
    "app_patch_4467.py": "updates/v4_4_67_receipt_large_clean/app_patch_4467.py",
    "app_patch_4466.py": "updates/v4_4_66_receipt_raster/app_patch_4466.py",
    "app_patch_4465.py": "updates/v4_4_65_receipt_unified/app_patch_4465.py",
    "app_patch_4464.py": "updates/v4_4_64_receipt_edge_to_edge/app_patch_4464.py",
    "app_patch_4463.py": "updates/v4_4_63_receipt_match_preview/app_patch_4463.py",
    "app_patch_4462.py": "updates/v4_4_62_receipt_uniform/app_patch_4462.py",
    "app_patch_4461.py": "updates/v4_4_61_receipt_crm308/app_patch_4461.py",
    "app_patch_4459.py": "updates/v4_4_60_rescue_direct_app/app_patch_4459.py",
    "app_prev_4458.py": "updates/v4_4_60_rescue_direct_app/app_prev_4458.py",
    "app_base_4428.py": "updates/v4_4_60_rescue_direct_app/app_base_4428.py",
    "historia_bridge.py": "updates/v4_5_17_historia_link_status/historia_bridge.py",
}

PROTECTED_NAMES = {
    ".env",
    "BASE DE DATOS 2026.xlsx",
    "HISTORICO_PACIENTES_2020_2025.csv",
}
PROTECTED_DIRS = {"data", ".venv", "backups", "update_backups"}


def msg(text: str, error: bool = False) -> None:
    try:
        ctypes.windll.user32.MessageBoxW(None, str(text), TITLE, 0x10 if error else 0x40)
    except Exception:
        print(text, file=sys.stderr if error else sys.stdout)


def fail(text: str) -> None:
    msg(text, True)
    raise SystemExit(1)


def is_candidate(root: Path) -> bool:
    try:
        return (root / "app.py").is_file() and (root / ".venv" / "Scripts" / "python.exe").is_file()
    except Exception:
        return False


def shortcut_candidates():
    ps = r"""
$ErrorActionPreference='SilentlyContinue'
$ws=New-Object -ComObject WScript.Shell
$dirs=@(
 [Environment]::GetFolderPath('Desktop'),
 [Environment]::GetFolderPath('CommonDesktopDirectory'),
 [Environment]::GetFolderPath('Programs'),
 [Environment]::GetFolderPath('CommonPrograms')
) | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -Unique
foreach($d in $dirs){
 Get-ChildItem -LiteralPath $d -Filter *.lnk -Recurse -ErrorAction SilentlyContinue | ForEach-Object {
  try {
   $s=$ws.CreateShortcut($_.FullName)
   $t=(($s.TargetPath+' '+$s.Arguments+' '+$s.WorkingDirectory)).ToLowerInvariant()
   if($t -match 'abrir_recepcion\.py' -or $t -match 'recepci[oó]n'){
    if($s.WorkingDirectory){ [Console]::WriteLine($s.WorkingDirectory) }
   }
  } catch {}
 }
}
"""
    try:
        encoded = base64.b64encode(ps.encode("utf-16le")).decode("ascii")
        out = subprocess.check_output(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
            text=True,
            encoding="utf-8",
            errors="ignore",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        for line in out.splitlines():
            line = line.strip().strip('"')
            if line:
                yield Path(line)
    except Exception:
        return


def choose_folder() -> Path | None:
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        messagebox.showinfo(
            TITLE,
            "No encontré Recepción automáticamente.\n\nSelecciona la carpeta donde restauraste Recepción.",
            parent=root,
        )
        selected = filedialog.askdirectory(title="Selecciona la carpeta de Recepción", mustexist=True, parent=root)
        root.destroy()
        return Path(selected) if selected else None
    except Exception:
        return None


def detect_root() -> Path:
    candidates = []
    env_root = os.environ.get("DR_REVELO_RECEPTION_ROOT", "").strip()
    if env_root:
        candidates.append(Path(env_root))
    candidates += [
        Path(r"C:\Recepcion Dr Revelo"),
        Path(r"C:\Recepción Dr Revelo"),
        Path(r"C:\Recepcion Dr. Revelo"),
        Path(r"C:\Recepción Dr. Revelo"),
        Path(r"C:\Recepcion Pacientes"),
        Path(r"C:\Recepción Pacientes"),
    ]
    candidates += list(shortcut_candidates())

    try:
        for child in Path("C:/").iterdir():
            if child.is_dir() and ("recep" in child.name.lower() or "revelo" in child.name.lower()):
                candidates.append(child)
    except Exception:
        pass

    seen = set()
    for c in candidates:
        try:
            c = c.resolve()
        except Exception:
            pass
        key = str(c).lower()
        if key in seen:
            continue
        seen.add(key)
        if is_candidate(c):
            return c

    chosen = choose_folder()
    if chosen and is_candidate(chosen):
        return chosen
    fail("No pude localizar la copia restaurada de Recepción.\n\nLa carpeta debe contener app.py y .venv\\Scripts\\python.exe.")
    raise AssertionError


def active_patch(root: Path) -> int | None:
    text = (root / "app.py").read_text(encoding="utf-8-sig", errors="ignore")
    m = re.search(r"(?m)^\s*import\s+app_patch_(\d+)\s+as\s+previous", text)
    if m:
        return int(m.group(1))
    m = re.search(r'(?m)^\s*APP_VERSION\s*=\s*["\']4\.5\.(\d+)["\']', text)
    if m:
        return 4500 + int(m.group(1))
    return None


def safety_check(root: Path) -> None:
    patch = active_patch(root)
    if patch is not None and patch >= 4520:
        fail(
            "SEGURIDAD: esta instalación parece ser una Recepción nueva (4.5.20 o superior).\n\n"
            "Este reparador es SOLO para la copia vieja/restaurada con error STARTUP-IMPORT.\n"
            "No se realizó ningún cambio."
        )
    if not (root / ".venv" / "Scripts" / "python.exe").is_file():
        fail("Falta el Python local de Recepción. Este reparador no modificará la instalación.")


def fetch(relative: str) -> bytes:
    url = RAW + relative
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "DrRevelo-StartupImportRepair/1.0",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        if getattr(r, "status", 200) != 200:
            raise RuntimeError(f"HTTP {getattr(r, 'status', '?')} al descargar {relative}")
        return r.read()


def valid_python(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8-sig")
        compile(text, str(path), "exec")
        return True
    except Exception:
        return False


def repair_files(root: Path) -> tuple[list[str], list[str], Path | None]:
    stage = Path(tempfile.mkdtemp(prefix="dr_revelo_startup_repair_"))
    repaired: list[str] = []
    untouched: list[str] = []
    backup_dir: Path | None = None
    try:
        prepared = {}
        for name, relative in SOURCES.items():
            dest = root / name
            if dest.is_file() and (not name.endswith(".py") or valid_python(dest)):
                untouched.append(name)
                continue
            payload = fetch(relative)
            if name.endswith(".py"):
                compile(payload.decode("utf-8-sig"), name, "exec")
            sp = stage / name
            sp.write_bytes(payload)
            prepared[name] = sp

        if not prepared:
            return repaired, untouched, None

        backup_root = root / "data" / "startup_import_repair_backups"
        backup_root.mkdir(parents=True, exist_ok=True)
        backup_dir = backup_root / time.strftime("%Y%m%d_%H%M%S")
        backup_dir.mkdir(parents=True, exist_ok=True)

        for name, sp in prepared.items():
            if name in PROTECTED_NAMES:
                raise RuntimeError("Intento de tocar archivo protegido: " + name)
            dest = root / name
            if dest.parent != root:
                raise RuntimeError("Ruta fuera de la raíz: " + name)
            if dest.exists():
                shutil.copy2(dest, backup_dir / name)
            tmp = dest.with_name(dest.name + ".startup_repair_new")
            shutil.copy2(sp, tmp)
            os.replace(tmp, dest)
            repaired.append(name)

        return repaired, untouched, backup_dir
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def ensure_pg8000(root: Path) -> None:
    py = root / ".venv" / "Scripts" / "python.exe"
    probe = subprocess.run(
        [str(py), "-c", "import pg8000"],
        cwd=str(root),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=20,
    )
    if probe.returncode == 0:
        return
    proc = subprocess.run(
        [str(py), "-m", "pip", "install", "--disable-pip-version-check", "pg8000==1.31.2"],
        cwd=str(root),
        timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError("No se pudo preparar pg8000 en el Python local.")


def import_test(root: Path) -> tuple[bool, str]:
    py = root / ".venv" / "Scripts" / "python.exe"
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    code = (
        "import app; "
        "print('STARTUP_IMPORT_OK', getattr(app,'APP_VERSION',getattr(getattr(app,'core',None),'APP_VERSION','?')))"
    )
    try:
        proc = subprocess.run(
            [str(py), "-c", code],
            cwd=str(root),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        out = proc.stdout or ""
        return proc.returncode == 0 and "STARTUP_IMPORT_OK" in out, out[-8000:]
    except subprocess.TimeoutExpired as exc:
        return False, "La prueba de importación excedió 60 segundos.\n" + str(exc)


def write_report(root: Path, repaired: list[str], output: str) -> Path:
    report_dir = root / "data"
    report_dir.mkdir(parents=True, exist_ok=True)
    p = report_dir / "startup_import_repair_report.txt"
    body = [
        "REPARACIÓN STARTUP-IMPORT - RECEPCIÓN DR. REVELO",
        f"Fecha: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Fuente histórica congelada: {PIN}",
        "",
        "Archivos repuestos:",
        *(["- " + x for x in repaired] or ["- ninguno"]),
        "",
        "Prueba final:",
        output,
        "",
        "NO se modificaron .env, data, bases, Excel ni canales de actualización.",
    ]
    p.write_text("\n".join(body) + "\n", encoding="utf-8")
    return p


def launch(root: Path) -> None:
    pyw = root / ".venv" / "Scripts" / "pythonw.exe"
    launcher = root / "ABRIR_RECEPCION.py"
    if pyw.is_file() and launcher.is_file():
        try:
            subprocess.Popen(
                [str(pyw), str(launcher)],
                cwd=str(root),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                | getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception:
            pass


def main() -> None:
    if os.name != "nt":
        fail("Este reparador solo funciona en Windows.")

    root = detect_root()
    safety_check(root)

    if os.environ.get("DR_REVELO_REPAIR_TEST") == "1":
        repaired, _, _ = repair_files(root)
        print("TEST_REPAIR_OK", len(repaired))
        return

    msg(
        "Voy a reparar únicamente la cadena STARTUP-IMPORT de esta copia vieja de Recepción.\n\n"
        "NO se tocarán .env, data, bases de pacientes, Excel, Neon ni el canal estable publicado.\n\n"
        f"Carpeta detectada:\n{root}"
    )

    repaired, _, backup_dir = repair_files(root)
    ensure_pg8000(root)
    ok, output = import_test(root)
    report = write_report(root, repaired, output)

    if not ok:
        fail(
            "Se repusieron los módulos faltantes, pero la prueba final todavía falló.\n\n"
            "No se tocaron tus datos.\n\n"
            f"Diagnóstico guardado en:\n{report}\n\n"
            + output[-1800:]
        )

    msg(
        "STARTUP-IMPORT REPARADO ✅\n\n"
        f"Archivos repuestos: {len(repaired)}\n"
        f"Respaldo de archivos inválidos: {backup_dir or 'no fue necesario'}\n\n"
        "La prueba 'import app' terminó correctamente.\n"
        "No se modificaron datos ni configuración privada."
    )
    launch(root)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        fail(f"No se pudo completar la reparación.\n\n{type(exc).__name__}: {exc}")

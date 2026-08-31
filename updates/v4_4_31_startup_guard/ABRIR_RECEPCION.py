from __future__ import annotations

# v4.4.31 — launcher guard.
#
# Mantiene intacto el launcher estable 4.3.57 como motor interno y añade una
# comprobación que antes faltaba: si una actualización compila, se instala, pero
# el backend NUEVO no logra responder, se restaura automáticamente el respaldo
# anterior antes de abrir la interfaz. Así una mejora no debe dejar una ventana
# blanca por un fallo de arranque.

import os
import time
import traceback
import zipfile
from pathlib import Path

import ABRIR_RECEPCION_base_4357 as base

LAUNCHER_VERSION = "4.4.31-startup-guard-1"
base.LAUNCHER_VERSION = LAUNCHER_VERSION


def _restore_update(result: dict, root: Path = base.ROOT) -> bool:
    raw = str((result or {}).get("backup") or "").strip()
    paths = [
        str(x or "").replace("\\", "/").lstrip("/")
        for x in ((result or {}).get("paths") or [])
    ]
    if not raw:
        return False
    backup = Path(raw)
    if not backup.is_file():
        return False

    try:
        with zipfile.ZipFile(backup, "r") as z:
            backed = {
                str(name).replace("\\", "/").lstrip("/")
                for name in z.namelist()
            }

            # Si el update añadió un archivo que antes no existía, el ZIP no lo
            # contiene. Solo se elimina si ese archivo estaba expresamente en la
            # lista de la actualización; nunca se toca data/.venv/.env.
            for rel in paths:
                if not rel or rel in backed:
                    continue
                try:
                    dest = base._safe_target(root, rel)
                    if dest.is_file():
                        dest.unlink()
                except Exception:
                    pass

            for name in z.namelist():
                dest = base._safe_target(root, name)
                dest.parent.mkdir(parents=True, exist_ok=True)
                tmp = dest.with_name(
                    dest.name + f".health_rollback_{os.getpid()}_{time.time_ns()}"
                )
                tmp.write_bytes(z.read(name))
                os.replace(tmp, dest)

        return base._installation_consistent(root)
    except Exception as exc:
        base._log("Rollback por health-check falló: " + repr(exc), root)
        return False


def _start_expected(expected: str, splash, first_wait: float = 20.0) -> bool:
    base._start_server()
    splash.set("Cargando agenda…", "Esperando al servidor local")
    if base._wait_server(expected, first_wait, splash):
        return True

    base._stop_server()
    base._start_server()
    splash.set("Verificando conexión…", "Reintentando el inicio local")
    return base._wait_server(expected, 16.0, splash)


def main() -> None:
    base._set_windows_identity()

    if base._running_version(timeout=0.45) is not None and base._focus_existing_window():
        return

    handle, already = base._acquire_mutex()
    if already:
        base._focus_existing_window()
        base._release_mutex(handle)
        return

    splash = base.Splash()
    rollback_used = False

    try:
        splash.set("Verificando actualización…", "Comprobando el canal seguro")
        result = base.check_and_apply_update(base.ROOT)

        if result.get("blocked"):
            splash.close()
            base._message(
                result.get("error")
                or "La instalación local necesita reparación."
            )
            return

        if result.get("updated"):
            splash.set(
                "Instalando actualización…",
                f"Versión {result.get('version') or ''}",
            )
            if "app.py" in {str(p).lower() for p in result.get("paths", [])}:
                base._stop_server()

        expected = base._expected_app_version(base.ROOT)
        current = base._running_version()

        if current != expected:
            splash.set("Iniciando sistema…", "Preparando datos locales")
            if current is not None:
                base._stop_server()

            if not _start_expected(expected, splash):
                # DIFERENCIA CLAVE CON EL LAUNCHER ANTERIOR:
                # si justo acabamos de actualizar y la nueva versión no arranca,
                # restauramos el backup que el propio launcher ya había creado.
                if result.get("updated") and result.get("backup"):
                    failed_version = str(result.get("version") or expected or "")
                    splash.set(
                        "Recuperando versión anterior…",
                        "La mejora no inició; restaurando automáticamente",
                    )
                    base._log(
                        f"Health-check falló tras instalar {failed_version}; "
                        "rollback automático en curso.",
                        base.ROOT,
                    )
                    base._stop_server()

                    if not _restore_update(result, base.ROOT):
                        raise RuntimeError(
                            "La actualización no inició y el respaldo automático "
                            "no pudo restaurarse."
                        )

                    expected = base._expected_app_version(base.ROOT)
                    splash.set(
                        "Recuperación completada…",
                        f"Abriendo versión estable {expected}",
                    )
                    if not _start_expected(expected, splash, first_wait=22.0):
                        raise RuntimeError(
                            "El respaldo fue restaurado, pero el backend anterior "
                            "tampoco respondió. Revisa data\\backend_startup.log."
                        )

                    rollback_used = True
                    base._write_state(
                        base.ROOT,
                        runtime_rollback=True,
                        failed_update_version=failed_version,
                        restored_version=expected,
                        last_error=(
                            "Actualización revertida automáticamente porque "
                            "no pasó el health-check de arranque"
                        ),
                    )
                    base._log(
                        f"Rollback automático OK. Restaurada versión {expected}.",
                        base.ROOT,
                    )
                else:
                    raise RuntimeError(
                        "El backend no respondió. "
                        "Revisa data\\backend_startup.log."
                    )

        if rollback_used:
            splash.set(
                "Sistema recuperado",
                "Se descartó la mejora defectuosa; tus datos no fueron modificados",
            )
            time.sleep(0.8)
        else:
            splash.set("Listo", "Abriendo Recepción")
            time.sleep(0.08)

        splash.close()
        if not base._open_webview():
            base._open_fallback()

    except Exception as exc:
        base._log(
            "Fallo general del launcher blindado: "
            + repr(exc)
            + " | "
            + traceback.format_exc(limit=6).replace("\n", " | "),
            base.ROOT,
        )
        splash.close()
        base._message(
            "No se pudo iniciar Recepción.\n\n"
            "El detalle quedó guardado en data\\launcher_errors.log."
        )
    finally:
        splash.close()
        base._release_mutex(handle)


if __name__ == "__main__":
    main()

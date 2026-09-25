# Stack activo de Recepción

Arquitectura oficial vigente:

- Recepción: **v4.5.44**
- Fuente canónica de versión: `updates/v4_5_33_single_version_source/recepcion-version.json`
- Launcher nativo: **Launcher v1**
- Canal de Recepción: `launcher-v1/app-channel.json`
- Canal del launcher: `launcher-v1/launcher-channel.json`
- Launcher: `launcher-v1/RecepcionLauncher`
- Helper de self-update: `launcher-v1/LauncherUpdater`
- Desinstalador: `launcher-v1/Uninstaller`

## Reglas

1. `recepcion-version.json` es la única fuente real de versión de Recepción.
2. `version`, `app_version` y `runtime_version` solo existen como aliases temporales de compatibilidad y deben ser idénticos a la versión canónica.
3. El launcher Python `ABRIR_RECEPCION.py` está retirado. No debe aparecer en instaladores, reparadores ni workflows activos.
4. Las actualizaciones oficiales son obligatorias. Si existe una versión superior, Recepción no debe abrir hasta instalarla correctamente.
5. `.env`, `data/`, bases, Excel y backups son rutas protegidas y nunca forman parte de un payload de actualización.
6. `latest-v4*.json` son únicamente canales legacy de compatibilidad; el canal oficial es `launcher-v1/app-channel.json`.
7. Los árboles históricos bajo `updates/` se conservan para trazabilidad y dependencias antiguas, pero no son entrypoints activos.
8. Cualquier instalador maestro futuro debe construirse desde cero sobre Launcher v1; los builders Python antiguos fueron retirados.
\n## Audit candidate (not published)\n- Recepción 4.6.0 candidate: `audit/recepcion-v4.6.0-stabilization`\n- Launcher 1.0.13 candidate: strict isolated preflight + same-version repair + portable runtime support.\n
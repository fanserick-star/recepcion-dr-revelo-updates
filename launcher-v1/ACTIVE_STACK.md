# Stack activo de Recepción

Arquitectura oficial vigente:

- Recepción: **v4.5.48**
- Fuente canónica de versión: `recepcion-version.json`
- Fuente del payload oficial: `launcher-v1/app-channel-source.json`
- Canal validado de Recepción: `launcher-v1/app-channel.json`
- Launcher nativo: **v1.0.12**
- Canal del launcher: `launcher-v1/launcher-channel.json`
- Launcher: `launcher-v1/RecepcionLauncher`
- Helper de self-update: `launcher-v1/LauncherUpdater`
- Desinstalador: `launcher-v1/Uninstaller`

## Estado del runtime

Recepción 4.5.48 conserva el comportamiento funcional de 4.5.47 y añade una reparación de integridad del paquete.

El canal oficial vuelve a distribuir todos los módulos que forman la cadena ACTIVA del runtime. Esto permite que el launcher repare una instalación a la que le falte un módulo histórico o tenga uno dañado, en vez de depender de que esos archivos ya existan en la PC.

Los módulos 4.5.13–4.5.16 no forman parte de la cadena activa actual y no se distribuyen como dependencias. Los árboles históricos bajo `updates/` se conservan solamente para trazabilidad.

Los helpers de instalación/base `azur_client.py`, `whatsapp_client.py` y `remote_agenda.py` siguen siendo dependencias de la instalación base y no se reemplazan mediante una actualización ordinaria hasta cerrar la auditoría del instalador maestro.

## Reglas

1. `recepcion-version.json` es la única fuente real de versión de Recepción.
2. `version`, `app_version` y `runtime_version` son aliases de compatibilidad y deben coincidir exactamente con la versión canónica.
3. El launcher Python `ABRIR_RECEPCION.py` está retirado. No debe aparecer en instaladores, reparadores ni workflows activos.
4. Las actualizaciones oficiales son obligatorias. Si existe una versión superior, Recepción no debe abrir hasta instalarla correctamente.
5. `.env`, `data/`, bases, Excel, histórico y backups son rutas protegidas y nunca forman parte de un payload de actualización.
6. Cada archivo del canal se descarga a staging y se verifica por SHA-256 antes de modificar la instalación.
7. La actualización crea respaldo de los archivos reemplazados y ejecuta rollback si la candidata no inicia.
8. `latest-v4*.json` son canales legacy de compatibilidad; el canal oficial es `launcher-v1/app-channel.json`.
9. Los árboles históricos bajo `updates/` no son entrypoints activos.
10. El instalador actual del Launcher es un migrador para instalaciones existentes, no un instalador limpio de la aplicación completa. Un instalador maestro futuro debe construirse desde cero sobre Launcher v1.

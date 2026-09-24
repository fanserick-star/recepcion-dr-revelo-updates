# Stack activo de Historia Clínica

Arquitectura nueva de launcher:

- Historia Clínica candidata oficial: **v1.3.5**
- Fuente canónica de versión: `historia-version.json`
- Launcher nativo: **Historia Launcher v1.0.0**
- Puerto local: **8787**
- Canal de Historia: `historia-clinica/launcher-v1/app-channel.json`
- Canal del launcher: `historia-clinica/launcher-v1/launcher-channel.json`
- Launcher: `HistoriaClinicaLauncher.exe`
- Helper: `HistoriaLauncherUpdater.exe`

Reglas:
1. data/, .env, DB, MDB/ACCDB, Excel y backups nunca forman parte de un payload.
2. La actualización es obligatoria cuando el canal anuncia una versión superior.
3. Antes de instalar se prueba una copia aislada con backup SQLite.
4. El launcher Python queda solo como compatibilidad histórica hasta confirmar la migración real.
5. Reparar acceso directo usa HistoriaClinicaLauncher.exe desde Historia 1.3.5.

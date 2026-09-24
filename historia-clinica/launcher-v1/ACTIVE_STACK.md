# Stack activo de Historia Clínica

Arquitectura nueva preparada para migración:

- Historia Clínica: **v1.3.5**
- Fuente canónica de versión: `historia-clinica/updates/v1_3_5_launcher_v1_migration/historia-version.json`
- Launcher nativo: **v1.0.0**
- Canal de Historia: `historia-clinica/launcher-v1/app-channel.json`
- Canal del launcher: `historia-clinica/launcher-v1/launcher-channel.json`
- Puerto local: **8787**
- AppUserModelID: `DrArmandoRevelo.HistoriaClinica`

## Blindajes

1. Instancia única y enfoque de la ventana existente.
2. Actualizaciones oficiales obligatorias: actualizar o salir.
3. Self-update autocontenido con helper nativo oculto.
4. SHA-256 del instalador, helper y archivos de Historia.
5. Soporte de archivos multipart con SHA del archivo final ensamblado.
6. Preprueba aislada antes de tocar la instalación real.
7. Copia SQLite consistente para la preprueba.
8. Backup y rollback si la versión nueva no inicia.
9. Verificación de `product=historia-clinica-dr-revelo` antes de cerrar el proceso del puerto 8787.
10. Rutas protegidas: `data/`, `.env`, backups, DB/SQLite/Access y Excel.
11. WebView2 nativo dentro del launcher.
12. Logs de backend y self-update.
13. Reparación de acceso directo apunta a `HistoriaClinicaLauncher.exe`.
14. `historia-version.json` es la única fuente real de versión; aliases legacy deben coincidir.

## Migración

Los canales legacy `latest-historia.json` y `latest-historia-runtime.json` se conservan sin cambios hasta confirmar que el launcher v1 funciona correctamente en la PC real. Después se podrán retirar o marcar como compatibilidad, igual que se hizo con Recepción.

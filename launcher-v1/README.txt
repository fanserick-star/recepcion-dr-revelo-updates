LAUNCHER RECEPCIÓN - DR. ARMANDO REVELO v1.0.12

CONTENIDO
- INSTALAR_LAUNCHER_RECEPCION_DR_REVELO_V1_0_12.exe
  Migra una instalación EXISTENTE de Recepción al launcher nativo.
  Reemplaza los accesos directos y elimina los restos conocidos de ABRIR_RECEPCION.py.
  NO es un instalador limpio de la aplicación completa.
  NO toca .env, data, bases, Excel, histórico ni historias clínicas.

- RecepcionLauncher.exe
  Launcher nativo escrito desde cero. Ventana propia WebView2 con icono turquesa exclusivo de Recepción.
  No depende de Tkinter ni del launcher Python antiguo.
  Las actualizaciones oficiales de Recepción son obligatorias.
  Cada actualización se descarga a staging, se verifica por SHA-256,
  se prueba antes de aplicar, respalda los archivos reemplazados y conserva rollback automático.
  Si no hay Internet y no existe una actualización conocida pendiente, abre la versión instalada.

- LauncherUpdater.exe
  Helper temporal del self-update del launcher.
  Se descarga y verifica junto con el instalador del launcher nuevo.

- Desinstalar_Recepcion_Dr_Revelo.exe
  Borrado TOTAL de Recepción.
  Requiere escribir ELIMINAR y confirmar por segunda vez.
  Elimina C:\Recepcion Dr Revelo, .env, data, bases locales, respaldos,
  perfiles propios, accesos directos, AppData y temporales de Recepción.
  NO elimina Historia Clínica.

PROTECCIONES
- Instancia única: un segundo clic no abre otra Recepción; trae la existente al frente.
- Canal oficial: launcher-v1/app-channel.json.
- Fuente única de versión: recepcion-version.json.
- .env, data/, bases, Excel, histórico y backups no forman parte de las actualizaciones ordinarias.
- SHA-256, preflight y rollback antes de dar por válida una actualización.
- Desde Recepción 4.5.48 el canal vuelve a distribuir la cadena activa completa del runtime, por lo que también puede reparar módulos históricos faltantes o dañados.

IMPORTANTE
Este instalador v1.0.12 es un MIGRADOR de launcher y requiere que Recepción ya exista en C:\Recepcion Dr Revelo.
El instalador limpio/maestro de la aplicación completa se audita y se construye por separado.

LAUNCHER RECEPCIÓN - DR. ARMANDO REVELO v1.0

CONTENIDO
- INSTALAR_LAUNCHER_RECEPCION_DR_REVELO_V1.exe
  Migra una instalación existente de Recepción al launcher nuevo.
  Reemplaza los accesos directos y elimina ABRIR_RECEPCION.py.
  NO toca app.py, .env, data, bases, Excel ni historias clínicas.

- RecepcionLauncher.exe
  Launcher nuevo escrito desde cero.
  No depende de Tkinter ni del launcher Python antiguo.
  Comprueba actualizaciones pero pide confirmación antes de descargar.
  Si no hay internet, abre la versión instalada.
  Las actualizaciones se descargan a staging, verifican SHA-256,
  se prueban antes de aplicar y conservan rollback automático.

- Desinstalar_Recepcion_Dr_Revelo.exe
  Borrado TOTAL de Recepción.
  Requiere escribir ELIMINAR y confirmar por segunda vez.
  Elimina C:\Recepcion Dr Revelo, .env, data, bases locales, respaldos,
  perfiles propios, accesos directos, AppData y temporales de Recepción.
  NO elimina Historia Clínica.

RECOMENDACIÓN
Primero ejecutar INSTALAR_LAUNCHER_RECEPCION_DR_REVELO_V1.exe.
Usar el desinstalador únicamente si realmente se desea borrar Recepción y todos sus datos locales.

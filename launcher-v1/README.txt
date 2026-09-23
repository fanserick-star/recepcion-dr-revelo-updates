LAUNCHER RECEPCIÓN - DR. ARMANDO REVELO v1.0.3

CONTENIDO
- INSTALAR_LAUNCHER_RECEPCION_DR_REVELO_V1_0_3.exe
  Migra una instalación existente de Recepción al launcher nuevo.
  Reemplaza los accesos directos y elimina ABRIR_RECEPCION.py.
  NO toca app.py, .env, data, bases, Excel ni historias clínicas.

- RecepcionLauncher.exe
  Launcher nuevo escrito desde cero. Ventana propia WebView2 con icono del consultorio en título y barra de tareas.
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

- Protección de instancia única: un segundo clic no abre otra Recepción; trae la existente al frente.

- Autoactualización del propio launcher con confirmación, progreso y SHA-256.

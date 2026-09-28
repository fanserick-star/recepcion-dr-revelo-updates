INSTALADOR MAESTRO ONLINE - CONSULTORIO DR. ARMANDO REVELO

Versión del instalador maestro: 2.0.0

OBJETIVO
- instalar desde cero o reparar Recepción, Historia Clínica o ambos
- mantener el EXE maestro pequeño: no incrusta dos instaladores completos
- descargar únicamente los runtimes y launchers oficiales vigentes
- comprobar SHA-256 de cada archivo de aplicación y de cada launcher
- instalar un runtime privado compartido de Python 3.12 y crear cada .venv automáticamente
- no depender de Python previamente instalado en Windows
- no pedir archivos .env ni claves API durante el asistente

PROTECCIONES
- conserva data/, .env, .venv, bases locales, Excel, backups y archivos privados que no formen parte del canal oficial
- rechaza rutas inseguras del manifiesto
- comprueba la firma Authenticode del instalador oficial de Python
- comprueba SHA-256 de runtimes y launchers antes de usarlos
- los builds de ramas de prueba solo generan artefactos; únicamente main puede publicar el release de producción
- cualquier error deja registro en C:\ProgramData\DrReveloRuntime\logs

VERSIONES ESTABLES AL DISEÑAR V2
- Recepción: 4.6.7
- Historia Clínica: 1.3.73
- Recepción Launcher: 1.0.12
- Historia Clínica Launcher: 1.0.8

RUTAS CANÓNICAS
- Recepción: C:\Recepcion Dr Revelo
- Historia Clínica: C:\Historia Clinica Dr Revelo
- Runtime Python compartido: C:\ProgramData\DrReveloRuntime\Python312

CONFIGURACIÓN PRIVADA
El instalador no publica credenciales dentro del repositorio ni las solicita en pantalla.
Si una instalación existente ya tiene configuración privada, se conserva sin reemplazarla.
Las funciones que no requieren secretos arrancan con la configuración incorporada por el programa.
Las integraciones privadas siguen usando el mecanismo seguro definido por cada aplicación; este instalador nunca convierte claves privadas en archivos públicos del repositorio.

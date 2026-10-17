# Instalador online del consultorio (rama de validación)

Este proyecto recupera la arquitectura liviana: el EXE no contiene el programa clínico, datos clínicos ni credenciales reales. Al ejecutarlo, el bootstrap descarga desde los **canales publicados en main** la última Recepción e Historia Clínica, verifica cada archivo por SHA-256, instala dependencias/launchers y crea la configuración privada en la máquina autorizada.

## Qué quedó separado
- **Base pública**: \`INSTALADOR_CONSULTORIO_BASE_SIN_CREDENCIALES.exe\`. No funciona para instalaciones clínicas; rechaza iniciar sin la configuración sellada.
- **Instalador privado**: se genera **fuera de GitHub**, en un equipo de confianza, mediante \`seal_private_installer.py\`. Nunca enviarlo por correo ni publicarlo en un release, artifact o repositorio público.
- **Configuración real**: debe provenir de un almacén privado/operador autorizado. Nunca se agrega a commits, Actions públicos ni archivos de prueba.

## Formato para el operador autorizado (NO subir al repositorio)

\`\`\`ini
DR_REVELO_CONFIG_V2
[RECEPTION]
DATABASE_URL=<conexion PRIVADA de Recepción>
AZUR_API_KEY=<clave PRIVADA si aplica>
[HISTORIA]
HISTORIA_DATABASE_URL=<conexion PRIVADA de Historia Clínica>
\`\`\`

Se admiten otras claves pertinentes dentro de \`[RECEPTION]\`. El instalador la configura sin formularios en la PC destino; el archivo fuente privado solo se usa al sellar el instalador en el equipo de confianza.

\`\`\`powershell
python seal_private_installer.py --base INSTALADOR_CONSULTORIO_BASE_SIN_CREDENCIALES.exe --config configuracion-privada-local.txt --output INSTALAR_CONSULTORIO_PRIVADO.exe
\`\`\`

> Seguridad: como toda aplicación desatendida con credenciales, alguien con acceso al instalador privado puede extraerlas mediante ingeniería inversa. Distribución estrictamente privada, cifrado de disco, credenciales de privilegio mínimo y rotación/revocación si se filtra. No confundir cifrado integrado al EXE con un gestor de secretos de acceso cero.

## Validaciones pendientes antes de instalar en producción

Se valida sintaxis de PowerShell, compilación Windows x64 y sellado **con credenciales falsas**. Faltan pruebas completas con Windows limpio, dependencias y conexiones reales autorizadas. **No cambiar el instalador v1 publicado ni ejecutar en la PC del consultorio hasta aprobar esas pruebas.**

Rutas: \`C:\Recepcion Dr Revelo\`, \`C:\Historia Clinica Dr Revelo\`. Se conservan \`data/\` y archivos privados que no se actualizan por canal. Los accesos directos los prepara el instalador oficial del launcher.

Este proceso NO modifica pacientes, facturas ni bases de datos en GitHub.

## Crear el ejecutable privado SIN escribir las claves

En la PC de Recepción que ya está correctamente configurada, coloque juntos `create_private_installer.ps1`, `seal_private_installer.py` y el ejecutable base de la compilación de pruebas. Ejecute en PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\create_private_installer.ps1 -BaseExe .\INSTALADOR_CONSULTORIO_BASE_SIN_CREDENCIALES.exe
```

La herramienta lee los valores de `C:\Recepcion Dr Revelo\.env` y, si existe, `C:\Historia Clinica Dr Revelo\.env`. Si solo existe la configuración de Recepción, toma la conexión a Historia desde el puente ya configurado en Recepción. No pide escribir las API keys, no toca las bases, no imprime credenciales y elimina el archivo privado temporal. El ejecutable resultante se guarda en el escritorio como `INSTALAR_CONSULTORIO_PRIVADO.exe`.

Si la PC de Recepción no tiene guardadas todas las claves necesarias (por ejemplo, AZUR o integraciones específicas), deberán obtenerse del almacén privado autorizado antes de sellar; nunca de GitHub público. No distribuir el ejecutable privado fuera del consultorio.

## Auditoría de claves, 17 de octubre de 2026

Antes de crear un EXE privado, `create_private_installer.ps1` comprueba que en Recepción existan, con valor no vacío, `DATABASE_URL`, `AZUR_BASE_URL`, `AZUR_API_KEY`, `MOBILE_DOCTOR_TOKEN`, `MOBILE_RECEPTION_TOKEN`, y que Historia tenga una URL Neon independiente. **Esta preprueba garantiza presencia, no validez ni vigencia**: la conexión de Neon se comprueba tras la instalación; AZUR y los enlaces móviles requieren pruebas funcionales autorizadas en una PC nueva.

El creador no transfiere `RP_WORKSTATION_NAME`, `RP_DATA_DIR`, `RP_FORCE_OFFLINE`, `RP_PORT` ni otras opciones ligadas al equipo original. Configura la nueva Recepción en modo mensajería de nube (`WHATSAPP_CLOUD_MODE=1`, `WHATSAPP_ENABLED=0`) para no arrancar un segundo emisor local. Los secretos del proveedor que estén únicamente en workers de nube **no se extraen ni se necesitan en el EXE local**, pero se deben comprobar en su servicio de origen.

**La firma electrónica es una excepción expresa:** en Historia el certificado `data/firma_electronica/certificado_doctor.p12` y su `config.json` están fuera de `.env`. La contraseña PAdES no se almacena; se habilita localmente cuando lo autorice el doctor. El instalador online **no** transfiere ni desbloquea automáticamente el certificado, y no se deben poner esos archivos en GitHub.

Si el programa se reinstala sobre una PC existente, se conservan las claves locales ya escritas; por lo tanto una clave local incorrecta no queda reparada automáticamente y deberá diagnosticarse de forma segura. Las credenciales incorporadas a un USB pueden caducar o ser revocadas, por lo que conviene regenerar el EXE privado al rotar claves.

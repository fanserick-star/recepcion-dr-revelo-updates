# Entrega clínica desde Recepción — actualizado para Recepción 4.8.76

## Separación de responsabilidades
- Historia Clínica: el doctor crea, guarda y firma. No se envía WhatsApp desde Historia.
- Recepción: ficha del paciente → **Documentos médicos**, lista solo lectura desde `public.prescriptions` y `public.certificates` del **Neón dedicado de Historia**. Nunca vincula aquí; requiere `patient_links.verified=1`.
- Los PDF firmados se leen **solo** del archivo local de Historia por LAN, comprobando paciente/tipo/id, huella SHA-256 y ruta dentro de `data/documentos_firmados`. Nunca se regenera ni vuelve a firmar.
- Si Historia está apagada, el índice puede consultarse desde Neon, pero un PDF no se puede previsualizar ni enviar.
- Un documento sin PDF firmado no se envía como firmado.
- Recepción no cambia atenciones, fichas clínicas, recetas, cobros, AZUR, agenda ni alarmas del worker WhatsApp.

## Copia faststart de entrega para iPhone — Recepción 4.8.81

Con diagnóstico clínico **avc1, moov al final y R2 HTTP 206 correcto**,
preparar únicamente una copia temporal de entrega. El MP4 diagnóstico original
y la videocistoscopía archivada permanecen inmutables. La entrega anterior
con enlace temporal no cambia; se requiere **nuevo envío manual** a número de
pruebas ya autorizado y consentimiento específico.

- Al pulsar **«Preparar para iPhone y enviar ESTE video a MI WhatsApp de pruebas»**,
  Recepción identifica si moov está al final. Si es así, comprueba primero
  que FFmpeg esté instalado en el PATH o en una ruta local permitida y haya
  espacio en disco para otra copia completa. Si no lo está, responde 503
  ANTES de subir nada y sin intentar WhatsApp. No descarga ni ejecuta
  binarios de Internet automáticamente.
- Crea una copia privada bajo DATA_DIR/clinical_delivery_tmp con
  **FFmpeg -map 0 -c copy -movflags +faststart**: copia los flujos de audio
  y video sin recomprimir ni alterar los originales. No reduce calidad.
  Después vuelve a verificar que moov esté antes de mdat, que los
  identificadores de códec se conserven y que respete el límite 550 MiB.
- La copia es exclusivamente para R2. Se borra en un bloque finally
  independiente de éxito o fallo. La fase «Preparando copia iPhone» es
  anterior a la barra R2, para no falsificar velocidades de Internet.
- R2 se verifica con HEAD y URL corta, tras lo cual se solicita una única
  entrega manual mediante la plantilla aprobada a WHATSAPP_TEST_PHONE.
  En respuesta incierta, NO se reintenta ni se elimina el enlace de 7 días
  (el receptor podría haberlo recibido); comprobar primero en WhatsApp.
- Si incluso la copia faststart falla en iPhone, estudiar perfil/nivel,
  pixel format, audio y headers del archivo concreto. **No reducir ni
  recodificar un video clínico real a ciegas.**
- El envío general a pacientes sigue desactivado mediante
  CLINICAL_DELIVERY_LIVE_ENABLED=0. No cambiar alarmas, citas, facturas,
  sincronización ni Worker de WhatsApp.

## Alternativa sin WinGet — Recepción 4.8.83

Para equipos Windows antiguos sin `winget.exe`, el mismo botón
**«Instalar FFmpeg aquí (sin requerir WinGet)»** ofrece una ruta alternativa
tras la confirmación explícita del operador.

- Descarga **solo un wheel binario Windows** de `imageio-ffmpeg 0.6.0`
  desde una URL `files.pythonhosted.org` fijada en el código.
- Exige que su SHA-256 coincida exactamente con el publicado por PyPI
  para `win_amd64` o `win32`; limita bytes y verifica un ejecutable
  Windows antes de instalarlo.
- No ejecuta scripts del wheel ni `pip`. Extrae exclusivamente el
  ejecutable FFmpeg a `DATA_DIR/tools/ffmpeg.exe`, ejecuta
  `ffmpeg.exe -version` sin shell y publica el ejecutable con
  reemplazo atómico solo tras validarlo.
- Requiere conexión a PyPI y espacio suficiente en disco; ante fallo
  elimina archivos temporales y mantiene los envíos bloqueados.
- **No descarga ninguna videocistoscopia**, no cambia el video original,
  no llama a Meta/Cloudflare ni modifica Neón o las citas.
- Si WinGet sí está disponible, mantiene el instalador local anterior.
  No se utiliza ninguna instalación automática al actualizar Recepción:
  el usuario siempre debe autorizar expresamente la acción.

## Instalación guiada de FFmpeg — Recepción 4.8.82

- Si falta FFmpeg, **Recepción no sube ni envía la videocistoscopía**.
  En Documentos médicos aparece «Instalar FFmpeg en esta PC (Windows)».
  La instalación solo se inicia tras confirmar explícitamente el operador.
- El servidor acepta este cambio **únicamente desde localhost** y usa
  un comando fijo de `winget`: paquete `Gyan.FFmpeg`, versión `9.0.2`,
  origen `winget`, alcance de usuario y modo silencioso. No hay shell,
  argumentos provenientes de pacientes ni descargas de binarios a GitHub.
- La barra de estado local distingue instalando, disponible y error.
  WinGet es quien obtiene el paquete y valida sus hashes de distribución.
  La ruta `%LOCALAPPDATA%/Microsoft/WinGet/Links/ffmpeg.exe` y las carpetas
  portables del paquete se buscan sin depender del PATH del launcher.
- Si WinGet o el instalador no funciona, **no se relaja el bloqueo**;
  se muestra un mensaje para instalar App Installer de Microsoft o
  FFmpeg desde `https://ffmpeg.org/download.html#build-windows`.
- El paquete FFmpeg **no** está integrado en el actualizador de Recepción
  y su instalación puede requerir internet/espacio libre. No cambia el
  almacenamiento original, Neon, las alarmas de citas ni los mensajes.
- Tras el éxito, repetir el diagnóstico. El video real solo se envía
  mediante su botón habitual y con identidad/consentimiento verificados.

## Diagnóstico de reproducción iPhone/Safari — Recepción 4.8.80

Un MP4 de videocistoscopía real ya se entregó correctamente por WhatsApp
mediante enlace corto R2, pero Safari mostró reproductor tachado. HTTP 200,
subida completa y tamaño por HEAD **no demuestran compatibilidad de reproducción**.
No reenviar archivos reales ni modificar calidad diagnóstica sin identificar causa.

En la ficha correcta (Documentos médicos → Archivo de videocistoscopías),
presionar **«Diagnosticar reproducción en iPhone»** junto al MP4 ya guardado:

1. El servidor comprueba que la ficha Recepción↔Historia esté vinculada
   y que el video concreto pertenece a dicha ficha.
2. Analiza **solo la estructura local MP4**, leyendo como máximo 12 MiB
   del índice moov: detecta las pistas por el identificador del códec
   (`avc1`, `hvc1`, `mp4v`, etc.), posición del índice y presencia del
   contenedor MP4. No convierte, edita ni elimina la grabación original.
3. En un procedimiento independiente sube **126 bytes ficticios** a R2,
   solicita `GET Range: bytes=0-1`, exige `HTTP 206`, bytes correctos
   y `Content-Range`, y elimina ese archivo sintético.
   No sube material clínico ni llama al Worker/Meta.
4. Muestra resultado y recomendación sin nombres, rutas, números ni
   enlaces firmados. Que HTTP 206 funcione para el archivo ficticio
   **no garantiza** que el objeto original conserve todos sus headers;
   es un primer diagnóstico de conexión. Que el códec sea `avc1`
   tampoco garantiza que su perfil y estructura sean soportados.
5. Si el MP4 usa códec no compatible con Safari, planificar una **copia
   específica para reproducción H.264** con consentimiento y revisión
   clínica; conservar el MP4 diagnóstico original sin cambios.
   Si moov está al final, valorar `faststart` sobre copia, sin
   sobreescribir el original. No aplicar ninguna conversión a ciegas.

La versión mantiene `CLINICAL_DELIVERY_LIVE_ENABLED=0` y no modifica
las citas, sus alarmas ni la entrega del enlace de siete días ya enviado.

## Video archivado real a WhatsApp propio de pruebas — Recepción 4.8.79

Con la videocistoscopía **ya guardada en Recepción y vinculada a la ficha
verificada en Historia**, el operador puede efectuar un envío manual al
número personal previamente autorizado como `WHATSAPP_TEST_PHONE`.

1. En Documentos médicos, junto a cada video archivado aparece
   **«Enviar ESTE video a MI WhatsApp de pruebas»**. No reutiliza el
   archivo seleccionado en USB: accede a la copia local archivada, cuya
   pertenencia a la ficha clínica se confirma en el servidor.
2. Es obligatorio escribir el número personal de pruebas y declarar dos
   confirmaciones: ficha y video correctos; **consentimiento explícito del
   paciente para enviar su video médico a ese número particular**. Los
   pacientes reales no tienen habilitado envío general.
3. Un único trabajo envía el MP4 a R2 con progreso de bytes y velocidad.
   Se verifica tamaño mediante HEAD y enlace corto seguro antes de Meta.
   Solo se usa la plantilla de DOCUMENTO previamente aprobada con
   etiqueta **VIDEO CLINICO AUTORIZADO** (sin nombres ni datos personales
   dentro del mensaje).
4. El Worker comparte emisor Meta de citas, pero utiliza autorización
   clínica de un solo uso en Neon, totalmente separada de las alarmas.
   R2 conserva el objeto durante el plazo privado de 7 días si se
   acepta el mensaje; si se falla antes de Meta, se intenta borrar.
   Si Meta responde con incertidumbre no se reintenta automáticamente.
5. El resultado «Meta aceptó» NO confirma entrega ni lectura al teléfono.
   Se requiere comprobarlo en el WhatsApp de pruebas. Auditar el
   identificador de mensaje localmente; no escribir contenido médico a Neon.
6. **Mantener `CLINICAL_DELIVERY_LIVE_ENABLED=0`**. El nuevo botón no
   autoriza enviar arbitrariamente a cualquier número, no expone videos
   en el Worker ni requiere reconfigurar credenciales de citas.

## Prueba de subida REAL con progreso — Recepción 4.8.78

En Recepción → ficha verificada → Documentos médicos → Archivo de videocistoscopías, seleccionar un MP4 real (máximo 550 MiB) y pulsar «Medir subida REAL a Cloudflare R2». Confirmar que corresponde al paciente y que existe autorización para la transferencia temporal a la nube.

1. El navegador primero copia el MP4 hacia el servidor local de Recepción. La interfaz distingue esta fase del tiempo de subida a Internet.
2. Recepción transmite el MP4 a R2 en bloques de 512 KiB; el estado solo accesible con usuario de Recepción y un identificador aleatorio reporta bytes enviados, MiB/s, tiempo transcurrido y ETA aproximado. El 100 % de bytes no equivale a entrega hasta confirmar HTTP.
3. Se consulta HEAD de R2 y se compara Content-Length con los bytes originales. Después se solicita inmediatamente DELETE de R2. La prueba termina correctamente solo si la eliminación fue confirmada.
4. El original de la PC se conserva; la copia temporal local se borra en finally. Si falla R2 se intenta también borrar el archivo remoto. La regla R2 clinical-temp/ de siete días sigue siendo protección adicional si la red impide el borrado inmediato.
5. NO envía enlace por WhatsApp ni cambia CLINICAL_DELIVERY_LIVE_ENABLED=0, alarmas, citas, facturas ni datos clínicos. El envío a un paciente necesitará confirmación de identidad, teléfono, consentimiento y habilitación explícita del módulo.

La velocidad indicada es de bytes enviados por el socket a R2, no prueba de persistencia hasta que HEAD lo confirme. Subida multipart/reanudable aún no se ha implementado; primero recoger tiempos reales con autorización.

## Enlaces cortos y prueba de video — Recepción 4.8.76

- Recepción ahora guarda un manifiesto JSON privado en
  `clinical-temp/short-links/<token-aleatorio>.json` dentro del mismo bucket R2.
  Solo contiene la URL firmada a R2 y su fecha de caducidad. **No se guarda en
  Neón, ni contiene nombres, números de teléfono o fichas de pacientes.**
- El Worker de WhatsApp usa el binding `CLINICAL_LINKS_R2` para buscar ese
  manifiesto. `GET /d/<token>` devuelve una redirección temporal **302**
  hacia el enlace firmado, nunca transmite el PDF ni el MP4 por el Worker.
  El enlace es aleatorio, no enumerativo, expira tras siete días y no es
  indexable; sigue siendo un enlace de posesión: quien lo tenga puede abrirlo.
- El manifiesto reside dentro del prefijo `clinical-temp/`, cubierto por la
  política de eliminación automática de 7 días. El Worker comprueba
  independientemente `expires_epoch` y rechaza URL externas.
- Antes de solicitar el envío WhatsApp, Recepción comprueba que el enlace corto
  realmente resuelva al archivo R2 esperado, con petición de rango de 1 byte;
  ante un fallo no envía el mensaje.
- Hay dos pruebas manuales separadas en **Documentos médicos**: PDF sintético y
  **MP4 sintético de 2 segundos**, dirigido exclusivamente a
  `WHATSAPP_TEST_PHONE`. Ambas comparten el bloqueo de 5 minutos. La prueba MP4
  utiliza deliberadamente la plantilla de documento ya aprobada para comprobar
  el transporte, pero **no valida todavía la plantilla de video**.
- **No se prueba un video de 500 MB todavía.** La subida en paralelo,
  reanudación y progreso son una optimización posterior que requiere medición,
  sin usar jamás videos médicos reales como datos ficticios.
- Mantener `CLINICAL_DELIVERY_LIVE_ENABLED=0` hasta completar pruebas y
  revisar permisos y consentimiento de entrega a pacientes.

## Motor WhatsApp unificado — Recepción 4.8.75

**Esta sección sustituye la configuración de tokens locales descrita en
versiones anteriores.** La entrega clínica utiliza ahora exactamente el Worker
Cloudflare de citas (`dr-revelo-whatsapp-cloud`), con una puerta y una
autorización independientes en `/clinical/dispatch`.

1. Recepción valida identidad, teléfono, consentimiento y vínculo histórico.
   `CLINICAL_DELIVERY_LIVE_ENABLED=0` continúa bloqueando pacientes.
2. El PDF o MP4 se sube **directamente desde Recepción a R2**, sin enviar el
   archivo al Worker ni a Neón. Se firma el enlace temporal a siete días.
3. Recepción genera un permiso aleatorio efímero de 256 bits. En la tabla
   independiente `whatsapp_cloud.clinical_delivery_caps` (solo creada una vez)
   se guardan exclusivamente SHA-256 del permiso y un hash del destinatario ligado al permiso secreto, modalidad,
   caducidad y marca de consumo. No contiene teléfonos, nombres ni URLs.
4. Recepción llama a `/clinical/dispatch` con un cuerpo acotado.
   Cloudflare reclama el permiso en una actualización atómica y **solo entonces**
   llama al mismo `sendMeta` que utiliza la mensajería de citas. No utiliza
   cron, colas de citas ni alarma Durable Object.
5. Si la respuesta de Meta es incierta, nunca hay un reintento automático.
   Una ID de Meta significa *aceptación*, no recepción en el teléfono.

**Ya no se necesita `WHATSAPP_CLINICAL_ACCESS_TOKEN` ni
`WHATSAPP_ACCESS_TOKEN` local para entrega clínica.** Los valores
preexistentes en el `.env` quedan intactos para evitar pérdidas, pero
el módulo clínico no los consulta al enviar. El token emisor vigente
permanece como secreto en el Worker, donde hoy funciona para citas.

La primera prueba debe usar exclusivamente el PDF ficticio y
`WHATSAPP_TEST_PHONE`. Probar el botón de envío real a pacientes solo después
de autorización, pruebas sintéticas aprobadas y consentimiento, manteniendo
el control independiente de habilitación.

**Sobre rendimiento**: este cambio reduce el salto de mensajería y elimina
duplicados de configuración, pero la transferencia de MP4 de ~500 MB sigue
limitada por la subida de Internet de Recepción. La optimización multipart
con barra de progreso es una etapa separada, que requiere benchmark seguro
del almacenamiento R2 y no debe improvisarse en producción.

## Diagnóstico Meta sin mensajes — Recepción 4.8.73

En **Documentos médicos → Prueba de WhatsApp en mi celular**, presiona
**Comprobar permisos Meta sin enviar mensajes**. Realiza dos solicitudes GET a Meta
con el token exclusivo de entregas clínicas, sin subir archivos, enviar WhatsApp,
leer pacientes ni modificar Neon, alarmas o cuenta.

- **Identidad del token**: consulta `/me?fields=id`; si la respuesta es accesible,
  Meta reconoce ese token.
- **Lectura del número**: consulta `/{Phone-Number-ID}?fields=id,display_phone_number`;
  puede requerir `whatsapp_business_management`, incluso cuando
  `whatsapp_business_messaging` está disponible. Un rechazo aquí no demuestra
  por sí solo que la mensajería esté bloqueada.
- Solo se muestran éxito/fallo y códigos HTTP/Meta numéricos; no se devuelven token,
  teléfono, identidad del usuario, nombres, enlaces firmados ni mensajes de error
  originales del proveedor.

**La lectura de metadatos no valida la autorización para enviar mensajes.** Si el envío
real sigue rechazado con código 10 después de comprobar scopes, número y asignación,
revisar con Meta el permiso efectivo de la cuenta WhatsApp y los detalles del error.
No cambiar `CLINICAL_DELIVERY_LIVE_ENABLED=0` ni insistir en envíos repetidos.

## Token clínico independiente — Recepción 4.8.72

El Worker de citas, autoagenda y recordatorios usa sus propias plantillas y credenciales de Cloudflare. La entrega clínica es manual y se realiza desde Recepción, que toma los nombres de las dos plantillas clínicas de su configuración local. Meta no exige que los nombres estén en un `.env`; la separación es una decisión de arquitectura, no la causa directa del código de permiso 10.

**IMPORTANTE:** el envío de documentos/vídeos utiliza únicamente `WHATSAPP_CLINICAL_ACCESS_TOKEN`. Ya no reutiliza `WHATSAPP_ACCESS_TOKEN` ni el token del Worker de citas. No se copiaron claves a GitHub y el actualizador preserva el `.env`.

Para utilizar el nuevo token de sistema que se guardó en `WHATSAPP_ACCESS_TOKEN` antes de esta versión:
1. Actualizar Recepción mediante su launcher hasta 4.8.72.
2. Abrir `Configurar_envios_clinicos.vbs` en Windows.
3. Pulsar **Copiar token ya guardado a clínica** y confirmar explícitamente. Solo copia el valor a `WHATSAPP_CLINICAL_ACCESS_TOKEN`: no elimina, revoca ni cambia el original, el token de citas, la base de datos ni el Worker. Alternativamente, pegar manualmente un token clínico distinto en **Meta: Token EXCLUSIVO de entrega clínica** y pulsar **Guardar SOLO token clínico**.
4. No usar **Guardar preparación** solo para guardar el token. Mantener `CLINICAL_DELIVERY_LIVE_ENABLED=0`, y preservar `WHATSAPP_CLINICAL_TEMPLATES_APPROVED=1` si Meta ya aprobó ambas plantillas.
5. Reiniciar Recepción, comprobar estado en **Documentos médicos**, y solo después usar **una prueba sintética explícita** al número `WHATSAPP_TEST_PHONE`. No habilitar entregas a pacientes hasta verificar permisos y entrega.

Si Meta devuelve HTTP 400, código 10, hay que comprobar asignación/autorización del token a la cuenta WABA, permisos y número; la presencia de plantillas en el `.env` no causa por sí sola ese código.

## Preparación local asistida — Recepción 4.8.60

El bucket `dr-revelo-clinical-2026` ya se creó con retención R2 de 7 días; la prueba real de S3 desde GitHub validó PUT, GET, hash SHA-256, DELETE y 404 tras borrar. **Esto no instala las claves en la PC:** GitHub Actions Secrets no pueden leerse desde el programa ni publicarse en un canal de actualizaciones. No intentar copiar tokens desde los logs.

1. En Windows, actualizar Recepción con su launcher a **4.8.60**. Desde la carpeta de instalación del programa, abrir **`Configurar_envios_clinicos.vbs`** con doble clic; inicia el asistente gráfico usando su `.venv\\Scripts\\pythonw.exe`, sin CMD.
2. En el asistente introducir **Account ID** de Cloudflare y la pareja R2 S3 **Access Key ID / Secret Access Key** restringida al bucket. No confundir con el token general **`CLOUDFLARE_R2_API_TOKEN`**. Si la clave secreta se perdió, emitir otra credencial R2 específica desde Cloudflare, no copiarla de GitHub ni pegarla en chats.
3. Opcional por ahora: **Phone Number ID** y un **token Meta con permisos de envío**, correspondientes al mismo número de citas; el Worker de Cloudflare mantiene su propio secreto y este asistente nunca lo lee ni modifica. Añadir celular de prueba autorizado si se conoce.
4. Generar y guardar la clave compartida **LAN** de Recepción. Configurar **exactamente el mismo valor** en el archivo privado `.env` de la PC de Historia Clínica (`CLINICAL_DELIVERY_LAN_SECRET`) usando un canal local controlado, no mensajería externa. No cambiarla si ya estaba configurada.
5. Guardar. **Siempre queda `CLINICAL_DELIVERY_LIVE_ENABLED=0` y `WHATSAPP_CLINICAL_TEMPLATES_APPROVED=0`.** Reiniciar Recepción para recargar la configuración y ejecutar la comprobación R2 en la ficha → Documentos médicos. Ningún envío clínico a pacientes se activa con este paso.
6. Una vez que Meta muestre estado **Aprobada/Activa** para `entrega_documento_clinico` y `entrega_video_clinico` en **Spanish (ECU)**, se revisarán el idioma, orden de las cuatro variables, acceso LAN y entrega al iPhone de prueba. Solo después, habilitar manualmente los indicadores y las plantillas del entorno local. No marcar "aprobadas" durante revisión.

El asistente actualiza solo un conjunto permitido de claves en el `.env` **local protegido de Recepción**, que el launcher conserva. Preserva intactas `DATABASE_URL`, `WHATSAPP_ENABLED`, las alarmas, AZUR, la configuración de citas, archivos clínicos y datos de pacientes. El `.env` contiene secretos locales en texto; no subirlo a repositorios, enviarlo por WhatsApp, ni adjuntarlo a soporte. Restringir el acceso al usuario Windows autorizado y mantener las protecciones del equipo. Las claves guardadas en GitHub son para pruebas de GitHub Actions y no se sincronizan a la PC.

## Activar (solo después de configurar)

En la configuración privada de Recepción (no subir claves al repositorio):

```dotenv
CLINICAL_R2_ACCOUNT_ID=<account-id>
CLINICAL_R2_BUCKET=<nombre-bucket-privado-standard>
CLINICAL_R2_ACCESS_KEY_ID=<r2-access-key>
CLINICAL_R2_SECRET_ACCESS_KEY=<r2-secret-key>
CLINICAL_R2_7_DAY_LIFECYCLE_CONFIRMED=1
CLINICAL_DELIVERY_LAN_SECRET=<clave-aleatoria-de-64-caracteres-o-mas>
WHATSAPP_CLINICAL_DOCUMENT_TEMPLATE=entrega_documento_clinico
WHATSAPP_CLINICAL_VIDEO_TEMPLATE=entrega_video_clinico
WHATSAPP_CLINICAL_LANGUAGE=es_EC
```

En la PC de Historia se requiere `CLINICAL_DELIVERY_LAN_SECRET` con el **mismo valor**, al menos 32 caracteres. Mantenerla privada y reiniciar ambos programas. Además se necesitan las variables WhatsApp Graph de Recepción `WHATSAPP_GRAPH_VERSION`, `WHATSAPP_PHONE_NUMBER_ID` y **`WHATSAPP_CLINICAL_ACCESS_TOKEN`**, exclusivamente para la entrega clínica; deben corresponder al mismo número registrado en Meta. Si actualmente estas credenciales solo están en el worker Cloudflare, hay que provisionarlas en Recepción de forma segura. No copiarlas a archivos públicos.

### Cloudflare R2
1. Crear bucket **privado, Standard**. No activar `r2.dev` público ni dominio público para los objetos.
2. Crear clave API restringida al bucket.
3. Configurar regla de *Object Lifecycles* que elimine los objetos del prefijo `clinical-temp/` después de **7 días**. Confirmar la regla en el dashboard ANTES de poner `CLINICAL_R2_7_DAY_LIFECYCLE_CONFIRMED=1`.
4. El enlace presignado GET vence a 604800 segundos (siete días). La eliminación física R2 puede completarse después de vencer el objeto según su política.
5. El enlace firmado es un **enlace portador**: quien lo reciba puede abrirlo durante su vigencia. La comprobación de identidad y el consentimiento en Recepción se hacen antes del envío; no existe autenticación del destinatario al abrir el enlace. Para exigir comprobación de identidad al descargar, debe añadirse una pasarela de autenticación; no presentar esta versión como acceso con OTP.

### Plantillas Meta
Crear y obtener aprobación explícita de dos plantillas de categoría *Utility*, idioma `es_EC`, cuerpo con **cuatro variables, en este orden**: nombre del paciente, clase de archivo, fecha de expiración, URL. El backend **no** manda texto libre fuera de la ventana de 24 h; solo invoca plantillas. No configurar los nombres anteriores hasta ver **Approved** en Meta.

**entrega_documento_clinico**
> Estimado/a {{1}}: el consultorio del Dr. Armando Revelo le comparte su {{2}}. Descárguelo desde el enlace privado: {{4}}. Disponible hasta {{3}}. Le recomendamos guardarlo y no compartir el enlace. Este mensaje contiene información médica confidencial.

**entrega_video_clinico**
> Estimado/a {{1}}: el consultorio del Dr. Armando Revelo le comparte el video de su {{2}}. Descárguelo en calidad original: {{4}}. Estará disponible hasta {{3}}. Guarde su copia antes del vencimiento y no comparta el enlace.

Los textos definitivos requieren aceptación por Meta. Si Meta rechaza o no acepta la plantilla, no se confirma el envío.

### Procedimiento operador
- Abrir ficha del paciente en Recepción → Documentos médicos. Confirmar identidad y celular; no enviar si ficha sin vínculo clínico verificado.
- Seleccionar **Ver PDF** (si el doctor firmó), o **Enviar WhatsApp**. Para video conectar el USB, seleccionar MP4 de hasta 550 MiB.
- Confirmar de forma individual el celular, la identidad y consentimiento para el canal. No hay envíos automáticos.
- El sistema transmite temporalmente a R2, solicita a Meta el mensaje y registra únicamente el id enviado / fecha de vencimiento en la PC de Recepción.
- Los PDF originales del doctor NO se borran. El MP4 original del USB NO se borra.

### No probar con datos reales hasta completar la configuración
No compartir claves, videos ni enlaces de pacientes en chats de soporte. Probar primero con un archivo sintético y el teléfono del propio consultorio. La API de WhatsApp puede producir cargos de plantilla según categoría, país y ventanas de servicio. La aplicación no garantiza lectura/descarga final: el ID de Meta confirma aceptación de la API, no la entrega efectiva.

## Prueba desde tu iPhone — sin pacientes

**Primera etapa (disponible sin Cloudflare ni Meta):** abre desde Safari en el iPhone:
https://fanserick-star.github.io/recepcion-dr-revelo-updates/prueba-envio-clinico.html

Puedes alternar entre documento/videocistoscopía y descargar un PDF sintético. Esto solo **simula** el texto y la presentación; no genera mensajes en la API de Meta, no sube nada a R2 ni crea datos clínicos.

**Segunda etapa (mensaje real desde el número de citas):** una vez configuradas las credenciales y aprobadas las plantillas, abre Recepción → cualquier ficha → Documentos médicos → Prueba de WhatsApp en mi celular. Introduce el número de prueba configurado como `WHATSAPP_TEST_PHONE` y pulsa «Enviar PRUEBA REAL a mi WhatsApp». Debes confirmar personalmente. El programa:
- Comprueba que el número coincide EXACTAMENTE con el autorizado como `WHATSAPP_TEST_PHONE`.
- Crea un PDF con el texto «PRUEBA SIN DATOS MEDICOS», nunca consulta documentos de pacientes.
- Lo sube al prefijo `clinical-temp/self-test/` de R2 y lo descarga para verificar igualdad de bytes.
- Envía una única plantilla Meta `WHATSAPP_CLINICAL_DOCUMENT_TEMPLATE` con variables: «PACIENTE DE PRUEBA», «DOCUMENTO DE PRUEBA (SIN DATOS MEDICOS)», vencimiento y enlace.
- Limita los reenvíos de prueba a uno por cinco minutos por ejecución.

La aceptación de Meta **no garantiza la recepción en el teléfono**: revisar el WhatsApp de tu iPhone y tocar el enlace es la comprobación final. No incluyas datos clínicos, teléfonos ajenos ni credenciales en el chat de soporte.

## Acciones que se hacen en los paneles oficiales de Cloudflare y Meta

No es posible provisionar Cloudflare R2 ni aprobar plantillas únicamente publicando código de GitHub. Estas acciones requieren que el propietario de las cuentas entre al proveedor; no pegues tokens en ChatGPT ni subas `.env` a GitHub.

**Cloudflare (solo una vez):**
1. Abrir https://dash.cloudflare.com/ → R2 Object Storage y activar R2 si aún no está habilitado.
2. Crear bucket **privado** de clase Standard (por ejemplo `revelo-clinical-delivery`); NO activar exposición pública.
3. Bucket → Settings → Object lifecycle rules → nueva regla para el prefijo `clinical-temp/` → eliminar objetos tras **7 días**. No confundir con limpieza de multipart uploads incompletos: son reglas distintas.
4. Crear una credencial R2 S3 restringida al bucket con acceso de lectura/escritura para generar enlaces y subir archivos. Copiarla exclusivamente a la configuración local privada de Recepción. [Instrucciones oficiales](https://developers.cloudflare.com/r2/api/tokens/).
5. Una vez confirmado visualmente el bucket y la regla, activar `CLINICAL_R2_7_DAY_LIFECYCLE_CONFIRMED=1` en el `.env` privado de Recepción; nunca activarla antes de crear la regla.

**Meta WhatsApp Manager:**
1. Abrir https://business.facebook.com/wa/manage/message-templates/ con la cuenta de WhatsApp Business que usa el consultorio.
2. Crear las plantillas `entrega_documento_clinico` y `entrega_video_clinico` en el idioma `es_EC` (o el idioma que Meta permita). Usar exactamente cuatro variables en el orden definido en este documento: nombre, clase de archivo, vencimiento y URL.
3. No activar los nombres de las plantillas en el `.env` hasta que Meta muestre el estado **Approved**.
4. El envío parte de la **misma WABA/número de confirmaciones**, con Graph API y token autorizado. Cuando las credenciales solo existan en el worker Cloudflare, se debe suministrar una credencial válida para Recepción de forma privada; no copiar la clave por chat ni tocar alarmas o confirmaciones.

**Configuración local de los dos equipos:**
- En la instalación de Recepción, usar el archivo privado `.env` situado junto a `core_runtime.py`; completar todas las variables del bloque de configuración anterior y añadir `WHATSAPP_TEST_PHONE=09XXXXXXXX` (tu teléfono de prueba) y `WHATSAPP_CLINICAL_ACCESS_TOKEN` (token exclusivo, secreto).
- En la instalación de Historia, agregar `CLINICAL_DELIVERY_LAN_SECRET=<mismo-secreto-largo>` al `.env` situado junto a `app.py`. Historia 1.4.22 lee ese archivo desde el puente LAN. El valor debe ser un secreto aleatorio de al menos 32 caracteres, idéntico en las dos PC.
- Mantener estos archivos fuera de copias públicas y restringir su acceso al personal del consultorio. Reiniciar ambos programas para volver a cargar claves WhatsApp.
- Consultar `/api/clinical-delivery/status` desde el equipo de Recepción para ver únicamente estados de configuración. Nunca muestra los tokens.

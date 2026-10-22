# Entrega clínica desde Recepción — 4.8.59 / Historia 1.4.22

## Separación de responsabilidades
- Historia Clínica: el doctor crea, guarda y firma. No se envía WhatsApp desde Historia.
- Recepción: ficha del paciente → **Documentos médicos**, lista solo lectura desde `public.prescriptions` y `public.certificates` del **Neón dedicado de Historia**. Nunca vincula aquí; requiere `patient_links.verified=1`.
- Los PDF firmados se leen **solo** del archivo local de Historia por LAN, comprobando paciente/tipo/id, huella SHA-256 y ruta dentro de `data/documentos_firmados`. Nunca se regenera ni vuelve a firmar.
- Si Historia está apagada, el índice puede consultarse desde Neon, pero un PDF no se puede previsualizar ni enviar.
- Un documento sin PDF firmado no se envía como firmado.
- Recepción no cambia atenciones, fichas clínicas, recetas, cobros, AZUR, agenda ni alarmas del worker WhatsApp.

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

En la PC de Historia se requiere `CLINICAL_DELIVERY_LAN_SECRET` con el **mismo valor**, al menos 32 caracteres. Mantenerla privada y reiniciar ambos programas. Además se necesitan las variables WhatsApp Graph de Recepción `WHATSAPP_GRAPH_VERSION`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_ACCESS_TOKEN`; **deben corresponder al mismo número** utilizado para confirmación. Si actualmente estas credenciales solo están en el worker Cloudflare, hay que provisionarlas en Recepción de forma segura. No copiarlas a archivos públicos.

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
- En la instalación de Recepción, usar el archivo privado `.env` situado junto a `core_runtime.py`; completar todas las variables del bloque de configuración anterior y añadir `WHATSAPP_TEST_PHONE=09XXXXXXXX` (tu teléfono de prueba).
- En la instalación de Historia, agregar `CLINICAL_DELIVERY_LAN_SECRET=<mismo-secreto-largo>` al `.env` situado junto a `app.py`. Historia 1.4.22 lee ese archivo desde el puente LAN. El valor debe ser un secreto aleatorio de al menos 32 caracteres, idéntico en las dos PC.
- Mantener estos archivos fuera de copias públicas y restringir su acceso al personal del consultorio. Reiniciar ambos programas para volver a cargar claves WhatsApp.
- Consultar `/api/clinical-delivery/status` desde el equipo de Recepción para ver únicamente estados de configuración. Nunca muestra los tokens.

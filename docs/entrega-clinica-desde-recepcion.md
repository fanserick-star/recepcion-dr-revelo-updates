# Entrega clínica desde Recepción — 4.8.58 / Historia 1.4.21

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

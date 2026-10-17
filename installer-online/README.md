# Instalador maestro único — Consultorio Dr. Revelo

**ESTADO ACTUAL: CANDIDATO DE PRUEBAS. NO APTO TODAVÍA PARA PRODUCCIÓN.**

## Arquitectura única y limpia

El candidato oficial se compila exclusivamente desde `consultorio_oneclick.c`.
El EXE público no contiene claves del consultorio, ni dependencias empacadas
ni datos de pacientes. Contiene solamente dos scripts sin secretos:

- `auto_enroll_install.ps1`: autoriza la computadora mediante el servicio aislado
  Cloudflare, con una clave RSA-CNG efímera, código de autorización y
  contraseña administrativa. Descarga la configuración cifrada exclusivamente
  para esa PC y no la almacena en archivos temporales.
- `bootstrap.ps1`: instala automáticamente **Recepción e Historia Clínica**
  (ambos), Python 3.12, WebView2, las dependencias, los launchers y los accesos
  directos. Descarga desde los canales publicados usando comprobación SHA-256.

El método histórico de incrustar secretos en un EXE privado NO se usa ni se
compila en el nuevo instalador maestro.

## Recuperación de Historia Clínica

En PC completamente nueva `bootstrap.ps1` ejecuta una recuperación inicial
desde el **Neon dedicado de Historia Clínica**, no desde el de Recepción. El
código está en `restore_historia_initial.py` y está incrustado sin cambios en
el bootstrap. Usa una transacción PostgreSQL **READ ONLY**, solo escribe la
SQLite **local** de la PC nueva y compara cantidades de pacientes/atenciones.

También restaura las revisiones de consultas y los registros de auditoría,
que son tablas de solo subida en la sincronización habitual. La instalación
no se declara terminada si la recuperación inicial queda incompleta.

Una base clínica existente del doctor jamás se borra ni se sobrescribe. Si
el instalador reanuda una recuperación creada por él mismo usa su marcador
privado y aborta ante cambios locales pendientes para no sobrescribir datos.
No se borra ni reinicia el estado de sincronización de instalaciones antiguas.

## Servicio de autorización centralizada

Servicio independiente: `dr-revelo-enrollment.drrevelo.workers.dev` y
namespace KV independiente. El repositorio contiene el código sin secretos
en `enrollment_worker.mjs`. Requiere los secretos Cloudflare
`DR_REVELO_ADMIN_TOKEN`, `RECEPTION_ENV_B64` y `HISTORIA_ENV_B64`.
Hasta configurar los tres, el servicio falla cerrado y ninguna computadora
puede obtener las claves.

No está integrado en `dr-revelo-whatsapp-cloud` y no modifica la agenda,
la facturación, la recepción o la historia actualmente instaladas.

Una vez hecha la provisión por la administración, instalar cualquier nueva PC
es doble clic al mismo EXE, aprobar esa PC con la contraseña administrativa,
y dejar que se instalen ambos programas. La PC original puede estar apagada.

## Única configuración inicial (una vez en el consultorio)

1. Desplegar el Worker independiente mediante
   `.github/workflows/deploy-consultorio-enrollment.yml`. **Su despliegue
   independiente ya pasó el workflow de GitHub**, pero hay que comprobar
   y registrar los secretos reales antes de habilitar instalaciones.
2. Desde la PC de Recepción ya configurada, el administrador ejecuta
   `provision_once_reception.ps1` de manera local con un token Cloudflare
   autorizado de alcance limitado y el identificador de cuenta. La herramienta
   lee únicamente los valores necesarios del `.env` local y configura de modo
   cifrado los secretos Cloudflare, sin introducir manualmente claves Neon/AZUR
   y sin pasar sus valores a GitHub ni a este chat.
3. Guardar la contraseña administrativa de autorización en un gestor seguro.
   Cada PC nueva requiere aprobación, pero nunca introducir API keys.

Las configuraciones locales de Historia se contrastaron por presencia. Su
conexión `HISTORIA_DATABASE_URL` debe corresponder al mismo Neon clínico
dedicado. Otros secretos que estuviesen únicamente en la PC del doctor y
fuesen necesarios deberán añadirse mediante un procedimiento autorizado
antes de afirmar que están incorporados.

**EXCEPCIÓN NECESARIA:** el certificado electrónico `.p12/.pfx` del doctor
no está en `.env` y su contraseña no se guarda. El módulo se instalará
automáticamente; el doctor debe configurar/desbloquear el certificado
en la PC autorizada, sin almacenar su contraseña en el instalador.

## Puertas obligatorias antes de una entrega real

- [x] Compilación PE x64 y pruebas automatizadas de Windows PowerShell.
- [x] Pruebas de denegación de solicitudes no autorizadas y cifrado de claves
  usando datos ficticios.
- [x] Ensayos que prueban no modificación de SQLite con datos clínicos previos
  o locales pendientes.
- [x] Worker independiente desplegado sin afectar al worker de WhatsApp.
- [ ] Provisión segura inicial de secretos auténticos desde la PC autorizada.
- [ ] Autorización real de una PC Windows limpia y descarga completa de ambos
  canales publicados.
- [ ] Restauración de los registros clínicos, revisión de conteos, consultas y
  recetas en esa PC nueva sin ningún cambio remoto.
- [ ] Verificación de AZUR sin emitir facturas, agenda móvil y WhatsApp sin
  un segundo emisor.
- [ ] Pruebas de impresoras, actualización de ambos launchers y estabilidad en
  una computadora antigua.
- [ ] Revisión de antivirus/SmartScreen y firma del ejecutable si se requiere.
- [ ] Confirmación explícita de que el instalador se puede distribuir.

**No se debe entregar el EXE ni fusionar esta rama de prueba a los canales
de actualización del consultorio mientras las puertas estén pendientes.**

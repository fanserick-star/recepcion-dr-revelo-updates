# Auditoría independiente de Recepción — 25-09-2026

## Base estable

- Versión funcional de partida: **4.5.47**.
- 4.5.47 conserva el runtime bueno de 4.5.44/4.5.46 y corrige únicamente el cálculo de procedimientos con valor editable en la capa de pagos.
- La auditoría posterior no debe reconstruir Recepción desde una versión anterior ni mezclarla con Historia Clínica.

## Cambios aplicados durante la auditoría

### 4.5.48 — integridad del runtime

Se detectó que el canal oficial distribuía pocos archivos aunque `app.py` dependía de una cadena histórica grande de módulos. El precheck del launcher podía resolver módulos faltantes desde la instalación antigua, por lo que una actualización podía pasar la prueba sin ser autosuficiente para reparar una PC dañada.

Corrección:

- El canal oficial 4.5.48 distribuye **59 archivos**.
- Incluye **55 dependencias activas** del runtime.
- Conserva exactamente el comportamiento funcional de 4.5.47.
- Mantiene el arreglo de Fulguración/valores editables.
- No cambia esquemas, pacientes, Neon, Historia Clínica, Bendo, agenda, facturación ni impresión.
- Los módulos 4.5.13–4.5.16 no pertenecen a la cadena activa y no se redistribuyen.
- Se agregó `static/runtime_keep.txt` para que el staging aislado tenga el directorio `static/` requerido por FastAPI durante el precheck.

### Canal y CI

- `launcher-v1/app-channel-source.json` es la fuente del payload.
- `launcher-v1/app-channel.json` se genera únicamente después de validar los blobs exactos y SHA-256.
- La publicación validada de 4.5.48 terminó correctamente.
- Se endureció `.github/workflows/audit-active-reception-channel-bytes.yml`:
  - descarga cada archivo exacto del canal;
  - verifica SHA-256;
  - valida rutas protegidas;
  - valida versión canónica y aliases;
  - compila todos los módulos Python del payload;
  - comprueba el cierre de imports locales;
  - comprueba que todas las dependencias declaradas estén en el canal;
  - impide reintroducir 4.5.13–4.5.16 como dependencias activas.

## Protecciones que se mantienen

El launcher no permite que una actualización ordinaria escriba sobre:

- `.env`
- `data/`
- bases SQLite
- Excel
- histórico 2020–2025
- backups
- `RecepcionLauncher.exe`

La actualización usa staging, SHA-256, respaldo previo y rollback.

## Hallazgos todavía abiertos

### 1. Cadena histórica grande

El runtime sigue compuesto por muchos módulos históricos. En 4.5.48 se volvió reparable y verificable, pero todavía no se consolidó físicamente.

**Decisión:** no hacer otra consolidación directa sobre producción. La futura 4.6.x debe construirse como candidata separada y demostrar equivalencia antes de publicarse.

### 2. Helpers de la instalación base

`app_base_4428.py` todavía importa:

- `azur_client.py`
- `whatsapp_client.py`
- `remote_agenda.py`

No forman parte del canal ordinario actual. Las instalaciones existentes ya los tienen, pero un instalador limpio debe incorporarlos explícitamente y validarlos.

**No reemplazar ni inventar estos helpers desde una actualización normal.**

### 3. Cloudflare Tunnel legado

El core todavía contiene importaciones y endpoints `/api/mobile/remote/*` del sistema viejo de túnel. El flujo actual de Agenda 24/7 usa GitHub Pages + Neon y el startup ya intenta detener el túnel antiguo.

**Pendiente:** comprobar que ningún flujo visible ni herramienta de rescate usa esos endpoints antes de retirar el helper `remote_agenda.py` y las rutas antiguas.

### 4. Actualizador ZIP interno legado

Sigue existiendo `POST /api/update/apply`, aunque la interfaz actual usa Launcher v1 como actualizador oficial y las cajas antiguas están ocultas.

**Pendiente:** confirmar que no existe ningún caller activo antes de retirar el endpoint y el código ZIP antiguo.

### 5. Instalador limpio

El instalador de Launcher v1.0.12 es un **migrador**: exige una instalación existente de Recepción. No constituye un instalador maestro limpio.

Un instalador maestro privado antiguo del consultorio usaba `ABRIR_RECEPCION.py`, por lo que ya no representa la arquitectura vigente.

**Pendiente:** construir un instalador limpio nativo que:
- use `RecepcionLauncher.exe`;
- incluya el runtime completo y los helpers base;
- preserve `.env` y `data/` en reinstalaciones;
- no incluya bases de pacientes;
- valide SHA-256;
- pueda instalar en una PC vacía;
- no dependa del launcher Python retirado.

## Regla de publicación durante la auditoría

No se publica una versión funcional nueva solo por “limpiar código”. Los cambios de producción se limitan a reparaciones verificables y reversibles. Las consolidaciones, eliminaciones grandes y el instalador limpio se prueban fuera del canal estable antes de reemplazar el runtime usado en el consultorio.

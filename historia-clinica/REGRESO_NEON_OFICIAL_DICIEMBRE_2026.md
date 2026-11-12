# Regreso inteligente de Historia Clínica al Neon Oficial (diciembre de 2026)

**Estado:** procedimiento PREPARADO; retorno NO activado. El Neon de emergencia continúa activo.
Nunca desactivar ni eliminar un proyecto antes de completar la validación final.

## Por qué no repetir la migración de noviembre
El cambio de noviembre volvió a poner ~25.000 filas del SQLite en la cola `sync_dirty`.
Eso causó escrituras redundantes, excesiva transferencia y riesgo de reactivar filas eliminadas.
**No ejecutar** `_seed_emergency_cutover` ni copiar la tabla completa para volver al Neon original.

## Preflight ahora preparado
Archivo `tools/historia_neon_return_preflight.py`: herramienta de **solo lectura**.
Obtiene un resumen por bloques (256 buckets MD5 por PK), compara huellas calculadas
en cada Neon y descarga solo los identificadores y fingerprints de los bloques
diferentes. No transfiere notas clínicas, nombres, recetas ni secretos a la salida.
Reconoce inserciones, actualizaciones, borrados, posibles resurrecciones y cambios
de esquema. `cloud_updated_at` se excluye como metadato; el estado de `deleted_at`
se compara explícitamente. Esta es una evaluación, **no** la migración.

Para ejecutarlo **únicamente en diciembre, con Historia cerrada tras terminar la consulta**, 
definir localmente, de forma privada, las variables `HISTORIA_RETURN_EMERGENCY_URL` y
`HISTORIA_RETURN_OFFICIAL_URL` (cadenas directas, base `neondb`), y ejecutar
`python tools/historia_neon_return_preflight.py`. Nunca introducir claves en GitHub
ni en el chat. El programa impone `SET TRANSACTION READ ONLY` en ambas conexiones.

## Reglas del regreso (NO implementado aún)
1. Fuente autoritativa: Neon de emergencia y SQLite local, **después** de reconciliar
   consultas eliminadas por error (tombstones) y vaciar/explicar la cola pendiente.
2. Congelar cambios clínicos un instante al finalizar las atenciones; mantener
   respaldos verificables de SQLite, PDFs firmados y ambos Neon.
3. Comparar 11 conjuntos (incluyendo auditorías), sus IDs y contenido lógico:
   no confiar solo en el número de filas. Revisar cambios exclusivos del Neon
   antiguo. `patient_links` se mantiene bajo autoridad de Recepción, `waiting_queue`
   requiere reconciliación de turnos activos, y auditorías/revisiones deben
   deduplicarse por sus claves únicas reales.
4. Transferir **solo** filas nuevas/modificadas, en lotes pequeños y reanudables,
   preferentemente con inserciones condicionales/guardas de versión. Nunca usar
   `deleted_at=NULL` indiscriminadamente ni sobreescribir un registro firmado
   más reciente. Conflictos -> detener y revisar, no aplicar «local wins» a ciegas.
5. Verificar datos, firmas, PDFs, enlaces de pacientes, eliminaciones y colas
   antes y después de la copia. Comparar fingerprints finales y casos críticos.
6. Cambiar la conexión del doctor al Neon original **solo tras autorización
   explícita del usuario** y con rollback ensayado. No encender las dos
   sincronizaciones activas en paralelo. Registrar la transición sin credenciales.
7. Observar transferencia/latencia durante la primera jornada y conservar
   Neon de emergencia como respaldo hasta validar estabilidad.

## Pendiente de implementación antes de diciembre
- Motor de transferencia diferencial **en modo simulación primero** y después
  transacciones con checkpoints; **no existe todavía y no debe improvisarse**.
- Reparación y validación de tombstones históricos afectados por Historia 1.4.81.
- Pruebas end-to-end de consultas, recetas, certificados, revisiones y firmas.
- Confirmar cuotas, transferencia disponible y conectividad del Neon original.

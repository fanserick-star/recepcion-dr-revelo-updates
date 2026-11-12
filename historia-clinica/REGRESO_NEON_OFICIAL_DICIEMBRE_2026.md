# Regreso inteligente de Historia Clínica al Neon Oficial — diciembre 2026

**Estado:** motor de regreso **implementado y preparado** en `neon_official_return.py` de Historia 1.4.84.
**No activado:** Historia continúa trabajando con Neon de emergencia. Ningún cambio de servidor se ejecuta automáticamente.

## Ahorro de datos
- El motor calcula huellas dentro de cada base (256 grupos por clave) y solo trae al proceso local **identificadores y huellas de los grupos distintos**.
- Copia solamente filas ausentes y, tras autorización adicional, filas modificadas con verificación optimista. Tamaño de transacción: 25. Reanuda ejecutando un plan nuevo: lo ya copiado no se repite.
- Excluye `cloud_updated_at` de las diferencias de contenido y respeta `deleted_at`. Nunca reactiva automáticamente un registro eliminado.
- Imprime totales por tabla, nunca nombres de pacientes, notas clínicas, recetas, cadenas de conexión ni archivos firmados.
- `audit_log` y `encounter_revisions` son de solo inserción (sin modificar entradas originales).
- `patient_links` (autoridad de Recepción), `waiting_queue` (turnos activos) y `clinic_settings` (preferencias del servidor) no se sobreescriben. Cualquier diferencia requiere revisión humana antes del cambio.

## Uso futuro exclusivamente con mantenimiento clínico
1. Actualizar Historia a 1.4.84 (esto **solo instala la herramienta**), corregir los registros ya afectados por el error antiguo de eliminación, y mantener Neon de emergencia como activo hasta diciembre.
2. Terminar las consultas, cerrar Historia en la PC del doctor; comprobar que `sync_dirty` no tenga pendientes ni conflictos abiertos. Conservar copias verificadas **de ambos Neon**, SQLite y documentos firmados.
3. El operador autorizado, **en esa misma PC, fuera del programa**, ejecuta el proceso:
   - `python neon_official_return.py --phase plan` con la variable de entorno temporal `HISTORIA_RETURN_MAINTENANCE_CONFIRMED=1`.
   - Revisar los conteos de inserciones, diferencias, marcas de eliminación y tablas manuales. La herramienta imprime `plan_sha256`.
   - `python neon_official_return.py --phase copy --approved-plan HASH --confirm COPIAR_DIFERENCIAS` con las variables `HISTORIA_RETURN_MAINTENANCE_CONFIRMED=1` y `HISTORIA_RETURN_BACKUPS_VERIFIED=1` después de verificar las copias. Solo copiará diferencias aprobadas; no restaurará eliminados. Si existen actualizaciones de filas existentes, requiere revisión adicional y la opción `--allow-reviewed-updates`.
   - Repetir un plan nuevo si hubo cambios desde la copia (la operación es idempotente por clave, sin resetear todo).
   - `python neon_official_return.py --phase verify`. La verificación bloqueará el regreso si hay diferencias clínicas, eliminaciones contradictorias o tablas manuales pendientes.
   - Solo si la verificación es satisfactoria y tras autorización explícita del usuario: `python neon_official_return.py --phase switch --approved-plan HASH_VERIFICADO --confirm ACTIVAR_NEON_OFICIAL` con ambos indicadores de mantenimiento y copias. Esta fase cambia el `.env` local de manera atómica, conserva la conexión anterior en un archivo privado y escribe el punto de sincronización comprobado para impedir la descarga íntegra en el primer arranque.
4. Abrir Historia desde el launcher, comprobar pacientes, consultas, firmas, recetas, TV/LAN y consumo de transferencia. Si algo no cuadra, interrumpir, **no eliminar** el Neon de emergencia. Regreso/rollback siempre con intervención autorizada.

## Protecciones
- El programa no inicia este mecanismo por sí solo, ni en noviembre ni en diciembre.
- Si el puerto de Historia sigue abierto, si hay sincronización local pendiente, conflictos abiertos o no se verificaron respaldos, bloquea la transferencia.
- Si el plan cambia, su huella anterior deja de servir y la copia se rehúsa.
- Las modificaciones existentes requieren verificación de huellas inmediatamente antes de escribir y protección de `signed_at` para consultas firmadas.
- No hay escrituras automáticas de tablas propias de Recepción, ni transferencia de ZIP/PDF grandes por Neon.
- El plan y los ensayos con datos ficticios están integrados en las pruebas CI. **No se ha probado todavía un traslado real de producción.**

**Para diciembre:** no ejecutar nada de esto hasta que la sincronización de emergencia termine, el caso de las consultas antiguas incorrectamente reactivadas esté corregido y el usuario apruebe el traslado.

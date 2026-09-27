# Recepción: continuación del refactor — 2026-09-27 UTC

Base publicada: 4.6.6. Rama de trabajo: `refactor/reception-definitive-runtime`.
Los canales de producción no se modifican en esta etapa.

## Hallazgos reproducidos

El candidato anterior juntaba todas las funciones en `features_runtime.py` y
copiaba sus atributos a `SimpleNamespace`. Las funciones seguían consultando
el mismo diccionario global, aunque los atributos del namespace se cambiaran.
La equivalencia de rutas y OpenAPI no detectaba las consecuencias:

- Consultar un grupo de facturación podía terminar en `RecursionError`:
  `_stable_billing_group_records` era reemplazado por el envoltorio anterior.
- Los endpoints de comprobante y formulario fiscal conservaban los renderizadores
  iniciales, aunque otros módulos reemplazaban sus atributos por los definitivos.
- Los endpoints de salud/versionado heredados devolvían 4.5.25 en vez de 4.6.6.
- La expresión regular de la prueba de módulos históricos estaba doblemente
  escapada; informaba cero incluso para la base que carga 51 módulos históricos.

La prueba `tools/test_reception_runtime_bindings.py` falla con aquel candidato y
pasa con el nuevo. Utiliza una base temporal y compara con la 4.6.6 original.

## Cambios

- Módulos Python físicos con nombres por función y globals independientes.
  El registro contiene módulos reales: modificar un atributo modifica el global
  que consulta la función, preservando el comportamiento del programa original.
- `features_runtime.py` se limita al orden de inicio explícito. No hay fuentes
  embebidas, import hooks ni imports ejecutables de `app_patch_*`.
- Se eliminan tres capas que solo incrementaban versiones (4.5.9, 4.5.10 y 4.5.11);
  sus claves de compatibilidad apuntan a la implementación existente.
- El paquete se construye únicamente desde archivos declarados. Se excluyen las
  bases temporales y bytecode; se elimina del candidato la base vacía generada por
  la prueba anterior. No se modifican bases de usuarios.
- La prueba de actualización/rollback incluye archivos testigo del histórico
  2020–2025, además de configuración, SQLite, Excel 2026 y respaldos.

## Verificación

Las pruebas locales comprobaron 243 rutas sin duplicados, 12 tablas, 220 rutas
OpenAPI y 36 esquemas. Los hashes OpenAPI y de los overlays coinciden con la base.
También pasan la regresión de facturación/impresión/versiones, importación desde
el manifiesto y actualización/rollback conservando diez archivos testigo.

El workflow `Test Reception Flat Prototype` vuelve a construir y ejecutar las
pruebas en Windows. `VERIFICATION.json` se genera allí solo después de aprobarlas;
un sello anterior no se conserva como evidencia de estos cambios.

## Límites y siguientes etapas

La migración preserva código funcional auditado; no representa aún una eliminación
de todo código histórico o una separación completa de `core_runtime.py` en servicios.
El registro mantiene claves antiguas para preservar mutaciones entre funciones.
Las pruebas de impresión verifican el renderizador seleccionado; la salida física
requiere la impresora del consultorio. Los archivos históricos son testigos de
conservación, no una copia ni una auditoría de los datos reales de pacientes.

El instalador maestro existente sigue siendo para instalaciones base ya preparadas.
No se genera ni se publica un instalador nuevo en esta continuación del runtime.
Antes de publicar: revisar el resultado Windows, preparar una versión nueva y
validar en las PCs el arranque, la impresión y la actualización real del launcher.

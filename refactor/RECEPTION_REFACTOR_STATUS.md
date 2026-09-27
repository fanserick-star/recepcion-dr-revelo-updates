# Recepción — runtime consolidado listo para promoción

Base publicada actual: **4.6.6**. Rama aislada: `refactor/reception-definitive-runtime`.
Esta rama todavía **no publica ni modifica el canal estable**.

## Estado del runtime

La consolidación ya no depende de una cadena ejecutable de versiones históricas.
El arranque utiliza módulos físicos con nombres por función y un orden explícito en
`features_runtime.py`.

Garantías estructurales actuales:

- cero imports ejecutables `app_base_*`, `app_prev_*` o `app_patch_*`;
- cero `_rf_layers`, `_rf_legacy` y recorridos de `previous` entre releases;
- `app.py` importa directamente el runtime semántico;
- las funciones conservan globals reales por módulo, evitando los problemas del
  prototipo basado en `SimpleNamespace`;
- las bases de datos, `.env`, Excel, respaldos e históricos no forman parte del
  payload de actualización.

`runtime_registry.py` queda únicamente como archivo de compatibilidad inerte del
contrato 4.6.6 ya verificado: no contiene registro de capas y ningún módulo lo
importa. No representa una cadena de versiones.

## Verificación que se conserva

El workflow permanente `Verify Reception Semantic Runtime` trabaja directamente
sobre el candidato materializado; ya no reconstruye nada desde las capas antiguas.
Comprueba:

1. ausencia de cadenas históricas;
2. layout y dependencias del runtime;
3. equivalencia de rutas, tablas, OpenAPI y overlays con 4.6.6;
4. flujo funcional de consulta/procedimiento;
5. bindings de facturación, impresión y versión;
6. importación usando únicamente el manifiesto de paquete;
7. actualización y rollback conservando archivos de usuario protegidos.

## Limpieza realizada

Se eliminaron los constructores y transformadores usados durante la migración,
los analizadores de patrones/aliases, inventarios masivos, parches temporales de
builder y workflows de investigación. También se retiró `refactor_meta.json` del
candidato porque era trazabilidad del proceso y no forma parte del programa.

Se mantienen únicamente el runtime materializado, su evidencia de verificación,
las pruebas de regresión útiles y los workflows de auditoría/publicación que serán
necesarios al promoverlo.

## Siguiente etapa

La siguiente versión debe partir de este runtime semántico, no volver a generarse
desde `app_patch_*`. Para hacerlo oficial se preparará una versión nueva (4.6.7),
se conservará 4.6.6 como rollback y primero se probará en una PC del consultorio
antes de activar el canal para las demás.

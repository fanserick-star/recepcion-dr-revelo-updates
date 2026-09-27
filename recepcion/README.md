# Recepción — fuente canónica

Desde Recepción 4.6.7, `recepcion/app/` es la única fuente viva del runtime de Recepción.

Reglas permanentes:

- Las nuevas funciones y correcciones se editan directamente en `recepcion/app/`.
- `recepcion/app/recepcion-version.json` es la única fuente canónica de versión.
- No se crean carpetas `updates/v...` para nuevas versiones de Recepción.
- `updates/` se conserva únicamente como archivo histórico/compatibilidad y no debe usarse como origen de una publicación nueva.
- El canal estable se genera desde los archivos declarados en `launcher-v1/app-channel-source.json` y debe apuntar exclusivamente a `recepcion/app/`.
- Los datos locales, `.env`, bases SQLite/Excel y ejecutables del launcher no forman parte del payload del runtime.
- Antes de publicar una nueva versión se valida el runtime físico, el cierre del manifiesto, SHA-256 y rollback.

La versión 4.6.6 se conserva bajo `releases/reception/4.6.6/` como referencia de rollback. El historial completo anterior sigue disponible en Git y en `updates/` solo por compatibilidad.

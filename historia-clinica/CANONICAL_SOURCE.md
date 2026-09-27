# Historia Clínica — fuente canónica

Desde Historia Clínica 1.3.73, `historia-clinica/app/` es la única fuente viva del runtime.

Reglas permanentes:

- Las nuevas funciones y correcciones se editan directamente en `historia-clinica/app/`.
- `historia-clinica/app/historia-version.json` es la única fuente canónica de versión.
- No se crean carpetas `historia-clinica/updates/v...` para nuevas versiones.
- `historia-clinica/updates/` queda congelado como archivo histórico/compatibilidad y no se usa como origen de una publicación nueva.
- El payload de publicación se deriva de `historia-clinica/app/update_manifest.json`; el canal no mantiene una segunda lista manual de archivos.
- `.env`, bases clínicas, copias de seguridad, MDB/SQLite y datos del paciente nunca forman parte del payload del runtime.
- La 1.3.72 queda preservada bajo `releases/historia/1.3.72/` como rollback explícito.
- La 1.3.73 canónica parte byte por byte del runtime autocontenido ya publicado.

El árbol histórico `historia-clinica/updates/` queda sellado con SHA Git `c4759d655845a1f299b0a8569761a0fa128ac6f8`. Las validaciones deben fallar si ese árbol vuelve a cambiar.

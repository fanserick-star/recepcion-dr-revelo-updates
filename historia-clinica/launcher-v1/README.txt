LAUNCHER HISTORIA CLÍNICA - DR. ARMANDO REVELO
Versión 1.0.7

Migración del sistema de arranque de Historia Clínica al launcher nativo blindado.

Incluye:
- ventana nativa WinForms + WebView2;
- identidad visual azul clínico + marfil propia de Historia;
- instancia única;
- actualizaciones obligatorias;
- self-update autocontenido y silencioso;
- SHA-256;
- preprueba aislada con copia segura SQLite;
- backup/rollback transaccional;
- protección de data/, .env, bases, Excel/Access y backups;
- puerto dedicado 8787 con validación de producto;
- logs de arranque y self-update;
- reparación del acceso directo con el launcher nuevo.

Este instalador NO instala una base nueva de Historia. Requiere una instalación existente en:
C:\Historia Clinica Dr Revelo

No reemplaza historias, data/, .env ni la base local.

- v1.0.1: corrige la preprueba aislada con importación explícita de app.py y diagnóstico real de errores.

- v1.0.2: corrige definitivamente la preprueba aislada; usa scripts Python temporales reales en vez de bloques complejos por python -c.

- v1.0.3: reconstruye explícitamente el runtime aislado de Historia, verifica que app.py y dependencias existan físicamente y fuerza la ruta de importación de la copia de prueba.

- v1.0.4: carga app.py por ruta exacta con importlib.util tanto en preprueba como en arranque real, eliminando la dependencia del import por nombre.

- v1.0.6: consolida el launcher final sin reutilizar tags; WebView2 obligatorio, ventanas internas para documentos y hashes de release inmutables.

- v1.0.6: muestra el logo del consultorio y despierta/verifica la sincronización con Neon al iniciar, manteniendo modo local si la nube no responde.

- v1.0.7: icono azul marino/verde exclusivo de Historia Clínica para diferenciarlo visualmente de Recepción.

# Puente Recepción → Historia Clínica (candidato v4.5.8)

Candidato preparado para enlazar el botón/guardado de **Nueva atención** de Recepción con la cola **Pacientes en espera** de Historia Clínica.

- No envía notas clínicas, diagnósticos ni tratamientos.
- Envía únicamente ID interno de Recepción, nombre, identificación (si existe), tipo de atención, hora y los IDs de las atenciones creadas.
- Usa `HISTORIA_DATABASE_URL` desde el `.env` local de Recepción. La credencial **no se publica** en GitHub.
- Si Neon no está disponible, la atención de Recepción se guarda normalmente y el evento queda en `data/historia_bridge.db` para reintento.
- Esta carpeta es **candidato**, no cambia por sí sola el canal obligatorio `latest-v4.json` de Recepción.
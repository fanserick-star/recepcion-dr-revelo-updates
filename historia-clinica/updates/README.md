# Actualizaciones históricas de Historia Clínica

Las carpetas históricas que antes vivían en `historia-clinica/updates/` fueron retiradas físicamente de la rama `main` después de consolidar Historia Clínica.

Desde la versión 1.3.73:

- la única fuente viva del programa es `historia-clinica/app/`;
- no se deben crear nuevas carpetas `historia-clinica/updates/v...`;
- el canal estable no debe apuntar a este directorio;
- el rollback operativo conservado está en `releases/historia/1.3.72/`;
- versiones anteriores siguen recuperables mediante el historial de Git.

Este directorio se mantiene solo como marcador para impedir que vuelva el patrón de carpetas por versión.

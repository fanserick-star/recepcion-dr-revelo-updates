# Instalador maestro privado de Recepción

Este directorio reemplaza el creador maestro antiguo que dependía de `ABRIR_RECEPCION.py`.

## Objetivo

Crear, desde la PC estable de Recepción, un EXE privado capaz de instalar Recepción en una PC vacía usando la arquitectura vigente:

- `RecepcionLauncher.exe` como único iniciador;
- runtime Python portátil existente;
- runtime completo de Recepción;
- helpers base que todavía no viajan en el canal ordinario;
- WebView2 cuando haga falta;
- configuración privada del consultorio opcionalmente embebida.

## Seguridad

El EXE generado puede contener el `.env` privado del consultorio. No debe publicarse en GitHub, enviarse a terceros ni guardarse en un lugar público.

No se copian:

- `data/`
- bases SQLite
- backups
- Excel de pacientes
- histórico de pacientes
- logs

Al reinstalar sobre una PC existente, el `.env` y `data/` actuales se conservan.

## Validaciones antes de construir

El creador:

1. consulta `launcher-v1/app-channel.json`;
2. exige que la Recepción local esté en la misma versión publicada;
3. verifica SHA-256 de todos los archivos que pertenecen al canal oficial;
4. exige `RecepcionLauncher.exe`, Python portátil y los helpers base;
5. rechaza una instalación local incompleta;
6. copia la instalación sin datos clínicos/operativos;
7. elimina del payload los launchers Python retirados;
8. compila el instalador con Inno Setup.

## Uso

En la PC estable de Recepción:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_private_reception_master.ps1
```

El EXE y su SHA-256 se crean en el Escritorio.

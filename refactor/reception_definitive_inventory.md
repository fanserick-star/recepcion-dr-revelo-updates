# Inventario para refactor definitivo de Recepción 4.6.6

- Módulos embebidos totales: **54**
- Capas históricas app_base/app_patch/app_prev: **51**
- Helpers embebidos: **3** — azur_client, remote_agenda, whatsapp_client
- Raíces del grafo embebido: **app_patch_4525**
- Hojas del grafo embebido: **azur_client, remote_agenda, whatsapp_client**
- Rutas FastAPI activas en runtime: **243**
- Rutas runtime duplicadas por path+método: **0**

## Cadenas simples detectadas
- `app_patch_4525` → `app_patch_4524`

## Módulos más grandes
- `app_base_4428`: 12486 líneas, 753194 bytes, 150 rutas decoradas, importa ['azur_client', 'remote_agenda', 'whatsapp_client']
- `app_prev_4458`: 2473 líneas, 116092 bytes, 0 rutas decoradas, importa ['app_base_4428']
- `app_patch_4504`: 2066 líneas, 60822 bytes, 1 rutas decoradas, importa ['app_patch_4502']
- `app_patch_4476`: 1176 líneas, 45529 bytes, 1 rutas decoradas, importa ['app_patch_4475']
- `app_patch_4506`: 1069 líneas, 36218 bytes, 1 rutas decoradas, importa ['app_patch_4505']
- `app_patch_4507`: 1140 líneas, 31744 bytes, 2 rutas decoradas, importa ['app_patch_4506']
- `app_patch_4501`: 700 líneas, 25872 bytes, 4 rutas decoradas, importa ['app_patch_4491']
- `azur_client`: 464 líneas, 20129 bytes, 0 rutas decoradas, importa []
- `app_patch_4470`: 302 líneas, 19100 bytes, 1 rutas decoradas, importa ['app_patch_4469']
- `app_patch_4502`: 551 líneas, 18835 bytes, 1 rutas decoradas, importa ['app_patch_4501']
- `app_patch_4475`: 529 líneas, 18592 bytes, 1 rutas decoradas, importa ['app_patch_4474']
- `app_patch_4468`: 484 líneas, 18082 bytes, 1 rutas decoradas, importa ['app_patch_4467']
- `app_patch_4523`: 566 líneas, 17649 bytes, 1 rutas decoradas, importa ['app_patch_4522']
- `app_patch_4466`: 369 líneas, 16585 bytes, 1 rutas decoradas, importa ['app_patch_4465']
- `app_patch_4465`: 351 líneas, 16535 bytes, 1 rutas decoradas, importa ['app_patch_4464']
- `app_patch_4485`: 527 líneas, 16259 bytes, 2 rutas decoradas, importa ['app_patch_4484']
- `app_patch_4467`: 414 líneas, 15663 bytes, 1 rutas decoradas, importa ['app_patch_4466']
- `app_patch_4463`: 382 líneas, 15464 bytes, 1 rutas decoradas, importa ['app_patch_4462']
- `app_patch_4525`: 460 líneas, 14573 bytes, 1 rutas decoradas, importa ['app_patch_4524']
- `app_patch_4459`: 223 líneas, 13371 bytes, 1 rutas decoradas, importa ['app_prev_4458']

## Rutas activas por módulo de endpoint
- `app_base_4428`: 136
- `reception_466_inventory_runtime`: 13
- `app_prev_4458`: 7
- `app_patch_4506`: 6
- `app_patch_4476`: 5
- `fastapi.applications`: 4
- `app_patch_4459`: 4
- `app_patch_4501`: 4
- `app_patch_4504`: 4
- `app_patch_4522`: 4
- `app_patch_4483`: 3
- `app_patch_4466`: 2
- `app_patch_4467`: 2
- `app_patch_4468`: 2
- `app_patch_4469`: 2
- `app_patch_4470`: 2
- `app_patch_4475`: 2
- `app_patch_4477`: 2
- `app_patch_4482`: 2
- `app_patch_4485`: 2
- `app_patch_4489`: 2
- `app_patch_4505`: 2
- `app_patch_4507`: 2
- `app_patch_4517`: 2
- `app_patch_4519`: 2
- `None`: 1
- `app_patch_4461`: 1
- `app_patch_4462`: 1
- `app_patch_4463`: 1
- `app_patch_4464`: 1
- `app_patch_4465`: 1
- `app_patch_4473`: 1
- `app_patch_4474`: 1
- `app_patch_4478`: 1
- `app_patch_4479`: 1
- `app_patch_4480`: 1
- `app_patch_4481`: 1
- `app_patch_4484`: 1
- `app_patch_4486`: 1
- `app_patch_4487`: 1
- `app_patch_4488`: 1
- `app_patch_4490`: 1
- `app_patch_4491`: 1
- `app_patch_4502`: 1
- `app_patch_4518`: 1
- `app_patch_4520`: 1
- `app_patch_4521`: 1
- `app_patch_4523`: 1
- `app_patch_4524`: 1
- `app_patch_4525`: 1

## Duplicados activos
- Ninguno

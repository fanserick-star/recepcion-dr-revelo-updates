# Bendo Smart — plan de integración para Recepción Dr. Armando Revelo

Estado: **preparación técnica, NO activado en producción**.

Objetivo: dejar el sistema listo para cobrar consultas/procedimientos con tarjeta mediante Bendo Smart sin almacenar datos sensibles de tarjeta y sin alterar el flujo estable actual de efectivo/transferencia.

## 1. Lo confirmado públicamente por Bendo

- Bendo Smart es un POS autónomo para cobros presenciales; usa Wi‑Fi o 4G y no necesita estar conectado por cable a la PC.
- La activación se realiza con credenciales Bendo; el dispositivo queda vinculado al código de comercio.
- Bendo Smart procesa tarjetas de crédito/débito y billeteras digitales y puede imprimir vouchers.
- Bendo dispone de Panel de Comercio para revisar transacciones.
- Los T&C de Bendo describen una API y hablan de credenciales de prueba/producción; además indican que la notificación oficial de una transacción exitosa se realiza por medios digitales/API definidos por Bendo.
- La documentación pública revisada NO expone todavía el contrato técnico de esa API (base URL, autenticación, endpoints, webhook/callback, idempotencia ni mecanismo específico para iniciar una venta en Bendo Smart desde un POS externo).
- Bendo permite anulaciones/reversos el mismo día bajo sus reglas operativas; fuera de la ventana correspondiente el proceso puede requerir soporte/reembolso.

Fuentes públicas revisadas:
- https://www.bendo.ec/pos-bendo-smart/
- https://www.bendo.ec/terminos-y-condiciones-de-compraventa-de-dispositivos/
- https://www.bendo.ec/terminos-y-condiciones-de-uso/
- https://www.bendo.ec/realizar-devolucion/
- https://www.bendo.ec/ayuda/

## 2. Conclusión de arquitectura

No conviene diseñar una conexión USB/Bluetooth inventada. Bendo Smart es autónomo y la integración correcta, si Bendo la habilita para el comercio, debe ser **cloud/API** o mediante el mecanismo oficial que Bendo documente para POS/ECR de terceros.

Se contemplan tres modos, en este orden de preferencia:

1. **API integrada (ideal):** Recepción crea la orden por API, Bendo Smart recibe/ejecuta el cobro, y Recepción confirma el resultado por API/webhook.
2. **API de consulta/conciliación:** el monto se digita en Bendo Smart, pero Recepción consulta la transacción aprobada y la enlaza automáticamente a la atención.
3. **Modo manual controlado:** si Bendo no ofrece API para terceros, Recepción registra “Tarjeta Bendo”, muestra el importe exacto, el cobro se realiza en Bendo Smart y se registra el número de aprobación/referencia. Nunca se marca como cobrada automáticamente sin confirmación.

## 3. Datos que debemos pedir a Bendo

Cuando llegue el equipo o antes, solicitar a soporte/comercial:

- ¿Bendo Smart ofrece integración con sistemas POS/ECR de terceros?
- ¿Existe API/SDK oficial para iniciar una venta presencial en el Bendo Smart desde un sistema Windows?
- Documentación técnica de API y ambiente sandbox/pruebas.
- Base URL de sandbox y producción.
- Método de autenticación (API key/OAuth/token) y cómo rotar credenciales.
- Código de comercio / merchant ID y, si existe, terminal ID/device ID.
- Endpoint para crear/iniciar cobro presencial.
- Endpoint para consultar estado por transaction/order ID.
- Webhook/callback: URL, eventos, firma/HMAC y reintentos.
- Soporte de `idempotency_key` o equivalente para evitar cobros duplicados.
- Estados exactos: pendiente, aprobada, rechazada, anulada, reversada, reembolsada, timeout.
- Campos de respuesta: transaction ID, número de aprobación, marca, tipo crédito/débito, PAN enmascarado/últimos 4, cuotas/diferido, fecha/hora, monto.
- Endpoint y reglas para anulación/reverso/reembolso.
- Si el dispositivo puede recibir una orden automáticamente o el valor debe ingresarse manualmente.
- Si permite pagos diferidos/cuotas vía API y cómo se representa el plan.

## 4. Modelo interno preparado

La atención y la facturación seguirán separadas del procesador de tarjeta.

### Forma de pago SRI

El sistema actual usa:
- Efectivo → SRI `01`.
- Transferencia → SRI `20`.

Para Bendo se incorporarán, cuando la integración esté habilitada:
- Tarjeta de débito → SRI `16`.
- Tarjeta de crédito → SRI `19`.
- Tarjeta prepago → SRI `18` solo si Bendo la identifica y el comercio la utiliza.

El tipo SRI debe salir de la respuesta confirmada de Bendo o, si Bendo no lo entrega, de una selección explícita y validada del operador. Nunca se debe adivinar.

### Registro de transacción

Crear una tabla/registro independiente para pagos Bendo, enlazada a los IDs exactos de las atenciones facturadas. Campos previstos:

- `payment_id` interno UUID.
- `provider = BENDO`.
- IDs de las visitas/atenciones cubiertas.
- `amount` bruto cobrado.
- `currency` (USD).
- `status` normalizado.
- `provider_transaction_id`.
- `approval_code` / número de aprobación.
- `card_brand` si Bendo lo devuelve.
- `card_type` (DEBIT/CREDIT/PREPAID) si Bendo lo devuelve.
- `masked_pan` o últimos 4 únicamente si Bendo lo devuelve ya enmascarado.
- `installments`/plan diferido cuando aplique.
- `created_at`, `approved_at`, `reversed_at`.
- respuesta técnica mínima sanitizada para auditoría.

**Nunca guardar:** PAN completo, CVV, fecha de expiración, PIN ni track/chip data.

## 5. Flujo de atención propuesto

Cuando `BENDO_ENABLED=1`:

1. En “Nueva atención” aparecerá `Tarjeta` además de Efectivo y Transferencia.
2. Se guarda primero la atención clínica para no perderla si el pago se rechaza.
3. Se genera un `payment_id`/idempotency key único y se solicita el cobro por el monto exacto.
4. Pantalla: `Esperando pago en Bendo Smart…` con opción segura de cancelar la espera, no de duplicar el cobro.
5. El sistema espera estado confirmado:
   - **APROBADO:** registra referencia, tipo de tarjeta y forma SRI; continúa impresión/facturación.
   - **RECHAZADO/CANCELADO:** la atención queda guardada pero no se marca como pagada con tarjeta.
   - **TIMEOUT/DESCONOCIDO:** no se permite reintentar inmediatamente; primero se consulta por `payment_id`/referencia para evitar doble cobro.
6. El recibo de Recepción puede mostrar `TARJETA · BENDO` y, opcionalmente, marca/últimos 4 y aprobación. El voucher oficial de tarjeta lo imprime Bendo Smart.

## 6. Facturación AZUR/SRI

AZUR acepta códigos SRI `16` (débito) y `19` (crédito). Al emitir la factura, el programa debe enviar el código confirmado del cobro Bendo.

La factura siempre se emite por el valor bruto del servicio. La comisión de Bendo y sus retenciones son costos/liquidaciones del comercio y no deben reducir el total cobrado al paciente en la factura.

## 7. Seguridad y confiabilidad

- Credenciales Bendo únicamente en `.env` local o almacenamiento seguro; nunca GitHub, frontend ni logs.
- Verificación de firma de webhook si Bendo la ofrece.
- Idempotencia obligatoria para evitar doble cobro por doble clic, timeout o reintento.
- Registrar solo datos no sensibles necesarios para conciliación.
- Ante error de red, consultar estado antes de repetir el cobro.
- No considerar pago exitoso por un mensaje visual del navegador; usar confirmación oficial de Bendo/API cuando esté disponible.
- Guardar auditoría de creación, aprobación, rechazo, anulación y reembolso.

## 8. Reportes previstos

En Reportes/Facturación se podrá separar:
- Efectivo.
- Transferencia.
- Tarjeta Bendo — crédito.
- Tarjeta Bendo — débito.
- Total bruto cobrado con tarjeta.
- Comisión/retenciones Bendo solo como conciliación, cuando la API o archivo de liquidación lo permita.

No se mezclará la comisión de Bendo con el valor de la consulta ni con el total SRI de la factura.

## 9. Pendiente hasta tener dispositivo/documentación

No activar UI ni cobros reales hasta confirmar:

- modelo/versión exacta del Bendo Smart recibido;
- número de serie/terminal ID si aplica;
- credenciales del comercio;
- documentación API/SDK oficial;
- sandbox o método de pruebas;
- mecanismo real de conexión entre un POS externo y Bendo Smart.

En cuanto llegue el equipo, tomar fotos de: frente, parte posterior/etiqueta (ocultando claves), pantalla de Ajustes/Acerca de y cualquier manual/QR incluido. Con esos datos se cierra la integración sin adivinar protocolos.

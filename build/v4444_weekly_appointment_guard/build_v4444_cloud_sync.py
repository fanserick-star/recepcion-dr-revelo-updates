from __future__ import annotations

import json

import build_v4444 as base


SYNC_BLOCK = r'''

    # -----------------------------------------------------------------------
    # v4.4.44 — puente seguro Cloud/WhatsApp -> agenda SQLite visible.
    # -----------------------------------------------------------------------
    # La agenda de Recepción sigue leyendo SQLite. Al abrir una semana, traemos
    # únicamente las citas externas de esos siete días desde Neon y las copiamos
    # a ConfirmafyAgendaItem local. No crea Patients, no migra tablas, no borra
    # filas locales y se omite por completo si existe una cola offline pendiente.
    _v4444_cloud_staged_lock = core.threading.Lock()
    _v4444_cloud_staged_at = {}

    def _v4444_sync_cloud_staged_for_dates(dates, min_interval: float = 5.0) -> int:
        normalized = []
        for value in dates or []:
            try:
                item_date = value if isinstance(value, _date) else _date.fromisoformat(str(value)[:10])
            except Exception:
                continue
            if item_date not in normalized:
                normalized.append(item_date)
        normalized.sort()
        if not normalized:
            return 0
        if not core.cloud_configured() or core.FORCE_OFFLINE or not core.CloudSessionLocal:
            return 0
        if core.queue_count() > 0:
            return 0

        key = "|".join(x.isoformat() for x in normalized)
        now = core.time.time()
        if not _v4444_cloud_staged_lock.acquire(blocking=False):
            return 0
        try:
            last = float(_v4444_cloud_staged_at.get(key) or 0.0)
            if last and now - last < max(1.0, float(min_interval or 5.0)):
                return 0
            if not core.check_cloud(force=False):
                return 0

            changed = 0
            with core.CloudSessionLocal() as cdb, core.LocalSessionLocal() as ldb:
                rows = list(cdb.scalars(
                    core.select(core.ConfirmafyAgendaItem)
                    .where(core.ConfirmafyAgendaItem.fecha.in_(normalized))
                    .order_by(core.ConfirmafyAgendaItem.fecha, core.ConfirmafyAgendaItem.hora, core.ConfirmafyAgendaItem.id)
                ))
                for row in rows:
                    source_hash = str(getattr(row, "source_hash", "") or "").strip()
                    if not source_hash or source_hash.startswith("mobile:whatsapp-cloud-test:"):
                        continue

                    existing = ldb.scalar(
                        core.select(core.ConfirmafyAgendaItem)
                        .where(core.ConfirmafyAgendaItem.source_hash == source_hash)
                        .limit(1)
                    )
                    if existing is not None:
                        values = {
                            "nombre": row.nombre,
                            "celular": row.celular,
                            "fecha": row.fecha,
                            "hora": row.hora,
                            "duracion": int(row.duracion or 20),
                            "created_at": row.created_at,
                        }
                        dirty = False
                        for attr, value in values.items():
                            if getattr(existing, attr, None) != value:
                                setattr(existing, attr, value)
                                dirty = True
                        if dirty:
                            changed += 1
                        continue

                    cloud_id = int(row.id)
                    # No sobreescribimos jamás otra fila local que por casualidad
                    # use el mismo ID. La copia completa normal resolverá ese caso
                    # excepcional sin arriesgar una cita existente.
                    if ldb.get(core.ConfirmafyAgendaItem, cloud_id) is not None:
                        continue
                    ldb.add(core.ConfirmafyAgendaItem(
                        id=cloud_id,
                        nombre=row.nombre,
                        celular=row.celular,
                        fecha=row.fecha,
                        hora=row.hora,
                        duracion=int(row.duracion or 20),
                        source_hash=source_hash,
                        created_at=row.created_at,
                    ))
                    changed += 1
                if changed:
                    ldb.commit()
            _v4444_cloud_staged_at[key] = core.time.time()
            return changed
        except Exception:
            # La agenda local debe seguir abriendo aunque Neon no responda.
            return 0
        finally:
            _v4444_cloud_staged_lock.release()

    @app.middleware("http")
    async def v4444_cloud_staged_agenda_catchup(request, call_next):
        # Solo la vista semanal necesita esta lectura. El resto del programa
        # continúa 100 % local-first y no añade sondeos periódicos a Neon.
        if request.url.path == "/api/agenda/week":
            try:
                raw_anchor = str(request.query_params.get("anchor") or "").strip()
                anchor_date = _date.fromisoformat(raw_anchor[:10])
                monday = anchor_date - core.timedelta(days=anchor_date.weekday())
                week_dates = [monday + core.timedelta(days=i) for i in range(7)]
                _v4444_sync_cloud_staged_for_dates(week_dates)
            except Exception:
                pass
        return await call_next(request)
'''


def main() -> None:
    base.FEATURE_BLOCK = base.FEATURE_BLOCK + SYNC_BLOCK
    base.build()

    # El contenido binario y los SHA ya fueron calculados por build() con el
    # bloque nuevo incluido. Solo ampliamos el texto informativo del canal.
    candidate_path = base.OUT / "candidate_latest.json"
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    candidate["message"] = (
        "v4.4.44: Nueva cita advierte si el mismo paciente ya tiene una cita entre lunes y domingo y permite "
        "Agendar de todas formas solo con confirmación manual. Además, al abrir la Agenda, las citas creadas desde "
        "WhatsApp/Agenda Cloud bajan a la copia local de la semana para que el horario no aparezca falsamente libre. "
        "No crea pacientes, no cambia tablas, .env ni bases de datos; conserva el modo local-first y el funcionamiento offline."
    )
    candidate_path.write_text(json.dumps(candidate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("BUILD_V4444_CLOUD_SYNC_OK")


if __name__ == "__main__":
    main()

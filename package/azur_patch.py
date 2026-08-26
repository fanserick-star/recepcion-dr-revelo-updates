from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from fastapi import Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import Date, DateTime, Integer, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from azur_client import (
    AzurError,
    emit_invoice as azur_emit_invoice,
    mask_api_key as azur_mask_api_key,
    normalize_base_url as azur_normalize_base_url,
    test_connection as azur_test_connection,
)

_INSTALLED = False


class AzurConfigIn(BaseModel):
    base_url: str
    api_key: Optional[str] = None


def install(core) -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    # These are intentionally local-only secrets/settings.
    state = {
        "base_url": (os.getenv("AZUR_BASE_URL") or "").strip(),
        "api_key": (os.getenv("AZUR_API_KEY") or "").strip(),
        "tipo_iva": (os.getenv("AZUR_TIPO_IVA") or "0").strip() or "0",
        "forma_pago": (os.getenv("AZUR_FORMA_PAGO") or "01").strip() or "01",
        "live": (os.getenv("AZUR_LIVE_EMISSION") or "0").strip() == "1",
    }

    class AzurEmission(core.Base):
        __tablename__ = "azur_emissions"
        id: Mapped[int] = mapped_column(Integer, primary_key=True)
        group_key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
        patient_id: Mapped[int] = mapped_column(Integer, index=True)
        fecha: Mapped[date] = mapped_column(Date, index=True)
        estado: Mapped[str] = mapped_column(String(30), default="ENVIADA", index=True)
        clave_acceso: Mapped[Optional[str]] = mapped_column(String(80), nullable=True, index=True)
        numero_factura: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
        request_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
        response_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
        created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
        updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Create only the missing technical table. No patient/clinical data is altered.
    try:
        core.Base.metadata.create_all(core.local_engine)
    except Exception:
        pass
    try:
        if getattr(core, "cloud_engine", None) is not None:
            core.Base.metadata.create_all(core.cloud_engine)
    except Exception:
        pass

    def _upsert_local_env(values: dict[str, str]) -> None:
        env_path = Path(core.BASE_DIR) / ".env"
        try:
            existing = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
        except Exception as exc:
            raise HTTPException(500, f"No se pudo leer .env: {exc}")
        lines = existing.splitlines()
        keys = set(values)
        written = set()
        output: list[str] = []
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in line:
                output.append(line)
                continue
            key = line.split("=", 1)[0].strip()
            if key in keys:
                output.append(f"{key}={values[key]}")
                written.add(key)
            else:
                output.append(line)
        for key, value in values.items():
            if key not in written:
                output.append(f"{key}={value}")
        tmp = env_path.with_suffix(".env.tmp")
        try:
            tmp.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
            os.replace(tmp, env_path)
        except Exception as exc:
            try:
                if tmp.exists():
                    tmp.unlink()
            except Exception:
                pass
            raise HTTPException(500, f"No se pudo guardar la configuración de AZUR: {exc}")

    def _config_payload() -> dict:
        domain = ""
        try:
            domain = urlparse(state["base_url"]).hostname or "" if state["base_url"] else ""
        except Exception:
            pass
        return {
            "configured": bool(state["base_url"] and state["api_key"]),
            "base_url": state["base_url"],
            "domain": domain,
            "api_key_saved": bool(state["api_key"]),
            "api_key_masked": azur_mask_api_key(state["api_key"]),
            "tipo_iva": state["tipo_iva"],
            "forma_pago": state["forma_pago"],
            "live_emission_enabled": bool(state["live"]),
        }

    @core.app.get("/api/azur/status")
    def azur_status(user: core.User = Depends(core.current_user)):
        return _config_payload()

    @core.app.post("/api/azur/config")
    def azur_save_config(data: AzurConfigIn, user: core.User = Depends(core.current_user)):
        if user.role != "admin":
            raise HTTPException(403, "Solo el administrador puede configurar AZUR")
        try:
            base_url = azur_normalize_base_url(data.base_url)
        except AzurError as exc:
            raise HTTPException(400, str(exc))
        new_key = (data.api_key or "").strip()
        if not new_key and not state["api_key"]:
            raise HTTPException(400, "Ingresa la API key de AZUR")
        values = {"AZUR_BASE_URL": base_url}
        if new_key:
            values["AZUR_API_KEY"] = new_key
        _upsert_local_env(values)
        state["base_url"] = base_url
        if new_key:
            state["api_key"] = new_key
        return {"ok": True, **_config_payload()}

    @core.app.post("/api/azur/test")
    def azur_test(user: core.User = Depends(core.current_user)):
        if not state["base_url"] or not state["api_key"]:
            raise HTTPException(400, "Configura primero la dirección de AZUR y la API key")
        try:
            result = azur_test_connection(state["base_url"], state["api_key"], timeout=12)
        except AzurError as exc:
            raise HTTPException(502, str(exc))
        result["base_url"] = state["base_url"]
        return result

    def _group_key(patient_id: int, fecha: date) -> str:
        return f"{int(patient_id)}:{fecha.isoformat()}"

    def _recipient(data, p) -> dict:
        if bool(data.factura_otro):
            ident_raw = str(data.factura_identificacion or "").strip()
            name = " ".join(str(data.factura_nombre or "").split()).upper()
            address = " ".join(str(data.factura_direccion or "").split()).upper()
            phone = re.sub(r"\D", "", str(data.factura_telefono or ""))
            email = str(data.factura_correo or "").strip().lower()
        else:
            ident_raw = str(p.cedula or "").strip()
            name = " ".join(str(p.nombre or "").split()).upper()
            address = " ".join(str(p.lugar or "").split()).upper()
            phone = re.sub(r"\D", "", str(p.celular or ""))
            email = str(p.correo or "").strip().lower()
        ident_digits = re.sub(r"\D", "", ident_raw)
        if len(ident_digits) == 13:
            ident_type, ident = "04", ident_digits
        elif len(ident_digits) == 10:
            ident_type, ident = "05", ident_digits
        elif ident_raw:
            ident_type, ident = "08", ident_raw
        else:
            raise HTTPException(400, "Falta identificación para emitir en AZUR")
        if not name:
            raise HTTPException(400, "Falta nombre o razón social para emitir en AZUR")
        if not email or "@" not in email:
            raise HTTPException(400, "Falta un correo válido para emitir en AZUR")
        buyer = {
            "tipo_identificacion": ident_type,
            "identificacion": ident,
            "razon_social": name,
            "direccion": address or "NO REGISTRADA",
            "correo": email,
        }
        if phone:
            buyer["celular"] = phone
        return buyer

    def _payload(data, p, rows) -> dict:
        try:
            tipo_iva = int(state["tipo_iva"])
        except Exception:
            tipo_iva = 0
        items = []
        total = 0.0
        for _, v in rows:
            value = round(float(v.valor or 0), 2)
            if value <= 0:
                raise HTTPException(400, "Todas las atenciones de la factura deben tener un valor mayor a cero")
            raw_desc = (v.procedimiento or "CONSULTA MEDICA").strip().upper() or "CONSULTA MEDICA"
            code = "CONSULTA" if not (v.procedimiento or "").strip() else f"SERV-{int(v.id)}"
            items.append({
                "codigo_principal": code,
                "descripcion": raw_desc,
                "cantidad": 1,
                "precio_unitario": value,
                "descuento": 0,
                "tipoproducto": 2,
                "tipo_iva": tipo_iva,
            })
            total += value
        total = round(total, 2)
        return {
            "codigoDoc": "01",
            "emisor": {"fecha_emision": data.fecha.strftime("%Y/%m/%d"), "manejo_interno_secuencia": "SI"},
            "comprador": _recipient(data, p),
            "items": items,
            "pagos": [{"tipo": state["forma_pago"], "total": total, "tiempo": "dias", "plazo": 0}],
            "informacion_adicional": [{"nombre": "Origen", "detalle": "Recepcion Dr. Armando Revelo"}],
        }

    @core.app.post("/api/billing/azur/preview")
    def billing_azur_preview(data: core.BillingGroupIn, db: Session = Depends(core.get_db), user: core.User = Depends(core.current_user)):
        p = db.get(core.Patient, data.patient_id)
        if not p:
            raise HTTPException(404, "Paciente no encontrado")
        core.validate_billing_recipient(data, p)
        rows = core.billing_group_records(db, data.patient_id, data.fecha)
        if not rows:
            raise HTTPException(404, "No hay atenciones para facturar ese día")
        payload = _payload(data, p, rows)
        existing = db.scalar(select(AzurEmission).where(AzurEmission.group_key == _group_key(data.patient_id, data.fecha)))
        return {
            "configured": bool(state["base_url"] and state["api_key"]),
            "domain": _config_payload().get("domain"),
            "payload": payload,
            "already_sent": bool(existing and existing.clave_acceso),
            "live_enabled": bool(state["live"]),
            "azur": {
                "estado": existing.estado,
                "clave_acceso": existing.clave_acceso,
                "numero_factura": existing.numero_factura,
            } if existing else None,
        }

    @core.app.post("/api/billing/azur/emit")
    def billing_azur_emit(data: core.BillingGroupIn, db: Session = Depends(core.get_db), user: core.User = Depends(core.current_user)):
        if not state["live"]:
            raise HTTPException(403, "La emisión real está bloqueada en esta versión de prueba. Primero confirma la conexión con AZUR")
        if core.is_offline_db(db):
            raise HTTPException(503, "Emitir en AZUR requiere conexión a Internet")
        if not state["base_url"] or not state["api_key"]:
            raise HTTPException(400, "AZUR todavía no está configurado. Ve a Configuración > AZUR")
        p = db.get(core.Patient, data.patient_id)
        if not p:
            raise HTTPException(404, "Paciente no encontrado")
        core.validate_billing_recipient(data, p)
        rows = core.billing_group_records(db, data.patient_id, data.fecha)
        if not rows:
            raise HTTPException(404, "No hay atenciones aprobadas para ese día")
        if any(b.estado != "APROBADA" for b, _ in rows):
            raise HTTPException(409, "Primero aprueba la pre-factura completa")
        group_key = _group_key(data.patient_id, data.fecha)
        existing = db.scalar(select(AzurEmission).where(AzurEmission.group_key == group_key))
        if existing and existing.clave_acceso:
            raise HTTPException(409, "Esta factura ya fue enviada a AZUR. No se reenviará para evitar duplicados")
        payload = _payload(data, p, rows)
        request_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        try:
            result = azur_emit_invoice(state["base_url"], state["api_key"], payload, timeout=20)
        except AzurError as exc:
            raise HTTPException(502, str(exc))
        response = result.get("data") if isinstance(result, dict) else {}
        response = response if isinstance(response, dict) else {}
        access_key = str(response.get("claveacceso") or response.get("clave_acceso") or "").strip() or None
        invoice_number = str(response.get("numero_factura") or response.get("numero_comprobante") or response.get("numero") or "").strip() or None
        now = datetime.utcnow()
        record = existing or AzurEmission(group_key=group_key, patient_id=data.patient_id, fecha=data.fecha)
        if not existing:
            db.add(record)
        record.estado = "ENVIADA"
        record.clave_acceso = access_key
        record.numero_factura = invoice_number
        record.request_hash = request_hash
        try:
            record.response_json = json.dumps(response, ensure_ascii=False)[:10000]
        except Exception:
            record.response_json = None
        record.updated_at = now
        if invoice_number:
            record.estado = "EMITIDA"
            for b, _ in rows:
                b.estado = "EMITIDA"
                b.numero_factura = invoice_number
                b.emitted_at = now
                if not b.approved_at:
                    b.approved_at = now
        core.audit(db, user, "emitir_factura_azur", f"Paciente {data.patient_id}, fecha {data.fecha}, estado {record.estado}")
        db.commit()
        if invoice_number:
            for b, _ in rows:
                core.mirror_billing_to_local(b)
        return {
            "ok": True,
            "estado": record.estado,
            "clave_acceso": access_key,
            "numero_factura": invoice_number,
            "message": "Factura enviada a AZUR." + (" Número recibido: " + invoice_number if invoice_number else " AZUR devolvió la clave de acceso; el registro quedó protegido contra reenvíos."),
        }

    core.AzurEmission = AzurEmission

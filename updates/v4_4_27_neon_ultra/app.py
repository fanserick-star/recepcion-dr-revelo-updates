from __future__ import annotations

import os
import csv
import io
import hashlib
import hmac
import secrets
import re
import json
import uuid
import shutil
import threading
import sqlite3
import zipfile
import tempfile
import subprocess
import sys
import time
import socket
import ipaddress
import ctypes
import webbrowser
import unicodedata
from difflib import SequenceMatcher
from datetime import date, datetime, timedelta
from typing import Optional
from pathlib import Path
from urllib.parse import urlparse, urlunparse, unquote, quote
import ssl
import urllib.request
import urllib.error

from azur_client import AzurError, emit_invoice as azur_emit_invoice, query_comprobante as azur_query_comprobante, mask_api_key as azur_mask_api_key, normalize_base_url as azur_normalize_base_url, test_connection as azur_test_connection
from whatsapp_client import WhatsAppError, build_template_payload as whatsapp_build_template_payload, send_template as whatsapp_send_template
from remote_agenda import (
    normalize_public_base_url as remote_normalize_base_url,
    start_quick_tunnel as remote_start_quick_tunnel,
    start_named_tunnel as remote_start_named_tunnel,
    start_named_tunnel_background as remote_start_named_tunnel_background,
    stop_managed_tunnel as remote_stop_tunnel,
    tunnel_status as remote_tunnel_status,
)
from xml.sax.saxutils import escape as xml_escape

from fastapi import FastAPI, HTTPException, Request, Response, Depends, File, Form, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import (
    create_engine, String, Integer, Date, DateTime, Numeric, ForeignKey, Text,
    select, or_, func, text, delete, update, insert, case, event
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError, OperationalError, IntegrityError
from dotenv import load_dotenv
import pg8000.dbapi as pg8000_dbapi
_POSTGRES_DRIVER = "pg8000"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_VERSION = "4.4.27"
try:
    LOCAL_HTTP_PORT = int((os.getenv("RP_PORT") or "8000").strip())
except Exception:
    LOCAL_HTTP_PORT = 8000
if not (1024 <= LOCAL_HTTP_PORT <= 65535):
    LOCAL_HTTP_PORT = 8000
# Desde esta actualización, Facturación muestra la cola generada desde este punto en adelante.
BILLING_QUEUE_START_DATE = date(2026, 8, 24)
CONFIRMAFY_ATTENDED_ORIGIN = "CONFIRMAFY_ATENDIDO"
CONFIRMAFY_ATTENDED_NOTE_PREFIX = "CONFIRMAFY_HASH:"
LEGACY_DATA_DIR = os.path.join(BASE_DIR, "data")
AGENDA_INITIAL_FILE = os.path.join(LEGACY_DATA_DIR, "agenda_inicial_confirmafy.csv")
AGENDA_SEED_ACTION = "agenda_import_confirmafy_2026_08_22_v1"
HISTORICAL_REGISTRY_FILE = os.path.join(BASE_DIR, "HISTORICO_PACIENTES_2020_2025.csv")
HISTORICAL_REGISTRY_MARKER = "historico_pacientes_2020_2025_v3"
DATA_DIR = (os.getenv("RP_DATA_DIR") or "").strip() or LEGACY_DATA_DIR
os.makedirs(DATA_DIR, exist_ok=True)
BACKUP_DIR = os.path.join(DATA_DIR, "backups")
UPDATE_BACKUP_DIR = os.path.join(BASE_DIR, "_update_backups")
os.makedirs(BACKUP_DIR, exist_ok=True)
os.makedirs(UPDATE_BACKUP_DIR, exist_ok=True)
load_dotenv(os.path.join(BASE_DIR, ".env"))

# AZUR se configura únicamente en el .env local. La API key nunca se guarda en
# Neon, SQLite, GitHub ni en el frontend.
AZUR_BASE_URL = (os.getenv("AZUR_BASE_URL") or "").strip()
AZUR_API_KEY = (os.getenv("AZUR_API_KEY") or "").strip()
AZUR_TIPO_IVA = (os.getenv("AZUR_TIPO_IVA") or "0").strip() or "0"
AZUR_FORMA_PAGO = (os.getenv("AZUR_FORMA_PAGO") or "01").strip() or "01"
AZUR_LIVE_EMISSION = (os.getenv("AZUR_LIVE_EMISSION") or "1").strip() != "0"
# WhatsApp / Meta Cloud API. v4.3.35 adapta recordatorio_cita exactamente a la
# plantilla aprobada por Meta: 2 variables (nombre + fecha/hora) y botones Sí / No.
# Sigue DESACTIVADA por defecto. El .env no se modifica durante la actualización.
WHATSAPP_ENABLED = (os.getenv("WHATSAPP_ENABLED") or "0").strip() == "1"
# v4.3.38: la automatización real vive en Cloudflare + Neon. Por defecto el
# worker local queda bloqueado para evitar mensajes duplicados entre PC y nube.
WHATSAPP_CLOUD_MODE = (os.getenv("WHATSAPP_CLOUD_MODE") or "1").strip() != "0"
WHATSAPP_GRAPH_VERSION = (os.getenv("WHATSAPP_GRAPH_VERSION") or "").strip()
WHATSAPP_PHONE_NUMBER_ID = (os.getenv("WHATSAPP_PHONE_NUMBER_ID") or "").strip()
WHATSAPP_ACCESS_TOKEN = (os.getenv("WHATSAPP_ACCESS_TOKEN") or "").strip()
WHATSAPP_TEST_PHONE = (os.getenv("WHATSAPP_TEST_PHONE") or "").strip()
# Compatibilidad: se conserva la variable global antigua, pero desde v4.3.37
# cada plantilla usa su propio idioma porque Meta aprobó variantes distintas.
WHATSAPP_TEMPLATE_LANGUAGE = (os.getenv("WHATSAPP_TEMPLATE_LANGUAGE") or "es").strip() or "es"
WHATSAPP_LANGUAGE_CITA_AGENDADA = (os.getenv("WHATSAPP_LANGUAGE_CITA_AGENDADA") or "es_EC").strip() or "es_EC"
WHATSAPP_LANGUAGE_RECORDATORIO_CITA = (os.getenv("WHATSAPP_LANGUAGE_RECORDATORIO_CITA") or "es_ES").strip() or "es_ES"
WHATSAPP_LANGUAGE_RECORDATORIO_HOY = (os.getenv("WHATSAPP_LANGUAGE_RECORDATORIO_HOY") or "es_EC").strip() or "es_EC"
WHATSAPP_HEADER_IMAGE_ID = (os.getenv("WHATSAPP_HEADER_IMAGE_ID") or "").strip()
WHATSAPP_TEMPLATE_CITA_AGENDADA = (os.getenv("WHATSAPP_TEMPLATE_CITA_AGENDADA") or "cita_agendada").strip() or "cita_agendada"
WHATSAPP_TEMPLATE_RECORDATORIO_CITA = (os.getenv("WHATSAPP_TEMPLATE_RECORDATORIO_CITA") or "recordatorio_cita").strip() or "recordatorio_cita"
WHATSAPP_TEMPLATE_RECORDATORIO_HOY = (os.getenv("WHATSAPP_TEMPLATE_RECORDATORIO_HOY") or "recordatorio_hoy").strip() or "recordatorio_hoy"
# Activación por plantilla: solo recordatorio_cita está aprobado hoy. Aunque
# WHATSAPP_ENABLED llegue a 1, las otras dos no se intentan hasta aprobarlas.
WHATSAPP_AUTO_CITA_AGENDADA = (os.getenv("WHATSAPP_AUTO_CITA_AGENDADA") or "1").strip() != "0"
WHATSAPP_AUTO_RECORDATORIO_CITA = (os.getenv("WHATSAPP_AUTO_RECORDATORIO_CITA") or "1").strip() != "0"
WHATSAPP_AUTO_RECORDATORIO_HOY = (os.getenv("WHATSAPP_AUTO_RECORDATORIO_HOY") or "1").strip() != "0"
# Estado de aprobación de plantillas. Se deja parametrizable en .env para que
# una futura aprobación de Meta no requiera cambiar código.
WHATSAPP_APPROVED_CITA_AGENDADA = (os.getenv("WHATSAPP_APPROVED_CITA_AGENDADA") or "1").strip() != "0"
WHATSAPP_APPROVED_RECORDATORIO_CITA = (os.getenv("WHATSAPP_APPROVED_RECORDATORIO_CITA") or "1").strip() != "0"
WHATSAPP_APPROVED_RECORDATORIO_HOY = (os.getenv("WHATSAPP_APPROVED_RECORDATORIO_HOY") or "1").strip() != "0"
# Preparado para una futura segunda plantilla con encabezado de imagen/logo.
# Nunca sustituye a la aprobada mientras esta bandera permanezca en 0.
WHATSAPP_TEMPLATE_RECORDATORIO_CITA_LOGO = (os.getenv("WHATSAPP_TEMPLATE_RECORDATORIO_CITA_LOGO") or "recordatorio_cita_logo").strip() or "recordatorio_cita_logo"
WHATSAPP_RECORDATORIO_CITA_LOGO_ENABLED = (os.getenv("WHATSAPP_RECORDATORIO_CITA_LOGO_ENABLED") or "0").strip() == "1"
WHATSAPP_PREVIOUS_DAY_TIME = (os.getenv("WHATSAPP_PREVIOUS_DAY_TIME") or "08:00").strip() or "08:00"
if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", WHATSAPP_PREVIOUS_DAY_TIME):
    WHATSAPP_PREVIOUS_DAY_TIME = "08:00"
try:
    WHATSAPP_TODAY_HOURS_BEFORE = min(max(int((os.getenv("WHATSAPP_TODAY_HOURS_BEFORE") or "2").strip()), 1), 12)
except Exception:
    WHATSAPP_TODAY_HOURS_BEFORE = 2
try:
    WHATSAPP_POLL_SECONDS = min(max(int((os.getenv("WHATSAPP_POLL_SECONDS") or "60").strip()), 60), 900)
except Exception:
    WHATSAPP_POLL_SECONDS = 60
MOBILE_DOCTOR_TOKEN = (os.getenv("MOBILE_DOCTOR_TOKEN") or "").strip()
MOBILE_RECEPTION_TOKEN = (os.getenv("MOBILE_RECEPTION_TOKEN") or "").strip()
AGENDA_CLOUD_BASE_URL = (os.getenv("AGENDA_CLOUD_BASE_URL") or "https://fanserick-star.github.io/recepcion-dr-revelo-updates/").strip().rstrip("/") + "/"
AGENDA_CLOUD_KEYS_SYNCED_SHA = (os.getenv("AGENDA_CLOUD_KEYS_SYNCED_SHA") or "").strip()
# Agenda remota por HTTPS. El token del túnel se lee únicamente del .env local.
REMOTE_AGENDA_BASE_URL = (os.getenv("REMOTE_AGENDA_BASE_URL") or "").strip().rstrip("/")
REMOTE_AGENDA_TUNNEL_TOKEN = (os.getenv("REMOTE_AGENDA_TUNNEL_TOKEN") or "").strip()
REMOTE_AGENDA_AUTOSTART = (os.getenv("REMOTE_AGENDA_AUTOSTART") or "1").strip() != "0"

# ---------------------------------------------------------------------------
# Base principal (nube) + cache local de emergencia
# ---------------------------------------------------------------------------

CONFIGURED_DB_URL = (os.getenv("DATABASE_URL") or "").strip()
FORCE_OFFLINE = (os.getenv("RP_FORCE_OFFLINE") or "").strip() == "1"  # solo diagnóstico/pruebas
INITIAL_LOCAL_DB = os.path.join(DATA_DIR, "recepcion.db")
OFFLINE_DB_PATH = os.path.join(DATA_DIR, "offline_cache.db")
LEGACY_INITIAL_LOCAL_DB = os.path.join(LEGACY_DATA_DIR, "recepcion.db")
LEGACY_OFFLINE_DB_PATH = os.path.join(LEGACY_DATA_DIR, "offline_cache.db")

# v3.1: los archivos que cambian durante el uso diario viven en AppData para que
# INICIAR.bat no requiera privilegios de administrador. La primera vez copiamos
# la cache v3.0 (si existe) o, como respaldo, la base inicial incluida.
if not os.path.exists(OFFLINE_DB_PATH):
    for candidate in (LEGACY_OFFLINE_DB_PATH, INITIAL_LOCAL_DB, LEGACY_INITIAL_LOCAL_DB):
        if candidate and os.path.exists(candidate) and os.path.abspath(candidate) != os.path.abspath(OFFLINE_DB_PATH):
            try:
                shutil.copy2(candidate, OFFLINE_DB_PATH)
                break
            except Exception:
                pass

LOCAL_DB_URL = f"sqlite:///{OFFLINE_DB_PATH}"
local_engine = create_engine(
    LOCAL_DB_URL,
    connect_args={"check_same_thread": False},
    pool_pre_ping=False,
    # La interfaz hace pocas peticiones simultáneas. Limitar el pool evita que una
    # PC con poca RAM acumule conexiones SQLite/hilos innecesarios, sin bloquear
    # el refresco de caché que puede correr en paralelo.
    pool_size=3,
    max_overflow=1,
    pool_timeout=5,
    pool_use_lifo=True,
)


@event.listens_for(local_engine, "connect")
def _configure_local_sqlite(dbapi_connection, _connection_record):
    """Ajustes seguros para que la copia local no bloquee la interfaz mientras se sincroniza."""
    try:
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA temp_store=MEMORY")
        cur.execute("PRAGMA cache_size=-16000")
        cur.execute("PRAGMA mmap_size=33554432")
        cur.execute("PRAGMA journal_size_limit=8388608")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()
    except Exception:
        pass


LocalSessionLocal = sessionmaker(bind=local_engine, expire_on_commit=False)


def normalize_cloud_url(url: str) -> str:
    """Normaliza Neon al driver PostgreSQL disponible en esta instalacion."""
    if not url:
        return url
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme in {"postgres", "postgresql", "postgresql+psycopg", "postgresql+pg8000"}:
        driver = "pg8000" if _POSTGRES_DRIVER == "pg8000" else "psycopg"
        query = "" if driver == "pg8000" else parsed.query
        parsed = parsed._replace(scheme=f"postgresql+{driver}", query=query)
        return urlunparse(parsed)
    return url


cloud_engine = None
CloudSessionLocal = None
if CONFIGURED_DB_URL:
    cloud_url = normalize_cloud_url(CONFIGURED_DB_URL)
    cloud_connect_args = {"check_same_thread": False} if cloud_url.startswith("sqlite") else {}
    if cloud_url.startswith("postgresql+"):
        # Neon rechaza algunos parámetros de arranque enviados en `options`.
        # Usamos solo connect_timeout para mantener la conexión compatible y estable.
        cloud_connect_args = (
    {"timeout": 12, "ssl_context": ssl.create_default_context()}
    if _POSTGRES_DRIVER == "pg8000"
    else {"connect_timeout": 12}
)
    cloud_engine = create_engine(
        cloud_url,
        connect_args=cloud_connect_args,
        pool_pre_ping=True,
        pool_recycle=300,
        # Una sola conexión persistente basta para esta PC. Dejamos un único
        # overflow para que una escritura no espere si coincide con un refresco
        # de la copia local. Menos conexiones = menos RAM y menos sesiones en Neon.
        pool_size=1,
        max_overflow=1,
        pool_timeout=10,
        pool_use_lifo=True,
    )
    CloudSessionLocal = sessionmaker(bind=cloud_engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Patient(Base):
    __tablename__ = "patients"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cedula: Mapped[Optional[str]] = mapped_column(String(30), index=True, nullable=True)
    nombre: Mapped[str] = mapped_column(String(220), index=True)
    fecha_nacimiento: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    celular: Mapped[Optional[str]] = mapped_column(String(40), index=True, nullable=True)
    correo: Mapped[Optional[str]] = mapped_column(String(220), index=True, nullable=True)
    lugar: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    notas: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    visits: Mapped[list[Visit]] = relationship(back_populates="patient", cascade="all, delete-orphan")
    appointments: Mapped[list["Appointment"]] = relationship(back_populates="patient", cascade="all, delete-orphan")


class Visit(Base):
    __tablename__ = "visits"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    fecha: Mapped[date] = mapped_column(Date, index=True)
    tipo: Mapped[str] = mapped_column(String(1))
    procedimiento: Mapped[Optional[str]] = mapped_column(String(180), nullable=True)
    valor: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    observacion: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_row: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    patient: Mapped[Patient] = relationship(back_populates="visits")
    billing_record: Mapped[Optional["BillingRecord"]] = relationship(
        back_populates="visit", cascade="all, delete-orphan", uselist=False
    )


class BillingRecord(Base):
    __tablename__ = "billing_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    visit_id: Mapped[int] = mapped_column(ForeignKey("visits.id", ondelete="CASCADE"), unique=True, index=True)
    estado: Mapped[str] = mapped_column(String(20), default="PENDIENTE", index=True)
    numero_factura: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    emitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    visit: Mapped[Visit] = relationship(back_populates="billing_record")


class AzurEmission(Base):
    """Registro mínimo para evitar dobles emisiones hacia AZUR.

    No almacena la API key ni datos clínicos. Se conserva el resultado técnico
    necesario para saber si un grupo de facturación ya fue enviado.
    """
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


class BillingPreference(Base):
    """Datos alternativos persistentes de facturación de un paciente.

    No modifica la ficha clínica. Se usa automáticamente en emisión individual
    y masiva hasta que recepción la desactive o reemplace.
    """
    __tablename__ = "billing_preferences"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), unique=True, index=True)
    enabled: Mapped[int] = mapped_column(Integer, default=1)
    identificacion: Mapped[str] = mapped_column(String(30))
    nombre: Mapped[str] = mapped_column(String(220))
    direccion: Mapped[Optional[str]] = mapped_column(String(240), nullable=True)
    telefono: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    correo: Mapped[str] = mapped_column(String(220))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Appointment(Base):
    __tablename__ = "appointments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), index=True)
    fecha: Mapped[date] = mapped_column(Date, index=True)
    hora: Mapped[str] = mapped_column(String(5), index=True)
    duracion: Mapped[int] = mapped_column(Integer, default=20)
    nota: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    estado: Mapped[str] = mapped_column(String(20), default="PENDIENTE", index=True)
    origen: Mapped[str] = mapped_column(String(30), default="REAGENDADO")
    exported_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    loaded_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    patient: Mapped[Patient] = relationship(back_populates="appointments")


class ConfirmafyAgendaItem(Base):
    """Cita importada de Confirmafy todavía sin ficha clínica vinculada.

    La agenda externa se guarda separada de patients para que importar un CSV no
    cree, edite ni active pacientes. La vinculación ocurre únicamente cuando
    recepción pulsa la cita para atender al paciente cara a cara.
    """
    __tablename__ = "confirmafy_agenda_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(220), index=True)
    celular: Mapped[Optional[str]] = mapped_column(String(40), index=True, nullable=True)
    fecha: Mapped[date] = mapped_column(Date, index=True)
    hora: Mapped[str] = mapped_column(String(5), index=True)
    duracion: Mapped[int] = mapped_column(Integer, default=20)
    source_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Procedure(Base):
    __tablename__ = "procedures"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(180), unique=True)
    valor_default: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    activo: Mapped[int] = mapped_column(Integer, default=1)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(30), default="admin")


class Audit(Base):
    __tablename__ = "audit"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    username: Mapped[str] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(120))
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)




class TrashItem(Base):
    """Papelera recuperable para acciones borradas desde la interfaz.

    El snapshot se guarda como JSON de texto para funcionar igual en SQLite y
    PostgreSQL. No contiene claves, tokens ni configuración del programa.
    """
    __tablename__ = "trash_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(40), index=True)
    entity_id: Mapped[int] = mapped_column(Integer, index=True)
    patient_id: Mapped[Optional[int]] = mapped_column(Integer, index=True, nullable=True)
    label: Mapped[str] = mapped_column(String(240))
    snapshot_json: Mapped[str] = mapped_column(Text)
    deleted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    deleted_by: Mapped[str] = mapped_column(String(80))
    origin: Mapped[str] = mapped_column(String(120), default="PC RECEPCION")
    restored_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    restored_by: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)

class SyncOperation(Base):
    """Registro en la nube para que reintentos de sincronización no dupliquen datos."""
    __tablename__ = "sync_operations"
    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    operation: Mapped[str] = mapped_column(String(80))
    result_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class LocalBase(DeclarativeBase):
    pass


class OfflineQueue(LocalBase):
    __tablename__ = "offline_queue"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    operation: Mapped[str] = mapped_column(String(80), index=True)
    entity: Mapped[str] = mapped_column(String(40))
    local_entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    payload: Mapped[str] = mapped_column(Text)
    username: Mapped[str] = mapped_column(String(80), default="admin")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class OfflineIdMap(LocalBase):
    __tablename__ = "offline_id_map"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity: Mapped[str] = mapped_column(String(40), index=True)
    local_id: Mapped[int] = mapped_column(Integer, index=True)
    cloud_id: Mapped[int] = mapped_column(Integer)


class CacheMeta(LocalBase):
    __tablename__ = "cache_meta"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class WhatsAppOutbox(LocalBase):
    """Cola local de mensajes de Meta. Nunca guarda el access token.

    Vive solo en SQLite para evitar lecturas periódicas a Neon y para que un
    reinicio de la PC no duplique recordatorios.
    """
    __tablename__ = "whatsapp_outbox"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_key: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    template_name: Mapped[str] = mapped_column(String(100), index=True)
    source_type: Mapped[str] = mapped_column(String(30), index=True)
    source_id: Mapped[int] = mapped_column(Integer, index=True)
    phone: Mapped[str] = mapped_column(String(30))
    payload_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", index=True)
    due_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    response_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class HistoricalPatient(LocalBase):
    """Índice local y estático de pacientes atendidos entre 2020 y 2025.

    No se sube a Neon ni se mezcla automáticamente con la tabla principal.
    Sirve para buscar pacientes antiguos y reconocerlos como subsecuentes sin
    cargar miles de registros históricos a la nube.
    """
    __tablename__ = "historical_patients"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_key: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    nombre: Mapped[str] = mapped_column(String(240), index=True)
    search_text: Mapped[str] = mapped_column(Text)
    cedula: Mapped[Optional[str]] = mapped_column(String(30), index=True, nullable=True)
    celular: Mapped[Optional[str]] = mapped_column(String(40), index=True, nullable=True)
    correo: Mapped[Optional[str]] = mapped_column(String(220), index=True, nullable=True)
    lugar: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    first_year: Mapped[int] = mapped_column(Integer, default=2020)
    last_year: Mapped[int] = mapped_column(Integer, default=2025, index=True)
    # Última fecha exacta que pudo recuperarse con seguridad del Excel histórico.
    # Puede ser anterior a last_year cuando en los años posteriores el libro trae
    # una ficha sin encabezado de día; en ese caso no inventamos una fecha.
    last_visit_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    row_count: Mapped[int] = mapped_column(Integer, default=1)
    aliases: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    phones: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    emails: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cedulas: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class HistoricalPatientLink(LocalBase):
    """Vínculo manual local entre una ficha 2020–2025 y un paciente actual.

    El histórico vive solo en SQLite, por eso el vínculo también es local. Se usa
    para dejar de mostrar dos veces a la misma persona y para conservar la fecha
    histórica sin crear otro Patient ni añadir lecturas periódicas a Neon.
    """
    __tablename__ = "historical_patient_links"
    source_key: Mapped[str] = mapped_column(String(40), primary_key=True)
    patient_id: Mapped[int] = mapped_column(Integer, index=True)
    linked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


def seed_local_historical_registry() -> dict:
    """Carga una vez el índice histórico desde el CSV incluido en la app.

    Es una operación exclusivamente SQLite/local. No abre conexiones a Neon.
    Se usa un INSERT por lote para que incluso una PC antigua lo procese rápido.
    """
    if not os.path.exists(HISTORICAL_REGISTRY_FILE):
        return {"loaded": 0, "skipped": True, "reason": "missing_file"}
    try:
        with LocalSessionLocal() as db:
            marker = db.get(CacheMeta, HISTORICAL_REGISTRY_MARKER)
            count = int(db.scalar(select(func.count(HistoricalPatient.id))) or 0)
            if marker and marker.value == "1" and count >= 4000:
                return {"loaded": count, "skipped": True}
            rows = []
            with open(HISTORICAL_REGISTRY_FILE, encoding="utf-8-sig", newline="") as fh:
                for row in csv.DictReader(fh):
                    name = " ".join(str(row.get("nombre") or "").split()).upper()
                    if not name:
                        continue
                    rows.append({
                        "source_key": str(row.get("source_key") or "").strip(),
                        "nombre": name,
                        "search_text": str(row.get("search_text") or name).upper(),
                        "cedula": str(row.get("cedula") or "").strip() or None,
                        "celular": str(row.get("celular") or "").strip() or None,
                        "correo": str(row.get("correo") or "").strip().lower() or None,
                        "lugar": " ".join(str(row.get("lugar") or "").split()).upper() or None,
                        "first_year": int(row.get("first_year") or 2020),
                        "last_year": int(row.get("last_year") or 2025),
                        "last_visit_date": date.fromisoformat(str(row.get("last_visit_date") or "").strip()) if str(row.get("last_visit_date") or "").strip() else None,
                        "row_count": int(row.get("row_count") or 1),
                        "aliases": str(row.get("aliases") or "").strip() or None,
                        "phones": str(row.get("phones") or "").strip() or None,
                        "emails": str(row.get("emails") or "").strip() or None,
                        "cedulas": str(row.get("cedulas") or "").strip() or None,
                    })
            if not rows:
                return {"loaded": 0, "skipped": True, "reason": "empty_file"}
            db.execute(delete(HistoricalPatient))
            db.execute(insert(HistoricalPatient), rows)
            if marker:
                marker.value = "1"
            else:
                db.add(CacheMeta(key=HISTORICAL_REGISTRY_MARKER, value="1"))
            db.commit()
            return {"loaded": len(rows), "skipped": False}
    except Exception as exc:
        return {"loaded": 0, "skipped": True, "reason": str(exc)[:160]}


Base.metadata.create_all(local_engine)
LocalBase.metadata.create_all(local_engine)
# create_all no agrega columnas a una tabla SQLite existente. Esta migración local
# es diminuta, no toca Neon y permite enriquecer las fichas históricas ya instaladas.
try:
    with local_engine.begin() as conn:
        cols = {str(row[1]) for row in conn.exec_driver_sql("PRAGMA table_info(historical_patients)").fetchall()}
        if cols and "last_visit_date" not in cols:
            conn.exec_driver_sql("ALTER TABLE historical_patients ADD COLUMN last_visit_date DATE")
            conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_historical_patients_last_visit_date ON historical_patients (last_visit_date)")
except Exception:
    pass
seed_local_historical_registry()

TOKENS: dict[str, str] = {}
_state_lock = threading.RLock()
_sync_lock = threading.Lock()
_cache_refresh_lock = threading.Lock()
_agenda_status_sync_lock = threading.Lock()
_agenda_status_sync_at: dict[str, float] = {}
_cloud_check_lock = threading.Lock()
_queue_count_lock = threading.Lock()
_user_cache_lock = threading.Lock()
_cloud_init_lock = threading.Lock()
# La copia completa de emergencia es costosa; las escrituras de esta PC se reflejan
# al instante. La copia total solo se renueva cuando vence (60 min), al volver de
# una pausa larga o cuando hace falta reconciliar cambios offline.
# v4.0: la copia completa ya no se refresca por un temporizador que mantenga
# Neon despierto. Se actualiza al iniciar, al volver de AFK y tras operaciones
# que realmente lo requieren.
CACHE_REFRESH_SECONDS = 12 * 60 * 60
AGENDA_CACHE_REFRESH_SECONDS = 30 * 60
# Las lecturas de pantalla son locales; esta sonda solo hace falta antes de
# operaciones reales. Alargamos el intervalo y aplicamos backoff cuando falla.
CLOUD_CHECK_SECONDS = 600.0
CLOUD_RETRY_SECONDS = 20.0
REMOTE_REFRESH_IDLE_SECONDS = 30 * 60
IDLE_AFTER_SECONDS = 300
QUEUE_COUNT_CACHE_SECONDS = 1.5
USER_CACHE_SECONDS = 45.0
_queue_count_cache = {"value": None, "ts": 0.0}
_user_cache: dict[str, tuple[float, User]] = {}
_cloud_initialized = False
# RC2: forzar una única revisión de esquema de Neon porque RC1 añadió
# billing_preferences y azur_emissions, pero heredaba el marcador antiguo v4.3.7.
# Con el marcador viejo una PC ya inicializada podía saltarse create_all() y
# "Aprobar para facturar" fallaba con HTTP 500 al consultar la tabla nueva.
CLOUD_SCHEMA_MARKER = "cloud_schema_ready_v4_4_0_ops_" + hashlib.sha1(CONFIGURED_DB_URL.encode("utf-8")).hexdigest()[:10]
_state = {
    "online": False,
    "last_checked": 0.0,
    "last_error": "",
    "last_cache_refresh": 0.0,
    "last_success": 0.0,
    "consecutive_failures": 0,
    "last_probe_ms": None,
    "client_idle": False,
    "last_activity": time.time(),
    "idle_since": 0.0,
}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return f"{salt.hex()}:{dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, dk_hex = stored.split(":", 1)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 200_000)
        return hmac.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


def _workstation_label() -> str:
    raw = (os.getenv("RP_WORKSTATION_NAME") or os.getenv("COMPUTERNAME") or socket.gethostname() or "PC RECEPCION").strip()
    raw = re.sub(r"[^A-Za-z0-9 _.-]+", "", raw)[:60].strip()
    return raw.upper() or "PC RECEPCION"


def audit(db: Session, username_or_user, action: str, detail: str = ""):
    """Registra la acción en la base de trabajo y refleja la misma línea en SQLite.

    La copia local se hace DESPUÉS de que la transacción principal confirme, así
    abrir Actividad nunca necesita consultar Neon. No añade ninguna lectura a la nube.
    """
    username = getattr(username_or_user, "username", None) or str(username_or_user or "admin")
    clean = str(detail or "").strip()
    tagged = f"[PC:{_workstation_label()}] {clean}".strip()
    stamp = datetime.utcnow()
    db.add(Audit(ts=stamp, username=username, action=action, detail=tagged))
    try:
        if db.get_bind() is not local_engine:
            db.info.setdefault("rp_audit_local_mirror", []).append({
                "ts": stamp, "username": username, "action": action, "detail": tagged,
            })
    except Exception:
        pass


@event.listens_for(Session, "after_commit")
def _audit_after_commit_local_mirror(session):
    try:
        if session.get_bind() is local_engine:
            session.info.pop("rp_audit_local_mirror", None)
            return
    except Exception:
        return
    pending = session.info.pop("rp_audit_local_mirror", [])
    if not pending:
        return
    try:
        with LocalSessionLocal() as ldb:
            for row in pending:
                ldb.add(Audit(ts=row["ts"], username=row["username"], action=row["action"], detail=row["detail"]))
            ldb.commit()
    except Exception:
        pass


@event.listens_for(Session, "after_rollback")
def _audit_after_rollback_clear_local_mirror(session):
    session.info.pop("rp_audit_local_mirror", None)



def normalize_lookup_name(value: Optional[str]) -> str:
    raw = (value or "").strip().upper()
    raw = "".join(
        ch for ch in unicodedata.normalize("NFD", raw)
        if unicodedata.category(ch) != "Mn"
    )
    return re.sub(r"[^A-Z0-9]+", " ", raw).strip()


def normalize_lookup_phone(value: Optional[str]) -> str:
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith("593") and len(digits) >= 12:
        return "0" + digits[3:12]
    return digits[:10] if digits else ""


def lookup_name_tokens(value: Optional[str]) -> set[str]:
    """Tokens normalizados para comparar nombres sin depender del orden."""
    return {token for token in normalize_lookup_name(value).split() if len(token) >= 2}


def strong_name_overlap(left: Optional[str], right: Optional[str]) -> bool:
    """Coincidencia conservadora: al menos dos palabras y un nombre contenido en el otro."""
    a = lookup_name_tokens(left)
    b = lookup_name_tokens(right)
    if len(a) < 2 or len(b) < 2:
        return False
    return a.issubset(b) or b.issubset(a)


def patient_name_word_count(value: Optional[str]) -> int:
    """Cantidad de palabras útiles del nombre, sin depender de tildes o puntuación."""
    return len([x for x in normalize_lookup_name(value).split() if len(x) >= 2])


def patient_name_quality(value: Optional[str]) -> str:
    """Calidad práctica para recepción. 4+ es ideal; 3 se acepta; 1-2 requiere revisión."""
    count = patient_name_word_count(value)
    if count >= 4:
        return "completo"
    if count == 3:
        return "aceptable"
    return "incompleto"


def _name_similarity(left: Optional[str], right: Optional[str]) -> tuple[float, list[str]]:
    """Compara nombres por palabras y tolera una errata pequeña (JHONNY/JHONY).

    Para evitar falsos positivos exigimos dos palabras relacionadas y, salvo que
    exista un identificador externo, al menos una coincidencia literal larga.
    """
    a = [x for x in normalize_lookup_name(left).split() if len(x) >= 2]
    b = [x for x in normalize_lookup_name(right).split() if len(x) >= 2]
    if not a or not b:
        return 0.0, []
    used: set[int] = set()
    matches: list[tuple[str, str, float]] = []
    # Primero emparejamos palabras idénticas.
    for token in a:
        for j, other in enumerate(b):
            if j not in used and token == other:
                used.add(j); matches.append((token, other, 1.0)); break
    # Luego permitimos una sola diferencia ortográfica razonable por palabra.
    for token in a:
        if any(x == token for x, _, _ in matches):
            continue
        best_j = None; best = 0.0
        for j, other in enumerate(b):
            if j in used or min(len(token), len(other)) < 4:
                continue
            ratio = SequenceMatcher(None, token, other).ratio()
            if ratio > best:
                best = ratio; best_j = j
        if best_j is not None and best >= 0.84:
            used.add(best_j); matches.append((token, b[best_j], best))
    if len(matches) < 2:
        return 0.0, []
    # Si ambas fichas ya tienen tres o más palabras, dos apellidos iguales no
    # bastan: podrían ser familiares. Exigimos al menos tres términos relacionados.
    if min(len(a), len(b)) >= 3 and len(matches) < 3:
        return 0.0, []
    exact_long = any(score == 1.0 and len(x) >= 4 for x, _, score in matches)
    if not exact_long:
        return 0.0, []
    coverage = len(matches) / max(2, min(len(a), len(b)))
    avg = sum(score for _, _, score in matches) / len(matches)
    # Penalizamos nombres muy largos cuando solo coinciden dos términos.
    long_penalty = 0.08 if max(len(a), len(b)) >= 5 and len(matches) == 2 else 0.0
    score = max(0.0, min(1.0, 0.58 * coverage + 0.42 * avg - long_penalty))
    labels = [x if x == y else f"{x}≈{y}" for x, y, _ in matches]
    return score, labels


def patient_similarity(left: Patient, right: Patient) -> tuple[float, str]:
    """Puntaje de posible duplicado, usado solo para advertir o fusionar con confirmación."""
    lc = re.sub(r"\D", "", left.cedula or "")
    rc = re.sub(r"\D", "", right.cedula or "")
    if lc and rc and lc == rc:
        return 1.0, "misma cédula"
    lp = normalize_lookup_phone(left.celular)
    rp = normalize_lookup_phone(right.celular)
    name_score, labels = _name_similarity(left.nombre, right.nombre)
    if lp and rp and lp == rp:
        # Un teléfono compartido no basta por sí solo; con nombre relacionado sí.
        if name_score >= 0.58:
            return max(0.96, name_score), "mismo celular y nombre parecido"
        return 0.0, ""
    if name_score >= 0.74:
        return name_score, "nombre parecido: " + ", ".join(labels[:4])
    return 0.0, ""


def _pipe_values(value: Optional[str]) -> list[str]:
    return [x.strip() for x in str(value or "").split("|") if x.strip()]


def historical_dict(h: HistoricalPatient) -> dict:
    return {
        "id": None,
        "historical": True,
        "historical_id": int(h.id),
        "cedula": h.cedula,
        "nombre": h.nombre,
        "fecha_nacimiento": None,
        "celular": h.celular,
        "correo": h.correo,
        "lugar": h.lugar,
        "notas": None,
        "ultima_atencion": h.last_visit_date,
        "historical_first_year": int(h.first_year or 2020),
        "historical_last_year": int(h.last_year or 2025),
        "historical_last_visit_date": h.last_visit_date,
        "historical_rows": int(h.row_count or 1),
    }


def _historical_linked_keys(ldb: Session, patient_id: Optional[int] = None) -> set[str]:
    stmt = select(HistoricalPatientLink.source_key)
    if patient_id is not None:
        stmt = stmt.where(HistoricalPatientLink.patient_id == int(patient_id))
    return {str(x) for x in ldb.scalars(stmt)}


def _historical_link_patient(source_key: str, patient_id: int) -> None:
    """Guarda o actualiza un vínculo explícito exclusivamente en SQLite."""
    with LocalSessionLocal() as ldb:
        link = ldb.get(HistoricalPatientLink, str(source_key))
        if link:
            link.patient_id = int(patient_id); link.linked_at = datetime.utcnow()
        else:
            ldb.add(HistoricalPatientLink(source_key=str(source_key), patient_id=int(patient_id)))
        ldb.commit()


def _historical_reassign_links(source_patient_id: int, target_patient_id: int) -> None:
    """Mantiene vínculos históricos cuando recepción fusiona dos pacientes actuales."""
    try:
        with LocalSessionLocal() as ldb:
            links = list(ldb.scalars(select(HistoricalPatientLink).where(HistoricalPatientLink.patient_id == int(source_patient_id))))
            for link in links:
                link.patient_id = int(target_patient_id); link.linked_at = datetime.utcnow()
            if links:
                ldb.commit()
    except Exception:
        pass


def _historical_remove_links(patient_id: int) -> None:
    try:
        with LocalSessionLocal() as ldb:
            ldb.execute(delete(HistoricalPatientLink).where(HistoricalPatientLink.patient_id == int(patient_id)))
            ldb.commit()
    except Exception:
        pass


def _historical_name_alias_sets(h: HistoricalPatient) -> list[set[str]]:
    names = _pipe_values(h.aliases) or [h.nombre]
    return [lookup_name_tokens(x) for x in names if lookup_name_tokens(x)]


def _historical_identity_match(h: HistoricalPatient, p: Patient) -> tuple[bool, str]:
    """Compara un histórico con un paciente actual sin aceptar coincidencias débiles."""
    p_ced = re.sub(r"\D", "", p.cedula or "")
    h_ceds = set(_pipe_values(h.cedulas) or ([h.cedula] if h.cedula else []))
    if p_ced and p_ced in h_ceds:
        return True, "cedula"

    p_phone = normalize_lookup_phone(p.celular)
    h_phones = {normalize_lookup_phone(x) for x in (_pipe_values(h.phones) or ([h.celular] if h.celular else []))}
    h_phones.discard("")
    p_tokens = lookup_name_tokens(p.nombre)
    aliases = _historical_name_alias_sets(h)
    if p_phone and p_phone in h_phones and any(len(p_tokens & a) >= 2 for a in aliases):
        return True, "celular"

    p_email = str(p.correo or "").strip().lower()
    h_emails = {x.lower() for x in (_pipe_values(h.emails) or ([h.correo] if h.correo else []))}
    if p_email and p_email in h_emails and any(len(p_tokens & a) >= 2 for a in aliases):
        return True, "correo"

    # Por nombre solamente exigimos 3 palabras coincidentes para reducir homónimos.
    for a in aliases:
        if len(a) >= 3 and len(p_tokens) >= 3 and (a == p_tokens or a.issubset(p_tokens) or p_tokens.issubset(a)):
            if len(a & p_tokens) >= 3:
                return True, "nombre"
    return False, ""


def historical_summary_for_patient(p: Patient) -> Optional[dict]:
    """Busca el historial 2020-2025 solo en SQLite; nunca consulta Neon."""
    try:
        with LocalSessionLocal() as ldb:
            candidates: dict[int, HistoricalPatient] = {}
            # Un vínculo confirmado por recepción tiene prioridad sobre cualquier
            # heurística de nombre y sobrevive aunque luego se complete/corrija la ficha.
            linked_keys = _historical_linked_keys(ldb, int(p.id))
            if linked_keys:
                for h in ldb.scalars(select(HistoricalPatient).where(HistoricalPatient.source_key.in_(linked_keys))):
                    candidates[int(h.id)] = h
            ced = re.sub(r"\D", "", p.cedula or "")
            phone = normalize_lookup_phone(p.celular)
            email = str(p.correo or "").strip().lower()
            if ced:
                for h in ldb.scalars(select(HistoricalPatient).where(HistoricalPatient.cedula == ced).limit(8)):
                    candidates[int(h.id)] = h
            if phone:
                for h in ldb.scalars(select(HistoricalPatient).where(or_(HistoricalPatient.celular == phone, HistoricalPatient.phones.ilike(f"%{phone}%"))).limit(12)):
                    candidates[int(h.id)] = h
            if email:
                for h in ldb.scalars(select(HistoricalPatient).where(or_(HistoricalPatient.correo == email, HistoricalPatient.emails.ilike(f"%{email}%"))).limit(12)):
                    candidates[int(h.id)] = h
            tokens = list(lookup_name_tokens(p.nombre))
            if len(tokens) >= 3:
                stmt = select(HistoricalPatient)
                for token in tokens[:6]:
                    stmt = stmt.where(HistoricalPatient.search_text.ilike(f"%{token}%"))
                for h in ldb.scalars(stmt.limit(12)):
                    candidates[int(h.id)] = h
            matched = []
            reasons = set()
            for h in candidates.values():
                if h.source_key in linked_keys:
                    matched.append(h); reasons.add("vinculo_manual"); continue
                ok, reason = _historical_identity_match(h, p)
                if ok:
                    matched.append(h); reasons.add(reason)
            if not matched:
                return None
            exact_dates = [h.last_visit_date for h in matched if h.last_visit_date]
            return {
                "matched": True,
                "first_year": min(int(h.first_year or 2020) for h in matched),
                "last_year": max(int(h.last_year or 2025) for h in matched),
                # Se llama fecha "conocida" deliberadamente: si el Excel menciona
                # al paciente en un año posterior sin día legible, no inventamos día/mes.
                "last_visit_date": max(exact_dates) if exact_dates else None,
                "records": len(matched),
                "reason": ",".join(sorted(reasons)),
            }
    except Exception:
        return None


def _historical_matches_current(h: HistoricalPatient, patients: list[Patient]) -> list[Patient]:
    return [p for p in patients if _historical_identity_match(h, p)[0]]


def search_historical_patients(q: str, limit: int = 12) -> list[dict]:
    raw = " ".join(str(q or "").strip().upper().split())
    if len(raw) < 2:
        return []
    tokens = [t for t in normalize_lookup_name(raw).split() if t][:8]
    if not tokens:
        return []
    try:
        with LocalSessionLocal() as ldb:
            linked_keys = _historical_linked_keys(ldb)
            stmt = select(HistoricalPatient)
            for token in tokens:
                stmt = stmt.where(HistoricalPatient.search_text.ilike(f"%{token}%"))
            hist = list(ldb.scalars(stmt.order_by(HistoricalPatient.last_year.desc(), HistoricalPatient.nombre).limit(min(max(limit * 2, 12), 40))))
            if not hist:
                return []
            # Solo pacientes actuales que podrían compartir esos mismos términos.
            p_stmt = select(Patient)
            for token in tokens:
                pat = f"%{token}%"
                p_stmt = p_stmt.where(or_(Patient.cedula.ilike(pat), Patient.nombre.ilike(pat), Patient.celular.ilike(pat), Patient.correo.ilike(pat)))
            current = list(ldb.scalars(p_stmt.limit(80)))
            result = []
            for h in hist:
                if h.source_key in linked_keys:
                    continue
                # Fichas antiguas de solo dos palabras y sin ningún identificador
                # son demasiado débiles para activarlas automáticamente. Preferimos
                # no mostrarlas antes que crear un homónimo por error.
                alias_sets = _historical_name_alias_sets(h)
                has_identifier = bool(h.cedula or h.celular or h.correo)
                if not has_identifier and not any(len(x) >= 3 for x in alias_sets):
                    continue
                # Si ya existe con una coincidencia segura, no mostramos una ficha histórica duplicada.
                if _historical_matches_current(h, current):
                    continue
                result.append(historical_dict(h))
                if len(result) >= limit:
                    break
            return result
    except Exception:
        return []


def _historical_similarity_candidates(name: str, limit: int = 8) -> list[dict]:
    """Busca candidatos históricos parecidos usando solo SQLite local."""
    tokens = [x for x in normalize_lookup_name(name).split() if len(x) >= 3]
    if not tokens:
        return []
    try:
        with LocalSessionLocal() as ldb:
            linked_keys = _historical_linked_keys(ldb)
            # Para no recorrer 4.222 filas en cada tecla, preseleccionamos por cualquiera
            # de las palabras largas y solo calculamos similitud sobre un grupo pequeño.
            stmt = select(HistoricalPatient).where(or_(*[HistoricalPatient.search_text.ilike(f"%{t}%") for t in tokens[:5]]))
            rows = list(ldb.scalars(stmt.order_by(HistoricalPatient.last_year.desc()).limit(90)))
            out = []
            for h in rows:
                if h.source_key in linked_keys:
                    continue
                score, labels = _name_similarity(name, h.nombre)
                if score < 0.74:
                    continue
                item = historical_dict(h)
                item.update({"similarity": round(score, 3), "similar_reason": "nombre histórico parecido: " + ", ".join(labels[:4])})
                out.append(item)
            out.sort(key=lambda x: (-float(x.get("similarity") or 0), -int(x.get("historical_last_year") or 0), str(x.get("nombre") or "")))
            return out[:limit]
    except Exception:
        return []


def _historical_review_matches(patients: list[Patient], per_patient: int = 6) -> dict[int, list[dict]]:
    """Candidatos histórico↔actual para Por revisar, sin un O(n×m) completo.

    Se construyen índices de cédula, teléfono, correo y palabras una sola vez en
    SQLite. Luego solo se calcula similitud sobre filas que comparten al menos dos
    términos o un identificador. Se ejecuta únicamente al abrir Por revisar.
    """
    if not patients:
        return {}
    try:
        with LocalSessionLocal() as ldb:
            linked_keys = _historical_linked_keys(ldb)
            historical_rows = [h for h in ldb.scalars(select(HistoricalPatient)) if h.source_key not in linked_keys]
    except Exception:
        return {}

    from collections import defaultdict, Counter
    by_id: dict[int, HistoricalPatient] = {}
    token_index: dict[str, set[int]] = defaultdict(set)
    cedula_index: dict[str, set[int]] = defaultdict(set)
    phone_index: dict[str, set[int]] = defaultdict(set)
    email_index: dict[str, set[int]] = defaultdict(set)
    for h in historical_rows:
        hid = int(h.id); by_id[hid] = h
        all_tokens: set[str] = set()
        for alias in (_pipe_values(h.aliases) or [h.nombre]):
            all_tokens.update(t for t in lookup_name_tokens(alias) if len(t) >= 3)
        for token in all_tokens:
            token_index[token].add(hid)
        for value in (_pipe_values(h.cedulas) or ([h.cedula] if h.cedula else [])):
            digits = re.sub(r"\D", "", str(value or ""))
            if digits: cedula_index[digits].add(hid)
        for value in (_pipe_values(h.phones) or ([h.celular] if h.celular else [])):
            phone = normalize_lookup_phone(value)
            if phone: phone_index[phone].add(hid)
        for value in (_pipe_values(h.emails) or ([h.correo] if h.correo else [])):
            email = str(value or "").strip().lower()
            if email: email_index[email].add(hid)

    out: dict[int, list[dict]] = {}
    for p in patients:
        pid = int(p.id)
        candidate_ids: set[int] = set()
        strong_ids: set[int] = set()
        p_ced = re.sub(r"\D", "", p.cedula or "")
        p_phone = normalize_lookup_phone(p.celular)
        p_email = str(p.correo or "").strip().lower()
        if p_ced:
            strong_ids |= cedula_index.get(p_ced, set())
        if p_phone:
            strong_ids |= phone_index.get(p_phone, set())
        if p_email:
            strong_ids |= email_index.get(p_email, set())
        candidate_ids |= strong_ids

        hits: Counter[int] = Counter()
        for token in [t for t in lookup_name_tokens(p.nombre) if len(t) >= 3]:
            for hid in token_index.get(token, set()):
                hits[hid] += 1
        candidate_ids.update(hid for hid, n in hits.items() if n >= 2)

        matches: list[dict] = []
        for hid in candidate_ids:
            h = by_id.get(hid)
            if not h:
                continue
            h_ceds = {re.sub(r"\D", "", x) for x in (_pipe_values(h.cedulas) or ([h.cedula] if h.cedula else [])) if re.sub(r"\D", "", x)}
            # v4.3.89: la cédula histórica no bloquea el vínculo por similitud; la ficha actual conserva su cédula.
            identity_ok, identity_reason = _historical_identity_match(h, p)
            score, labels = _name_similarity(p.nombre, h.nombre)
            same_phone = bool(p_phone and p_phone in {normalize_lookup_phone(x) for x in (_pipe_values(h.phones) or ([h.celular] if h.celular else []))})
            if identity_ok:
                score = max(score, 0.99 if identity_reason == "cedula" else 0.96)
                reason = f"histórico: misma {identity_reason}"
            elif same_phone and score >= 0.58:
                score = max(score, 0.94); reason = "histórico: mismo celular y nombre parecido"
            elif score >= 0.75:
                reason = "histórico: nombre parecido: " + ", ".join(labels[:4])
            else:
                continue
            item = historical_dict(h)
            item.update({"similarity": round(float(score), 3), "similar_reason": reason, "visit_count": 0})
            matches.append(item)
        matches.sort(key=lambda x: (-float(x.get("similarity") or 0), -int(x.get("historical_last_year") or 0), str(x.get("nombre") or "")))
        if matches:
            out[pid] = matches[:max(1, int(per_patient))]
    return out


def _confirmafy_patient_status_map(db: Session, patients: list[Patient]) -> dict[int, dict]:
    """Clasifica fichas cuyo origen Confirmafy puede demostrarse sin adivinar.

    Se usa solo bajo demanda en Pacientes -> Por revisar / Confirmafy. Una ficha se
    considera eliminable manualmente únicamente si no tiene atenciones clínicas,
    sus datos son los mínimos que solían crear las importaciones antiguas y existe
    una prueba de origen (citas CONFIRMAFY_IMPORTADO o ventana de Audit).
    """
    if not patients:
        return {}
    ids = [int(p.id) for p in patients]
    visit_counts = {int(pid): int(total or 0) for pid, total in db.execute(
        select(Visit.patient_id, func.count(Visit.id)).where(Visit.patient_id.in_(ids)).group_by(Visit.patient_id)
    ).all()}
    appointment_stats = {int(pid): (int(total or 0), int(imported or 0)) for pid, total, imported in db.execute(
        select(
            Appointment.patient_id,
            func.count(Appointment.id),
            func.sum(case((Appointment.origen == "CONFIRMAFY_IMPORTADO", 1), else_=0)),
        ).where(Appointment.patient_id.in_(ids)).group_by(Appointment.patient_id)
    ).all()}
    import_windows = _confirmafy_import_audit_windows(db)

    out: dict[int, dict] = {}
    for p in patients:
        pid = int(p.id)
        total_apps, imported_apps = appointment_stats.get(pid, (0, 0))
        created = p.created_at
        created_in_window = bool(created and any(a <= created <= b for a, b in import_windows))
        # Para mostrar/borrar manualmente como "creado por Confirmafy" exigimos
        # la prueba más fuerte: created_at dentro de una ventana registrada de importación.
        # Tener una cita importada no basta, porque un paciente real también puede tenerla.
        created_by_confirmafy = bool(created_in_window)
        sparse = not any([p.cedula, p.fecha_nacimiento, p.correo, p.lugar, p.notas])
        visits = visit_counts.get(pid, 0)
        all_apps_imported = bool(total_apps == 0 or (total_apps > 0 and imported_apps == total_apps))
        safe_delete = bool(created_by_confirmafy and visits == 0 and sparse and all_apps_imported)
        out[pid] = {
            "confirmafy_origin": created_by_confirmafy,
            "confirmafy_related": bool(imported_apps > 0),
            "safe_confirmafy_delete": safe_delete,
            "visit_count": visits,
            "appointment_count": total_apps,
            "imported_appointment_count": imported_apps,
        }
    return out



def _auto_link_safe_review_duplicates(db: Session, user: User) -> dict:
    """Auto-vincula Por revisar con umbral >=75%.

    Los históricos 2020-2025 viven solo en SQLite, así que se pueden vincular
    incluso cuando la pantalla Por revisar está leyendo la copia local. Una misma
    ficha actual puede absorber todos sus históricos >=75% en una sola apertura.
    La cédula histórica nunca reemplaza la cédula de la ficha actual.
    """
    local_read = is_offline_db(db)
    patients = list(db.scalars(select(Patient).order_by(Patient.id)))

    # Actual↔actual requiere la base principal para mover atenciones/citas. Se
    # conserva la protección de cédulas distintas porque fusionar dos Patients
    # actuales sí sería destructivo. Esta rama no corre en el GET local.
    linked=0; skipped_conflict=0
    if not local_read:
        visit_counts = {int(pid): int(n or 0) for pid, n in db.execute(
            select(Visit.patient_id, func.count(Visit.id)).group_by(Visit.patient_id)
        ).all()}
        appointment_counts = {int(pid): int(n or 0) for pid, n in db.execute(
            select(Appointment.patient_id, func.count(Appointment.id)).where(Appointment.patient_id.is_not(None)).group_by(Appointment.patient_id)
        ).all()}
        def valid_ident(p):
            d=re.sub(r"\D","",str(p.cedula or ""))
            return d if len(d) in {10,13} and d and set(d)!={"0"} else ""
        def completeness(p):
            return sum(bool(str(getattr(p,f,None) or "").strip()) for f in ("cedula","fecha_nacimiento","celular","correo","lugar"))
        pairs=[]
        for i,left in enumerate(patients):
            for right in patients[i+1:]:
                lc,rc=valid_ident(left),valid_ident(right)
                if lc and rc and lc!=rc: continue
                score,why=patient_similarity(left,right)
                if float(score or 0)<0.75: continue
                pairs.append((float(score),int(left.id),int(right.id),str(why or "similitud >= 75%")))
        pairs.sort(key=lambda x:(-x[0],x[1],x[2]))
        for _score,aid,bid,_why in pairs:
            a=db.get(Patient,aid); b=db.get(Patient,bid)
            if not a or not b or int(a.id)==int(b.id): continue
            ac,bc=valid_ident(a),valid_ident(b)
            if ac and bc and ac!=bc:
                skipped_conflict+=1; continue
            def rank(p):
                pid=int(p.id)
                return (visit_counts.get(pid,0),appointment_counts.get(pid,0),completeness(p),-pid)
            target,source=(a,b) if rank(a)>=rank(b) else (b,a)
            score,_=patient_similarity(source,target)
            if float(score or 0)<0.75: continue
            try:
                result=merge_patient_confirmed(int(source.id),int(target.id),db=db,user=user)
                if result.get("deleted_source"):
                    linked+=1
                    tid=int(target.id)
                    visit_counts[tid]=visit_counts.get(tid,0)+visit_counts.get(int(source.id),0)
                    appointment_counts[tid]=appointment_counts.get(tid,0)+appointment_counts.get(int(source.id),0)
            except Exception:
                continue

    # Histórico↔actual: SIEMPRE puede ejecutarse porque el vínculo es local.
    # Se enlazan todos los candidatos >=75%, aunque sean varios para el mismo
    # paciente y aunque el histórico solo tenga un nombre + un apellido.
    historical_linked=0
    try:
        current=list(db.scalars(select(Patient).order_by(Patient.id)))
        historical_matches=_historical_review_matches(current,per_patient=24)
        for p in current:
            for item in historical_matches.get(int(p.id),[]):
                if float(item.get("similarity") or 0)<0.75: continue
                hid=int(item.get("historical_id") or 0)
                if not hid: continue
                try:
                    with LocalSessionLocal() as ldb:
                        h=ldb.get(HistoricalPatient,hid)
                        if not h: continue
                        source_key=str(h.source_key)
                    _historical_link_patient(source_key,int(p.id))
                    historical_linked+=1
                except Exception:
                    continue
    except Exception:
        pass

    return {
        "linked": linked,
        "historical_linked": historical_linked,
        "skipped": False,
        "threshold": 0.75,
        "local_review": bool(local_read),
        "cedula_conflicts": skipped_conflict,
    }


def _patient_review_rows(db: Session, limit: int = 30, confirmafy_only: bool = False) -> list[dict]:
    """Lista local y accionable, calculada solo cuando el usuario la solicita."""
    patients = list(db.scalars(select(Patient).order_by(Patient.nombre)))
    last_dates = {int(pid): last for pid, last in db.execute(
        select(Visit.patient_id, func.max(Visit.fecha)).group_by(Visit.patient_id)
    ).all()}
    status = _confirmafy_patient_status_map(db, patients)
    reasons: dict[int, list[str]] = {int(p.id): [] for p in patients}
    matches: dict[int, list[dict]] = {int(p.id): [] for p in patients}
    historical_matches = _historical_review_matches(patients)

    for p in patients:
        if patient_name_quality(p.nombre) == "incompleto":
            reasons[int(p.id)].append("Nombre corto: confirma apellidos y nombres")
        if status.get(int(p.id), {}).get("confirmafy_origin"):
            reasons[int(p.id)].append("Ficha creada por una importación antigua de Confirmafy")
        hm = historical_matches.get(int(p.id)) or []
        if hm:
            reasons[int(p.id)].append(f"Posible histórico: {hm[0].get('nombre')}")
            if len(hm) > 1:
                reasons[int(p.id)].append(f"+ {len(hm)-1} histórico(s) parecido(s)")
            matches[int(p.id)].extend(hm)

    # Comparación O(n²) solo bajo demanda. En la PC del consultorio se ejecuta
    # únicamente al pulsar Por revisar/Confirmafy y sobre SQLite local.
    for i, left in enumerate(patients):
        for right in patients[i + 1:]:
            score, why = patient_similarity(left, right)
            if score < 0.78:
                continue
            left_id, right_id = int(left.id), int(right.id)
            reasons[left_id].append(f"Posible coincidencia con {right.nombre}")
            reasons[right_id].append(f"Posible coincidencia con {left.nombre}")
            matches[left_id].append({
                **p_dict(right), "similarity": round(score, 3), "similar_reason": why,
                "ultima_atencion": last_dates.get(right_id),
                "visit_count": status.get(right_id, {}).get("visit_count", 0),
            })
            matches[right_id].append({
                **p_dict(left), "similarity": round(score, 3), "similar_reason": why,
                "ultima_atencion": last_dates.get(left_id),
                "visit_count": status.get(left_id, {}).get("visit_count", 0),
            })

    rows = []
    for p in patients:
        pid = int(p.id); st = status.get(pid, {})
        if confirmafy_only and not st.get("confirmafy_origin"):
            continue
        rs = reasons.get(pid) or []
        if not confirmafy_only and not rs:
            continue
        candidates = sorted(matches.get(pid) or [], key=lambda x: (-float(x.get("similarity") or 0), 0 if x.get("historical") else 1, str(x.get("nombre") or "")))[:6]
        item = {
            **p_dict(p), "ultima_atencion": last_dates.get(pid), "historical": False,
            "review_reason": " · ".join(dict.fromkeys(rs)),
            "review_matches": candidates,
            **st,
        }
        rows.append(item)
    rows.sort(key=lambda x: (
        0 if x.get("safe_confirmafy_delete") else 1,
        0 if x.get("review_matches") else 1,
        str(x.get("nombre") or ""),
    ))
    return rows[:limit]

def _confirmafy_import_audit_windows(db: Session) -> list[tuple[datetime, datetime]]:
    """Ventanas de tiempo que prueban que un paciente pudo ser creado por Confirmafy.

    Las versiones antiguas no guardaban un campo de origen en Patient. Sin embargo,
    sí registraban en Audit el final de cada importación. Los pacientes creados por
    aquella importación se insertaban segundos/minutos antes de ese Audit. Usamos una
    ventana conservadora de 15 minutos hacia atrás y 1 minuto hacia adelante.
    """
    rows = list(db.scalars(
        select(Audit).where(or_(
            Audit.action == AGENDA_SEED_ACTION,
            Audit.action == "importar_agenda_confirmafy",
        )).order_by(Audit.ts)
    ))
    windows: list[tuple[datetime, datetime]] = []
    for row in rows:
        if not row.ts:
            continue
        windows.append((row.ts - timedelta(minutes=15), row.ts + timedelta(minutes=1)))
    return windows


def _confirmafy_legacy_duplicate_plan(db: Session, patient_rows: list[Patient]) -> list[dict]:
    """Detecta duplicados antiguos creados por importaciones de Confirmafy.

    Solo considera como eliminable un registro MUY conservador:
    - no tiene atenciones clínicas;
    - no tiene cédula, correo, nacimiento, lugar ni notas (el celular sí puede venir de Confirmafy);
    - o bien conserva citas y TODAS son CONFIRMAFY_IMPORTADO, o bien su fecha de creación
      cae dentro de una ventana de importación registrada en Audit;
    - existe exactamente un paciente establecido con coincidencia segura;
    - si ambos tienen celular, debe ser el mismo.

    Esto permite limpiar también huérfanos cuyo último Appointment importado ya fue
    purgado por la limpieza semanal, sin confundirlos con pacientes creados manualmente.
    Si no existe una coincidencia única, no se toca nada.
    """
    if not patient_rows:
        return []
    visit_counts = {
        int(pid): int(total or 0)
        for pid, total in db.execute(
            select(Visit.patient_id, func.count(Visit.id)).group_by(Visit.patient_id)
        ).all()
    }
    appointment_stats = {
        int(pid): (int(total or 0), int(imported or 0))
        for pid, total, imported in db.execute(
            select(
                Appointment.patient_id,
                func.count(Appointment.id),
                func.sum(case((Appointment.origen == "CONFIRMAFY_IMPORTADO", 1), else_=0)),
            ).group_by(Appointment.patient_id)
        ).all()
    }
    import_windows = _confirmafy_import_audit_windows(db)

    def created_during_confirmafy_import(p: Patient) -> bool:
        created = p.created_at
        if not created:
            return False
        return any(start <= created <= end for start, end in import_windows)

    def clearly_imported_only(p: Patient) -> bool:
        total, imported = appointment_stats.get(int(p.id), (0, 0))
        sparse = not any([p.cedula, p.fecha_nacimiento, p.correo, p.lugar, p.notas])
        source_proven = bool((total > 0 and imported == total) or (total == 0 and created_during_confirmafy_import(p)))
        return bool(
            visit_counts.get(int(p.id), 0) == 0
            and sparse
            and source_proven
        )

    imported_only = [p for p in patient_rows if clearly_imported_only(p)]
    imported_ids = {int(p.id) for p in imported_only}
    established = [p for p in patient_rows if int(p.id) not in imported_ids]
    plan = []

    for duplicate in imported_only:
        dup_phone = normalize_lookup_phone(duplicate.celular)
        dup_name = normalize_lookup_name(duplicate.nombre)

        # 1) Mismo celular, siempre que sea una coincidencia única.
        phone_matches = [
            p for p in established
            if dup_phone and normalize_lookup_phone(p.celular) == dup_phone
        ]
        keeper = phone_matches[0] if len(phone_matches) == 1 else None
        reason = "mismo celular" if keeper is not None else ""

        # 2) Nombre compatible único. También tolera una errata pequeña como
        # JHONNY/JHONY, pero únicamente para una ficha cuyo origen Confirmafy ya
        # fue demostrado y que no tiene historial clínico.
        if keeper is None and len(phone_matches) <= 1:
            name_matches = []
            for p in established:
                keeper_phone = normalize_lookup_phone(p.celular)
                if dup_phone and keeper_phone and dup_phone != keeper_phone:
                    continue
                score, why = patient_similarity(duplicate, p)
                if score >= 0.78:
                    name_matches.append((p, why))
            if len(name_matches) == 1:
                keeper = name_matches[0][0]
                reason = name_matches[0][1] or "nombre compatible único"

        if keeper is None:
            continue
        plan.append({
            "duplicate": duplicate,
            "keeper": keeper,
            "reason": reason,
            "duplicate_phone": dup_phone,
        })
    return plan


def _apply_confirmafy_legacy_duplicate_plan(db: Session, plan: list[dict]) -> dict:
    """Fusiona citas y borra únicamente el registro importado redundante."""
    if not plan:
        return {"cleaned": 0, "appointments_moved": 0, "appointments_removed": 0}
    duplicate_ids = [int(x["duplicate"].id) for x in plan]
    keeper_ids = [int(x["keeper"].id) for x in plan]
    relevant_ids = sorted(set(duplicate_ids + keeper_ids))
    appointments = list(db.scalars(select(Appointment).where(Appointment.patient_id.in_(relevant_ids))))
    by_patient: dict[int, list[Appointment]] = {}
    for appointment in appointments:
        by_patient.setdefault(int(appointment.patient_id), []).append(appointment)

    moved = removed = cleaned = 0
    for item in plan:
        duplicate = item["duplicate"]
        keeper = item["keeper"]
        dup_id, keeper_id = int(duplicate.id), int(keeper.id)
        keeper_keys = {(a.fecha, str(a.hora)) for a in by_patient.get(keeper_id, [])}
        duplicate_appointments = by_patient.get(dup_id, [])
        remove_ids = [int(a.id) for a in duplicate_appointments if (a.fecha, str(a.hora)) in keeper_keys]
        move_ids = [int(a.id) for a in duplicate_appointments if int(a.id) not in set(remove_ids)]

        if remove_ids:
            db.execute(delete(Appointment).where(Appointment.id.in_(remove_ids)))
            removed += len(remove_ids)
        if move_ids:
            db.execute(update(Appointment).where(Appointment.id.in_(move_ids)).values(patient_id=keeper_id))
            moved += len(move_ids)

        if not keeper.celular and duplicate.celular:
            keeper.celular = duplicate.celular
        db.execute(delete(Patient).where(Patient.id == dup_id))
        cleaned += 1
    db.flush()
    return {"cleaned": cleaned, "appointments_moved": moved, "appointments_removed": removed}


def seed_initial_agenda(session_factory):
    """Importa la agenda inicial sin crear pacientes automáticamente.

    v4.2.6: incluso en una instalación nueva, Confirmafy solo puede vincular
    citas a pacientes ya existentes. Los nombres parciales pueden coincidir si
    la coincidencia es única y no hay celulares contradictorios.
    """
    if session_factory is None or not os.path.exists(AGENDA_INITIAL_FILE):
        return {"imported": 0, "patients_created": 0, "skipped": True}
    try:
        with session_factory() as db:
            if db.scalar(select(Audit.id).where(Audit.action == AGENDA_SEED_ACTION).limit(1)):
                return {"imported": 0, "patients_created": 0, "skipped": True}

            patient_rows = list(db.scalars(select(Patient).order_by(Patient.id)))
            by_phone: dict[str, list[Patient]] = {}
            by_name: dict[str, list[Patient]] = {}
            for p in patient_rows:
                ph = normalize_lookup_phone(p.celular)
                nm = normalize_lookup_name(p.nombre)
                if ph:
                    by_phone.setdefault(ph, []).append(p)
                if nm:
                    by_name.setdefault(nm, []).append(p)

            def match_existing(name: str, phone: str):
                phone_matches = by_phone.get(phone, []) if phone else []
                if len(phone_matches) == 1:
                    return phone_matches[0]
                if len(phone_matches) > 1:
                    return None
                name_key = normalize_lookup_name(name)
                exact = by_name.get(name_key, []) if name_key else []
                if len(exact) == 1:
                    return exact[0]
                if len(exact) > 1:
                    return None
                fuzzy = []
                for p in patient_rows:
                    pp = normalize_lookup_phone(p.celular)
                    if phone and pp and phone != pp:
                        continue
                    if strong_name_overlap(name_key, p.nombre):
                        fuzzy.append(p)
                return fuzzy[0] if len(fuzzy) == 1 else None

            imported = skipped_unmatched = 0
            source_slots: dict[tuple[str, str], int] = {}
            with open(AGENDA_INITIAL_FILE, encoding="utf-8-sig", newline="") as f:
                rows = list(csv.DictReader(f))

            for row in rows:
                name = " ".join((row.get("name") or "").replace("\t", " ").split()).upper()
                phone = normalize_lookup_phone(row.get("phone"))
                if not name:
                    continue
                try:
                    fecha = date.fromisoformat(str(row.get("date") or "")[:10])
                except Exception:
                    continue
                hora = str(row.get("time") or "").strip()[:5]
                if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", hora):
                    continue

                p = match_existing(name, phone)
                if p is None:
                    skipped_unmatched += 1
                    continue
                if not p.celular and phone:
                    p.celular = phone
                    by_phone.setdefault(phone, []).append(p)

                exists = db.scalar(select(Appointment.id).where(
                    Appointment.patient_id == p.id,
                    Appointment.fecha == fecha,
                    Appointment.hora == hora,
                ).limit(1))
                if exists:
                    continue
                db.add(Appointment(
                    patient_id=p.id, fecha=fecha, hora=hora, duracion=20, nota=None,
                    estado="CARGADO", origen="CONFIRMAFY_IMPORTADO",
                    exported_at=datetime.utcnow(), loaded_at=datetime.utcnow(),
                ))
                imported += 1
                slot_key = (fecha.isoformat(), hora)
                source_slots[slot_key] = source_slots.get(slot_key, 0) + 1

            source_conflicts = sum(1 for n in source_slots.values() if n > 1)
            db.add(Audit(
                username="system", action=AGENDA_SEED_ACTION,
                detail=f"{imported} citas importadas, 0 pacientes creados, {skipped_unmatched} pacientes no identificados, {source_conflicts} conflicto(s)",
            ))
            db.commit()
            return {
                "imported": imported, "patients_created": 0,
                "unmatched": skipped_unmatched, "source_conflicts": source_conflicts,
                "skipped": False,
            }
    except Exception:
        return {"imported": 0, "patients_created": 0, "skipped": True}


def seed_database(session_factory):
    """Crea mínimos iniciales con pocas consultas (importante para Neon)."""
    if session_factory is None:
        return
    try:
        with session_factory() as db:
            # Antes se hacía una consulta por cada procedimiento. Ahora son dos
            # lecturas pequeñas en total: usuario existente + nombres existentes.
            if not db.scalar(select(User.id).limit(1)):
                db.add(User(username="admin", password_hash=hash_password("Cambiar123!"), role="admin"))
            quick_procedures = [
                ("FULGURACION", None),
                ("CISTOSCOPIA", None),
                ("DILATACION", None),
                ("CIRCUNSICION", None),
                ("INSTILACION", 80),
            ]
            names = [x[0] for x in quick_procedures]
            existing = set(db.scalars(select(Procedure.nombre).where(Procedure.nombre.in_(names))))
            for name, val in quick_procedures:
                if name not in existing:
                    db.add(Procedure(nombre=name, valor_default=val))
            db.commit()
    except Exception:
        pass


seed_database(LocalSessionLocal)
seed_initial_agenda(LocalSessionLocal)


def cloud_configured() -> bool:
    return cloud_engine is not None and CloudSessionLocal is not None


def _cloud_error_hint(error: object) -> str:
    """Mensaje corto y seguro para diagnóstico; nunca expone la cadena de conexión."""
    raw = str(error or "").lower()
    if "timeout" in raw or "timed out" in raw:
        return "Neon tardó demasiado en responder. Se volverá a intentar automáticamente."
    if "name or service not known" in raw or "getaddrinfo" in raw or "could not translate host" in raw:
        return "No se pudo resolver la dirección de Neon. Revisa Internet o DNS."
    if "password authentication failed" in raw or "authentication failed" in raw:
        return "Neon rechazó las credenciales de conexión. Hay que revisar la configuración de nube."
    if "connection refused" in raw:
        return "Neon rechazó temporalmente la conexión. Se volverá a intentar."
    if "network is unreachable" in raw or "no route to host" in raw:
        return "La PC no pudo llegar a Internet en ese momento."
    if "ssl" in raw:
        return "No se pudo establecer la conexión segura con Neon."
    return "No se pudo abrir la conexión con Neon. El programa seguirá usando la copia de emergencia."


def _raw_psycopg_url() -> str:
    """Devuelve una URL PostgreSQL limpia para la sonda directa de Neon."""
    url = CONFIGURED_DB_URL
    for prefix in ("postgresql+psycopg://", "postgresql+pg8000://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql://" + url[len(prefix):]
    return url


def _probe_cloud_direct() -> float:
    """Prueba Neon fuera del pool de SQLAlchemy.

    El diagnóstico en la PC mostró que una conexión nueva sí funciona, mientras
    que el pool interno podía quedarse en un estado lento. Esta sonda usa primero
    un TCP IPv4 corto y luego una conexión PostgreSQL real, sin tocar datos.
    Devuelve la latencia total en milisegundos.
    """
    started = time.perf_counter()
    raw_url = _raw_psycopg_url()
    parsed = urlparse(raw_url)
    host = parsed.hostname
    port = parsed.port or 5432

    if host:
        # Si realmente no hay Internet, no esperamos 12 s a PostgreSQL: esta
        # comprobación falla rápido. Preferimos IPv4 porque fue la ruta estable
        # observada por el diagnóstico de Windows.
        infos = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
        if not infos:
            raise OSError("No se encontró una dirección IPv4 para Neon")
        last_socket_error = None
        connected = False
        for family, socktype, proto, _canon, sockaddr in infos[:3]:
            try:
                with socket.socket(family, socktype, proto) as sock:
                    sock.settimeout(2.5)
                    sock.connect(sockaddr)
                connected = True
                break
            except OSError as exc:
                last_socket_error = exc
        if not connected:
            raise last_socket_error or OSError("No se pudo abrir TCP hacia Neon")

    # Conexión nueva e independiente del pool. SELECT 1 no modifica ningún dato.
    if _POSTGRES_DRIVER == "pg8000":
        parsed = urlparse(raw_url)
        database = unquote((parsed.path or "").lstrip("/"))
        if not parsed.hostname or not parsed.username or not database:
            raise RuntimeError("La URL de Neon está incompleta")
        conn = pg8000_dbapi.connect(
            user=unquote(parsed.username),
            password=unquote(parsed.password or ""),
            host=parsed.hostname,
            port=parsed.port or 5432,
            database=database,
            timeout=12,
            ssl_context=ssl.create_default_context(),
        )
        try:
            conn.autocommit = True
            cur = conn.cursor()
            try:
                cur.execute("SELECT 1")
                row = cur.fetchone()
            finally:
                cur.close()
        finally:
            conn.close()
    if not row or int(row[0]) != 1:
        raise RuntimeError("Neon no respondió correctamente a la prueba")
    return (time.perf_counter() - started) * 1000.0


def check_cloud(force: bool = False) -> bool:
    # En modo AFK no hacemos sondas ni SELECT 1. Conservamos el último estado
    # conocido hasta que el usuario vuelva o fuerce una comprobación manual.
    with _state_lock:
        if bool(_state.get("client_idle")) and not force:
            return bool(_state.get("online"))

    if not cloud_configured() or FORCE_OFFLINE:
        with _state_lock:
            _state["online"] = False
            _state["last_error"] = "Modo sin conexión forzado" if FORCE_OFFLINE else "Nube no configurada"
            _state["last_checked"] = time.time()
        return False

    requested_at = time.time()
    now = requested_at
    with _state_lock:
        interval = CLOUD_CHECK_SECONDS if bool(_state["online"]) else min(180.0, CLOUD_RETRY_SECONDS * (2 ** min(int(_state.get("consecutive_failures") or 0), 3)))
        if not force and now - float(_state["last_checked"] or 0) < interval:
            return bool(_state["online"])

    # Un solo hilo prueba Neon. La prueba de disponibilidad ya NO depende del
    # pool de SQLAlchemy; así una conexión vieja no puede declarar offline a toda
    # la aplicación cuando Neon en realidad está accesible.
    with _cloud_check_lock:
        now = time.time()
        with _state_lock:
            interval = CLOUD_CHECK_SECONDS if bool(_state["online"]) else min(180.0, CLOUD_RETRY_SECONDS * (2 ** min(int(_state.get("consecutive_failures") or 0), 3)))
            last_checked = float(_state["last_checked"] or 0)
            if not force and now - last_checked < interval:
                return bool(_state["online"])
            # Si otra petición forzada empezó la misma comprobación mientras esta
            # esperaba el lock, reutilizamos su resultado. Evita que arranque, UI
            # y botón de estado abran dos conexiones a Neon casi simultáneas.
            if force and last_checked >= requested_at:
                return bool(_state["online"])
            was_online = bool(_state["online"])
            old_failures = int(_state.get("consecutive_failures") or 0)

        attempts = 2 if force else 1
        last_exc = None
        for attempt in range(attempts):
            try:
                probe_ms = _probe_cloud_direct()

                # Si veníamos de un falso offline, descartamos conexiones antiguas
                # del pool para que la siguiente operación real abra una limpia.
                if not was_online or old_failures:
                    try:
                        cloud_engine.dispose()
                    except Exception:
                        pass

                success_at = time.time()
                with _state_lock:
                    _state["online"] = True
                    _state["last_error"] = ""
                    _state["last_checked"] = success_at
                    _state["last_success"] = success_at
                    _state["consecutive_failures"] = 0
                    _state["last_probe_ms"] = round(probe_ms)
                return True
            except Exception as e:
                last_exc = e
                try:
                    cloud_engine.dispose()
                except Exception:
                    pass
                if attempt + 1 < attempts:
                    time.sleep(0.45)

        failed_at = time.time()
        with _state_lock:
            _state["online"] = False
            _state["last_error"] = _cloud_error_hint(last_exc)
            _state["last_checked"] = failed_at
            _state["consecutive_failures"] = int(_state.get("consecutive_failures") or 0) + 1
            _state["last_probe_ms"] = None
        return False


def invalidate_queue_count():
    with _queue_count_lock:
        _queue_count_cache["value"] = None
        _queue_count_cache["ts"] = 0.0


def queue_count(db: Optional[Session] = None, force: bool = False) -> int:
    now = time.time()
    if db is None and not force:
        with _queue_count_lock:
            value = _queue_count_cache.get("value")
            ts = float(_queue_count_cache.get("ts") or 0)
            if value is not None and now - ts < QUEUE_COUNT_CACHE_SECONDS:
                return int(value)
    own = db is None
    if own:
        db = LocalSessionLocal()
    try:
        value = int(db.scalar(select(func.count(OfflineQueue.id))) or 0)
        if own:
            with _queue_count_lock:
                _queue_count_cache["value"] = value
                _queue_count_cache["ts"] = now
        return value
    finally:
        if own:
            db.close()


def queue_errors() -> list[str]:
    with LocalSessionLocal() as db:
        rows = list(db.scalars(select(OfflineQueue).where(OfflineQueue.last_error.is_not(None)).order_by(OfflineQueue.id).limit(5)))
        return [x.last_error or "" for x in rows if x.last_error]


def _queue_patient_from_payload(db: Session, q: OfflineQueue, payload: dict) -> Optional[Patient]:
    """Obtiene el paciente local asociado a un cambio sin exponer el payload completo."""
    try:
        patient_id = payload.get("patient_id")
        if patient_id is not None:
            p = db.get(Patient, int(patient_id))
            if p:
                return p
        if q.operation.startswith("patient."):
            pid = q.local_entity_id or payload.get("patient_id")
            return db.get(Patient, int(pid)) if pid is not None else None
        if q.operation.startswith("visit.") or q.operation.startswith("billing."):
            vid = q.local_entity_id or payload.get("visit_id")
            if vid is not None:
                v = db.get(Visit, int(vid))
                if v:
                    return db.get(Patient, int(v.patient_id))
        if q.operation.startswith("appointment."):
            aid = q.local_entity_id or payload.get("appointment_id")
            if aid is not None:
                a = db.get(Appointment, int(aid))
                if a:
                    return db.get(Patient, int(a.patient_id))
    except Exception:
        return None
    return None


def queue_review_items() -> list[dict]:
    """Lista segura y legible de cambios offline pendientes para revisión humana."""
    labels = {
        "patient.create": "Paciente creado",
        "patient.update": "Paciente editado",
        "patient.delete": "Paciente eliminado",
        "visit.create": "Atención registrada",
        "visit.delete": "Atención eliminada",
        "appointment.create": "Cita creada",
        "appointment.update": "Cita reagendada",
        "appointment.export": "Cita exportada",
        "appointment.loaded": "Cita cargada en Confirmafy",
        "appointment.pending": "Cita devuelta a pendiente",
        "appointment.delete": "Cita eliminada",
        "billing.approve": "Factura aprobada",
        "billing.pending": "Factura devuelta a pendiente",
        "billing.emit": "Factura marcada emitida",
        "procedure.update": "Procedimiento actualizado",
    }
    with LocalSessionLocal() as db:
        rows = list(db.scalars(select(OfflineQueue).order_by(OfflineQueue.id.asc())))
        blocked = False
        out = []
        for q in rows:
            try:
                payload = json.loads(q.payload or "{}")
            except Exception:
                payload = {}
            patient = _queue_patient_from_payload(db, q, payload)
            name = patient.nombre if patient else ""
            title = labels.get(q.operation, q.operation.replace(".", " ").title())
            section = "config"
            detail_parts = []
            if name:
                detail_parts.append(name)
            if q.operation.startswith("appointment."):
                section = "agenda"
                fecha = payload.get("fecha")
                hora = payload.get("hora")
                if not fecha and q.local_entity_id:
                    a = db.get(Appointment, int(q.local_entity_id))
                    if a:
                        fecha, hora = a.fecha, a.hora
                if fecha:
                    try:
                        detail_parts.append(date.fromisoformat(str(fecha)[:10]).strftime("%d/%m/%Y"))
                    except Exception:
                        detail_parts.append(str(fecha)[:10])
                if hora:
                    detail_parts.append(str(hora)[:5])
            elif q.operation.startswith("visit."):
                section = "home"
                fecha = payload.get("fecha")
                if fecha:
                    try:
                        detail_parts.append(date.fromisoformat(str(fecha)[:10]).strftime("%d/%m/%Y"))
                    except Exception:
                        detail_parts.append(str(fecha)[:10])
                proc = payload.get("procedimiento")
                detail_parts.append(proc or "Consulta")
            elif q.operation.startswith("billing."):
                section = "facturacion"
            elif q.operation.startswith("patient."):
                section = "patients"
            elif q.operation.startswith("procedure."):
                section = "config"
                proc_id = payload.get("procedure_id")
                if proc_id:
                    proc = db.get(Procedure, int(proc_id))
                    if proc:
                        detail_parts.append(proc.nombre)

            has_error = bool((q.last_error or "").strip())
            status = "REVIEW" if has_error else ("WAITING" if blocked else "PENDING")
            if has_error:
                blocked = True
            out.append({
                "id": q.id,
                "operation": q.operation,
                "title": title,
                "detail": " · ".join(x for x in detail_parts if x),
                "created_at": q.created_at.isoformat(timespec="seconds") if q.created_at else None,
                "status": status,
                "error": (q.last_error or "")[:500] if has_error else "",
                "section": section,
            })
        return out


def cache_meta_set(db: Session, key: str, value: str):
    row = db.get(CacheMeta, key)
    if row:
        row.value = value
    else:
        db.add(CacheMeta(key=key, value=value))


def cache_meta_get(key: str, default: Optional[str] = None) -> Optional[str]:
    try:
        with LocalSessionLocal() as db:
            row = db.get(CacheMeta, key)
            return row.value if row and row.value is not None else default
    except Exception:
        return default


def persisted_cache_refresh_ts() -> float:
    raw = cache_meta_get("last_sync")
    if not raw:
        return 0.0
    try:
        return datetime.fromisoformat(str(raw)).timestamp()
    except Exception:
        return 0.0


def effective_cache_refresh_ts() -> float:
    with _state_lock:
        memory_ts = float(_state.get("last_cache_refresh") or 0)
    if memory_ts:
        return memory_ts
    persisted = persisted_cache_refresh_ts()
    if persisted:
        with _state_lock:
            _state["last_cache_refresh"] = persisted
    return persisted


def create_local_backup_snapshot(force: bool = False) -> Optional[str]:
    """Crea una copia SQLite consistente del cache de emergencia sin frenar la recepción."""
    try:
        if not os.path.exists(OFFLINE_DB_PATH):
            return None
        os.makedirs(BACKUP_DIR, exist_ok=True)
        existing = sorted(Path(BACKUP_DIR).glob("recepcion_backup_*.db"), key=lambda x: x.stat().st_mtime, reverse=True)
        if existing and not force and time.time() - existing[0].stat().st_mtime < 6 * 60 * 60:
            return str(existing[0])
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = Path(BACKUP_DIR) / f"recepcion_backup_{stamp}.db"
        with sqlite3.connect(OFFLINE_DB_PATH, timeout=10) as src, sqlite3.connect(dest, timeout=10) as dst:
            src.backup(dst)
        # Conservamos las 10 copias locales más recientes.
        existing = sorted(Path(BACKUP_DIR).glob("recepcion_backup_*.db"), key=lambda x: x.stat().st_mtime, reverse=True)
        for old in existing[10:]:
            try:
                old.unlink()
            except Exception:
                pass
        with LocalSessionLocal() as ldb:
            cache_meta_set(ldb, "last_backup", datetime.now().isoformat(timespec="seconds"))
            ldb.commit()
        return str(dest)
    except Exception as e:
        with _state_lock:
            _state["last_error"] = f"No se pudo crear respaldo local: {e}"[:300]
        return None


def _cleanup_expired_confirmafy_appointments(cdb: Session, ldb: Session) -> dict:
    """Borra de Agenda todas las citas de semanas ya terminadas.

    v4.3.46: una cita cancelada se conserva visible durante toda su semana para
    que recepción mantenga el rastro visual. Al comenzar una semana nueva se
    eliminan de Agenda todas las citas anteriores (incluidas canceladas,
    reagendadas, importadas y marcadores internos), además de las filas externas
    ya vencidas. Nunca toca pacientes, atenciones ni facturación.

    La limpieza se ejecuta como máximo una vez por día y solo dentro de una
    actualización de caché que ya iba a abrir Neon, por lo que no agrega
    conexiones de fondo.
    """
    today = date.today()
    marker_key = "last_agenda_week_cleanup_v446"
    marker = ldb.get(CacheMeta, marker_key)
    if marker and str(marker.value or "") == today.isoformat():
        return {"deleted": 0, "skipped": True}
    week_start = today - timedelta(days=today.weekday())
    result = cdb.execute(
        delete(Appointment).where(Appointment.fecha < week_start)
    )
    staged_result = cdb.execute(
        delete(ConfirmafyAgendaItem).where(ConfirmafyAgendaItem.fecha < week_start)
    )
    deleted = int(getattr(result, "rowcount", 0) or 0) + int(getattr(staged_result, "rowcount", 0) or 0)
    cdb.commit()
    if marker:
        marker.value = today.isoformat()
    else:
        ldb.add(CacheMeta(key=marker_key, value=today.isoformat()))
    # El commit local se hace junto con la nueva copia al final de refresh_local_cache.
    return {"deleted": deleted, "skipped": False, "cutoff": week_start.isoformat()}


def refresh_local_cache(force: bool = False, cloud_already_checked: bool = False) -> bool:
    """Copia la nube al cache local sin bloquear las peticiones normales.

    ``cloud_already_checked`` evita una segunda sonda a Neon cuando el llamador
    acaba de comprobar la conexión (arranque, regreso de AFK o sincronización).
    """
    if not cloud_configured() or (not cloud_already_checked and not check_cloud(force=force)):
        return False
    if queue_count() > 0:
        return False

    last_refresh = effective_cache_refresh_ts()
    if not force and last_refresh and time.time() - last_refresh < CACHE_REFRESH_SECONDS:
        return True

    # Solo una actualización de cache a la vez. Antes se mantenía _state_lock
    # durante toda la copia de tablas, pudiendo frenar la interfaz.
    if not _cache_refresh_lock.acquire(blocking=False):
        return True
    try:
        with CloudSessionLocal() as cdb, LocalSessionLocal() as ldb:
            # v4.3.2: una sola pasada de saneamiento después de actualizar. Se hace
            # dentro de la misma conexión usada para refrescar la copia local, por
            # lo que no añade consultas periódicas a Neon.
            legacy_marker_key = "confirmafy_legacy_cleanup_v434"
            legacy_marker = ldb.get(CacheMeta, legacy_marker_key)
            legacy_result = {"cleaned": 0, "appointments_moved": 0, "appointments_removed": 0}
            if not legacy_marker or str(legacy_marker.value or "") != "done":
                legacy_patients = list(cdb.scalars(select(Patient).order_by(Patient.id)))
                legacy_plan = _confirmafy_legacy_duplicate_plan(cdb, legacy_patients)
                if legacy_plan:
                    legacy_result = _apply_confirmafy_legacy_duplicate_plan(cdb, legacy_plan)
                    cdb.commit()
                if legacy_marker:
                    legacy_marker.value = "done"
                else:
                    ldb.add(CacheMeta(key=legacy_marker_key, value="done"))

            cleanup_result = _cleanup_expired_confirmafy_appointments(cdb, ldb)
            patients = list(cdb.scalars(select(Patient).order_by(Patient.id)))
            visits = list(cdb.scalars(select(Visit).order_by(Visit.id)))
            procedures = list(cdb.scalars(select(Procedure).order_by(Procedure.id)))
            users = list(cdb.scalars(select(User).order_by(User.id)))
            billing_records = list(cdb.scalars(select(BillingRecord).order_by(BillingRecord.id)))
            azur_emissions = list(cdb.scalars(select(AzurEmission).order_by(AzurEmission.id)))
            billing_preferences = list(cdb.scalars(select(BillingPreference).order_by(BillingPreference.id)))
            appointments = list(cdb.scalars(select(Appointment).order_by(Appointment.id)))
            confirmafy_agenda_items = list(cdb.scalars(select(ConfirmafyAgendaItem).order_by(ConfirmafyAgendaItem.id)))

            # Una sola transacción local: los lectores siguen viendo la copia
            # anterior hasta que la nueva queda completa.
            ldb.execute(delete(ConfirmafyAgendaItem))
            ldb.execute(delete(Appointment))
            ldb.execute(delete(BillingPreference))
            ldb.execute(delete(AzurEmission))
            ldb.execute(delete(BillingRecord))
            ldb.execute(delete(Visit))
            ldb.execute(delete(Patient))
            ldb.execute(delete(Procedure))
            ldb.execute(delete(User))
            ldb.execute(delete(SyncOperation))
            ldb.flush()

            ldb.add_all([Patient(
                id=p.id, cedula=p.cedula, nombre=p.nombre, fecha_nacimiento=p.fecha_nacimiento,
                celular=p.celular, correo=p.correo, lugar=p.lugar, notas=p.notas, created_at=p.created_at,
            ) for p in patients])
            ldb.flush()
            ldb.add_all([Visit(
                id=v.id, patient_id=v.patient_id, fecha=v.fecha, tipo=v.tipo,
                procedimiento=v.procedimiento, valor=v.valor, observacion=v.observacion,
                source_row=v.source_row, created_at=v.created_at,
            ) for v in visits])
            ldb.add_all([Procedure(id=p.id, nombre=p.nombre, valor_default=p.valor_default, activo=p.activo) for p in procedures])
            ldb.add_all([User(id=u.id, username=u.username, password_hash=u.password_hash, role=u.role) for u in users])
            ldb.add_all([BillingRecord(
                id=b.id, visit_id=b.visit_id, estado=b.estado, numero_factura=b.numero_factura,
                approved_at=b.approved_at, emitted_at=b.emitted_at, created_at=b.created_at,
            ) for b in billing_records])
            ldb.add_all([AzurEmission(
                id=x.id, group_key=x.group_key, patient_id=x.patient_id, fecha=x.fecha,
                estado=x.estado, clave_acceso=x.clave_acceso, numero_factura=x.numero_factura,
                request_hash=x.request_hash, response_json=x.response_json,
                created_at=x.created_at, updated_at=x.updated_at,
            ) for x in azur_emissions])
            ldb.add_all([BillingPreference(
                id=x.id, patient_id=x.patient_id, enabled=x.enabled, identificacion=x.identificacion,
                nombre=x.nombre, direccion=x.direccion, telefono=x.telefono, correo=x.correo,
                updated_at=x.updated_at,
            ) for x in billing_preferences])
            ldb.add_all([Appointment(
                id=a.id, patient_id=a.patient_id, fecha=a.fecha, hora=a.hora, duracion=a.duracion,
                nota=a.nota, estado=a.estado, origen=a.origen, exported_at=a.exported_at,
                loaded_at=a.loaded_at, created_at=a.created_at, updated_at=a.updated_at,
            ) for a in appointments])
            ldb.add_all([ConfirmafyAgendaItem(
                id=a.id, nombre=a.nombre, celular=a.celular, fecha=a.fecha, hora=a.hora,
                duracion=a.duracion, source_hash=a.source_hash, created_at=a.created_at,
            ) for a in confirmafy_agenda_items])
            _sync_stamp = datetime.now().isoformat(timespec="seconds")
            cache_meta_set(ldb, "last_sync", _sync_stamp)
            cache_meta_set(ldb, "last_agenda_sync", _sync_stamp)
            ldb.commit()

        # El respaldo se hace después de terminar la copia local, fuera de la transacción.
        create_local_backup_snapshot(force=False)

        with _state_lock:
            _state["last_cache_refresh"] = time.time()
        return True
    except Exception as e:
        with _state_lock:
            _state["last_error"] = f"No se pudo actualizar cache local: {e}"[:300]
        return False
    finally:
        _cache_refresh_lock.release()



def effective_agenda_refresh_ts() -> float:
    raw = cache_meta_get("last_agenda_sync") or cache_meta_get("last_sync")
    if not raw:
        return 0.0
    try:
        return datetime.fromisoformat(str(raw)).timestamp()
    except Exception:
        return 0.0


def refresh_remote_agenda_cache(force: bool = False, cloud_already_checked: bool = False) -> bool:
    """Trae únicamente Agenda desde Neon; el resto de Recepción permanece local.

    Se usa al arrancar o volver de una pausa larga cuando la copia completa todavía
    es reciente. Así incorporamos autoagendadas/reagendamientos/confirmaciones sin
    releer pacientes, visitas y facturación completas.
    """
    if not cloud_configured() or FORCE_OFFLINE or queue_count() > 0:
        return False
    last_refresh = effective_agenda_refresh_ts()
    if not force and last_refresh and time.time() - last_refresh < AGENDA_CACHE_REFRESH_SECONDS:
        return True
    if not cloud_already_checked and not check_cloud(force=False):
        return False
    if not _cache_refresh_lock.acquire(blocking=False):
        return True
    try:
        week_start = date.today() - timedelta(days=date.today().weekday())
        with CloudSessionLocal() as cdb, LocalSessionLocal() as ldb:
            appointments = list(cdb.scalars(
                select(Appointment)
                .where(Appointment.fecha >= week_start)
                .order_by(Appointment.id)
            ))
            staged = list(cdb.scalars(
                select(ConfirmafyAgendaItem)
                .where(ConfirmafyAgendaItem.fecha >= week_start)
                .order_by(ConfirmafyAgendaItem.id)
            ))

            # Cola vacía = no existen cambios locales sin subir que podamos pisar.
            ldb.execute(delete(Appointment).where(Appointment.fecha >= week_start))
            ldb.execute(delete(ConfirmafyAgendaItem).where(ConfirmafyAgendaItem.fecha >= week_start))
            ldb.flush()
            ldb.add_all([Appointment(
                id=a.id, patient_id=a.patient_id, fecha=a.fecha, hora=a.hora,
                duracion=a.duracion, nota=a.nota, estado=a.estado, origen=a.origen,
                exported_at=a.exported_at, loaded_at=a.loaded_at,
                created_at=a.created_at, updated_at=a.updated_at,
            ) for a in appointments])
            ldb.add_all([ConfirmafyAgendaItem(
                id=a.id, nombre=a.nombre, celular=a.celular, fecha=a.fecha,
                hora=a.hora, duracion=a.duracion, source_hash=a.source_hash,
                created_at=a.created_at,
            ) for a in staged])
            cache_meta_set(ldb, "last_agenda_sync", datetime.now().isoformat(timespec="seconds"))
            ldb.commit()
        now = time.time()
        with _state_lock:
            _state["online"] = True
            _state["last_success"] = now
            _state["last_checked"] = now
            _state["consecutive_failures"] = 0
            _state["last_error"] = ""
        return True
    except Exception as e:
        with _state_lock:
            _state["last_error"] = f"No se pudo actualizar Agenda desde la nube: {e}"[:300]
        return False
    finally:
        _cache_refresh_lock.release()


def schedule_remote_agenda_refresh(force: bool = False, cloud_already_checked: bool = False) -> bool:
    """Agenda remota bajo demanda; nunca crea un temporizador contra Neon."""
    if not cloud_configured() or FORCE_OFFLINE or queue_count() > 0:
        return False
    last_refresh = effective_agenda_refresh_ts()
    due = force or not last_refresh or (time.time() - last_refresh >= AGENDA_CACHE_REFRESH_SECONDS)
    if not due or _cache_refresh_lock.locked():
        return False
    threading.Thread(
        target=refresh_remote_agenda_cache,
        kwargs={"force": force, "cloud_already_checked": cloud_already_checked},
        daemon=True,
        name="rp-agenda-refresh",
    ).start()
    return True


def schedule_local_cache_refresh(force: bool = False, cloud_already_checked: bool = False) -> bool:
    """Lanza la copia de emergencia en segundo plano si ya corresponde."""
    if not cloud_configured() or FORCE_OFFLINE or queue_count() > 0:
        return False
    last_refresh = effective_cache_refresh_ts()
    due = force or not last_refresh or (time.time() - last_refresh >= CACHE_REFRESH_SECONDS)
    if not due or _cache_refresh_lock.locked():
        return False
    threading.Thread(target=refresh_local_cache, kwargs={"force": force, "cloud_already_checked": cloud_already_checked}, daemon=True, name="rp-cache-refresh").start()
    return True


def ensure_performance_indexes(engine):
    if engine is None:
        return
    statements = [
        "CREATE INDEX IF NOT EXISTS ix_visits_fecha_id ON visits (fecha, id)",
        "CREATE INDEX IF NOT EXISTS ix_visits_patient_fecha ON visits (patient_id, fecha)",
        "CREATE INDEX IF NOT EXISTS ix_appointments_fecha_hora ON appointments (fecha, hora)",
        "CREATE INDEX IF NOT EXISTS ix_appointments_estado_fecha ON appointments (estado, fecha)",
        "CREATE INDEX IF NOT EXISTS ix_confirmafy_agenda_fecha_hora ON confirmafy_agenda_items (fecha, hora)",
        "CREATE INDEX IF NOT EXISTS ix_billing_estado_visit ON billing_records (estado, visit_id)",
        "CREATE INDEX IF NOT EXISTS ix_visits_fecha_patient_id ON visits (fecha, patient_id, id)",
    ]
    try:
        with engine.begin() as conn:
            for stmt in statements:
                conn.execute(text(stmt))
    except Exception:
        pass


LOCAL_PERF_MARKER = "local_performance_ready_v4_3_14"


def optimize_local_sqlite_once() -> None:
    """Pide a SQLite optimizar estadísticas/índices sin VACUUM ni bloqueos largos."""
    try:
        with local_engine.begin() as conn:
            conn.exec_driver_sql("PRAGMA analysis_limit=400")
            conn.exec_driver_sql("PRAGMA optimize")
    except Exception:
        pass


def ensure_local_performance_ready() -> None:
    """Crea índices nuevos una sola vez por versión, no en cada arranque."""
    try:
        with LocalSessionLocal() as ldb:
            marker = ldb.get(CacheMeta, LOCAL_PERF_MARKER)
            if marker and str(marker.value or "") == "1":
                return
        ensure_performance_indexes(local_engine)
        optimize_local_sqlite_once()
        with LocalSessionLocal() as ldb:
            marker = ldb.get(CacheMeta, LOCAL_PERF_MARKER)
            if marker:
                marker.value = "1"
            else:
                ldb.add(CacheMeta(key=LOCAL_PERF_MARKER, value="1"))
            ldb.commit()
    except Exception:
        # Si algo falla, el próximo inicio vuelve a intentarlo; la app sigue usable.
        pass


def ensure_cloud_initialized() -> bool:
    """Prepara tablas/índices una sola vez por revisión para ahorrar consultas."""
    global _cloud_initialized
    if _cloud_initialized:
        return True
    with _cloud_init_lock:
        if _cloud_initialized:
            return True
        if cache_meta_get(CLOUD_SCHEMA_MARKER) == "1":
            _cloud_initialized = True
            return True
        try:
            Base.metadata.create_all(cloud_engine)
            ensure_performance_indexes(cloud_engine)
            seed_database(CloudSessionLocal)
            seed_initial_agenda(CloudSessionLocal)
            with LocalSessionLocal() as ldb:
                cache_meta_set(ldb, CLOUD_SCHEMA_MARKER, "1")
                ldb.commit()
            _cloud_initialized = True
            return True
        except Exception as e:
            with _state_lock:
                _state["last_error"] = _cloud_error_hint(e)
            return False


def initialize_cloud_if_possible():
    if not check_cloud(force=True):
        return
    try:
        if not ensure_cloud_initialized():
            return
        # Reutiliza la copia local si sigue reciente. v4.3.2 fuerza UNA sola
        # actualización tras instalarse para ejecutar el saneamiento de duplicados
        # heredados; después vuelve al comportamiento normal y liviano.
        with LocalSessionLocal() as ldb:
            cleanup_marker = ldb.get(CacheMeta, "confirmafy_legacy_cleanup_v434")
            force_cleanup_refresh = not cleanup_marker or str(cleanup_marker.value or "") != "done"
        full_scheduled = schedule_local_cache_refresh(force=force_cleanup_refresh, cloud_already_checked=True)
        if not full_scheduled:
            schedule_remote_agenda_refresh(force=False, cloud_already_checked=True)
    except Exception as e:
        with _state_lock:
            _state["last_error"] = _cloud_error_hint(e)


def prepare_desktop_runtime_background():
    """Prepara WebView2/pywebview una sola vez sin frenar el servidor.

    Cuando la aplicación fue arrancada por ABRIR_RECEPCION.py, el propio
    lanzador hace esta preparación antes de abrir la ventana y evitamos duplicar
    el trabajo. Tras actualizar desde una versión antigua, este proceso sí se
    ejecuta para dejar listo el siguiente inicio.
    """
    if os.name != "nt" or (os.getenv("RP_DESKTOP_LAUNCH") or "").strip() == "1":
        return
    helper = os.path.join(BASE_DIR, "PREPARAR_ESCRITORIO.py")
    if not os.path.exists(helper):
        return
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
        subprocess.Popen(
            [sys.executable, helper, "--background"],
            cwd=BASE_DIR,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=flags, close_fds=True,
        )
    except Exception:
        pass


ensure_local_performance_ready()
# La UI local tiene prioridad al arrancar. En una PC lenta dejamos que FastAPI y
# WebView2 terminen de abrir antes de iniciar el único chequeo de nube de arranque.
def _deferred_cloud_init():
    time.sleep(1.0)
    initialize_cloud_if_possible()


if cloud_configured() and not FORCE_OFFLINE:
    threading.Thread(target=_deferred_cloud_init, daemon=True, name="rp-cloud-init").start()
prepare_desktop_runtime_background()


# ---------------------------------------------------------------------------
# WhatsApp / Meta Cloud API - cola local y automatización de citas
# ---------------------------------------------------------------------------

_WA_WEEKDAYS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
_WA_MONTHS = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre")
_whatsapp_worker_lock = threading.Lock()
_whatsapp_worker_started = False


def whatsapp_date_label(value: date) -> str:
    return f"{_WA_WEEKDAYS[value.weekday()]} {value.day} de {_WA_MONTHS[value.month - 1]} de {value.year}"


def whatsapp_time_label(value: str) -> str:
    hh, mm = [int(x) for x in str(value or "00:00")[:5].split(":")]
    return f"{(hh % 12) or 12}:{mm:02d} {'PM' if hh >= 12 else 'AM'}"


def whatsapp_recordatorio_datetime_label(fecha: date, hora: str) -> str:
    """Texto exacto para {{2}} de recordatorio_cita aprobado por Meta.

    Ejemplo: martes, 25 de agosto de 2026 a las 1:00 p. m.
    """
    hh, mm = [int(x) for x in str(hora or "00:00")[:5].split(":")]
    period = "p. m." if hh >= 12 else "a. m."
    return (
        f"{_WA_WEEKDAYS[fecha.weekday()]}, {fecha.day} de {_WA_MONTHS[fecha.month - 1]} "
        f"de {fecha.year} a las {(hh % 12) or 12}:{mm:02d} {period}"
    )


def whatsapp_recordatorio_template_name() -> str:
    return WHATSAPP_TEMPLATE_RECORDATORIO_CITA_LOGO if WHATSAPP_RECORDATORIO_CITA_LOGO_ENABLED else WHATSAPP_TEMPLATE_RECORDATORIO_CITA


def whatsapp_language_for_template(template_name: str) -> str:
    name = str(template_name or "")
    if name in (WHATSAPP_TEMPLATE_RECORDATORIO_CITA, WHATSAPP_TEMPLATE_RECORDATORIO_CITA_LOGO):
        return WHATSAPP_LANGUAGE_RECORDATORIO_CITA
    if name == WHATSAPP_TEMPLATE_CITA_AGENDADA:
        return WHATSAPP_LANGUAGE_CITA_AGENDADA
    if name == WHATSAPP_TEMPLATE_RECORDATORIO_HOY:
        return WHATSAPP_LANGUAGE_RECORDATORIO_HOY
    return WHATSAPP_TEMPLATE_LANGUAGE


def whatsapp_template_enabled(template_name: str) -> bool:
    name = str(template_name or "")
    if name in (WHATSAPP_TEMPLATE_RECORDATORIO_CITA, WHATSAPP_TEMPLATE_RECORDATORIO_CITA_LOGO):
        return WHATSAPP_AUTO_RECORDATORIO_CITA
    if name == WHATSAPP_TEMPLATE_CITA_AGENDADA:
        return WHATSAPP_AUTO_CITA_AGENDADA
    if name == WHATSAPP_TEMPLATE_RECORDATORIO_HOY:
        return WHATSAPP_AUTO_RECORDATORIO_HOY
    return False


def whatsapp_enabled_template_names() -> list[str]:
    names = []
    for name in (WHATSAPP_TEMPLATE_CITA_AGENDADA, whatsapp_recordatorio_template_name(), WHATSAPP_TEMPLATE_RECORDATORIO_HOY):
        if whatsapp_template_enabled(name) and name not in names:
            names.append(name)
    return names


def whatsapp_ready() -> tuple[bool, list[str]]:
    missing = []
    if not WHATSAPP_GRAPH_VERSION: missing.append("WHATSAPP_GRAPH_VERSION")
    if not WHATSAPP_PHONE_NUMBER_ID: missing.append("WHATSAPP_PHONE_NUMBER_ID")
    if not WHATSAPP_ACCESS_TOKEN: missing.append("WHATSAPP_ACCESS_TOKEN")
    # Solo exigimos imagen si alguna plantilla ACTIVA realmente la necesita.
    image_needed = WHATSAPP_AUTO_CITA_AGENDADA or WHATSAPP_AUTO_RECORDATORIO_HOY or (WHATSAPP_AUTO_RECORDATORIO_CITA and WHATSAPP_RECORDATORIO_CITA_LOGO_ENABLED)
    if image_needed and not WHATSAPP_HEADER_IMAGE_ID:
        missing.append("WHATSAPP_HEADER_IMAGE_ID")
    return not missing, missing


def _whatsapp_event_key(source_type: str, source_id: int, template_name: str, fecha: date, hora: str) -> str:
    raw = f"{source_type}|{source_id}|{template_name}|{fecha.isoformat()}|{hora}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _whatsapp_cancel_pending(source_type: str, source_id: int) -> None:
    try:
        with LocalSessionLocal() as db:
            rows = list(db.scalars(select(WhatsAppOutbox).where(
                WhatsAppOutbox.source_type == source_type,
                WhatsAppOutbox.source_id == int(source_id),
                WhatsAppOutbox.status.in_(["PENDING", "ERROR"]),
            )))
            now = datetime.now()
            for row in rows:
                row.status = "CANCELLED"
                row.updated_at = now
            if rows:
                db.commit()
    except Exception:
        pass


def _whatsapp_queue_one(*, source_type: str, source_id: int, phone: str, template_name: str,
                        fecha: date, hora: str, due_at: datetime, body_params: list[str],
                        header_required: bool = False, quick_reply_payloads: Optional[list[str]] = None) -> bool:
    normalized_phone = confirmafy_phone(phone)
    if len(normalized_phone) < 8 or len(normalized_phone) > 15:
        return False
    key = _whatsapp_event_key(source_type, source_id, template_name, fecha, hora)
    payload = {
        "body_params": body_params,
        "header_required": bool(header_required),
        "quick_reply_payloads": quick_reply_payloads or [],
        "appointment_date": fecha.isoformat(),
        "appointment_time": hora,
        "original_due_at": due_at.isoformat(),
    }
    try:
        with LocalSessionLocal() as db:
            existing = db.scalar(select(WhatsAppOutbox).where(WhatsAppOutbox.event_key == key))
            if existing:
                return False
            db.add(WhatsAppOutbox(
                event_key=key, template_name=template_name, source_type=source_type,
                source_id=int(source_id), phone=normalized_phone,
                payload_json=json.dumps(payload, ensure_ascii=False), status="PENDING", due_at=due_at,
            ))
            db.commit()
        return True
    except IntegrityError:
        return False
    except Exception:
        return False


def schedule_whatsapp_for_contact(*, source_type: str, source_id: int, name: str, phone: str,
                                  fecha: date, hora: str) -> dict:
    """Prepara los tres mensajes. No hace ninguna llamada a Meta por sí sola."""
    now = datetime.now()
    try:
        hh, mm = [int(x) for x in hora.split(":")]
        appointment_at = datetime(fecha.year, fecha.month, fecha.day, hh, mm)
    except Exception:
        return {"queued": 0, "reason": "invalid_datetime"}
    if appointment_at <= now:
        _whatsapp_cancel_pending(source_type, source_id)
        return {"queued": 0, "reason": "past_appointment"}

    _whatsapp_cancel_pending(source_type, source_id)
    clean_name = " ".join(str(name or "").split()).upper()
    date_text = whatsapp_date_label(fecha)
    time_text = whatsapp_time_label(hora)
    queued = 0

    # 1) Inmediato al crear/reagendar. Lleva logo + nombre + fecha + hora.
    queued += int(_whatsapp_queue_one(
        source_type=source_type, source_id=source_id, phone=phone,
        template_name=WHATSAPP_TEMPLATE_CITA_AGENDADA, fecha=fecha, hora=hora, due_at=now,
        body_params=[clean_name, date_text, time_text], header_required=True,
    ))

    # 2) Confirmación previa: a las 08:00 AM del día anterior a la cita.
    # Plantilla aprobada por Meta `recordatorio_cita`:
    #   {{1}} nombre
    #   {{2}} fecha + hora en un solo texto
    # Los botones visibles son Sí / No; los payloads internos siguen siendo
    # CONFIRMAR / CANCELAR para que el webhook pueda distinguir la acción.
    previous_hh, previous_mm = [int(x) for x in WHATSAPP_PREVIOUS_DAY_TIME.split(":")]
    previous_date = fecha - timedelta(days=1)
    reminder_at = datetime(previous_date.year, previous_date.month, previous_date.day, previous_hh, previous_mm)
    if reminder_at > now:
        yes_payload = f"CONFIRMAR|{source_type}|{source_id}|{fecha.isoformat()}|{hora}"
        no_payload = f"CANCELAR|{source_type}|{source_id}|{fecha.isoformat()}|{hora}"
        queued += int(_whatsapp_queue_one(
            source_type=source_type, source_id=source_id, phone=phone,
            template_name=whatsapp_recordatorio_template_name(), fecha=fecha, hora=hora, due_at=reminder_at,
            body_params=[clean_name, whatsapp_recordatorio_datetime_label(fecha, hora)],
            header_required=WHATSAPP_RECORDATORIO_CITA_LOGO_ENABLED,
            quick_reply_payloads=[yes_payload, no_payload],
        ))

    # 3) Recordatorio final: exactamente 2 horas antes de la cita por defecto.
    today_at = appointment_at - timedelta(hours=WHATSAPP_TODAY_HOURS_BEFORE)
    if now < today_at < appointment_at:
        queued += int(_whatsapp_queue_one(
            source_type=source_type, source_id=source_id, phone=phone,
            template_name=WHATSAPP_TEMPLATE_RECORDATORIO_HOY, fecha=fecha, hora=hora, due_at=today_at,
            body_params=[clean_name, time_text], header_required=True,
        ))
    return {"queued": queued}


def _whatsapp_rebase_pending_schedule() -> int:
    """Recalcula recordatorios pendientes creados por versiones anteriores."""
    changed = 0
    try:
        with LocalSessionLocal() as db:
            rows = list(db.scalars(select(WhatsAppOutbox).where(
                WhatsAppOutbox.status.in_(["PENDING", "ERROR"]),
                WhatsAppOutbox.template_name.in_([WHATSAPP_TEMPLATE_RECORDATORIO_CITA, WHATSAPP_TEMPLATE_RECORDATORIO_CITA_LOGO, WHATSAPP_TEMPLATE_RECORDATORIO_HOY]),
            )))
            for row in rows:
                try:
                    payload = json.loads(row.payload_json or "{}")
                    fecha = date.fromisoformat(str(payload.get("appointment_date")))
                    hh, mm = [int(x) for x in str(payload.get("appointment_time")).split(":")]
                    appointment_at = datetime(fecha.year, fecha.month, fecha.day, hh, mm)
                    payload_changed = False
                    if row.template_name in (WHATSAPP_TEMPLATE_RECORDATORIO_CITA, WHATSAPP_TEMPLATE_RECORDATORIO_CITA_LOGO):
                        ph, pm = [int(x) for x in WHATSAPP_PREVIOUS_DAY_TIME.split(":")]
                        previous_date = fecha - timedelta(days=1)
                        target = datetime(previous_date.year, previous_date.month, previous_date.day, ph, pm)

                        # v4.3.35: convertir también filas pendientes creadas por versiones
                        # anteriores (3 variables) al formato aprobado de 2 variables.
                        old_params = list(payload.get("body_params") or [])
                        patient_name = str(old_params[0] if old_params else "").strip()
                        expected_params = [patient_name, whatsapp_recordatorio_datetime_label(fecha, str(payload.get("appointment_time")))]
                        if old_params != expected_params:
                            payload["body_params"] = expected_params
                            payload_changed = True
                        expected_replies = [
                            f"CONFIRMAR|{row.source_type}|{row.source_id}|{fecha.isoformat()}|{str(payload.get('appointment_time'))}",
                            f"CANCELAR|{row.source_type}|{row.source_id}|{fecha.isoformat()}|{str(payload.get('appointment_time'))}",
                        ]
                        if list(payload.get("quick_reply_payloads") or []) != expected_replies:
                            payload["quick_reply_payloads"] = expected_replies
                            payload_changed = True
                        expected_header = row.template_name == WHATSAPP_TEMPLATE_RECORDATORIO_CITA_LOGO and WHATSAPP_RECORDATORIO_CITA_LOGO_ENABLED
                        if bool(payload.get("header_required")) != bool(expected_header):
                            payload["header_required"] = bool(expected_header)
                            payload_changed = True
                    else:
                        target = appointment_at - timedelta(hours=WHATSAPP_TODAY_HOURS_BEFORE)
                    if row.due_at != target or payload.get("original_due_at") != target.isoformat():
                        row.due_at = target
                        payload["original_due_at"] = target.isoformat()
                        payload_changed = True
                    if payload_changed:
                        row.payload_json = json.dumps(payload, ensure_ascii=False)
                        row.updated_at = datetime.now()
                        changed += 1
                except Exception:
                    continue
            if changed:
                db.commit()
    except Exception:
        return 0
    return changed


def _whatsapp_is_stale(row: WhatsAppOutbox, payload: dict, now: datetime) -> bool:
    try:
        fecha = date.fromisoformat(str(payload.get("appointment_date")))
        hh, mm = [int(x) for x in str(payload.get("appointment_time")).split(":")]
        appointment_at = datetime(fecha.year, fecha.month, fecha.day, hh, mm)
        original_due = datetime.fromisoformat(str(payload.get("original_due_at")))
    except Exception:
        return True
    if now >= appointment_at:
        return True
    age = now - original_due
    if row.template_name == WHATSAPP_TEMPLATE_CITA_AGENDADA:
        return age > timedelta(hours=1)
    if row.template_name in (WHATSAPP_TEMPLATE_RECORDATORIO_CITA, WHATSAPP_TEMPLATE_RECORDATORIO_CITA_LOGO, WHATSAPP_TEMPLATE_RECORDATORIO_HOY):
        return age > timedelta(hours=4)
    return age > timedelta(hours=4)


def process_whatsapp_outbox_once(limit: int = 20) -> dict:
    if WHATSAPP_CLOUD_MODE:
        return {"ok": True, "enabled": False, "cloud_mode": True, "processed": 0, "message": "Automatización gestionada por WhatsApp Cloud 24/7"}
    if not WHATSAPP_ENABLED:
        return {"ok": False, "enabled": False, "processed": 0}
    ready, missing = whatsapp_ready()
    if not ready:
        return {"ok": False, "enabled": True, "processed": 0, "missing": missing}
    if not _whatsapp_worker_lock.acquire(blocking=False):
        return {"ok": True, "enabled": True, "processed": 0, "busy": True}
    processed = sent = expired = errors = 0
    try:
        now = datetime.now()
        with LocalSessionLocal() as db:
            active_templates = whatsapp_enabled_template_names()
            if not active_templates:
                return {"ok": True, "enabled": True, "processed": 0, "sent": 0, "expired": 0, "errors": 0, "skipped_disabled": 0}
            rows = list(db.scalars(select(WhatsAppOutbox).where(
                WhatsAppOutbox.status.in_(["PENDING", "ERROR"]),
                WhatsAppOutbox.template_name.in_(active_templates),
                WhatsAppOutbox.due_at <= now,
                WhatsAppOutbox.attempts < 5,
            ).order_by(WhatsAppOutbox.due_at.asc(), WhatsAppOutbox.id.asc()).limit(max(1, min(int(limit), 50)))))
            skipped_disabled = 0
            for row in rows:
                processed += 1
                try:
                    payload_data = json.loads(row.payload_json or "{}")
                    if _whatsapp_is_stale(row, payload_data, now):
                        row.status = "EXPIRED"; row.updated_at = now; expired += 1
                        continue
                    header_image = WHATSAPP_HEADER_IMAGE_ID if payload_data.get("header_required") else None
                    wa_payload = whatsapp_build_template_payload(
                        to=row.phone,
                        template_name=row.template_name,
                        language_code=whatsapp_language_for_template(row.template_name),
                        body_params=[str(x) for x in payload_data.get("body_params", [])],
                        header_image_id=header_image,
                        quick_reply_payloads=[str(x) for x in payload_data.get("quick_reply_payloads", [])],
                    )
                    response = whatsapp_send_template(
                        graph_version=WHATSAPP_GRAPH_VERSION,
                        phone_number_id=WHATSAPP_PHONE_NUMBER_ID,
                        access_token=WHATSAPP_ACCESS_TOKEN,
                        payload=wa_payload,
                    )
                    row.status = "SENT"; row.sent_at = now; row.last_error = None
                    row.response_json = json.dumps(response, ensure_ascii=False)[:4000]
                    row.updated_at = now; sent += 1
                except Exception as exc:
                    row.attempts = int(row.attempts or 0) + 1
                    row.status = "ERROR"
                    row.last_error = str(exc)[:500]
                    # Reintento suave: nunca más de una vez cada 5 minutos.
                    row.due_at = now + timedelta(minutes=5)
                    row.updated_at = now; errors += 1
            db.commit()
        return {"ok": errors == 0, "enabled": True, "processed": processed, "sent": sent, "expired": expired, "errors": errors, "skipped_disabled": skipped_disabled}
    finally:
        _whatsapp_worker_lock.release()


def _whatsapp_background_loop() -> None:
    # Un único hilo liviano; no consulta Neon. Solo existe cuando WHATSAPP_ENABLED=1.
    while WHATSAPP_ENABLED:
        try:
            process_whatsapp_outbox_once(limit=20)
        except Exception:
            pass
        time.sleep(WHATSAPP_POLL_SECONDS)


def start_whatsapp_worker_if_enabled() -> None:
    global _whatsapp_worker_started
    if WHATSAPP_CLOUD_MODE:
        return
    if not WHATSAPP_ENABLED or _whatsapp_worker_started:
        return
    _whatsapp_worker_started = True
    threading.Thread(target=_whatsapp_background_loop, daemon=True, name="rp-whatsapp").start()


def mirror_patient_to_local(p: Patient):
    try:
        with LocalSessionLocal() as db:
            lp = db.get(Patient, p.id)
            values = dict(cedula=p.cedula, nombre=p.nombre, fecha_nacimiento=p.fecha_nacimiento, celular=p.celular, correo=p.correo, lugar=p.lugar, notas=p.notas, created_at=p.created_at)
            if lp:
                for k, v in values.items(): setattr(lp, k, v)
            else:
                db.add(Patient(id=p.id, **values))
            db.commit()
    except Exception:
        pass


def mirror_visit_to_local(v: Visit):
    try:
        with LocalSessionLocal() as db:
            lv = db.get(Visit, v.id)
            values = dict(patient_id=v.patient_id, fecha=v.fecha, tipo=v.tipo, procedimiento=v.procedimiento, valor=v.valor, observacion=v.observacion, source_row=v.source_row, created_at=v.created_at)
            if lv:
                for k, val in values.items(): setattr(lv, k, val)
            else:
                db.add(Visit(id=v.id, **values))
            db.commit()
    except Exception:
        pass


def mirror_billing_to_local(b: BillingRecord):
    try:
        with LocalSessionLocal() as db:
            lb = db.scalar(select(BillingRecord).where(BillingRecord.visit_id == b.visit_id))
            values = dict(
                visit_id=b.visit_id, estado=b.estado, numero_factura=b.numero_factura,
                approved_at=b.approved_at, emitted_at=b.emitted_at, created_at=b.created_at,
            )
            if lb:
                for k, val in values.items(): setattr(lb, k, val)
            else:
                db.add(BillingRecord(id=b.id, **values))
            db.commit()
    except Exception:
        pass


def mirror_azur_emission_to_local(record: AzurEmission):
    """Refleja inmediatamente el estado técnico AZUR/SRI en SQLite local.

    Facturación se lee local-first para que la PC antigua sea rápida; si solo
    actualizamos Neon, la pantalla seguiría mostrando EMITIDA aunque AZUR ya
    hubiese respondido AUTORIZADA.
    """
    try:
        with LocalSessionLocal() as db:
            local = db.scalar(select(AzurEmission).where(AzurEmission.group_key == record.group_key))
            values = dict(
                group_key=record.group_key, patient_id=record.patient_id, fecha=record.fecha,
                estado=record.estado, clave_acceso=record.clave_acceso, numero_factura=record.numero_factura,
                request_hash=record.request_hash, response_json=record.response_json,
                created_at=record.created_at, updated_at=record.updated_at,
            )
            if local:
                for key, value in values.items(): setattr(local, key, value)
            else:
                db.add(AzurEmission(id=record.id, **values))
            db.commit()
    except Exception:
        pass


def mirror_billing_preference_to_local(pref: BillingPreference):
    try:
        with LocalSessionLocal() as db:
            local = db.scalar(select(BillingPreference).where(BillingPreference.patient_id == pref.patient_id))
            values = dict(
                patient_id=pref.patient_id, enabled=pref.enabled, identificacion=pref.identificacion,
                nombre=pref.nombre, direccion=pref.direccion, telefono=pref.telefono,
                correo=pref.correo, updated_at=pref.updated_at,
            )
            if local:
                for key, value in values.items(): setattr(local, key, value)
            else:
                db.add(BillingPreference(id=pref.id, **values))
            db.commit()
    except Exception:
        pass


def mirror_delete_billing_preference_local(patient_id: int):
    try:
        with LocalSessionLocal() as db:
            row = db.scalar(select(BillingPreference).where(BillingPreference.patient_id == int(patient_id)))
            if row: db.delete(row)
            db.commit()
    except Exception:
        pass


def mirror_appointment_to_local(a: Appointment):
    try:
        with LocalSessionLocal() as db:
            la = db.get(Appointment, a.id)
            values = dict(
                patient_id=a.patient_id, fecha=a.fecha, hora=a.hora, duracion=a.duracion, nota=a.nota,
                estado=a.estado, origen=a.origen, exported_at=a.exported_at, loaded_at=a.loaded_at,
                created_at=a.created_at, updated_at=a.updated_at,
            )
            if la:
                for k, val in values.items(): setattr(la, k, val)
            else:
                db.add(Appointment(id=a.id, **values))
            db.commit()
    except Exception:
        pass


def mirror_delete_appointment_local(aid: int):
    try:
        with LocalSessionLocal() as db:
            a = db.get(Appointment, aid)
            if a: db.delete(a)
            db.commit()
    except Exception:
        pass


def mirror_confirmafy_agenda_local(item: ConfirmafyAgendaItem):
    try:
        with LocalSessionLocal() as db:
            local = db.get(ConfirmafyAgendaItem, item.id)
            values = {
                "nombre": item.nombre, "celular": item.celular, "fecha": item.fecha,
                "hora": item.hora, "duracion": item.duracion, "source_hash": item.source_hash,
                "created_at": item.created_at,
            }
            if local:
                for key, value in values.items(): setattr(local, key, value)
            else:
                db.add(ConfirmafyAgendaItem(id=item.id, **values))
            db.commit()
    except Exception:
        pass


def mirror_delete_confirmafy_agenda_local(item_id: int):
    try:
        with LocalSessionLocal() as db:
            item = db.get(ConfirmafyAgendaItem, item_id)
            if item: db.delete(item)
            db.commit()
    except Exception:
        pass


def mirror_delete_patient_local(pid: int):
    try:
        with LocalSessionLocal() as db:
            p = db.get(Patient, pid)
            if p: db.delete(p)
            db.commit()
    except Exception:
        pass


def mirror_delete_visit_local(vid: int):
    try:
        with LocalSessionLocal() as db:
            v = db.get(Visit, vid)
            if v: db.delete(v)
            db.commit()
    except Exception:
        pass


def mirror_procedure_local(p: Procedure):
    try:
        with LocalSessionLocal() as db:
            lp = db.get(Procedure, p.id)
            if lp:
                lp.nombre=p.nombre; lp.valor_default=p.valor_default; lp.activo=p.activo
            else:
                db.add(Procedure(id=p.id,nombre=p.nombre,valor_default=p.valor_default,activo=p.activo))
            db.commit()
    except Exception:
        pass


def mirror_user_local(u: User):
    try:
        with LocalSessionLocal() as db:
            lu=db.get(User,u.id)
            if lu:
                lu.username=u.username;lu.password_hash=u.password_hash;lu.role=u.role
            else:
                db.add(User(id=u.id,username=u.username,password_hash=u.password_hash,role=u.role))
            db.commit()
    except Exception:
        pass


LOCAL_FIRST_GET_PREFIXES = (
    "/api/bootstrap",
    "/api/today",
    "/api/patients",
    "/api/home/week",
    "/api/pending-summary",
    "/api/procedures",
    "/api/agenda/recent-patients",
    "/api/agenda/pending-count",
    "/api/agenda/appointments",
    "/api/agenda/week",
    "/api/agenda/confirmafy-staged",
    "/api/agenda/slots",
    "/api/billing",
    "/api/report",
    "/api/dashboard",
    "/api/export.xlsx",
    "/api/export.csv",
    "/api/agenda/dashboard",
)


def _mark_client_active() -> None:
    with _state_lock:
        _state["client_idle"] = False
        _state["last_activity"] = time.time()


def _prefer_local_read(request: Request) -> bool:
    if request.method.upper() != "GET":
        return False
    if str(request.query_params.get("fresh") or "").strip() == "1":
        return False
    path = request.url.path
    return any(path == prefix or path.startswith(prefix + "/") for prefix in LOCAL_FIRST_GET_PREFIXES)


def get_db(request: Request):
    # Las pantallas más consultadas leen desde la copia SQLite local. Las
    # escrituras siguen yendo a Neon cuando está disponible y se reflejan
    # inmediatamente al cache local. Así la PC vieja responde rápido y Neon
    # recibe muchas menos lecturas innecesarias.
    _mark_client_active()
    pending = queue_count()
    if pending > 0 or _prefer_local_read(request):
        use_cloud = False
    else:
        online = check_cloud()
        use_cloud = bool(online and CloudSessionLocal)
    factory = CloudSessionLocal if use_cloud else LocalSessionLocal
    db = factory()
    db.info["offline"] = not use_cloud
    db.info["local_first"] = bool(not use_cloud and pending == 0 and _prefer_local_read(request))
    try:
        yield db
    finally:
        db.close()


def is_offline_db(db: Session) -> bool:
    return bool(db.info.get("offline"))


def _user_snapshot(user: User) -> User:
    return User(id=user.id, username=user.username, password_hash=user.password_hash, role=user.role)


def invalidate_user_cache(username: Optional[str] = None):
    with _user_cache_lock:
        if username:
            _user_cache.pop(username, None)
        else:
            _user_cache.clear()


def _auto_login_enabled() -> bool:
    # La interfaz clínica solo se permite desde loopback. El servidor escucha también
    # en la LAN únicamente para la superficie protegida de Agenda móvil.
    try:
        return bool(_app_preferences().get("auto_login", True))
    except Exception:
        return True


def _default_local_user() -> Optional[User]:
    now = time.time()
    with _user_cache_lock:
        cached = _user_cache.get("admin")
        if cached and now - cached[0] < USER_CACHE_SECONDS:
            return cached[1]
    try:
        with LocalSessionLocal() as db:
            user = db.scalar(select(User).where(User.username == "admin")) or db.scalar(select(User).order_by(User.id))
            if user:
                snap = _user_snapshot(user)
                with _user_cache_lock:
                    _user_cache[snap.username] = (now, snap)
                return snap
    except Exception:
        pass
    return None


def current_user(request: Request) -> User:
    token = request.cookies.get("rp_session")
    username = TOKENS.get(token or "")
    if not username and _auto_login_enabled():
        auto_user = _default_local_user()
        if auto_user:
            return auto_user
    if not username:
        raise HTTPException(401, "No autenticado")
    now = time.time()
    with _user_cache_lock:
        cached = _user_cache.get(username)
        if cached and now - cached[0] < USER_CACHE_SECONDS:
            return cached[1]
    # La sesión ya iniciada debe seguir funcionando si Internet se cae.
    with LocalSessionLocal() as db:
        user = db.scalar(select(User).where(User.username == username))
        if user:
            snap = _user_snapshot(user)
            with _user_cache_lock:
                _user_cache[username] = (now, snap)
            return snap
    # El login manual conserva un último respaldo de nube, pero el modo
    # automático nunca despierta Neon solo para validar la sesión.
    if check_cloud(force=True):
        try:
            with CloudSessionLocal() as db:
                user = db.scalar(select(User).where(User.username == username))
                if user:
                    snap = _user_snapshot(user)
                    with _user_cache_lock:
                        _user_cache[username] = (now, snap)
                    return snap
        except Exception:
            pass
    raise HTTPException(401, "No autenticado")


def p_dict(p: Patient):
    return {
        "id": p.id, "cedula": p.cedula, "nombre": p.nombre,
        "fecha_nacimiento": p.fecha_nacimiento, "celular": p.celular,
        "correo": p.correo, "lugar": p.lugar, "notas": p.notas,
    }


def v_dict(v: Visit):
    return {
        "id": v.id, "patient_id": v.patient_id, "fecha": v.fecha, "tipo": v.tipo,
        "procedimiento": v.procedimiento,
        "valor": float(v.valor) if v.valor is not None else None,
        "observacion": v.observacion,
    }


def billing_dict(b: BillingRecord):
    return {
        "id": b.id, "visit_id": b.visit_id, "estado": b.estado,
        "numero_factura": b.numero_factura, "approved_at": b.approved_at,
        "emitted_at": b.emitted_at,
    }


def azur_emission_dict(x: Optional[AzurEmission]):
    if not x:
        return None
    return {
        "estado": x.estado,
        "numero_factura": x.numero_factura,
        "has_clave_acceso": bool(x.clave_acceso),
        "updated_at": x.updated_at,
    }


def billing_preference_dict(x: Optional[BillingPreference]):
    if not x:
        return None
    return {
        "patient_id": x.patient_id, "enabled": bool(x.enabled),
        "identificacion": x.identificacion, "nombre": x.nombre,
        "direccion": x.direccion, "telefono": x.telefono, "correo": x.correo,
        "updated_at": x.updated_at,
    }


def appointment_dict(a: Appointment):
    return {
        "id": a.id, "patient_id": a.patient_id, "fecha": a.fecha, "hora": a.hora,
        "duracion": int(a.duracion or 20), "nota": a.nota, "estado": a.estado,
        "origen": a.origen, "exported_at": a.exported_at, "loaded_at": a.loaded_at,
        "created_at": a.created_at, "updated_at": a.updated_at,
    }


def confirmafy_agenda_dict(a: ConfirmafyAgendaItem):
    return {
        "id": a.id, "nombre": a.nombre, "celular": a.celular, "fecha": a.fecha,
        "hora": a.hora, "duracion": int(a.duracion or 20),
        "source_hash": a.source_hash, "created_at": a.created_at,
    }


def confirmafy_phone(value: Optional[str]) -> str:
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith("593"):
        return digits
    if len(digits) == 10 and digits.startswith("0"):
        return "593" + digits[1:]
    return digits


def normalize_appointment_payload(data) -> dict:
    values = data.model_dump() if hasattr(data, "model_dump") else dict(data)
    raw_time = str(values.get("hora") or "").strip()[:5]
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", raw_time):
        raise HTTPException(400, "La hora no es válida")
    minutes = hhmm_to_minutes(raw_time)
    end = minutes + 20
    # Horario del consultorio: no se agenda durante el almuerzo (12:30–14:00)
    # y la última cita disponible comienza a las 17:00.
    if minutes < 8 * 60 or minutes > 17 * 60:
        raise HTTPException(400, "La cita debe estar entre las 08:00 y las 17:00")
    if minutes < 14 * 60 and end > 12 * 60 + 30:
        raise HTTPException(400, "De 12:30 a 14:00 es horario de almuerzo")
    values["hora"] = raw_time
    values["duracion"] = 20
    values["nota"] = (values.get("nota") or "").strip() or None
    return values



def confirmafy_marker_note(source_hash: str) -> str:
    return f"{CONFIRMAFY_ATTENDED_NOTE_PREFIX}{str(source_hash or '').strip()}"


def confirmafy_marker_hash(appointment: Appointment) -> str:
    note = str(getattr(appointment, "nota", "") or "")
    if note.startswith(CONFIRMAFY_ATTENDED_NOTE_PREFIX):
        return note[len(CONFIRMAFY_ATTENDED_NOTE_PREFIX):].strip()
    return ""


def active_confirmafy_attended_hashes(db: Session, dates: list[date]) -> set[str]:
    """Hashes de citas externas que ya tienen una atención clínica vigente.

    La cita de Confirmafy se conserva como staged y se oculta mientras exista
    al menos una atención del paciente vinculado en esa fecha. Si se borran
    todas las atenciones de ese día, vuelve a aparecer automáticamente.
    """
    clean_dates = [d for d in dates if d]
    if not clean_dates:
        return set()
    markers = list(db.scalars(
        select(Appointment).where(
            Appointment.fecha.in_(clean_dates),
            Appointment.origen == CONFIRMAFY_ATTENDED_ORIGIN,
        )
    ))
    if not markers:
        return set()
    patient_ids = sorted({int(a.patient_id) for a in markers if a.patient_id})
    if not patient_ids:
        return set()
    visit_pairs = {
        (int(pid), f) for pid, f in db.execute(
            select(Visit.patient_id, Visit.fecha).where(
                Visit.fecha.in_(clean_dates), Visit.patient_id.in_(patient_ids)
            ).distinct()
        ).all()
    }
    out: set[str] = set()
    for marker in markers:
        if (int(marker.patient_id), marker.fecha) not in visit_pairs:
            continue
        source_hash = confirmafy_marker_hash(marker)
        if source_hash:
            out.add(source_hash)
    return out


def hhmm_to_minutes(value: str) -> int:
    h, m = str(value or "00:00")[:5].split(":")
    return int(h) * 60 + int(m)


def appointment_conflicts(
    db: Session,
    fecha: date,
    hora: str,
    duration: int = 20,
    exclude_id: Optional[int] = None,
):
    """Devuelve cruces contra *toda* la agenda visible.

    Desde v4.3.7 las citas importadas de Confirmafy pueden vivir en
    ``confirmafy_agenda_items`` sin patient_id hasta que el paciente llega.
    Esas citas ocupan un bloque igual que una reagenda normal y por tanto deben
    bloquear tanto el selector visual como la validación final al guardar.

    El segundo elemento de cada tupla es ``Patient`` para citas vinculadas y
    ``None`` para citas externas; ``occupied_message`` entiende ambos casos.
    """
    new_start = hhmm_to_minutes(hora)
    new_end = new_start + int(duration or 20)

    stmt = select(Appointment, Patient).join(Patient).where(
        Appointment.fecha == fecha,
        Appointment.origen != CONFIRMAFY_ATTENDED_ORIGIN,
    )
    if exclude_id is not None:
        stmt = stmt.where(Appointment.id != int(exclude_id))
    rows = db.execute(stmt.order_by(Appointment.hora.asc(), Appointment.id.asc())).all()

    conflicts = []
    for a, p in rows:
        try:
            old_start = hhmm_to_minutes(a.hora)
        except Exception:
            continue
        old_end = old_start + int(a.duracion or 20)
        if new_start < old_end and old_start < new_end:
            conflicts.append((a, p))

    # Citas de Confirmafy aún sin vincular. No se excluyen mediante exclude_id,
    # porque ese id pertenece exclusivamente a Appointment.
    attended_hashes = active_confirmafy_attended_hashes(db, [fecha])
    staged_rows = [a for a in db.scalars(
        select(ConfirmafyAgendaItem)
        .where(ConfirmafyAgendaItem.fecha == fecha)
        .order_by(ConfirmafyAgendaItem.hora.asc(), ConfirmafyAgendaItem.id.asc())
    ) if str(a.source_hash or "") not in attended_hashes
       and not str(a.source_hash or "").startswith("mobile:whatsapp-cloud-test:")]
    for a in staged_rows:
        try:
            old_start = hhmm_to_minutes(a.hora)
        except Exception:
            continue
        old_end = old_start + int(a.duracion or 20)
        if new_start < old_end and old_start < new_end:
            conflicts.append((a, None))
    return conflicts


def occupied_message(fecha: date, hora: str, conflicts) -> str:
    if not conflicts:
        return ""
    labels = []
    for item, patient in conflicts[:3]:
        label = (getattr(patient, "nombre", None) if patient is not None else None) or getattr(item, "nombre", None) or "otra cita"
        labels.append(str(label))
    # Una migración antigua puede haber dejado la misma cita representada en
    # ambas tablas; no repetimos el mismo nombre en el aviso.
    labels = list(dict.fromkeys(labels))
    names = ", ".join(labels[:3])
    extra = "" if len(labels) <= 3 else f" y {len(labels) - 3} más"
    return f"El {fecha.strftime('%d/%m/%Y')} a las {hora} ya está ocupado por {names}{extra}. Elige otra hora."


def is_procedure(v: Visit) -> bool:
    return bool((v.procedimiento or "").strip()) or v.tipo == "P"


def valid_ecuadorian_cedula(value: str) -> bool:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) != 10 or int(digits[2]) > 5:
        return False
    total = 0
    for i, ch in enumerate(digits[:9]):
        n = int(ch) * (2 if i % 2 == 0 else 1)
        total += n - 9 if n >= 10 else n
    return ((10 - (total % 10)) % 10) == int(digits[9])


def normalize_patient_payload(data) -> dict:
    values = data.model_dump() if hasattr(data, "model_dump") else dict(data)
    marker_present = "extranjero" in values
    extranjero = bool(values.pop("extranjero", False))
    values["nombre"] = (values.get("nombre") or "").strip().upper()

    raw_id = str(values.get("cedula") or "").strip()
    if raw_id and not marker_present and not re.fullmatch(r"\d{10}", re.sub(r"\s+", "", raw_id)):
        extranjero = True
    if raw_id:
        if extranjero:
            normalized_id = re.sub(r"\s+", "", raw_id).upper()
            if len(normalized_id) > 30:
                raise HTTPException(400, "La identificación extranjera no puede superar 30 caracteres")
            values["cedula"] = normalized_id
        else:
            digits = re.sub(r"\D", "", raw_id)
            if len(digits) != 10:
                raise HTTPException(400, "La cédula ecuatoriana debe tener exactamente 10 dígitos")
            if not valid_ecuadorian_cedula(digits):
                raise HTTPException(400, "La cédula ecuatoriana no es válida. Revisa si se digitó correctamente")
            values["cedula"] = digits
    else:
        values["cedula"] = None

    raw_phone = (values.get("celular") or "").strip()
    values["celular"] = re.sub(r"\D", "", raw_phone) or None
    values["correo"] = (values.get("correo") or "").strip().lower() or None
    nac = values.get("fecha_nacimiento")
    if isinstance(nac, str) and nac.strip():
        try:
            values["fecha_nacimiento"] = date.fromisoformat(nac.strip()[:10])
        except Exception:
            values["fecha_nacimiento"] = None
    values["lugar"] = (values.get("lugar") or "").strip() or None
    values["notas"] = (values.get("notas") or "").strip() or None
    return values


def add_queue(db: Session, operation: str, entity: str, payload: dict, username: str, local_entity_id: Optional[int] = None) -> str:
    token = uuid.uuid4().hex
    invalidate_queue_count()
    db.add(OfflineQueue(
        token=token,
        operation=operation,
        entity=entity,
        local_entity_id=local_entity_id,
        payload=json.dumps(payload, default=str, ensure_ascii=False),
        username=username,
    ))
    return token


def get_id_map(db: Session, entity: str, local_id: int) -> Optional[int]:
    row = db.scalar(select(OfflineIdMap).where(OfflineIdMap.entity == entity, OfflineIdMap.local_id == local_id))
    return int(row.cloud_id) if row else None


def set_id_map(db: Session, entity: str, local_id: int, cloud_id: int):
    row = db.scalar(select(OfflineIdMap).where(OfflineIdMap.entity == entity, OfflineIdMap.local_id == local_id))
    if row:
        row.cloud_id = cloud_id
    else:
        db.add(OfflineIdMap(entity=entity, local_id=local_id, cloud_id=cloud_id))


def resolve_cloud_id(ldb: Session, entity: str, local_id: int) -> int:
    return get_id_map(ldb, entity, local_id) or int(local_id)


def sync_one_operation(q: OfflineQueue, ldb: Session, cdb: Session) -> Optional[int]:
    already = cdb.get(SyncOperation, q.token)
    if already:
        return already.result_id

    payload = json.loads(q.payload or "{}")
    result_id: Optional[int] = None

    if q.operation == "patient.create":
        values = normalize_patient_payload(payload)
        existing = None
        if values.get("cedula"):
            existing = cdb.scalar(select(Patient).where(Patient.cedula == values["cedula"]))
        if existing:
            result_id = existing.id
        else:
            p = Patient(**values)
            cdb.add(p)
            cdb.flush()
            result_id = p.id
        audit(cdb, q.username, "sincronizar_paciente_offline", f"Paciente local {q.local_entity_id} -> nube {result_id}")

    elif q.operation == "patient.update":
        local_id = int(payload.pop("patient_id"))
        cloud_id = resolve_cloud_id(ldb, "patient", local_id)
        p = cdb.get(Patient, cloud_id)
        if not p:
            raise RuntimeError(f"Paciente {cloud_id} no existe en la nube")
        values = normalize_patient_payload(payload)
        if values.get("cedula"):
            duplicate = cdb.scalar(select(Patient).where(Patient.cedula == values["cedula"], Patient.id != cloud_id))
            if duplicate:
                raise RuntimeError(f"La cédula {values['cedula']} ya pertenece a otro paciente")
        for k, v in values.items():
            setattr(p, k, v)
        result_id = cloud_id
        audit(cdb, q.username, "sincronizar_edicion_paciente_offline", f"Paciente {cloud_id}")

    elif q.operation == "patient.delete":
        local_id = int(payload["patient_id"])
        cloud_id = resolve_cloud_id(ldb, "patient", local_id)
        p = cdb.get(Patient, cloud_id)
        if p:
            cdb.delete(p)
        result_id = cloud_id
        audit(cdb, q.username, "sincronizar_borrado_paciente_offline", f"Paciente {cloud_id}")

    elif q.operation == "visit.create":
        local_patient_id = int(payload["patient_id"])
        cloud_patient_id = resolve_cloud_id(ldb, "patient", local_patient_id)
        p = cdb.get(Patient, cloud_patient_id)
        if not p:
            raise RuntimeError(f"No se encontró paciente {cloud_patient_id} para sincronizar la atención")
        fecha_val = date.fromisoformat(str(payload["fecha"])[:10])
        v = Visit(
            patient_id=cloud_patient_id,
            fecha=fecha_val,
            tipo=str(payload["tipo"]),
            procedimiento=(payload.get("procedimiento") or None),
            valor=payload.get("valor"),
            observacion=payload.get("observacion") or None,
        )
        cdb.add(v)
        cdb.flush()
        result_id = v.id
        cdb.add(BillingRecord(visit_id=v.id, estado="PENDIENTE"))
        audit(cdb, q.username, "sincronizar_atencion_offline", f"Atención local {q.local_entity_id} -> nube {result_id}")

    elif q.operation == "visit.delete":
        local_id = int(payload["visit_id"])
        cloud_id = resolve_cloud_id(ldb, "visit", local_id)
        v = cdb.get(Visit, cloud_id)
        if v:
            cdb.delete(v)
        result_id = cloud_id
        audit(cdb, q.username, "sincronizar_borrado_atencion_offline", f"Atención {cloud_id}")

    elif q.operation in {"billing.approve", "billing.pending", "billing.emit"}:
        local_visit_id = int(payload["visit_id"])
        cloud_visit_id = resolve_cloud_id(ldb, "visit", local_visit_id)
        b = cdb.scalar(select(BillingRecord).where(BillingRecord.visit_id == cloud_visit_id))
        if not b:
            b = BillingRecord(visit_id=cloud_visit_id, estado="PENDIENTE")
            cdb.add(b)
            cdb.flush()
        if q.operation == "billing.approve":
            if b.estado != "EMITIDA":
                b.estado = "APROBADA"
                b.approved_at = datetime.utcnow()
                b.numero_factura = None
                b.emitted_at = None
        elif q.operation == "billing.pending":
            if b.estado != "EMITIDA":
                b.estado = "PENDIENTE"
                b.approved_at = None
                b.numero_factura = None
                b.emitted_at = None
        else:
            b.estado = "EMITIDA"
            b.numero_factura = (payload.get("numero_factura") or "").strip() or None
            b.emitted_at = datetime.utcnow()
            if not b.approved_at:
                b.approved_at = datetime.utcnow()
        result_id = b.id
        audit(cdb, q.username, "sincronizar_facturacion_offline", f"Atención {cloud_visit_id}: {b.estado}")

    elif q.operation == "confirmafy_staged.create":
        source_hash = str(payload.get("source_hash") or "").strip()
        existing = cdb.scalar(select(ConfirmafyAgendaItem).where(ConfirmafyAgendaItem.source_hash == source_hash)) if source_hash else None
        if existing:
            result_id = existing.id
        else:
            item = ConfirmafyAgendaItem(
                nombre=str(payload.get("nombre") or "").strip().upper(),
                celular=normalize_lookup_phone(str(payload.get("celular") or "")) or None,
                fecha=date.fromisoformat(str(payload["fecha"])[:10]),
                hora=str(payload["hora"])[:5], duracion=20, source_hash=source_hash,
            )
            cdb.add(item); cdb.flush(); result_id = item.id
        audit(cdb, q.username, "sincronizar_agenda_confirmafy_offline", f"Cita externa local {q.local_entity_id} -> nube {result_id}")

    elif q.operation == "confirmafy_staged.delete":
        local_id = int(payload["item_id"])
        cloud_id = resolve_cloud_id(ldb, "confirmafy_staged", local_id)
        item = cdb.get(ConfirmafyAgendaItem, cloud_id)
        if item: cdb.delete(item)
        result_id = cloud_id
        audit(cdb, q.username, "sincronizar_agenda_confirmafy_atendida_offline", f"Cita externa {cloud_id}")

    elif q.operation == "appointment.create":
        local_patient_id = int(payload["patient_id"])
        cloud_patient_id = resolve_cloud_id(ldb, "patient", local_patient_id)
        p = cdb.get(Patient, cloud_patient_id)
        if not p:
            raise RuntimeError(f"No se encontró paciente {cloud_patient_id} para sincronizar la cita")
        sync_fecha = date.fromisoformat(str(payload["fecha"])[:10])
        sync_hora = str(payload["hora"])[:5]
        origin_value = payload.get("origen") or "REAGENDADO"
        if origin_value != CONFIRMAFY_ATTENDED_ORIGIN:
            conflicts = appointment_conflicts(cdb, sync_fecha, sync_hora, 20)
            if conflicts:
                raise RuntimeError(occupied_message(sync_fecha, sync_hora, conflicts))
        a = Appointment(
            patient_id=cloud_patient_id, fecha=sync_fecha,
            hora=sync_hora, duracion=20, nota=payload.get("nota") or None,
            estado=payload.get("estado") or "PENDIENTE", origen=origin_value,
        )
        cdb.add(a)
        cdb.flush()
        result_id = a.id
        audit(cdb, q.username, "sincronizar_cita_offline", f"Cita local {q.local_entity_id} -> nube {result_id}")

    elif q.operation == "appointment.update":
        local_id = int(payload["appointment_id"])
        cloud_id = resolve_cloud_id(ldb, "appointment", local_id)
        a = cdb.get(Appointment, cloud_id)
        if not a:
            raise RuntimeError(f"Cita {cloud_id} no existe en la nube")
        sync_fecha = date.fromisoformat(str(payload["fecha"])[:10])
        sync_hora = str(payload["hora"])[:5]
        origin_value = payload.get("origen") or a.origen or "REAGENDADO"
        if origin_value != CONFIRMAFY_ATTENDED_ORIGIN:
            conflicts = appointment_conflicts(cdb, sync_fecha, sync_hora, 20, cloud_id)
            if conflicts:
                raise RuntimeError(occupied_message(sync_fecha, sync_hora, conflicts))
        local_patient_id = payload.get("patient_id")
        if local_patient_id is not None:
            a.patient_id = resolve_cloud_id(ldb, "patient", int(local_patient_id))
        a.fecha = sync_fecha
        a.hora = sync_hora
        a.duracion = 20
        a.nota = payload.get("nota") or None
        a.origen = origin_value
        a.estado = payload.get("estado") or ("ATENDIDO" if origin_value == CONFIRMAFY_ATTENDED_ORIGIN else "PENDIENTE")
        a.exported_at = None
        a.loaded_at = None
        a.updated_at = datetime.utcnow()
        result_id = a.id
        audit(cdb, q.username, "sincronizar_reagenda_offline", f"Cita {cloud_id}")

    elif q.operation in {"appointment.export", "appointment.loaded", "appointment.pending"}:
        local_id = int(payload["appointment_id"])
        cloud_id = resolve_cloud_id(ldb, "appointment", local_id)
        a = cdb.get(Appointment, cloud_id)
        if not a:
            raise RuntimeError(f"Cita {cloud_id} no existe en la nube")
        if q.operation == "appointment.export":
            a.estado = "EXPORTADO"
            a.exported_at = datetime.utcnow()
            a.loaded_at = None
        elif q.operation == "appointment.loaded":
            a.estado = "CARGADO"
            if not a.exported_at: a.exported_at = datetime.utcnow()
            a.loaded_at = datetime.utcnow()
        else:
            a.estado = "PENDIENTE"
            a.exported_at = None
            a.loaded_at = None
        a.updated_at = datetime.utcnow()
        result_id = a.id
        audit(cdb, q.username, "sincronizar_estado_cita_offline", f"Cita {cloud_id}: {a.estado}")

    elif q.operation == "appointment.cancel":
        local_id = int(payload["appointment_id"])
        cloud_id = resolve_cloud_id(ldb, "appointment", local_id)
        a = cdb.get(Appointment, cloud_id)
        if not a:
            raise RuntimeError(f"Cita {cloud_id} no existe en la nube")
        a.estado = "CANCELADA"
        a.updated_at = datetime.utcnow()
        result_id = a.id
        audit(cdb, q.username, "sincronizar_cancelacion_cita_offline", f"Cita {cloud_id}: CANCELADA")

    elif q.operation == "appointment.delete":
        local_id = int(payload["appointment_id"])
        cloud_id = resolve_cloud_id(ldb, "appointment", local_id)
        a = cdb.get(Appointment, cloud_id)
        if a: cdb.delete(a)
        result_id = cloud_id
        audit(cdb, q.username, "sincronizar_borrado_cita_offline", f"Cita {cloud_id}")

    elif q.operation == "procedure.update":
        proc_id = int(payload["procedure_id"])
        p = cdb.get(Procedure, proc_id)
        if not p:
            raise RuntimeError(f"Procedimiento {proc_id} no existe en la nube")
        p.valor_default = payload.get("valor_default")
        result_id = p.id
        audit(cdb, q.username, "sincronizar_procedimiento_offline", f"{p.nombre}: {p.valor_default}")

    else:
        raise RuntimeError(f"Operación offline desconocida: {q.operation}")

    cdb.add(SyncOperation(token=q.token, operation=q.operation, result_id=result_id))
    return result_id


def process_offline_queue(cloud_already_checked: bool = False) -> dict:
    """Sincroniza cambios locales minimizando sondas y checkouts a Neon."""
    if not cloud_configured():
        return {"ok": False, "online": False, "processed": 0, "pending": queue_count(), "errors": queue_errors()}
    if not cloud_already_checked and not check_cloud(force=True):
        return {"ok": False, "online": False, "processed": 0, "pending": queue_count(), "errors": queue_errors()}

    if not _sync_lock.acquire(blocking=False):
        return {"ok": True, "online": True, "processed": 0, "pending": queue_count(), "syncing": True, "errors": queue_errors()}

    processed = 0
    try:
        if not ensure_cloud_initialized():
            return {"ok": False, "online": False, "processed": 0, "pending": queue_count(), "errors": ["No se pudo preparar la conexión con la nube"]}

        # Una sola sesión de Neon para toda la cola: evita un checkout/pre-ping
        # por cada cambio pendiente. Se confirma cada operación individualmente.
        with LocalSessionLocal() as ldb, CloudSessionLocal() as cdb:
            rows = list(ldb.scalars(select(OfflineQueue).order_by(OfflineQueue.id.asc())))
            for q in rows:
                try:
                    result_id = sync_one_operation(q, ldb, cdb)
                    cdb.commit()
                    if q.operation == "patient.create" and q.local_entity_id is not None and result_id is not None:
                        set_id_map(ldb, "patient", int(q.local_entity_id), int(result_id))
                    if q.operation == "visit.create" and q.local_entity_id is not None and result_id is not None:
                        set_id_map(ldb, "visit", int(q.local_entity_id), int(result_id))
                    if q.operation == "appointment.create" and q.local_entity_id is not None and result_id is not None:
                        set_id_map(ldb, "appointment", int(q.local_entity_id), int(result_id))
                    if q.operation == "confirmafy_staged.create" and q.local_entity_id is not None and result_id is not None:
                        set_id_map(ldb, "confirmafy_staged", int(q.local_entity_id), int(result_id))
                    ldb.delete(q)
                    ldb.commit()
                    invalidate_queue_count()
                    processed += 1
                except Exception as e:
                    cdb.rollback()
                    ldb.rollback()
                    current = ldb.get(OfflineQueue, q.id)
                    if current:
                        current.last_error = str(e)[:500]
                        ldb.commit()
                    break

        pending = queue_count(force=True)
        if pending == 0:
            # La reconciliación completa sigue siendo necesaria tras modo offline
            # para alinear IDs locales con los definitivos de la nube.
            refresh_local_cache(force=True, cloud_already_checked=True)
            with LocalSessionLocal() as ldb:
                ldb.execute(delete(OfflineIdMap))
                ldb.commit()
        return {"ok": pending == 0, "online": True, "processed": processed, "pending": pending, "errors": queue_errors()}
    finally:
        _sync_lock.release()



V4425_AUTOBOOK_CSS = r"""
.native-unlinked.native-auto-booked{background:#e8f2ff!important;color:#245c94!important;border:1px solid #bcd5ee!important;font-weight:950!important;letter-spacing:.035em!important}
.native-slot.occupied:has(.native-auto-booked){outline:2px solid #a8caea!important;outline-offset:-2px!important}
"""
V4425_AUTOBOOK_JS = r""";(()=>{
  if(window.__v4425AutoBooking)return;
  window.__v4425AutoBooking=true;
  const PREFIX='mobile:autoagenda:';
  const SEEN_KEY='rp-v4425-auto-bookings-seen';
  const e=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

  function installAgendaBadge(){
    const base=window.nativeAgendaRowCell;
    if(typeof base!=='function'||base.__v4425AutoBooking)return false;
    const wrapped=function(row,date,time){
      let html=base.apply(this,arguments);
      const staged=row?.staged||{};
      const hash=String(staged.source_hash||'');
      if(!hash.startsWith(PREFIX))return html;
      html=html.replace('SIN VINCULAR','AUTOAGENDADA');
      html=html.replace('class="native-unlinked"','class="native-unlinked native-auto-booked"');
      return html;
    };
    wrapped.__v4425AutoBooking=true;
    window.nativeAgendaRowCell=wrapped;
    return true;
  }

  function readSeen(){
    try{const x=JSON.parse(localStorage.getItem(SEEN_KEY)||'[]');return Array.isArray(x)?x:[]}catch{return[]}
  }
  function saveSeen(values){
    try{localStorage.setItem(SEEN_KEY,JSON.stringify(values.slice(-250)))}catch{}
  }
  function localDate(v){
    if(typeof window.fmtDate==='function')try{return window.fmtDate(v)}catch{}
    const m=/^(\d{4})-(\d{2})-(\d{2})/.exec(String(v||''));return m?`${m[3]}/${m[2]}/${m[1]}`:String(v||'');
  }
  function localTime(v){
    if(typeof window.fmtTime==='function')try{return window.fmtTime(v)}catch{}
    return String(v||'').slice(0,5);
  }
  let busy=false;
  async function poll(){
    if(busy||document.hidden)return;
    busy=true;
    try{
      const d=await api('/api/auto-bookings/recent');
      const items=Array.isArray(d?.items)?d.items:[];
      if(!items.length)return;
      const old=readSeen(),seen=new Set(old);
      const fresh=items.filter(x=>x?.source_hash&&String(x.source_hash).startsWith(PREFIX)&&!seen.has(String(x.source_hash)));
      if(!fresh.length)return;
      fresh.forEach(x=>{const h=String(x.source_hash||'');if(h){seen.add(h);old.push(h)}});saveSeen(old);
      const last=fresh[0]||fresh[fresh.length-1];
      const detail=`${String(last?.nombre||'PACIENTE')} · ${localDate(last?.fecha)} · ${localTime(last?.hora)}`;
      const msg=fresh.length===1?`Nueva cita autoagendada: ${detail}`:`${fresh.length} nuevas citas autoagendadas. Última: ${detail}`;
      if(typeof window.rpNotice==='function')window.rpNotice(msg);else alert(msg);
      if(document.querySelector('#agenda:not(.hidden)')&&typeof window.loadAgenda==='function')setTimeout(()=>window.loadAgenda(),250);
    }catch(_e){}
    finally{busy=false}
  }

  let tries=0;
  function boot(){
    if(!installAgendaBadge()&&++tries<15)setTimeout(boot,150);
    setTimeout(poll,900);
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
  setInterval(poll,120000);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)setTimeout(poll,600)});
})();"""
V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\n" + V4425_AUTOBOOK_CSS
V460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\n" + V4425_AUTOBOOK_JS

# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

app = FastAPI(title="Recepción de Pacientes")
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
MOBILE_DIR = os.path.join(BASE_DIR, "mobile")
if os.path.isdir(MOBILE_DIR):
    app.mount("/mobile-static", StaticFiles(directory=MOBILE_DIR), name="mobile-static")


@app.on_event("startup")
async def _limit_worker_threads_for_old_pc():
    """Evita picos de decenas de hilos en una PC de recepción con pocos recursos."""
    try:
        import anyio.to_thread
        anyio.to_thread.current_default_thread_limiter().total_tokens = 8
    except Exception:
        pass
    # Recalcula localmente cualquier recordatorio pendiente creado por una
    # versión anterior; no llama a Meta ni consulta Neon.
    _whatsapp_rebase_pending_schedule()
    # El worker de WhatsApp arranca después de que FastAPI ya está listo y solo
    # cuando WHATSAPP_ENABLED=1. En la preparación actual permanece apagado.
    start_whatsapp_worker_if_enabled()
    # v4.3.34: la Agenda 24/7 vive en GitHub Pages + Neon Data API.
    # Ya no arrancamos Cloudflare Tunnel ni ningún proceso adicional. Si quedó
    # uno de una versión anterior, lo cerramos para liberar RAM/CPU.
    remote_stop_tunnel(DATA_DIR)


class LoginIn(BaseModel):
    username: str
    password: str


class PatientIn(BaseModel):
    cedula: Optional[str] = None
    nombre: str
    fecha_nacimiento: Optional[date] = None
    celular: Optional[str] = None
    correo: Optional[str] = None
    lugar: Optional[str] = None
    notas: Optional[str] = None
    extranjero: bool = False


class VisitIn(BaseModel):
    patient_id: int
    fecha: date = date.today()
    tipo: Optional[str] = None
    procedimiento: Optional[str] = None
    valor: Optional[float] = None
    observacion: Optional[str] = None


class VisitBatchServiceIn(BaseModel):
    procedimiento: Optional[str] = None
    valor: Optional[float] = None


class VisitBatchIn(BaseModel):
    patient_id: int
    fecha: date = date.today()
    tipo: Optional[str] = None
    services: list[VisitBatchServiceIn]
    observacion: Optional[str] = None


class BillingGroupIn(BaseModel):
    patient_id: int
    fecha: date
    # Datos alternos solo para esta factura. No modifican la ficha clínica del paciente.
    factura_otro: bool = False
    factura_identificacion: Optional[str] = None
    factura_nombre: Optional[str] = None
    factura_direccion: Optional[str] = None
    factura_telefono: Optional[str] = None
    factura_correo: Optional[str] = None


class BillingEmitIn(BillingGroupIn):
    numero_factura: str


class AzurConfigIn(BaseModel):
    base_url: str
    api_key: Optional[str] = None


class BillingPreferenceIn(BaseModel):
    enabled: bool = True
    identificacion: Optional[str] = None
    nombre: Optional[str] = None
    direccion: Optional[str] = None
    telefono: Optional[str] = None
    correo: Optional[str] = None


class MobileAppointmentIn(BaseModel):
    nombre: str
    celular: str
    fecha: date
    hora: str


class MobileRescheduleIn(BaseModel):
    fecha: date
    hora: str


class MobileUnlinkedUpdateIn(MobileRescheduleIn):
    nombre: Optional[str] = None
    celular: Optional[str] = None


class AppointmentIn(BaseModel):
    patient_id: int
    fecha: date
    hora: str
    nota: Optional[str] = None


class AppointmentUpdateIn(BaseModel):
    fecha: date
    hora: str
    nota: Optional[str] = None


class ConfirmafyAttendedIn(BaseModel):
    patient_id: int


class PasswordIn(BaseModel):
    current_password: str
    new_password: str


class ProcedureIn(BaseModel):
    nombre: str
    valor_default: Optional[float] = None


class ProcedureValueIn(BaseModel):
    valor_default: Optional[float] = None


class WindowModeIn(BaseModel):
    mode: str


class PreferencesIn(BaseModel):
    print_mode: Optional[str] = None
    printer: Optional[str] = None
    show_blood_pressure: Optional[bool] = None
    confirm_delete: Optional[bool] = None
    auto_login: Optional[bool] = None


class ReceiptPrintIn(BaseModel):
    fecha: str
    nombre: str
    fecha_nacimiento: Optional[str] = None
    celular: Optional[str] = None
    turno: Optional[int] = None
    is_new: bool = False


LAUNCHER_SETTINGS_PATH = os.path.join(DATA_DIR, "launcher_settings.json")
APP_SETTINGS_PATH = os.path.join(DATA_DIR, "app_settings.json")
DESKTOP_RUNTIME_STATUS_PATH = os.path.join(DATA_DIR, "desktop_runtime_status.json")
VALID_WINDOW_MODES = {"AUTO", "WEBVIEW2", "EDGE"}
EXTERNAL_DESTINATIONS = {
    "confirmafy": "https://confirmafy.com/app/calendar",
    "facturero": "https://app.factureromovil.com/documentos/facturas",
    "azur": "https://azur.com.ec/plataforma",
}


def _read_json_file(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            value = json.load(fh)
            return value if isinstance(value, dict) else {}
    except Exception:
        return {}


DEFAULT_APP_PREFERENCES = {
    "print_mode": "PREVIEW",
    "printer": "",
    "show_blood_pressure": True,
    "confirm_delete": True,
    "auto_login": True,
}
VALID_PRINT_MODES = {"PREVIEW", "DIRECT"}


def _app_preferences() -> dict:
    raw = _read_json_file(APP_SETTINGS_PATH)
    mode = str(raw.get("print_mode") or DEFAULT_APP_PREFERENCES["print_mode"]).strip().upper()
    if mode not in VALID_PRINT_MODES:
        mode = "PREVIEW"
    printer = str(raw.get("printer") or "").strip()
    show_blood_pressure = raw.get("show_blood_pressure")
    if not isinstance(show_blood_pressure, bool):
        show_blood_pressure = True
    confirm_delete = raw.get("confirm_delete")
    if not isinstance(confirm_delete, bool):
        confirm_delete = True
    auto_login = raw.get("auto_login")
    if not isinstance(auto_login, bool):
        auto_login = True
    return {
        "print_mode": mode,
        "printer": printer,
        "show_blood_pressure": show_blood_pressure,
        "confirm_delete": confirm_delete,
        "auto_login": auto_login,
        "paper_width_mm": 80,
    }


def _save_app_preferences(data: PreferencesIn) -> dict:
    current = _app_preferences()
    if data.print_mode is not None:
        mode = str(data.print_mode or "").strip().upper()
        if mode not in VALID_PRINT_MODES:
            raise HTTPException(400, "Modo de impresión no válido")
        current["print_mode"] = mode
    if data.printer is not None:
        current["printer"] = str(data.printer or "").strip()
    if data.show_blood_pressure is not None:
        current["show_blood_pressure"] = bool(data.show_blood_pressure)
    if data.confirm_delete is not None:
        current["confirm_delete"] = bool(data.confirm_delete)
    if data.auto_login is not None:
        current["auto_login"] = bool(data.auto_login)
    persist = {k: current[k] for k in ("print_mode", "printer", "show_blood_pressure", "confirm_delete", "auto_login")}
    os.makedirs(os.path.dirname(APP_SETTINGS_PATH), exist_ok=True)
    tmp = APP_SETTINGS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(persist, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, APP_SETTINGS_PATH)
    return current


def _windows_printer_info() -> dict:
    if os.name != "nt":
        return {"supported": False, "default_printer": "", "printers": [], "error": "Impresión directa disponible en Windows"}
    try:
        import clr  # type: ignore
        clr.AddReference("System.Drawing")
        from System.Drawing.Printing import PrinterSettings  # type: ignore
        settings = PrinterSettings()
        default = str(settings.PrinterName or "")
        printers = [str(name) for name in PrinterSettings.InstalledPrinters]
        return {"supported": True, "default_printer": default, "printers": printers, "error": None}
    except Exception as exc:
        return {"supported": False, "default_printer": "", "printers": [], "error": str(exc)}


def _print_receipt_windows(payload: ReceiptPrintIn, printer_name: str = "", show_blood_pressure: bool = True) -> str:
    if os.name != "nt":
        raise RuntimeError("La impresión directa solo está disponible en Windows")
    import clr  # type: ignore
    clr.AddReference("System.Drawing")
    from System.Drawing import Font, FontStyle, Brushes, Pen, Image, StringFormat, StringAlignment, RectangleF  # type: ignore
    from System.Drawing.Printing import PrintDocument, PrinterSettings, PaperSize, Margins  # type: ignore

    available = [str(name) for name in PrinterSettings.InstalledPrinters]
    chosen = str(printer_name or "").strip() or str(PrinterSettings().PrinterName or "")
    if not chosen:
        raise RuntimeError("Windows no tiene una impresora predeterminada")
    if available and chosen not in available:
        raise RuntimeError(f"La impresora ‘{chosen}’ ya no está disponible")

    doc = PrintDocument()
    doc.PrinterSettings.PrinterName = chosen
    if not doc.PrinterSettings.IsValid:
        raise RuntimeError(f"Windows no puede usar la impresora ‘{chosen}’")
    doc.DocumentName = "Recibo de consulta médica"
    doc.OriginAtMargins = True
    # Las unidades son centésimas de pulgada: 315 ≈ 80 mm. El alto queda
    # holgado y el driver térmico puede cortar al terminar el contenido.
    doc.DefaultPageSettings.PaperSize = PaperSize("Recibo 80 mm", 315, 600)
    doc.DefaultPageSettings.Margins = Margins(8, 8, 8, 8)

    fonts = []
    image_holder = {"img": None}

    def font(size, bold=False):
        f = Font("Arial", float(size), FontStyle.Bold if bold else FontStyle.Regular)
        fonts.append(f)
        return f

    f_title = font(11, True)
    f_label = font(7.4, True)
    f_text = font(8.4, True)
    f_name = font(9.3, True)
    f_turn = font(11, True)
    f_check = font(6.9, True)
    from System.Drawing import Color  # type: ignore
    pen = Pen(Color.Black, 1.0)

    def on_print_page(sender, e):
        g = e.Graphics
        width = float(e.MarginBounds.Width)
        y = 0.0
        center = StringFormat()
        center.Alignment = StringAlignment.Center
        center.LineAlignment = StringAlignment.Near

        logo_path = os.path.join(BASE_DIR, "static", "doctor_isotype.png")
        if os.path.exists(logo_path):
            try:
                image_holder["img"] = Image.FromFile(logo_path)
                g.DrawImage(image_holder["img"], 2.0, 2.0, 38.0, 38.0)
            except Exception:
                image_holder["img"] = None
        g.DrawString("RECIBO DE\nCONSULTA MÉDICA", f_title, Brushes.Black, RectangleF(43.0, 5.0, width - 43.0, 38.0), center)
        y = 45.0
        g.DrawLine(pen, 0.0, y, width, y)

        def row(label, value, value_font=None, dotted=False):
            nonlocal y
            y += 7.0
            g.DrawString(str(label), f_label, Brushes.Black, 0.0, y)
            g.DrawString(str(value or ""), value_font or f_text, Brushes.Black, 86.0, y - 1.0)
            y += 18.0
            g.DrawLine(pen, 0.0, y, width, y)

        row("Fecha:", payload.fecha, f_text)
        y += 7.0
        g.DrawString("Nombre", f_label, Brushes.Black, RectangleF(0.0, y, width, 14.0), center)
        y += 13.0
        name = str(payload.nombre or "SIN NOMBRE").upper()
        name_fmt = StringFormat(); name_fmt.Alignment = StringAlignment.Center
        name_size = g.MeasureString(name, f_name, int(width))
        g.DrawString(name, f_name, Brushes.Black, RectangleF(0.0, y, width, max(24.0, float(name_size.Height) + 3.0)), name_fmt)
        y += max(22.0, float(name_size.Height) + 5.0)
        g.DrawLine(pen, 0.0, y, width, y)
        if payload.is_new and payload.fecha_nacimiento:
            row("Nacimiento:", payload.fecha_nacimiento, f_text)
        if show_blood_pressure:
            y += 7.0
            g.DrawString("Presión Arterial:", f_label, Brushes.Black, 0.0, y + 5.0)
            g.DrawRectangle(pen, 105.0, y, 52.0, 22.0)
            y += 29.0
            g.DrawLine(pen, 0.0, y, width, y)
        row("Teléfono:", payload.celular or "Sin registrar", f_text)
        if payload.turno:
            row("Turno:", str(payload.turno), f_turn)
        y += 9.0
        box = 15.0
        left_x = 18.0
        right_x = width / 2 + 8.0
        for x, label, checked in ((left_x, "PRIMERO", payload.is_new), (right_x, "SUBSECUENTE", not payload.is_new)):
            g.DrawRectangle(pen, x, y, box, box)
            if checked:
                g.DrawString("X", f_text, Brushes.Black, x + 2.0, y - 1.5)
            g.DrawString(label, f_check, Brushes.Black, x + box + 4.0, y + 2.0)
        e.HasMorePages = False

    doc.PrintPage += on_print_page
    try:
        doc.Print()
    finally:
        try:
            doc.PrintPage -= on_print_page
        except Exception:
            pass
        if image_holder.get("img") is not None:
            try: image_holder["img"].Dispose()
            except Exception: pass
        for f in fonts:
            try: f.Dispose()
            except Exception: pass
        try: pen.Dispose()
        except Exception: pass
        try: doc.Dispose()
        except Exception: pass
    return chosen


def _launcher_window_mode() -> str:
    mode = str(_read_json_file(LAUNCHER_SETTINGS_PATH).get("window_mode") or "AUTO").strip().upper()
    return mode if mode in VALID_WINDOW_MODES else "AUTO"


def _save_launcher_window_mode(mode: str) -> str:
    value = str(mode or "").strip().upper()
    if value not in VALID_WINDOW_MODES:
        raise HTTPException(400, "Modo de ventana no válido")
    os.makedirs(os.path.dirname(LAUNCHER_SETTINGS_PATH), exist_ok=True)
    temp_path = LAUNCHER_SETTINGS_PATH + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as fh:
        json.dump({"window_mode": value}, fh, ensure_ascii=False, indent=2)
    os.replace(temp_path, LAUNCHER_SETTINGS_PATH)
    return value


def _edge_executable_path() -> Optional[str]:
    if os.name != "nt":
        return None
    candidates = []
    for env_name in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        root = os.getenv(env_name)
        if not root:
            continue
        candidates.extend([
            os.path.join(root, "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(root, "Microsoft", "Edge Beta", "Application", "msedge.exe"),
        ])
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    return shutil.which("msedge") or shutil.which("msedge.exe")


def _open_external_destination(target: str) -> str:
    url = EXTERNAL_DESTINATIONS.get(str(target or "").strip().lower())
    if not url:
        raise HTTPException(404, "Destino externo no permitido")
    try:
        edge = _edge_executable_path()
        if edge:
            subprocess.Popen([edge, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            webbrowser.open(url, new=2)
    except Exception as exc:
        raise HTTPException(500, f"No se pudo abrir el navegador: {exc}")
    return url


def _desktop_runtime_info() -> dict:
    status = _read_json_file(DESKTOP_RUNTIME_STATUS_PATH)
    return {
        "mode": _launcher_window_mode(),
        "webview2": status.get("webview2"),
        "pywebview": status.get("pywebview"),
        "edge": status.get("edge"),
        "checked_at": status.get("checked_at"),
        "message": status.get("message") or "Se comprobará automáticamente al abrir Recepción.",
        "error": str(status.get("error") or "")[:240],
    }


@app.get("/", response_class=HTMLResponse)
def home():
    with open(os.path.join(BASE_DIR, "static", "index.html"), encoding="utf-8") as f:
        html = f.read()
    addon = (
        '<link rel="stylesheet" href="/v458/settings.css?v=4.3.58">'
        '<script defer src="/v458/settings.js?v=4.3.58"></script>'
        '<link rel="stylesheet" href="/v459/settings.css?v=4.3.59">'
        '<script defer src="/v459/settings.js?v=4.3.59"></script>'
        '<link rel="stylesheet" href="/v460/overlay.css?v=4.3.72">'
        '<script defer src="/v460/overlay.js?v=4.3.72"></script>'
    )
    return html.replace("</head>", addon + "</head>", 1) if "</head>" in html else html + addon


@app.get("/api/version")
def app_version():
    return {"version": APP_VERSION, "pid": os.getpid()}


def _connectivity_payload(configured: Optional[bool] = None, online: Optional[bool] = None, lite: bool = False) -> dict:
    configured = cloud_configured() if configured is None else bool(configured)
    with _state_lock:
        state_online = bool(_state.get("online"))
        idle = bool(_state.get("client_idle"))
        last_success_ts = float(_state.get("last_success") or 0)
        failures = int(_state.get("consecutive_failures") or 0)
        probe_ms = _state.get("last_probe_ms")
        last_error = str(_state.get("last_error") or "")[:160]
    online = state_online if online is None else bool(online)
    pending = queue_count()
    base = {
        "configured": configured,
        "online": online,
        "idle": idle,
        "idle_after_seconds": IDLE_AFTER_SECONDS,
        "pending": pending,
        "synced_now": 0,
        "last_success": datetime.fromtimestamp(last_success_ts).isoformat(timespec="seconds") if last_success_ts else None,
        "consecutive_failures": failures,
        "probe_ms": probe_ms,
        "last_error": last_error,
    }
    if lite:
        # El indicador pasivo no necesita recorrer respaldos ni leer el detalle de
        # la cola. En la PC vieja esto evita I/O local periódico sin perder el
        # estado que se muestra en la barra lateral.
        return base
    with LocalSessionLocal() as ldb:
        last_sync = ldb.get(CacheMeta, "last_sync")
        last_backup = ldb.get(CacheMeta, "last_backup")
    try:
        backup_count = len(list(Path(BACKUP_DIR).glob("recepcion_backup_*.db")))
    except Exception:
        backup_count = 0
    base.update({
        "errors": queue_errors(),
        "last_sync": last_sync.value if last_sync else None,
        "last_backup": last_backup.value if last_backup else None,
        "backup_count": backup_count,
    })
    return base


@app.get("/api/connectivity")
def connectivity(force: bool = False, lite: bool = False):
    configured = cloud_configured()
    # v4.0: consultar el indicador NO toca Neon. Solo una acción explícita
    # (Actualizar estado, Reconectar, volver de AFK o una operación real) fuerza
    # una sonda. Esto permite que Neon entre en suspensión cuando no se usa.
    if configured and force:
        with _state_lock:
            _state["client_idle"] = False
            _state["last_activity"] = time.time()
        online = check_cloud(force=True)
        if online and queue_count() == 0:
            schedule_local_cache_refresh(force=False, cloud_already_checked=True)
    else:
        with _state_lock:
            online = bool(_state.get("online")) if configured else False
    return _connectivity_payload(configured=configured, online=online, lite=lite)


@app.post("/api/power/idle")
def enter_power_idle(user: User = Depends(current_user)):
    # Antes de dormir intentamos proteger cualquier cambio local pendiente una
    # sola vez. Si no hay Internet, queda seguro en SQLite y no se descarta.
    sync_result = None
    pending = queue_count()
    if pending > 0 and cloud_configured():
        try:
            sync_result = process_offline_queue()
        except Exception:
            sync_result = None
    with _state_lock:
        now = time.time()
        _state["client_idle"] = True
        _state["last_activity"] = now
        _state["idle_since"] = now
    try:
        if cloud_engine is not None:
            cloud_engine.dispose()
    except Exception:
        pass
    payload = _connectivity_payload()
    payload["idle"] = True
    if sync_result:
        payload["sync"] = sync_result
    return payload


@app.post("/api/power/wake")
def leave_power_idle(user: User = Depends(current_user)):
    now = time.time()
    with _state_lock:
        idle_since = float(_state.get("idle_since") or 0)
        idle_for = max(0.0, now - idle_since) if idle_since else 0.0
        _state["client_idle"] = False
        _state["last_activity"] = now
        _state["idle_since"] = 0.0
    configured = cloud_configured()
    pending = queue_count()
    with _state_lock:
        cached_online = bool(_state.get("online")) if configured else False
    cloud_wake_needed = bool(configured and (pending > 0 or idle_for >= REMOTE_REFRESH_IDLE_SECONDS))
    online = check_cloud(force=True) if cloud_wake_needed else cached_online
    sync_result = None
    if online and pending > 0:
        sync_result = process_offline_queue(cloud_already_checked=True)
        pending = queue_count()
    refresh_scheduled = False
    refresh_kind = "none"
    if online and pending == 0 and idle_for >= REMOTE_REFRESH_IDLE_SECONDS:
        last_full = effective_cache_refresh_ts()
        full_due = (not last_full) or (time.time() - last_full >= CACHE_REFRESH_SECONDS)
        if full_due:
            refresh_scheduled = schedule_local_cache_refresh(force=False, cloud_already_checked=True)
            refresh_kind = "full" if refresh_scheduled else "none"
        else:
            refresh_scheduled = schedule_remote_agenda_refresh(force=False, cloud_already_checked=True)
            refresh_kind = "agenda" if refresh_scheduled else "none"
    payload = _connectivity_payload(configured=configured, online=online)
    payload["idle_for_seconds"] = round(idle_for)
    payload["cache_refresh_scheduled"] = bool(refresh_scheduled)
    payload["cache_refresh_kind"] = refresh_kind
    payload["cloud_wake_skipped"] = bool(configured and not cloud_wake_needed)
    if sync_result:
        payload["sync"] = sync_result
    return payload


@app.get("/api/window-mode")
def get_window_mode(user: User = Depends(current_user)):
    return _desktop_runtime_info()


@app.post("/api/window-mode")
def set_window_mode(data: WindowModeIn, user: User = Depends(current_user)):
    mode = _save_launcher_window_mode(data.mode)
    info = _desktop_runtime_info()
    info["mode"] = mode
    return info


@app.get("/api/preferences")
def get_preferences(user: User = Depends(current_user)):
    return _app_preferences()


@app.post("/api/preferences")
def set_preferences(data: PreferencesIn, user: User = Depends(current_user)):
    return _save_app_preferences(data)


@app.get("/api/printing/status")
def printing_status(user: User = Depends(current_user)):
    info = _windows_printer_info()
    prefs = _app_preferences()
    selected = prefs.get("printer") or info.get("default_printer") or ""
    info.update({
        "mode": prefs.get("print_mode"),
        "selected_printer": selected,
        "paper_width_mm": 80,
    })
    return info


@app.post("/api/printing/receipt")
def print_receipt(data: ReceiptPrintIn, user: User = Depends(current_user)):
    prefs = _app_preferences()
    printer = str(prefs.get("printer") or "").strip()
    try:
        used = _print_receipt_windows(data, printer, bool(prefs.get("show_blood_pressure", True)))
    except Exception as exc:
        raise HTTPException(500, f"No se pudo imprimir directamente: {exc}")
    return {"ok": True, "printer": used, "paper_width_mm": 80}


@app.get("/api/system-status")
def system_status(user: User = Depends(current_user)):
    cloud = connectivity(force=False)
    runtime = _desktop_runtime_info()
    printing = _windows_printer_info()
    prefs = _app_preferences()
    return {
        "cloud": cloud,
        "runtime": runtime,
        "printing": printing,
        "preferences": prefs,
    }


@app.post("/api/open-external/{target}")
def open_external(target: str, user: User = Depends(current_user)):
    return {"ok": True, "url": _open_external_destination(target)}


@app.post("/api/offline/sync")
def manual_sync(user: User = Depends(current_user)):
    return process_offline_queue()


@app.get("/api/offline/queue")
def offline_queue_review(user: User = Depends(current_user)):
    items = queue_review_items()
    return {"pending": len(items), "items": items}


@app.post("/api/offline/queue/retry")
def offline_queue_retry(user: User = Depends(current_user)):
    return process_offline_queue()


def _queue_dependent_ids(db: Session, target: OfflineQueue) -> list[int]:
    """Devuelve operaciones posteriores que dependen de un alta local pendiente."""
    if target.local_entity_id is None:
        return []
    local_id = int(target.local_entity_id)
    kind = None
    payload_key = None
    if target.operation == "patient.create":
        kind, payload_key = "patient", "patient_id"
    elif target.operation == "visit.create":
        kind, payload_key = "visit", "visit_id"
    elif target.operation == "appointment.create":
        kind, payload_key = "appointment", "appointment_id"
    else:
        return []

    deps = []
    later = list(db.scalars(select(OfflineQueue).where(OfflineQueue.id > target.id).order_by(OfflineQueue.id.asc())))
    for row in later:
        try:
            payload = json.loads(row.payload or "{}")
        except Exception:
            payload = {}
        if payload.get(payload_key) is not None:
            try:
                if int(payload.get(payload_key)) == local_id:
                    deps.append(int(row.id)); continue
            except Exception:
                pass
        if row.entity == kind and row.local_entity_id is not None:
            try:
                if int(row.local_entity_id) == local_id:
                    deps.append(int(row.id))
            except Exception:
                pass
    return deps


def _refresh_after_queue_discard() -> bool:
    """Si ya no hay cola, vuelve a la copia canónica de Neon para quitar cambios locales descartados."""
    if queue_count(force=True) != 0:
        return False
    try:
        with LocalSessionLocal() as ldb:
            ldb.execute(delete(OfflineIdMap))
            ldb.commit()
    except Exception:
        pass
    if cloud_configured() and check_cloud(force=True):
        return bool(refresh_local_cache(force=True, cloud_already_checked=True))
    return False


@app.delete("/api/offline/queue/{queue_id}")
def offline_queue_discard_one(queue_id: int, user: User = Depends(current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Solo el administrador puede descartar cambios pendientes")
    with LocalSessionLocal() as db:
        q = db.get(OfflineQueue, int(queue_id))
        if not q:
            raise HTTPException(404, "Ese cambio pendiente ya no existe")
        deps = _queue_dependent_ids(db, q)
        if deps:
            raise HTTPException(409, f"Este cambio tiene {len(deps)} cambio(s) posterior(es) que dependen de él. Descarta primero los posteriores o usa ‘Descartar todos’.")
        label = q.operation
        db.delete(q)
        audit(db, user, "descartar_cambio_offline", f"Cola {queue_id}: {label}")
        db.commit()
    invalidate_queue_count()
    pending = queue_count(force=True)
    refreshed = _refresh_after_queue_discard() if pending == 0 else False
    return {"ok": True, "discarded": 1, "pending": pending, "cache_refreshed": refreshed}


@app.delete("/api/offline/queue")
def offline_queue_discard_all(user: User = Depends(current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Solo el administrador puede descartar todos los cambios pendientes")
    with LocalSessionLocal() as db:
        count = int(db.scalar(select(func.count(OfflineQueue.id))) or 0)
        db.execute(delete(OfflineQueue))
        db.execute(delete(OfflineIdMap))
        audit(db, user, "descartar_todos_cambios_offline", f"{count} cambio(s) descartados")
        db.commit()
    invalidate_queue_count()
    refreshed = _refresh_after_queue_discard()
    return {"ok": True, "discarded": count, "pending": 0, "cache_refreshed": refreshed}


@app.post("/api/connectivity/recover")
def recover_connectivity(user: User = Depends(current_user)):
    """Reinicia el pool de Neon, comprueba la nube y sincroniza la cola local."""
    if not cloud_configured():
        return {"configured": False, "online": False, "pending": queue_count(), "last_error": "Nube no configurada"}
    try:
        cloud_engine.dispose()
    except Exception:
        pass
    online = check_cloud(force=True)
    sync_result = None
    if online and queue_count() > 0:
        sync_result = process_offline_queue(cloud_already_checked=True)
    status = connectivity(force=False)
    status["recovery"] = sync_result
    return status


@app.post("/api/backup/now")
@app.post("/api/data-protection/backup")
def backup_now(user: User = Depends(current_user)):
    path = create_local_backup_snapshot(force=True)
    if not path:
        raise HTTPException(500, "No se pudo crear el respaldo local")
    with LocalSessionLocal() as ldb:
        last_backup = ldb.get(CacheMeta, "last_backup")
    return {
        "ok": True,
        "last_backup": last_backup.value if last_backup else datetime.now().isoformat(timespec="seconds"),
        "backup_count": len(list(Path(BACKUP_DIR).glob("recepcion_backup_*.db"))),
    }


@app.post("/api/app/restart")
def restart_app(user: User = Depends(current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Solo el administrador puede reiniciar el programa")

    # Reinicio robusto: el helper espera a que el puerto local quede realmente
    # libre antes de levantar el nuevo backend. Evita que el segundo reinicio
    # falle por una carrera entre el proceso saliente y el entrante.
    app_path = os.path.join(BASE_DIR, "app.py")
    python_exe = sys.executable
    helper_code = f"""
import os, subprocess, time, socket
python_exe = {python_exe!r}
app_path = {app_path!r}
base_dir = {BASE_DIR!r}
deadline = time.time() + 15.0
while time.time() < deadline:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.25)
    try:
        busy = sock.connect_ex(('127.0.0.1', {LOCAL_HTTP_PORT})) == 0
    finally:
        sock.close()
    if not busy:
        break
    time.sleep(0.25)
time.sleep(0.25)
flags = 0
if os.name == 'nt':
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0) | getattr(subprocess, 'DETACHED_PROCESS', 0)
env = os.environ.copy()
env['RP_DESKTOP_LAUNCH'] = '1'
subprocess.Popen([python_exe, app_path], cwd=base_dir, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags, close_fds=True)
"""
    flags = 0
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    try:
        subprocess.Popen(
            [python_exe, "-c", helper_code],
            cwd=BASE_DIR,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=flags, close_fds=True,
        )
    except Exception as e:
        raise HTTPException(500, f"No se pudo preparar el reinicio: {e}")

    old_pid = os.getpid()
    threading.Timer(0.45, lambda: os._exit(0)).start()
    return {"ok": True, "version": APP_VERSION, "pid": old_pid}


@app.post("/api/login")
def login(data: LoginIn, response: Response, db: Session = Depends(get_db)):
    try:
        user = db.scalar(select(User).where(User.username == data.username))
    except Exception:
        user = None
    if not user and not is_offline_db(db):
        # Si la conexión cayó justo en el login, intentamos cache local.
        with LocalSessionLocal() as ldb:
            user = ldb.scalar(select(User).where(User.username == data.username))
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "Usuario o contraseña incorrectos")
    token = secrets.token_urlsafe(32)
    TOKENS[token] = user.username
    with _user_cache_lock:
        _user_cache[user.username] = (time.time(), _user_snapshot(user))
    response.set_cookie("rp_session", token, httponly=True, samesite="lax", secure=False, max_age=60 * 60 * 12)
    return {"ok": True, "username": user.username, "offline": is_offline_db(db)}


@app.post("/api/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get("rp_session")
    TOKENS.pop(token or "", None)
    response.delete_cookie("rp_session")
    return {"ok": True}


@app.get("/api/me")
def me(user: User = Depends(current_user)):
    return {"username": user.username, "role": user.role, "auto_login": _auto_login_enabled()}


@app.get("/api/bootstrap")
def bootstrap(anchor: date = date.today(), db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Datos mínimos para abrir Recepción con un solo checkout/conexión a la nube."""
    proc_rows = list(db.scalars(select(Procedure).where(Procedure.activo == 1).order_by(Procedure.nombre)))
    last_refresh = effective_cache_refresh_ts()
    cache_stale = bool(not last_refresh or (time.time() - last_refresh >= CACHE_REFRESH_SECONDS))
    return {
        "cache_stale": cache_stale,
        "home": home_week(anchor=anchor, db=db, user=user),
        "procedures": [
            {"id": x.id, "nombre": str(x.nombre or "").upper(), "valor_default": float(x.valor_default) if x.valor_default is not None else None}
            for x in proc_rows
        ],
        "pending": (lambda billing: {
            "billing": billing["total"],
            "billing_pending": billing["pending"],
            "billing_approved": billing["approved"],
            "agenda": int(db.scalar(select(func.count(Appointment.id)).where(Appointment.estado == "PENDIENTE")) or 0),
        })(_billing_action_counts(db)),
    }




@app.post("/api/historical/import")
async def import_historical_registry(
    file: UploadFile = File(...),
    user: User = Depends(current_user),
):
    """Restaura el índice histórico exclusivamente en SQLite local.

    El CSV llega desde el navegador de la PC de Recepción, se valida en memoria y
    no se sube a Neon ni se conserva como archivo dentro del programa. Solo se
    reemplaza la tabla historical_patients cuando el archivo completo ya pasó
    todas las validaciones.
    """
    filename = str(file.filename or "").strip()
    if not filename.lower().endswith(".csv"):
        raise HTTPException(400, "Selecciona el archivo histórico CSV preparado para Recepción.")
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "El archivo histórico está vacío.")
    if len(raw) > 5_000_000:
        raise HTTPException(400, "El archivo histórico supera el tamaño esperado.")
    try:
        content = raw.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content))
    except Exception:
        raise HTTPException(400, "No se pudo leer el archivo histórico como CSV.")

    required = {"source_key", "nombre", "search_text", "first_year", "last_year"}
    fields = {str(x or "").strip() for x in (reader.fieldnames or [])}
    if not required.issubset(fields):
        raise HTTPException(400, "El archivo no corresponde al histórico 2020–2025 de Recepción.")

    parsed = []
    seen = set()
    for row in reader:
        name = " ".join(str(row.get("nombre") or "").split()).upper()
        if not name:
            continue
        source_key = str(row.get("source_key") or "").strip().lower()
        if not re.fullmatch(r"[0-9a-f]{40}", source_key):
            source_key = hashlib.sha1(("HIST2020-2025|" + normalize_lookup_name(name)).encode("utf-8")).hexdigest()
        if source_key in seen:
            continue
        try:
            first_year = int(row.get("first_year") or 2020)
            last_year = int(row.get("last_year") or 2025)
        except Exception:
            continue
        if not (2020 <= first_year <= 2025 and 2020 <= last_year <= 2025 and first_year <= last_year):
            continue
        exact = None
        raw_date = str(row.get("last_visit_date") or "").strip()
        if raw_date:
            try:
                exact = date.fromisoformat(raw_date[:10])
            except Exception:
                exact = None
        try:
            row_count = max(1, int(row.get("row_count") or 1))
        except Exception:
            row_count = 1
        seen.add(source_key)
        parsed.append({
            "source_key": source_key,
            "nombre": name[:240],
            "search_text": str(row.get("search_text") or name).upper(),
            "cedula": str(row.get("cedula") or "").strip()[:30] or None,
            "celular": str(row.get("celular") or "").strip()[:40] or None,
            "correo": str(row.get("correo") or "").strip().lower()[:220] or None,
            "lugar": " ".join(str(row.get("lugar") or "").split()).upper()[:160] or None,
            "first_year": first_year,
            "last_year": last_year,
            "last_visit_date": exact,
            "row_count": row_count,
            "aliases": str(row.get("aliases") or "").strip() or None,
            "phones": str(row.get("phones") or "").strip() or None,
            "emails": str(row.get("emails") or "").strip() or None,
            "cedulas": str(row.get("cedulas") or "").strip() or None,
        })

    # Este índice real contiene miles de fichas. No permitimos reemplazarlo con
    # un CSV equivocado o incompleto que accidentalmente deje la tabla vacía.
    if len(parsed) < 1000:
        raise HTTPException(400, f"El archivo parece incompleto: solo contiene {len(parsed)} pacientes válidos.")

    try:
        with LocalSessionLocal() as ldb:
            ldb.execute(delete(HistoricalPatient))
            ldb.execute(insert(HistoricalPatient), parsed)
            marker = ldb.get(CacheMeta, HISTORICAL_REGISTRY_MARKER)
            if marker:
                marker.value = "1"
            else:
                ldb.add(CacheMeta(key=HISTORICAL_REGISTRY_MARKER, value="1"))
            ldb.commit()
    except Exception as exc:
        raise HTTPException(500, f"No se pudo guardar el histórico local: {str(exc)[:140]}")

    dated = sum(1 for x in parsed if x.get("last_visit_date"))
    return {
        "ok": True,
        "loaded": len(parsed),
        "with_exact_date": dated,
        "first_year": min(x["first_year"] for x in parsed),
        "last_year": max(x["last_year"] for x in parsed),
        "local_only": True,
    }


@app.get("/api/historical/stats")
def historical_stats(user: User = Depends(current_user)):
    try:
        with LocalSessionLocal() as db:
            total = int(db.scalar(select(func.count(HistoricalPatient.id))) or 0)
            first = db.scalar(select(func.min(HistoricalPatient.first_year)))
            last = db.scalar(select(func.max(HistoricalPatient.last_year)))
            return {"total": total, "first_year": first, "last_year": last, "local_only": True}
    except Exception:
        return {"total": 0, "first_year": None, "last_year": None, "local_only": True}


@app.get("/api/patients")
def search_patients(q: str = "", limit: int = 30, mode: str = "", db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Buscador local-first. Sin texto ni filtro no devuelve una lista aleatoria."""
    lim = min(max(int(limit or 30), 1), 100)
    raw = " ".join(str(q or "").strip().upper().split())
    mode = str(mode or "").strip().lower()

    last_visit = (
        select(func.max(Visit.fecha))
        .where(Visit.patient_id == Patient.id)
        .correlate(Patient)
        .scalar_subquery()
    )

    if not raw and not mode:
        return []

    if mode == "historical":
        # Este filtro es un visor del archivo histórico, no una lista de "sin vincular".
        # Debe mostrar TODO el índice 2020–2025 aunque la persona ya tenga ficha actual.
        # Al abrir un histórico, activate_historical_patient() sigue reutilizando una
        # coincidencia segura y evita crear duplicados.
        try:
            with LocalSessionLocal() as ldb:
                hist_rows = list(ldb.scalars(
                    select(HistoricalPatient)
                    .order_by(HistoricalPatient.last_visit_date.desc().nullslast(), HistoricalPatient.last_year.desc(), HistoricalPatient.nombre)
                    .limit(lim)
                ))
                return [historical_dict(h) for h in hist_rows]
        except Exception:
            return []

    if mode == "review":
        _auto_link_safe_review_duplicates(db, user)
        return _patient_review_rows(db, lim)
    if mode == "confirmafy":
        return _patient_review_rows(db, lim, confirmafy_only=True)

    stmt = select(Patient, last_visit.label("ultima_atencion"))
    if mode == "recent":
        stmt = stmt.where(last_visit.is_not(None)).order_by(last_visit.desc(), Patient.id.desc()).limit(lim)
    elif mode == "incomplete":
        stmt = stmt.where(or_(
            Patient.cedula.is_(None), Patient.cedula == "",
            Patient.celular.is_(None), Patient.celular == "",
            Patient.correo.is_(None), Patient.correo == "",
        )).order_by(Patient.nombre).limit(lim)
    else:
        if len(raw) < 2:
            return []
        tokens = [token for token in normalize_lookup_name(raw).split(" ") if token][:8]
        for token in tokens:
            pattern = f"%{token}%"
            stmt = stmt.where(or_(
                Patient.cedula.ilike(pattern),
                Patient.nombre.ilike(pattern),
                Patient.celular.ilike(pattern),
                Patient.correo.ilike(pattern),
            ))
        stmt = stmt.order_by(Patient.nombre).limit(lim)

    rows = db.execute(stmt).all()
    current = [{**p_dict(p), "ultima_atencion": ultima, "historical": False} for p, ultima in rows]
    if raw and not mode:
        historical = search_historical_patients(raw, limit=min(10, max(4, int(lim // 2) or 4)))
        result = current + historical
        # Si una palabra fue dictada con una pequeña diferencia (JHONNY/JHONY),
        # añadimos coincidencias parecidas al final. Todo ocurre sobre SQLite.
        name_tokens = [x for x in normalize_lookup_name(raw).split() if len(x) >= 3]
        if len(name_tokens) >= 2 and len(result) < lim + 6:
            any_stmt = select(Patient).where(or_(*[Patient.nombre.ilike(f"%{t}%") for t in name_tokens[:5]])).limit(100)
            already_current = {int(x.get("id")) for x in result if x.get("id") is not None}
            proxy = Patient(id=-1, nombre=raw, cedula=None, celular=None, correo=None, lugar=None, notas=None, fecha_nacimiento=None)
            fuzzy_current = []
            for p in db.scalars(any_stmt):
                if int(p.id) in already_current:
                    continue
                score, why = patient_similarity(proxy, p)
                if score >= 0.74:
                    fuzzy_current.append(({**p_dict(p), "ultima_atencion": None, "historical": False, "similarity": round(score, 3), "similar_reason": why}, score))
            fuzzy_current.sort(key=lambda x: (-x[1], str(x[0].get("nombre") or "")))
            result.extend([x[0] for x in fuzzy_current[:6]])
            existing_h = {int(x.get("historical_id")) for x in result if x.get("historical_id") is not None}
            for h in _historical_similarity_candidates(raw, 6):
                if int(h.get("historical_id") or 0) not in existing_h:
                    result.append(h)
        return result[: min(lim + 10, 110)]
    return current


@app.get("/api/patients/similar")
def similar_patients(name: str, exclude_id: int = 0, limit: int = 8, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Advertencias de identidad calculadas en SQLite; nunca despierta Neon."""
    raw = " ".join(str(name or "").strip().upper().split())
    if len(normalize_lookup_name(raw)) < 4:
        return {"name_quality": patient_name_quality(raw), "word_count": patient_name_word_count(raw), "matches": []}
    tokens = [x for x in normalize_lookup_name(raw).split() if len(x) >= 3]
    # Preselección por cualquier palabra para no recorrer toda la tabla en cada tecla.
    if tokens:
        stmt = select(Patient).where(or_(*[Patient.nombre.ilike(f"%{t}%") for t in tokens[:5]]))
        candidates = list(db.scalars(stmt.limit(80)))
    else:
        candidates = []
    proxy = Patient(id=-1, nombre=raw, cedula=None, celular=None, correo=None, lugar=None, notas=None, fecha_nacimiento=None)
    matches = []
    for p in candidates:
        if int(p.id) == int(exclude_id or 0):
            continue
        score, why = patient_similarity(proxy, p)
        if score < 0.74:
            continue
        matches.append({**p_dict(p), "historical": False, "similarity": round(score, 3), "similar_reason": why})
    historical_candidates = _historical_similarity_candidates(raw, max(4, int(limit)))
    if historical_candidates and candidates:
        try:
            with LocalSessionLocal() as ldb:
                hids = [int(x.get("historical_id") or 0) for x in historical_candidates if int(x.get("historical_id") or 0)]
                hmap = {int(h.id): h for h in ldb.scalars(select(HistoricalPatient).where(HistoricalPatient.id.in_(hids)))} if hids else {}
            filtered_hist = []
            for item in historical_candidates:
                h = hmap.get(int(item.get("historical_id") or 0))
                # En el modal de atención mostramos la ficha actual una sola vez.
                # El vínculo histórico pendiente seguirá apareciendo en Pacientes -> Por revisar.
                if h and any(int(p.id) != int(exclude_id or 0) and _historical_identity_match(h, p)[0] for p in candidates):
                    continue
                filtered_hist.append(item)
            historical_candidates = filtered_hist
        except Exception:
            pass
    matches.extend(historical_candidates)
    # La lista prioriza fichas actuales; históricos ya vinculados no entran aquí.
    matches.sort(key=lambda x: (-float(x.get("similarity") or 0), 1 if x.get("historical") else 0, str(x.get("nombre") or "")))
    dedup = []
    seen = set()
    for item in matches:
        key = ("h", item.get("historical_id")) if item.get("historical") else ("p", item.get("id"))
        if key in seen:
            continue
        seen.add(key); dedup.append(item)
        if len(dedup) >= min(max(int(limit or 8), 1), 12):
            break
    return {"name_quality": patient_name_quality(raw), "word_count": patient_name_word_count(raw), "matches": dedup}


@app.get("/api/patients/{pid}/review-detail")
def patient_review_detail(pid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Detalle local para revisar una posible ficha duplicada sin consultar Neon."""
    p = db.get(Patient, pid)
    if not p:
        raise HTTPException(404, "Paciente no encontrado")
    st = _confirmafy_patient_status_map(db, [p]).get(int(pid), {})
    last = db.scalar(select(func.max(Visit.fecha)).where(Visit.patient_id == pid))
    tokens = [x for x in normalize_lookup_name(p.nombre).split() if len(x) >= 3]
    if tokens:
        stmt = select(Patient).where(Patient.id != pid).where(or_(*[Patient.nombre.ilike(f"%{t}%") for t in tokens[:5]])).limit(100)
        candidates = list(db.scalars(stmt))
    else:
        candidates = []
    matches = []
    for other in candidates:
        score, why = patient_similarity(p, other)
        if score < 0.72:
            continue
        other_last = db.scalar(select(func.max(Visit.fecha)).where(Visit.patient_id == other.id))
        other_visits = int(db.scalar(select(func.count(Visit.id)).where(Visit.patient_id == other.id)) or 0)
        matches.append({
            **p_dict(other), "similarity": round(score, 3), "similar_reason": why,
            "ultima_atencion": other_last, "visit_count": other_visits,
        })
    matches.extend((_historical_review_matches([p]).get(int(pid)) or []))
    matches.sort(key=lambda x: (-float(x.get("similarity") or 0), 0 if x.get("historical") else 1, str(x.get("nombre") or "")))
    return {
        "patient": {**p_dict(p), "ultima_atencion": last, **st},
        "matches": matches[:10],
    }


@app.post("/api/patients/{pid}/link-historical/{hid}")
def link_historical_to_patient(pid: int, hid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Vincula manualmente un registro 2020–2025 con una ficha actual, sin crear paciente."""
    p = db.get(Patient, pid)
    if not p:
        raise HTTPException(404, "Paciente actual no encontrado")
    with LocalSessionLocal() as ldb:
        h = ldb.get(HistoricalPatient, hid)
        if not h:
            raise HTTPException(404, "Paciente histórico no encontrado")
        existing = ldb.get(HistoricalPatientLink, h.source_key)
        if existing and int(existing.patient_id) != int(pid):
            other = ldb.get(Patient, int(existing.patient_id))
            name = other.nombre if other else f"ID {existing.patient_id}"
            raise HTTPException(409, f"Este histórico ya está vinculado a {name}. Revísalo antes de cambiar el vínculo.")
        snapshot = {
            "source_key": h.source_key, "nombre": h.nombre, "cedula": h.cedula, "celular": h.celular,
            "correo": h.correo, "lugar": h.lugar, "first_year": h.first_year, "last_year": h.last_year,
            "last_visit_date": h.last_visit_date, "aliases": h.aliases, "phones": h.phones,
            "emails": h.emails, "cedulas": h.cedulas,
        }

    hproxy = HistoricalPatient(
        id=hid, source_key=snapshot["source_key"], nombre=snapshot["nombre"], search_text=snapshot["nombre"],
        cedula=snapshot["cedula"], celular=snapshot["celular"], correo=snapshot["correo"], lugar=snapshot["lugar"],
        first_year=int(snapshot["first_year"] or 2020), last_year=int(snapshot["last_year"] or 2025),
        last_visit_date=snapshot["last_visit_date"], row_count=1, aliases=snapshot["aliases"],
        phones=snapshot["phones"], emails=snapshot["emails"], cedulas=snapshot["cedulas"],
    )
    p_ced = re.sub(r"\D", "", p.cedula or "")
    h_ceds = {re.sub(r"\D", "", x) for x in (_pipe_values(snapshot["cedulas"]) or ([snapshot["cedula"]] if snapshot["cedula"] else [])) if re.sub(r"\D", "", x)}
    if p_ced and h_ceds and p_ced not in h_ceds:
        raise HTTPException(409, "La ficha actual y el histórico tienen cédulas diferentes. No se vinculó nada.")
    identity_ok, why = _historical_identity_match(hproxy, p)
    score, labels = _name_similarity(p.nombre, snapshot["nombre"])
    p_phone = normalize_lookup_phone(p.celular)
    h_phones = {normalize_lookup_phone(x) for x in (_pipe_values(snapshot["phones"]) or ([snapshot["celular"]] if snapshot["celular"] else []))}
    same_phone = bool(p_phone and p_phone in h_phones)
    if not identity_ok and not same_phone and score < 0.70:
        raise HTTPException(409, "La coincidencia es demasiado baja para vincular estas fichas. Revisa los nombres antes de continuar.")

    changed = False
    # Solo completamos huecos de datos razonablemente seguros; nunca cambiamos el nombre actual.
    historical_ced = re.sub(r"\D", "", snapshot["cedula"] or "")
    if not p.cedula and len(historical_ced) == 10 and valid_ecuadorian_cedula(historical_ced):
        p.cedula = historical_ced; changed = True
    for field in ("celular", "correo", "lugar"):
        incoming = snapshot.get(field)
        if incoming and not getattr(p, field, None):
            setattr(p, field, incoming); changed = True

    if changed:
        if is_offline_db(db):
            extranjero = bool(p.cedula and not valid_ecuadorian_cedula(str(p.cedula)))
            add_queue(db, "patient.update", "patient", {
                "patient_id": int(p.id), "extranjero": extranjero, "cedula": p.cedula, "nombre": p.nombre,
                "fecha_nacimiento": p.fecha_nacimiento, "celular": p.celular, "correo": p.correo,
                "lugar": p.lugar, "notas": p.notas,
            }, user.username, int(p.id))
            audit(db, user, "vincular_historico_offline", f"Paciente local {p.id} <- histórico {hid}; {why or ','.join(labels[:4])}")
            db.commit()
        else:
            audit(db, user, "vincular_historico", f"Paciente {p.id} <- histórico {hid}; {why or ','.join(labels[:4])}")
            db.commit(); mirror_patient_to_local(p)
    else:
        # El vínculo es puramente local cuando no hay campos vacíos que completar:
        # no hacemos Audit/COMMIT en Neon solo por ocultar el histórico duplicado.
        pass
    _historical_link_patient(snapshot["source_key"], int(p.id))
    return {
        "ok": True, "patient": p_dict(p), "historical_id": int(hid),
        "historical_name": snapshot["nombre"], "data_completed": bool(changed),
        "last_visit_date": snapshot["last_visit_date"],
    }


@app.post("/api/patients")
def create_patient(data: PatientIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    values = normalize_patient_payload(data)
    if not values["nombre"]:
        raise HTTPException(400, "El nombre es obligatorio")
    if values["cedula"]:
        existing = db.scalar(select(Patient).where(Patient.cedula == values["cedula"]))
        if existing:
            raise HTTPException(409, "Ya existe un paciente con esa cédula")
    p = Patient(**values)
    db.add(p)
    db.flush()
    if is_offline_db(db):
        add_queue(db, "patient.create", "patient", {"extranjero": bool(data.extranjero), **values}, user.username, p.id)
        audit(db, user, "crear_paciente_offline", f"Paciente local {p.id}: {p.nombre}")
        db.commit()
        result = p_dict(p)
        result["offline"] = True
        return result
    audit(db, user, "crear_paciente", f"Paciente {p.id}: {p.nombre}")
    db.commit()
    mirror_patient_to_local(p)
    result = p_dict(p)
    result["offline"] = False
    return result


@app.put("/api/patients/{pid}")
def update_patient(pid: int, data: PatientIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = db.get(Patient, pid)
    if not p:
        raise HTTPException(404, "Paciente no encontrado")
    values = normalize_patient_payload(data)
    if not values["nombre"]:
        raise HTTPException(400, "El nombre es obligatorio")
    if values["cedula"]:
        existing = db.scalar(select(Patient).where(Patient.cedula == values["cedula"], Patient.id != pid))
        if existing:
            raise HTTPException(409, "Ya existe otro paciente con esa cédula")
    for k, v in values.items():
        setattr(p, k, v)
    if is_offline_db(db):
        add_queue(db, "patient.update", "patient", {"patient_id": pid, "extranjero": bool(data.extranjero), **values}, user.username, pid)
        audit(db, user, "editar_paciente_offline", f"Paciente local {pid}")
        db.commit()
        result = p_dict(p)
        result["offline"] = True
        return result
    audit(db, user, "editar_paciente", f"Paciente {p.id}")
    db.commit()
    mirror_patient_to_local(p)
    result = p_dict(p)
    result["offline"] = False
    return result


@app.post("/api/patients/{source_id}/link/{target_id}")
def link_duplicate_patient(source_id: int, target_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Vincula un duplicado sin historial clínico con la ficha correcta.

    Se usa cuando recepción confirma una sugerencia. Nunca fusiona automáticamente
    dos pacientes con atenciones y no se ejecuta offline, para no dejar una fusión
    compleja pendiente entre SQLite y Neon.
    """
    if source_id == target_id:
        p = db.get(Patient, target_id)
        if not p:
            raise HTTPException(404, "Paciente no encontrado")
        return {"patient": p_dict(p), "deleted_source": False, "moved_appointments": 0}
    if is_offline_db(db):
        raise HTTPException(503, "Para vincular dos fichas necesitas conexión a Internet. No se hizo ningún cambio.")
    source = db.get(Patient, source_id)
    target = db.get(Patient, target_id)
    if not source or not target:
        raise HTTPException(404, "No se encontró una de las fichas")
    source_visits = int(db.scalar(select(func.count(Visit.id)).where(Visit.patient_id == source_id)) or 0)
    if source_visits:
        raise HTTPException(409, "La ficha que intentas fusionar ya tiene atenciones clínicas. Revísala manualmente para no perder historial.")
    score, why = patient_similarity(source, target)
    if score < 0.74:
        raise HTTPException(409, "Las fichas no tienen una coincidencia suficientemente clara para fusionarlas automáticamente.")

    # Completa solo huecos de la ficha buena; nunca pisa información existente.
    changed_target = False
    for field in ("cedula", "celular", "correo", "lugar", "fecha_nacimiento"):
        incoming = getattr(source, field, None)
        if incoming and not getattr(target, field, None):
            setattr(target, field, incoming); changed_target = True

    moved = 0; removed_appointments: list[int] = []; moved_appointments: list[Appointment] = []
    source_apps = list(db.scalars(select(Appointment).where(Appointment.patient_id == source_id).order_by(Appointment.id)))
    for a in source_apps:
        duplicate = db.scalar(select(Appointment).where(
            Appointment.patient_id == target_id, Appointment.fecha == a.fecha, Appointment.hora == a.hora, Appointment.id != a.id
        ))
        if duplicate:
            removed_appointments.append(int(a.id)); db.delete(a)
        else:
            a.patient_id = target_id; moved += 1; moved_appointments.append(a)

    source_name = source.nombre
    audit(db, user, "vincular_paciente_duplicado", f"{source_id} {source_name} -> {target_id} {target.nombre}; {why}; {moved} citas trasladadas")
    db.delete(source)
    db.commit()
    # Reflejo inmediato en SQLite sin esperar al próximo refresco completo.
    mirror_patient_to_local(target)
    for a in moved_appointments:
        mirror_appointment_to_local(a)
    for aid in removed_appointments:
        mirror_delete_appointment_local(aid)
    mirror_delete_patient_local(source_id)
    _historical_reassign_links(source_id, target_id)
    return {
        "patient": p_dict(target), "deleted_source": True,
        "moved_appointments": moved, "reason": why, "target_changed": changed_target,
    }


@app.post("/api/patients/{source_id}/merge/{target_id}")
def merge_patient_confirmed(source_id: int, target_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Fusión manual confirmada por recepción.

    Conserva la ficha target, traslada TODAS las atenciones y citas de source,
    completa solo campos vacíos y finalmente elimina source. Nunca se ejecuta
    offline. Si ambas fichas tienen cédulas distintas no permite fusionar hasta
    revisar ese dato, porque es una contradicción demasiado importante.
    """
    if source_id == target_id:
        raise HTTPException(400, "Selecciona una ficha diferente para fusionar")
    if is_offline_db(db):
        raise HTTPException(503, "Para fusionar pacientes necesitas conexión a Internet. No se hizo ningún cambio.")
    source = db.get(Patient, source_id); target = db.get(Patient, target_id)
    if not source or not target:
        raise HTTPException(404, "No se encontró una de las fichas")

    sid = re.sub(r"\s+", "", str(source.cedula or "").upper())
    tid = re.sub(r"\s+", "", str(target.cedula or "").upper())
    if sid and tid and sid != tid:
        raise HTTPException(409, "Las dos fichas tienen identificaciones diferentes. Revisa la cédula antes de fusionarlas.")
    score, why = patient_similarity(source, target)
    same_phone = bool(normalize_lookup_phone(source.celular) and normalize_lookup_phone(source.celular) == normalize_lookup_phone(target.celular))
    same_id = bool(sid and tid and sid == tid)
    if score < 0.62 and not same_phone and not same_id:
        raise HTTPException(409, "La coincidencia es demasiado baja para una fusión segura. Revisa los nombres o datos antes de continuar.")

    changed_target = False
    for field in ("cedula", "celular", "correo", "lugar", "fecha_nacimiento", "notas"):
        incoming = getattr(source, field, None)
        if incoming and not getattr(target, field, None):
            setattr(target, field, incoming); changed_target = True

    moved_visits = list(db.scalars(select(Visit).where(Visit.patient_id == source_id).order_by(Visit.id)))
    for v in moved_visits:
        v.patient_id = target_id

    source_apps = list(db.scalars(select(Appointment).where(Appointment.patient_id == source_id).order_by(Appointment.id)))
    moved_apps: list[Appointment] = []; removed_app_ids: list[int] = []
    for a in source_apps:
        duplicate = db.scalar(select(Appointment).where(
            Appointment.patient_id == target_id,
            Appointment.fecha == a.fecha,
            Appointment.hora == a.hora,
            Appointment.id != a.id,
        ))
        if duplicate:
            removed_app_ids.append(int(a.id)); db.delete(a)
        else:
            a.patient_id = target_id; moved_apps.append(a)

    # Persistimos primero los cambios de propietario. Así el cascade de Patient
    # no puede interpretar las atenciones trasladadas como hijas a eliminar.
    db.flush()
    source_name = source.nombre; target_name = target.nombre
    audit(db, user, "fusion_manual_paciente", f"{source_id} {source_name} -> {target_id} {target_name}; {why}; {len(moved_visits)} atenciones; {len(moved_apps)} citas trasladadas")
    db.delete(source)
    db.commit()

    mirror_patient_to_local(target)
    for v in moved_visits: mirror_visit_to_local(v)
    for a in moved_apps: mirror_appointment_to_local(a)
    for aid in removed_app_ids: mirror_delete_appointment_local(aid)
    mirror_delete_patient_local(source_id)
    _historical_reassign_links(source_id, target_id)
    return {
        "ok": True, "patient": p_dict(target), "deleted_source": True,
        "visits_moved": len(moved_visits), "appointments_moved": len(moved_apps),
        "appointments_removed": len(removed_app_ids), "target_changed": changed_target,
        "reason": why,
    }


@app.delete("/api/patients/{pid}/confirmafy-imported")
def delete_confirmafy_imported_patient(pid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Borra manualmente solo una ficha cuya creación antigua por Confirmafy está demostrada."""
    if is_offline_db(db):
        raise HTTPException(503, "Para borrar una ficha importada de Confirmafy necesitas conexión a Internet.")
    p = db.get(Patient, pid)
    if not p:
        raise HTTPException(404, "Paciente no encontrado")
    st = _confirmafy_patient_status_map(db, [p]).get(int(pid), {})
    if not st.get("safe_confirmafy_delete"):
        raise HTTPException(409, "Esta ficha no cumple las condiciones de seguridad para borrarla como importación de Confirmafy. No se eliminó nada.")
    apps = list(db.scalars(select(Appointment).where(Appointment.patient_id == pid)))
    if any(str(a.origen or "").upper() != "CONFIRMAFY_IMPORTADO" for a in apps):
        raise HTTPException(409, "La ficha tiene una cita que no proviene de Confirmafy. No se eliminó nada.")
    app_ids = [int(a.id) for a in apps]
    name = p.nombre
    audit(db, user, "borrar_paciente_importado_confirmafy", f"Paciente {pid}: {name}; {len(app_ids)} citas importadas eliminadas")
    db.delete(p); db.commit()
    for aid in app_ids: mirror_delete_appointment_local(aid)
    mirror_delete_patient_local(pid)
    _historical_remove_links(pid)
    return {"ok": True, "patient_id": pid, "appointments_deleted": len(app_ids)}


@app.delete("/api/patients/{pid}")
def delete_patient(pid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = db.get(Patient, pid)
    if not p:
        raise HTTPException(404, "Paciente no encontrado")
    visit_count = db.scalar(select(func.count(Visit.id)).where(Visit.patient_id == pid)) or 0
    name = p.nombre
    if is_offline_db(db):
        add_queue(db, "patient.delete", "patient", {"patient_id": pid}, user.username, pid)
        audit(db, user, "borrar_paciente_offline", f"Paciente local {pid}: {name}; atenciones: {visit_count}")
        db.delete(p)
        db.commit()
        _historical_remove_links(pid)
        return {"ok": True, "patient_id": pid, "visits_deleted": visit_count, "offline": True}
    audit(db, user, "borrar_paciente", f"Paciente {pid}: {name}; atenciones eliminadas: {visit_count}")
    db.delete(p)
    db.commit()
    mirror_delete_patient_local(pid)
    _historical_remove_links(pid)
    return {"ok": True, "patient_id": pid, "visits_deleted": visit_count, "offline": False}


@app.get("/api/patients/{pid}")
def get_patient(pid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = db.get(Patient, pid)
    if not p:
        raise HTTPException(404, "Paciente no encontrado")
    visits = list(db.scalars(select(Visit).where(Visit.patient_id == pid).order_by(Visit.fecha.desc(), Visit.id.desc())))
    historical = historical_summary_for_patient(p) if not visits else None
    return {
        **p_dict(p),
        "visits": [v_dict(v) for v in visits],
        "suggested_type": "S" if visits or historical else "N",
        "ultima_atencion": visits[0].fecha if visits else None,
        "historical": historical,
    }




@app.get("/api/patients/{pid}/profile")
def patient_profile(pid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Ficha integral de un paciente.

    Se consulta únicamente cuando Recepción abre una ficha: el buscador general
    sigue devolviendo un resumen liviano. No modifica datos ni fuerza una sonda
    extra a Neon; usa la misma sesión local-first que el resto de la aplicación.
    """
    p = db.get(Patient, pid)
    if not p:
        raise HTTPException(404, "Paciente no encontrado")

    visits = list(db.scalars(
        select(Visit)
        .where(Visit.patient_id == pid)
        .order_by(Visit.fecha.desc(), Visit.id.desc())
    ))
    appointments = list(db.scalars(
        select(Appointment)
        .where(
            Appointment.patient_id == pid,
            Appointment.origen != CONFIRMAFY_ATTENDED_ORIGIN,
        )
        .order_by(Appointment.fecha.desc(), Appointment.hora.desc(), Appointment.id.desc())
    ))
    billing_rows = db.execute(
        select(BillingRecord, Visit)
        .join(Visit, BillingRecord.visit_id == Visit.id)
        .where(Visit.patient_id == pid)
        .order_by(Visit.fecha.desc(), Visit.id.desc())
    ).all()
    emissions = list(db.scalars(
        select(AzurEmission)
        .where(AzurEmission.patient_id == pid)
        .order_by(AzurEmission.fecha.desc(), AzurEmission.id.desc())
    ))

    historical = historical_summary_for_patient(p)
    return {
        **p_dict(p),
        "visits": [v_dict(v) for v in visits],
        "ultima_atencion": visits[0].fecha if visits else None,
        "historical": historical,
        "appointments": [
            {
                "id": a.id,
                "fecha": a.fecha,
                "hora": a.hora,
                "duracion": a.duracion,
                "nota": a.nota,
                "estado": a.estado,
                "origen": a.origen,
                "created_at": a.created_at,
            }
            for a in appointments
        ],
        "billing": [
            {
                "id": b.id,
                "visit_id": v.id,
                "fecha": v.fecha,
                "estado": b.estado,
                "numero_factura": b.numero_factura,
                "valor": float(v.valor or 0),
                "tipo": v.tipo,
                "procedimiento": v.procedimiento,
                "approved_at": b.approved_at,
                "emitted_at": b.emitted_at,
            }
            for b, v in billing_rows
        ],
        "emissions": [
            {
                "id": x.id,
                "fecha": x.fecha,
                "estado": x.estado,
                "numero_factura": x.numero_factura,
                "has_clave_acceso": bool(x.clave_acceso),
                "updated_at": x.updated_at,
            }
            for x in emissions
        ],
    }


@app.post("/api/historical/{hid}/activate")
def activate_historical_patient(hid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Convierte una ficha histórica en paciente actual solo por acción del usuario.

    Antes de crear vuelve a buscar coincidencias en la base activa. Si existe una
    única coincidencia segura la reutiliza y solo completa campos vacíos.
    """
    with LocalSessionLocal() as ldb:
        h = ldb.get(HistoricalPatient, hid)
        if not h:
            raise HTTPException(404, "Paciente histórico no encontrado")
        snapshot = {
            "nombre": h.nombre, "cedula": h.cedula, "celular": h.celular,
            "correo": h.correo, "lugar": h.lugar, "first_year": h.first_year, "last_year": h.last_year,
            "last_visit_date": h.last_visit_date,
            "aliases": h.aliases, "phones": h.phones, "emails": h.emails, "cedulas": h.cedulas,
        }

    # Preselección barata por identificadores o palabras del nombre, en la base que recibirá la escritura.
    candidates: dict[int, Patient] = {}
    if snapshot["cedula"]:
        for p in db.scalars(select(Patient).where(Patient.cedula == snapshot["cedula"]).limit(4)):
            candidates[int(p.id)] = p
    if snapshot["celular"]:
        ph = normalize_lookup_phone(snapshot["celular"])
        if ph:
            for p in db.scalars(select(Patient).where(Patient.celular.ilike(f"%{ph[-9:]}%")).limit(8)):
                candidates[int(p.id)] = p
    name_tokens = list(lookup_name_tokens(snapshot["nombre"]))
    if len(name_tokens) >= 3:
        stmt = select(Patient)
        for token in name_tokens[:5]:
            stmt = stmt.where(Patient.nombre.ilike(f"%{token}%"))
        for p in db.scalars(stmt.limit(10)):
            candidates[int(p.id)] = p

    # Reconstruimos un objeto histórico liviano para usar la misma comparación segura.
    hproxy = HistoricalPatient(
        id=hid, source_key=str(hid), nombre=snapshot["nombre"], search_text=snapshot["nombre"],
        cedula=snapshot["cedula"], celular=snapshot["celular"], correo=snapshot["correo"], lugar=snapshot["lugar"],
        first_year=int(snapshot["first_year"] or 2020), last_year=int(snapshot["last_year"] or 2025),
        last_visit_date=snapshot.get("last_visit_date"), row_count=1,
        aliases=snapshot["aliases"], phones=snapshot["phones"], emails=snapshot["emails"], cedulas=snapshot["cedulas"],
    )
    matched = [p for p in candidates.values() if _historical_identity_match(hproxy, p)[0]]
    if len(matched) > 1:
        raise HTTPException(409, "Hay más de un paciente actual que podría corresponder a este histórico. Búscalo manualmente antes de continuar.")

    created = False
    if matched:
        p = matched[0]
        changed = False
        for field in ("cedula", "celular", "correo", "lugar"):
            incoming = snapshot.get(field)
            if incoming and not getattr(p, field):
                setattr(p, field, incoming); changed = True
        if changed:
            if is_offline_db(db):
                extranjero = bool(p.cedula and not valid_ecuadorian_cedula(str(p.cedula)))
                add_queue(db, "patient.update", "patient", {
                    "patient_id": int(p.id), "extranjero": extranjero,
                    "cedula": p.cedula, "nombre": p.nombre, "fecha_nacimiento": p.fecha_nacimiento,
                    "celular": p.celular, "correo": p.correo, "lugar": p.lugar, "notas": p.notas,
                }, user.username, int(p.id))
                audit(db, user, "completar_desde_historico_offline", f"Paciente local {p.id}; histórico {hid}; {snapshot['first_year']}-{snapshot['last_year']}")
                db.commit()
            else:
                audit(db, user, "completar_desde_historico", f"Paciente {p.id}; histórico {hid}; {snapshot['first_year']}-{snapshot['last_year']}")
                db.commit()
                mirror_patient_to_local(p)
    else:
        p = Patient(
            cedula=snapshot["cedula"] or None, nombre=str(snapshot["nombre"] or "").upper(),
            fecha_nacimiento=None, celular=snapshot["celular"] or None, correo=snapshot["correo"] or None,
            lugar=snapshot["lugar"] or None, notas=None,
        )
        db.add(p); db.flush(); created = True
        if is_offline_db(db):
            add_queue(db, "patient.create", "patient", {
                "extranjero": False, "cedula": p.cedula, "nombre": p.nombre, "fecha_nacimiento": None,
                "celular": p.celular, "correo": p.correo, "lugar": p.lugar, "notas": None,
            }, user.username, p.id)
            audit(db, user, "activar_historico_offline", f"Paciente local {p.id}; histórico {hid}; {snapshot['first_year']}-{snapshot['last_year']}")
            db.commit()
        else:
            audit(db, user, "activar_historico", f"Paciente {p.id}; histórico {hid}; {snapshot['first_year']}-{snapshot['last_year']}")
            db.commit(); mirror_patient_to_local(p)
    result = p_dict(p)
    result.update({"created": created, "historical": {
        "first_year": int(snapshot["first_year"] or 2020),
        "last_year": int(snapshot["last_year"] or 2025),
        "last_visit_date": snapshot.get("last_visit_date"),
    }})
    return result


@app.post("/api/visits")
def create_visit(data: VisitIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = db.get(Patient, data.patient_id)
    if not p:
        raise HTTPException(404, "Paciente no encontrado")
    prior = db.scalar(select(func.count(Visit.id)).where(Visit.patient_id == p.id)) or 0
    historical_prior = bool(not prior and historical_summary_for_patient(p))
    automatic_type = "S" if prior or historical_prior else "N"
    override = (data.tipo or "").strip().upper()
    if override and override not in {"N", "S"}:
        raise HTTPException(400, "Estado de paciente inválido")
    tipo = override or automatic_type
    procedimiento = (data.procedimiento or "").strip().upper() or None
    valor = data.valor
    if procedimiento is None:
        valor = 40.0
    v = Visit(
        patient_id=data.patient_id,
        fecha=data.fecha,
        tipo=tipo,
        procedimiento=procedimiento,
        valor=valor,
        observacion=data.observacion,
    )
    db.add(v)
    db.flush()
    billing = BillingRecord(visit_id=v.id, estado="PENDIENTE")
    db.add(billing)
    db.flush()
    if is_offline_db(db):
        payload = {
            "patient_id": data.patient_id,
            "fecha": data.fecha.isoformat(),
            "tipo": tipo,
            "procedimiento": procedimiento,
            "valor": float(valor) if valor is not None else None,
            "observacion": data.observacion,
        }
        add_queue(db, "visit.create", "visit", payload, user.username, v.id)
        audit(db, user, "crear_atencion_offline", f"Atención local {v.id}, paciente {p.id}, {procedimiento or 'CONSULTA'}")
        db.commit()
        result = v_dict(v)
        result["offline"] = True
        return result
    audit(db, user, "crear_atencion", f"Atención {v.id}, paciente {p.id}, estado {tipo}, servicio {procedimiento or 'CONSULTA'}")
    db.commit()
    mirror_visit_to_local(v)
    mirror_billing_to_local(billing)
    result = v_dict(v)
    result["offline"] = False
    return result


@app.post("/api/visits/batch")
def create_visit_batch(data: VisitBatchIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Guarda varias acciones de una misma atención en una sola operación."""
    p = db.get(Patient, data.patient_id)
    if not p:
        raise HTTPException(404, "Paciente no encontrado")
    if not data.services:
        raise HTTPException(400, "Selecciona al menos una atención")
    if len(data.services) > 20:
        raise HTTPException(400, "Hay demasiadas acciones seleccionadas")

    override = (data.tipo or "").strip().upper()
    if override and override not in {"N", "S"}:
        raise HTTPException(400, "Estado de paciente inválido")
    prior = db.scalar(select(func.count(Visit.id)).where(Visit.patient_id == p.id)) or 0
    historical_prior = bool(not prior and historical_summary_for_patient(p))
    first_type = override or ("S" if prior or historical_prior else "N")

    normalized = []
    seen = set()
    for item in data.services:
        procedimiento = (item.procedimiento or "").strip().upper() or None
        key = procedimiento or "CONSULTA"
        if key in seen:
            continue
        seen.add(key)
        valor = 40.0 if procedimiento is None else item.valor
        if valor is None:
            raise HTTPException(400, f"Ingresa el valor de {key}")
        try:
            valor = float(valor)
        except (TypeError, ValueError):
            raise HTTPException(400, f"El valor de {key} no es válido")
        if valor < 0:
            raise HTTPException(400, f"El valor de {key} no es válido")
        normalized.append((procedimiento, valor))
    if not normalized:
        raise HTTPException(400, "Selecciona al menos una atención")

    created = []
    billings = []
    offline = is_offline_db(db)
    for index, (procedimiento, valor) in enumerate(normalized):
        tipo = first_type if index == 0 else "S"
        v = Visit(
            patient_id=data.patient_id,
            fecha=data.fecha,
            tipo=tipo,
            procedimiento=procedimiento,
            valor=valor,
            observacion=data.observacion,
        )
        db.add(v)
        db.flush()
        billing = BillingRecord(visit_id=v.id, estado="PENDIENTE")
        db.add(billing)
        db.flush()
        created.append(v)
        billings.append(billing)
        service_name = procedimiento or "CONSULTA"
        if offline:
            payload = {
                "patient_id": data.patient_id,
                "fecha": data.fecha.isoformat(),
                "tipo": tipo,
                "procedimiento": procedimiento,
                "valor": valor,
                "observacion": data.observacion,
            }
            add_queue(db, "visit.create", "visit", payload, user.username, v.id)
            audit(db, user, "crear_atencion_multiple_offline", f"Atención local {v.id}, paciente {p.id}, {service_name}")
        else:
            audit(db, user, "crear_atencion_multiple", f"Atención {v.id}, paciente {p.id}, estado {tipo}, servicio {service_name}")

    db.commit()
    if not offline:
        for v, billing in zip(created, billings):
            mirror_visit_to_local(v)
            mirror_billing_to_local(billing)
    with LocalSessionLocal() as summary_db:
        billing_actions = _billing_action_counts(summary_db)
        pending_summary_local = {
            "billing": billing_actions["total"],
            "billing_pending": billing_actions["pending"],
            "billing_approved": billing_actions["approved"],
            "agenda": int(summary_db.scalar(select(func.count(Appointment.id)).where(Appointment.estado == "PENDIENTE")) or 0),
        }
    return {
        "ok": True,
        "count": len(created),
        "items": [v_dict(v) for v in created],
        "offline": offline,
        "pending": pending_summary_local,
    }


@app.delete("/api/visits/{visit_id}")
def delete_visit(visit_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    v = db.get(Visit, visit_id)
    if not v:
        raise HTTPException(404, "Atención no encontrada")
    patient_id = v.patient_id
    detail = f"Atención {v.id}, paciente {patient_id}, fecha {v.fecha}, servicio {v.procedimiento or 'CONSULTA'}"
    if is_offline_db(db):
        add_queue(db, "visit.delete", "visit", {"visit_id": visit_id}, user.username, visit_id)
        audit(db, user, "borrar_atencion_offline", detail)
        db.delete(v)
        db.commit()
        return {"ok": True, "visit_id": visit_id, "patient_id": patient_id, "offline": True}
    audit(db, user, "borrar_atencion", detail)
    db.delete(v)
    db.commit()
    mirror_delete_visit_local(visit_id)
    return {"ok": True, "visit_id": visit_id, "patient_id": patient_id, "offline": False}


@app.get("/api/dashboard")
def dashboard(fecha: date = date.today(), db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Resumen rápido para Inicio en una sola conexión."""
    rows = db.execute(select(Visit, Patient).join(Patient).where(Visit.fecha == fecha)).all()
    patient_ids = {p.id for _, p in rows}
    new_ids = {p.id for v, p in rows if v.tipo == "N"}
    subsequent_ids = patient_ids - new_ids
    procedures = sum(is_procedure(v) for v, _ in rows)
    total = sum(float(v.valor or 0) for v, _ in rows)

    pending_billing_groups = db.execute(
        select(Visit.patient_id, Visit.fecha)
        .join(BillingRecord, BillingRecord.visit_id == Visit.id)
        .where(BillingRecord.estado == "PENDIENTE")
        .distinct()
    ).all()
    pending_billing = len(pending_billing_groups)
    pending_agenda = int(db.scalar(select(func.count(Appointment.id)).where(Appointment.estado == "PENDIENTE")) or 0)
    return {
        "fecha": fecha,
        "patients": len(patient_ids),
        "new": len(new_ids),
        "subsequent": len(subsequent_ids),
        "procedures": procedures,
        "total": total,
        "billing_pending": pending_billing,
        "agenda_pending": pending_agenda,
    }


@app.get("/api/today")
def today(fecha: date = date.today(), db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = db.execute(select(Visit, Patient).join(Patient).where(Visit.fecha == fecha).order_by(Visit.id.desc())).all()
    visits = [{**v_dict(v), "patient": p_dict(p)} for v, p in rows]
    total = sum(float(v.valor or 0) for v, _ in rows)
    patient_ids = {p.id for _, p in rows}
    new_patient_ids = {p.id for v, p in rows if v.tipo == "N"}
    subsequent_patient_ids = patient_ids - new_patient_ids
    return {
        "fecha": fecha,
        "count": len(patient_ids),
        "N": len(new_patient_ids),
        "S": len(subsequent_patient_ids),
        "P": sum(is_procedure(v) for v, _ in rows),
        "total": total,
        "visits": visits,
    }


@app.get("/api/home/week")
def home_week(anchor: date, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Inicio semanal en una sola petición/conexión a Neon."""
    monday = anchor - timedelta(days=anchor.weekday())
    defs = [
        ("Jueves", monday + timedelta(days=3)),
        ("Viernes", monday + timedelta(days=4)),
        ("Sábado", monday + timedelta(days=5)),
    ]
    dates = [d for _, d in defs]
    rows = db.execute(
        select(Visit, Patient).join(Patient)
        .where(Visit.fecha.in_(dates))
        .order_by(Visit.fecha.asc(), Visit.id.desc())
    ).all()
    grouped = {d: [] for d in dates}
    for v, p in rows:
        grouped.setdefault(v.fecha, []).append((v, p))

    days = []
    for label, d in defs:
        day_rows = grouped.get(d, [])
        patient_ids = {p.id for _, p in day_rows}
        new_patient_ids = {p.id for v, p in day_rows if v.tipo == "N"}
        payload = {
            "fecha": d,
            "count": len(patient_ids),
            "N": len(new_patient_ids),
            "S": len(patient_ids - new_patient_ids),
            "P": sum(is_procedure(v) for v, _ in day_rows),
            "total": sum(float(v.valor or 0) for v, _ in day_rows),
            "visits": [{**v_dict(v), "patient": p_dict(p)} for v, p in day_rows],
        }
        days.append({"label": label, "date": d, "data": payload})
    return {"anchor": anchor, "week_start": monday, "days": days}


def build_report_data(rows):
    """Agrupa el período en pacientes/día para que N/S no se infle por procedimientos."""
    patient_days = {}
    for v, p in rows:
        patient_days.setdefault((v.fecha, p.id), []).append((v, p))

    turns = {}
    by_date = {}
    for key, items in patient_days.items():
        fecha, pid = key
        first_id = min(v.id for v, _ in items)
        by_date.setdefault(fecha, []).append((first_id, pid))
    for fecha, items in by_date.items():
        for n, (_, pid) in enumerate(sorted(items), 1):
            turns[(fecha, pid)] = n

    daily = {}
    service_totals = {}
    detail_rows = []
    for (fecha, pid), items in sorted(patient_days.items(), key=lambda kv: (kv[0][0], turns[kv[0]])):
        p = items[0][1]
        is_new = any(v.tipo == "N" for v, _ in items)
        classification = "NUEVO" if is_new else "SUBSECUENTE"
        d = daily.setdefault(fecha, {
            "fecha": fecha, "patients": 0, "N": 0, "S": 0,
            "consultations": 0, "procedures": 0, "total": 0.0,
        })
        d["patients"] += 1
        d["N" if is_new else "S"] += 1

        for v, _ in sorted(items, key=lambda pair: pair[0].id):
            procedure = (v.procedimiento or "").strip().upper()
            is_proc = is_procedure(v)
            service = procedure or ("PROCEDIMIENTO" if is_proc else "CONSULTA")
            value = float(v.valor or 0)
            if is_proc:
                d["procedures"] += 1
            else:
                d["consultations"] += 1
            d["total"] += value
            st = service_totals.setdefault(service, {"service": service, "count": 0, "total": 0.0})
            st["count"] += 1
            st["total"] += value
            detail_rows.append({
                "fecha": fecha,
                "turno": turns[(fecha, pid)],
                "patient_id": pid,
                "patient": p_dict(p),
                "classification": classification,
                "service": service,
                "value": value,
                "observacion": v.observacion or "",
                "visit_id": v.id,
            })

    days = [daily[d] for d in sorted(daily)]
    services = sorted(service_totals.values(), key=lambda x: (0 if x["service"] == "CONSULTA" else 1, x["service"]))
    patient_count = len(patient_days)
    new_count = sum(1 for items in patient_days.values() if any(v.tipo == "N" for v, _ in items))
    consultations = sum(not is_procedure(v) for v, _ in rows)
    procedures = sum(is_procedure(v) for v, _ in rows)
    total = sum(float(v.valor or 0) for v, _ in rows)
    return {
        "count": len(rows),
        "patients": patient_count,
        "N": new_count,
        "S": patient_count - new_count,
        "consultations": consultations,
        "P": procedures,
        "total": total,
        "services": services,
        "days": days,
        "details": detail_rows,
        "rows": [{**v_dict(v), "patient": p_dict(p)} for v, p in rows],
    }


def _xlsx_col_name(n: int) -> str:
    out = ""
    while n:
        n, r = divmod(n - 1, 26)
        out = chr(65 + r) + out
    return out


def _xlsx_cell(ref: str, value=None, style: int = 0, formula: str | None = None) -> str:
    style_attr = f' s="{style}"' if style else ""
    if formula is not None:
        numeric = "0" if value is None else str(value)
        return f'<c r="{ref}"{style_attr}><f>{xml_escape(formula)}</f><v>{numeric}</v></c>'
    if value is None:
        return f'<c r="{ref}"{style_attr}/>'
    if isinstance(value, bool):
        return f'<c r="{ref}" t="b"{style_attr}><v>{1 if value else 0}</v></c>'
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f'<c r="{ref}"{style_attr}><v>{value}</v></c>'
    text_value = xml_escape(str(value))
    return f'<c r="{ref}" t="inlineStr"{style_attr}><is><t xml:space="preserve">{text_value}</t></is></c>'


def _xlsx_sheet(rows, widths, merges=None, freeze_row=None, auto_filter=None) -> str:
    row_xml = []
    for row_num, height, cells in rows:
        h = f' ht="{height}" customHeight="1"' if height else ""
        row_xml.append(f'<row r="{row_num}"{h}>' + "".join(cells) + '</row>')
    cols = "".join(
        f'<col min="{i}" max="{i}" width="{w}" customWidth="1"/>'
        for i, w in enumerate(widths, 1)
    )
    if freeze_row:
        pane = f'<sheetViews><sheetView workbookViewId="0"><pane ySplit="{freeze_row}" topLeftCell="A{freeze_row+1}" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
    else:
        pane = '<sheetViews><sheetView workbookViewId="0"/></sheetViews>'
    merge_xml = ""
    if merges:
        merge_xml = f'<mergeCells count="{len(merges)}">' + "".join(f'<mergeCell ref="{m}"/>' for m in merges) + '</mergeCells>'
    filter_xml = f'<autoFilter ref="{auto_filter}"/>' if auto_filter else ""
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'{pane}<sheetFormatPr defaultRowHeight="15"/><cols>{cols}</cols>'
        f'<sheetData>{"".join(row_xml)}</sheetData>{merge_xml}{filter_xml}'
        '<pageMargins left="0.3" right="0.3" top="0.5" bottom="0.5" header="0.2" footer="0.2"/>'
        '</worksheet>'
    )


def build_report_payload(db: Session, desde: date, hasta: date) -> dict:
    """Reporte del período + comparativo con el mismo tramo del mes anterior cuando empieza el día 1."""
    rows = db.execute(
        select(Visit, Patient).join(Patient)
        .where(Visit.fecha >= desde, Visit.fecha <= hasta)
        .order_by(Visit.fecha.asc(), Visit.id.asc())
    ).all()
    data = build_report_data(rows)
    comparison = {"available": False}
    if desde.day == 1 and desde.year == hasta.year and desde.month == hasta.month:
        previous_last = desde - timedelta(days=1)
        previous_from = previous_last.replace(day=1)
        previous_to = min(previous_from + timedelta(days=max(0, hasta.day - 1)), previous_last)
        prev_rows = db.execute(
            select(Visit, Patient).join(Patient)
            .where(Visit.fecha >= previous_from, Visit.fecha <= previous_to)
            .order_by(Visit.fecha.asc(), Visit.id.asc())
        ).all()
        prev = build_report_data(prev_rows)
        comparison = {
            "available": True,
            "current_from": desde, "current_to": hasta,
            "previous_from": previous_from, "previous_to": previous_to,
            "previous": {
                "patients": prev["patients"], "N": prev["N"], "S": prev["S"],
                "consultations": prev["consultations"], "P": prev["P"], "total": prev["total"],
            },
        }
    data["comparison"] = comparison
    return data


def build_report_xlsx(data: dict, desde: date, hasta: date) -> bytes:
    """Genera un XLSX real con una hoja de resumen y otra de detalle."""
    period = f"Período: {desde.strftime('%d/%m/%Y')} al {hasta.strftime('%d/%m/%Y')}"

    summary_rows = []
    def add(row, cells, height=None):
        summary_rows.append((row, height, cells))

    add(1, [_xlsx_cell('A1', 'REPORTE DE ATENCIONES', 1)], 28)
    add(2, [_xlsx_cell('A2', 'Dr. Armando Revelo — Cirujano Urólogo', 2)], 20)
    add(3, [_xlsx_cell('A3', period, 15)], 18)
    add(5, [_xlsx_cell('A5', 'PACIENTES ATENDIDOS', 9), _xlsx_cell('C5', 'NUEVOS', 9), _xlsx_cell('E5', 'SUBSECUENTES', 9)], 20)
    add(6, [_xlsx_cell('A6', data['patients'], 10), _xlsx_cell('C6', data['N'], 10), _xlsx_cell('E6', data['S'], 10)], 26)
    add(8, [_xlsx_cell('A8', 'CONSULTAS', 9), _xlsx_cell('C8', 'PROCEDIMIENTOS', 9), _xlsx_cell('E8', 'TOTAL DEL PERÍODO', 9)], 20)
    add(9, [_xlsx_cell('A9', data['consultations'], 10), _xlsx_cell('C9', data['P'], 10), _xlsx_cell('E9', data['total'], 16)], 26)

    comparison = data.get('comparison') or {}
    comparison_title = None
    comparison_header = None
    row = 11
    if comparison.get('available'):
        prev = comparison.get('previous') or {}
        comparison_title = row
        add(row, [_xlsx_cell(f'A{row}', 'COMPARATIVO MENSUAL', 3)], 22); row += 1
        add(row, [_xlsx_cell(f'A{row}', f"Actual: {comparison['current_from'].strftime('%d/%m/%Y')} al {comparison['current_to'].strftime('%d/%m/%Y')}  |  Anterior: {comparison['previous_from'].strftime('%d/%m/%Y')} al {comparison['previous_to'].strftime('%d/%m/%Y')}", 15)], 18); row += 1
        comparison_header = row
        add(row, [_xlsx_cell(f'A{row}', 'Indicador', 4), _xlsx_cell(f'B{row}', 'Período actual', 4), _xlsx_cell(f'C{row}', 'Período anterior', 4), _xlsx_cell(f'D{row}', 'Variación', 4)], 20); row += 1
        metrics = [
            ('Pacientes', data['patients'], prev.get('patients', 0), False),
            ('Consultas', data['consultations'], prev.get('consultations', 0), False),
            ('Procedimientos', data['P'], prev.get('P', 0), False),
            ('Total', data['total'], prev.get('total', 0), True),
        ]
        for label, current_value, previous_value, is_money in metrics:
            cur_style = 8 if is_money else 7
            old_style = 8 if is_money else 7
            formula = f'IF(C{row}=0,IF(B{row}=0,0,1),(B{row}-C{row})/C{row})'
            add(row, [_xlsx_cell(f'A{row}', label, 5), _xlsx_cell(f'B{row}', current_value, cur_style), _xlsx_cell(f'C{row}', previous_value, old_style), _xlsx_cell(f'D{row}', 0, 18, formula=formula)], 19)
            row += 1
        row += 1

    service_title = row
    add(row, [_xlsx_cell(f'A{row}', 'TOTALES POR ATENCIÓN', 3)], 22); row += 1
    service_header = row
    add(row, [_xlsx_cell(f'A{row}', 'Atención', 4), _xlsx_cell(f'B{row}', 'Cantidad', 4), _xlsx_cell(f'C{row}', 'Total', 4)], 20); row += 1
    for item in data['services']:
        label = 'CONSULTA' if item['service'] == 'CONSULTA' else str(item['service'] or '').upper()
        add(row, [
            _xlsx_cell(f'A{row}', label, 5),
            _xlsx_cell(f'B{row}', item['count'], 7),
            _xlsx_cell(f'C{row}', item['total'], 8),
        ], 19)
        row += 1

    row += 1
    daily_title = row
    add(row, [_xlsx_cell(f'A{row}', 'RESUMEN POR DÍA', 3)], 22)
    row += 1
    daily_header = row
    headers = ['Fecha', 'Pacientes', 'Nuevos', 'Subsecuentes', 'Consultas', 'Procedimientos', 'Total']
    add(row, [_xlsx_cell(f'{_xlsx_col_name(i)}{row}', h, 4) for i, h in enumerate(headers, 1)], 20)
    row += 1
    for d in data['days']:
        add(row, [
            _xlsx_cell(f'A{row}', d['fecha'].strftime('%d/%m/%Y'), 6),
            _xlsx_cell(f'B{row}', d['patients'], 7),
            _xlsx_cell(f'C{row}', d['N'], 7),
            _xlsx_cell(f'D{row}', d['S'], 7),
            _xlsx_cell(f'E{row}', d['consultations'], 7),
            _xlsx_cell(f'F{row}', d['procedures'], 7),
            _xlsx_cell(f'G{row}', d['total'], 8),
        ], 19)
        row += 1
    if data['days']:
        add(row, [
            _xlsx_cell(f'A{row}', 'TOTAL', 13),
            _xlsx_cell(f'B{row}', data['patients'], 13),
            _xlsx_cell(f'C{row}', data['N'], 13),
            _xlsx_cell(f'D{row}', data['S'], 13),
            _xlsx_cell(f'E{row}', data['consultations'], 13),
            _xlsx_cell(f'F{row}', data['P'], 13),
            _xlsx_cell(f'G{row}', data['total'], 17),
        ], 20)

    summary_xml = _xlsx_sheet(
        summary_rows,
        [18, 12, 18, 15, 18, 15, 16],
        merges=(
            ['A1:G1', 'A2:G2', 'A3:G3',
             'A5:B5', 'C5:D5', 'E5:F5', 'A6:B6', 'C6:D6', 'E6:F6',
             'A8:B8', 'C8:D8', 'E8:F8', f'A{service_title}:C{service_title}', f'A{daily_title}:G{daily_title}']
            + ([f'A{comparison_title}:G{comparison_title}', f'A{comparison_title+1}:G{comparison_title+1}'] if comparison_title else [])
        ),
        freeze_row=3,
    )

    detail_rows = []
    def dadd(row, cells, height=None):
        detail_rows.append((row, height, cells))

    dadd(1, [_xlsx_cell('A1', 'DETALLE DE ATENCIONES', 1)], 28)
    dadd(2, [_xlsx_cell('A2', period, 15)], 18)
    headers = ['N.º', 'Fecha', 'Turno', 'Paciente', 'Estado', 'Atención', 'Valor', 'Observación']
    dadd(4, [_xlsx_cell(f'{_xlsx_col_name(i)}4', h, 4) for i, h in enumerate(headers, 1)], 22)

    rr = 5
    for n, item in enumerate(data['details'], 1):
        status_style = 11 if item['classification'] == 'NUEVO' else 12
        service = 'CONSULTA' if item['service'] == 'CONSULTA' else str(item['service'] or '').upper()
        dadd(rr, [
            _xlsx_cell(f'A{rr}', n, 7),
            _xlsx_cell(f'B{rr}', item['fecha'].strftime('%d/%m/%Y'), 6),
            _xlsx_cell(f'C{rr}', item['turno'], 7),
            _xlsx_cell(f'D{rr}', item['patient']['nombre'], 5),
            _xlsx_cell(f'E{rr}', item['classification'].title(), status_style),
            _xlsx_cell(f'F{rr}', service, 5),
            _xlsx_cell(f'G{rr}', item['value'], 8),
            _xlsx_cell(f'H{rr}', item['observacion'], 14),
        ], 20)
        rr += 1

    total_row = rr
    detail_merges = ['A1:H1', 'A2:H2']
    if data['details']:
        dadd(total_row, [
            _xlsx_cell(f'A{total_row}', 'TOTAL', 13),
            _xlsx_cell(f'G{total_row}', data['total'], 17, formula=f'SUM(G5:G{total_row-1})'),
        ], 22)
        detail_merges.append(f'A{total_row}:F{total_row}')

    detail_xml = _xlsx_sheet(
        detail_rows,
        [7, 13, 8, 34, 16, 24, 13, 34],
        merges=detail_merges,
        freeze_row=4,
        auto_filter=f'A4:H{max(4, total_row - 1)}',
    )

    styles = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="1"><numFmt numFmtId="164" formatCode="$#,##0.00"/></numFmts>
<fonts count="6">
<font><sz val="11"/><name val="Calibri"/></font>
<font><b/><sz val="17"/><color rgb="FF17365D"/><name val="Calibri"/></font>
<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>
<font><b/><sz val="11"/><color rgb="FF17365D"/><name val="Calibri"/></font>
<font><b/><sz val="15"/><color rgb="FF17365D"/><name val="Calibri"/></font>
<font><i/><sz val="10"/><color rgb="FF64748B"/><name val="Calibri"/></font>
</fonts>
<fills count="7">
<fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FF17365D"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFDCE6F1"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFE2F0D9"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFFFF2CC"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFF5F7FA"/></patternFill></fill>
</fills>
<borders count="2"><border/><border><left style="thin"><color rgb="FFD8DEE8"/></left><right style="thin"><color rgb="FFD8DEE8"/></right><top style="thin"><color rgb="FFD8DEE8"/></top><bottom style="thin"><color rgb="FFD8DEE8"/></bottom><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="19">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
<xf numFmtId="0" fontId="3" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment horizontal="center"/></xf>
<xf numFmtId="0" fontId="2" fillId="2" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="left" vertical="center"/></xf>
<xf numFmtId="0" fontId="2" fillId="2" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyAlignment="1"><alignment vertical="center"/></xf>
<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
<xf numFmtId="164" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyAlignment="1"><alignment horizontal="right" vertical="center"/></xf>
<xf numFmtId="0" fontId="3" fillId="3" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
<xf numFmtId="0" fontId="4" fillId="0" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
<xf numFmtId="0" fontId="3" fillId="4" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
<xf numFmtId="0" fontId="3" fillId="3" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
<xf numFmtId="0" fontId="3" fillId="5" borderId="1" xfId="0" applyAlignment="1"><alignment vertical="center"/></xf>
<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>
<xf numFmtId="0" fontId="5" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment horizontal="center"/></xf>
<xf numFmtId="164" fontId="4" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
<xf numFmtId="164" fontId="3" fillId="5" borderId="1" xfId="0" applyNumberFormat="1" applyAlignment="1"><alignment horizontal="right" vertical="center"/></xf>
<xf numFmtId="10" fontId="3" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
</cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>'''

    workbook = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Resumen" sheetId="1" r:id="rId1"/><sheet name="Detalle" sheetId="2" r:id="rId2"/></sheets><calcPr calcId="191029" fullCalcOnLoad="1" forceFullCalc="1"/></workbook>'''
    wb_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>'''
    root_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'''
    content_types = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>'''

    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', content_types)
        z.writestr('_rels/.rels', root_rels)
        z.writestr('xl/workbook.xml', workbook)
        z.writestr('xl/_rels/workbook.xml.rels', wb_rels)
        z.writestr('xl/styles.xml', styles)
        z.writestr('xl/worksheets/sheet1.xml', summary_xml)
        z.writestr('xl/worksheets/sheet2.xml', detail_xml)
    return out.getvalue()


@app.get("/api/report")
def report(desde: date, hasta: date, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if hasta < desde:
        raise HTTPException(400, "La fecha Hasta no puede ser anterior a Desde")
    return build_report_payload(db, desde, hasta)

MOBILE_LAN_PORT = LOCAL_HTTP_PORT
MOBILE_FIREWALL_RULE = "Agenda Dr Revelo - Red Local"


def _is_loopback_client(request: Request) -> bool:
    host = str(getattr(request.client, "host", "") or "").split("%", 1)[0]
    if host.lower() in {"localhost", "testclient"}:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except Exception:
        return host in {"127.0.0.1", "::1"}


def _remote_mobile_path_allowed(path: str) -> bool:
    # Tanto desde la LAN como a través de Cloudflare exponemos únicamente la
    # superficie de Agenda móvil. La aplicación clínica completa queda local.
    if path in {"/mobile", "/mobile/", "/mobile/manifest.webmanifest", "/mobile/sw.js", "/static/doctor_isotype.png"}:
        return True
    if path.startswith("/mobile-static/"):
        return True
    if path in {"/api/mobile/me", "/api/mobile/agenda/week", "/api/mobile/appointments"}:
        return True
    if path.startswith("/api/mobile/appointments/") or path.startswith("/api/mobile/unlinked/"):
        return True
    return False


def _request_is_external_surface(request: Request) -> bool:
    # cloudflared conecta al origen por 127.0.0.1, así que request.client por sí
    # solo parecería local. Cloudflare añade estos encabezados al tráfico que
    # viene de Internet. Si alguien los falsifica desde la LAN, el efecto es
    # únicamente más restrictivo (nunca obtiene acceso adicional).
    if request.headers.get("cf-connecting-ip") or request.headers.get("cf-ray"):
        return True
    return not _is_loopback_client(request)


@app.middleware("http")
async def local_network_surface_guard(request: Request, call_next):
    if _request_is_external_surface(request) and not _remote_mobile_path_allowed(request.url.path):
        return Response(
            content="Acceso disponible solo desde la PC de Recepción. Para el celular usa el enlace de Agenda web.",
            status_code=403,
            media_type="text/plain; charset=utf-8",
        )
    return await call_next(request)


def _preferred_lan_ip() -> str:
    candidates: list[str] = []
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0.25)
        # UDP connect no necesita que el destino responda; solo permite conocer
        # qué interfaz usaría Windows para salir a la red.
        sock.connect(("8.8.8.8", 80))
        candidates.append(str(sock.getsockname()[0]))
        sock.close()
    except Exception:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET, socket.SOCK_STREAM):
            candidates.append(str(info[4][0]))
    except Exception:
        pass

    seen = set()
    usable = []
    for raw in candidates:
        if raw in seen:
            continue
        seen.add(raw)
        try:
            ip = ipaddress.ip_address(raw)
        except Exception:
            continue
        if ip.version != 4 or ip.is_loopback or ip.is_link_local or not ip.is_private:
            continue
        if raw.startswith("192.168."):
            score = 30
        elif raw.startswith("10."):
            score = 20
        elif raw.startswith("172."):
            try:
                score = 20 if 16 <= int(raw.split('.')[1]) <= 31 else 10
            except Exception:
                score = 10
        else:
            score = 10
        usable.append((score, raw))
    usable.sort(reverse=True)
    return usable[0][1] if usable else ""


def _mobile_firewall_present() -> bool:
    if os.name != "nt":
        return True
    try:
        proc = subprocess.run(
            ["netsh", "advfirewall", "firewall", "show", "rule", "name=all"],
            capture_output=True, text=True, timeout=8, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return MOBILE_FIREWALL_RULE.lower() in ((proc.stdout or "") + (proc.stderr or "")).lower()
    except Exception:
        return False


def _try_add_mobile_firewall_rule() -> bool:
    if os.name != "nt":
        return True
    args = [
        "netsh", "advfirewall", "firewall", "add", "rule",
        f"name={MOBILE_FIREWALL_RULE}", "dir=in", "action=allow", "protocol=TCP",
        f"localport={MOBILE_LAN_PORT}", "remoteip=localsubnet", "profile=any",
    ]
    try:
        proc = subprocess.run(
            args, capture_output=True, text=True, timeout=8, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return proc.returncode == 0 and _mobile_firewall_present()
    except Exception:
        return False


def _request_mobile_firewall_elevation() -> bool:
    if os.name != "nt":
        return True
    params = (
        'advfirewall firewall add rule '
        f'name="{MOBILE_FIREWALL_RULE}" dir=in action=allow protocol=TCP '
        f'localport={MOBILE_LAN_PORT} remoteip=localsubnet profile=any'
    )
    try:
        rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", "netsh.exe", params, None, 0)
        return int(rc) > 32
    except Exception:
        return False


def _mobile_token_role(request: Request) -> str:
    token = str(request.query_params.get("token") or "").strip()
    auth = str(request.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
    if token and MOBILE_RECEPTION_TOKEN and hmac.compare_digest(token, MOBILE_RECEPTION_TOKEN):
        return "reception"
    if token and MOBILE_DOCTOR_TOKEN and hmac.compare_digest(token, MOBILE_DOCTOR_TOKEN):
        return "doctor"
    raise HTTPException(401, "Enlace de Agenda móvil inválido o vencido")


def _ensure_mobile_tokens() -> tuple[str, str]:
    global MOBILE_DOCTOR_TOKEN, MOBILE_RECEPTION_TOKEN
    updates = {}
    if not MOBILE_DOCTOR_TOKEN:
        MOBILE_DOCTOR_TOKEN = secrets.token_urlsafe(32)
        updates["MOBILE_DOCTOR_TOKEN"] = MOBILE_DOCTOR_TOKEN
    if not MOBILE_RECEPTION_TOKEN:
        MOBILE_RECEPTION_TOKEN = secrets.token_urlsafe(32)
        updates["MOBILE_RECEPTION_TOKEN"] = MOBILE_RECEPTION_TOKEN
    if updates:
        _upsert_local_env(updates)
    return MOBILE_DOCTOR_TOKEN, MOBILE_RECEPTION_TOKEN


def _mobile_require_reception(request: Request) -> str:
    role = _mobile_token_role(request)
    if role != "reception":
        raise HTTPException(403, "La agenda del doctor es solo lectura")
    return role


def _mobile_cloud_db() -> Session:
    if not cloud_configured() or FORCE_OFFLINE or not check_cloud(force=False) or not CloudSessionLocal:
        raise HTTPException(503, "La agenda móvil necesita conexión con la nube para guardar cambios")
    return CloudSessionLocal()


def _mobile_unlinked(item: ConfirmafyAgendaItem) -> bool:
    return str(item.source_hash or "").startswith("mobile:")


def _mobile_source_hash(nombre: str, celular: str, fecha: date, hora: str, nonce: Optional[str] = None) -> str:
    clean_name = normalize_lookup_name(nombre or "PACIENTE")
    phone = normalize_lookup_phone(celular or "")
    seed = nonce or uuid.uuid4().hex
    return "mobile:" + hashlib.sha1(f"{clean_name}|{phone}|{fecha.isoformat()}|{hora}|{seed}".encode("utf-8")).hexdigest()


def _mobile_normalize_contact(data) -> tuple[str, str, dict]:
    name = " ".join(str(getattr(data, "nombre", "") or "").split()).upper()
    phone = re.sub(r"\D", "", str(getattr(data, "celular", "") or ""))
    if len(name) < 3:
        raise HTTPException(400, "Escribe el nombre del paciente")
    if len(phone) < 8 or len(phone) > 15:
        raise HTTPException(400, "Escribe un número de celular válido")
    normalized = normalize_appointment_payload(type("MobileSlot", (), {
        "model_dump": lambda self: {"fecha": data.fecha, "hora": data.hora, "nota": None}
    })())
    return name, phone, normalized


@app.middleware("http")
async def mobile_asset_no_cache(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/mobile-static/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


@app.get("/mobile", response_class=FileResponse)
@app.get("/mobile/", response_class=FileResponse)
def mobile_agenda_page():
    path = Path(BASE_DIR) / "mobile" / "index.html"
    if not path.exists():
        raise HTTPException(404, "Agenda móvil no instalada")
    response = FileResponse(path)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.get("/mobile/manifest.webmanifest")
def mobile_manifest():
    path = Path(BASE_DIR) / "mobile" / "manifest.webmanifest"
    if not path.exists():
        raise HTTPException(404, "Agenda móvil no instalada")
    return FileResponse(path, media_type="application/manifest+json")


@app.get("/mobile/sw.js")
def mobile_service_worker():
    path = Path(BASE_DIR) / "mobile" / "sw.js"
    if not path.exists():
        raise HTTPException(404, "Agenda móvil no instalada")
    response = FileResponse(path, media_type="application/javascript")
    response.headers["Service-Worker-Allowed"] = "/mobile/"
    response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/api/mobile/me")
def mobile_me(request: Request):
    role = _mobile_token_role(request)
    return {"role": role, "read_only": role == "doctor", "version": APP_VERSION}


def _mobile_secret_path(token: str) -> str:
    # El secreto se coloca tras # para que el navegador NO lo envíe a Cloudflare
    # ni quede en logs HTTP. mobile/app.js lo toma del fragmento y luego usa un
    # encabezado Authorization para las APIs.
    return f"/mobile/?v=4.3.34#token={token}"


def _agenda_cloud_link(token: str) -> str:
    return f"{AGENDA_CLOUD_BASE_URL}#token={token}"


def _agenda_cloud_signature(doctor: str, reception: str) -> str:
    return hashlib.sha256(f"{doctor}|{reception}".encode("utf-8")).hexdigest()


def _write_cloud_agenda_keys(doctor: str, reception: str, *, replace_existing: bool = False) -> None:
    """Registra solo hashes de las llaves en Neon; nunca guarda el secreto en la nube."""
    if not cloud_configured() or not CloudSessionLocal:
        raise RuntimeError("Neon no está configurado")
    if FORCE_OFFLINE or not check_cloud(force=False):
        raise RuntimeError("Neon no está disponible en este momento")
    doctor_hash = hashlib.sha256(doctor.encode("utf-8")).hexdigest()
    reception_hash = hashlib.sha256(reception.encode("utf-8")).hexdigest()
    with CloudSessionLocal() as cdb:
        try:
            if replace_existing:
                # El enlace del doctor es permanente: nunca desactivamos llaves
                # de solo lectura al renovar el acceso editable de recepción.
                cdb.execute(text("""
                    UPDATE agenda_private.web_keys
                    SET active = false
                    WHERE access_level = 'reception'
                """))
            for key_hash, role in ((doctor_hash, "doctor"), (reception_hash, "reception")):
                cdb.execute(text("""
                    INSERT INTO agenda_private.web_keys (key_hash, access_level, active)
                    SELECT :key_hash, :role, true
                    WHERE NOT EXISTS (
                        SELECT 1 FROM agenda_private.web_keys WHERE key_hash = :key_hash
                    )
                """), {"role": role, "key_hash": key_hash})
                cdb.execute(text("""
                    UPDATE agenda_private.web_keys
                    SET access_level = :role, active = true
                    WHERE key_hash = :key_hash
                """), {"role": role, "key_hash": key_hash})
            cdb.commit()
        except Exception:
            cdb.rollback()
            raise


def _agenda_cloud_payload(doctor: str, reception: str, *, force_sync: bool = False) -> dict:
    global AGENDA_CLOUD_KEYS_SYNCED_SHA
    signature = _agenda_cloud_signature(doctor, reception)
    registered = bool(AGENDA_CLOUD_KEYS_SYNCED_SHA and hmac.compare_digest(AGENDA_CLOUD_KEYS_SYNCED_SHA, signature))
    error = ""
    if force_sync or not registered:
        try:
            _write_cloud_agenda_keys(doctor, reception, replace_existing=False)
            registered = True
            AGENDA_CLOUD_KEYS_SYNCED_SHA = signature
            _upsert_local_env({"AGENDA_CLOUD_KEYS_SYNCED_SHA": signature})
        except Exception as exc:
            error = _cloud_error_hint(exc) if "Neon" not in str(exc) else str(exc)
    return {
        "enabled": True,
        "base_url": AGENDA_CLOUD_BASE_URL,
        "doctor_url": _agenda_cloud_link(doctor),
        "reception_url": _agenda_cloud_link(reception),
        "registered": registered,
        "last_error": error,
        "always_available": True,
        "architecture": "GitHub Pages + Neon Data API",
    }


def _mobile_remote_payload(doctor: str, reception: str) -> dict:
    status = remote_tunnel_status(DATA_DIR)
    configured_base = ""
    try:
        configured_base = remote_normalize_base_url(REMOTE_AGENDA_BASE_URL) if REMOTE_AGENDA_BASE_URL else ""
    except Exception:
        configured_base = ""
    active_base = str(status.get("public_base_url") or "").rstrip("/")
    base = active_base or configured_base
    return {
        "configured": bool(configured_base and REMOTE_AGENDA_TUNNEL_TOKEN),
        "autostart": bool(REMOTE_AGENDA_AUTOSTART),
        "running": bool(status.get("running")),
        "mode": status.get("mode") or "off",
        "public_base_url": base,
        "active_base_url": active_base,
        "doctor_url": base + _mobile_secret_path(doctor) if base else "",
        "reception_url": base + _mobile_secret_path(reception) if base else "",
        "cloudflared_ready": bool(status.get("cloudflared_ready")),
        "downloading": bool(status.get("downloading")),
        "last_error": status.get("last_error") or "",
    }


@app.get("/api/mobile/config")
def mobile_config(request: Request, force_cloud: bool = False, user: User = Depends(current_user)):
    if not _is_loopback_client(request):
        raise HTTPException(403, "Esta configuración solo se abre desde la PC de Recepción")
    doctor, reception = _ensure_mobile_tokens()
    lan_ip = _preferred_lan_ip()
    lan_base = f"http://{lan_ip}:{MOBILE_LAN_PORT}" if lan_ip else ""
    firewall = _mobile_firewall_present() or _try_add_mobile_firewall_rule()
    return {
        "enabled": True,
        "doctor_path": _mobile_secret_path(doctor),
        "reception_path": _mobile_secret_path(reception),
        "lan_ip": lan_ip,
        "lan_base_url": lan_base,
        "firewall_ready": firewall,
        # Verificar la configuración también vuelve a registrar las llaves
        # actuales en Neon sin cambiarlas. Así una pérdida del registro cloud
        # no obliga a reemplazar el acceso guardado del doctor.
        "cloud": _agenda_cloud_payload(doctor, reception, force_sync=bool(force_cloud)),
        "note": (
            "La Agenda Cloud funciona 24/7 aunque esta PC esté apagada. La red local queda disponible solo como respaldo dentro del consultorio."
            if lan_ip else
            "La Agenda Cloud funciona 24/7 aunque esta PC esté apagada. No se detectó una red local para el acceso de respaldo."
        ),
    }


@app.post("/api/mobile/network/enable")
def mobile_network_enable(request: Request, user: User = Depends(current_user)):
    if not _is_loopback_client(request):
        raise HTTPException(403, "Esta acción solo se ejecuta desde la PC de Recepción")
    if os.name != "nt":
        return {"ready": True, "elevation_requested": False, "message": "No requiere regla de Windows."}
    if _mobile_firewall_present() or _try_add_mobile_firewall_rule():
        return {"ready": True, "elevation_requested": False, "message": "Acceso desde la red local habilitado."}
    requested = _request_mobile_firewall_elevation()
    return {
        "ready": False,
        "elevation_requested": requested,
        "message": (
            "Windows pidió permiso de administrador. Acéptalo y luego pulsa Renovar enlaces."
            if requested else
            "Windows no pudo abrir el permiso automáticamente. Revisa el Firewall de Windows."
        ),
    }


@app.get("/api/mobile/remote/status")
def mobile_remote_status(request: Request, user: User = Depends(current_user)):
    if not _is_loopback_client(request):
        raise HTTPException(403, "Esta configuración solo se abre desde la PC de Recepción")
    doctor, reception = _ensure_mobile_tokens()
    return _mobile_remote_payload(doctor, reception)


@app.post("/api/mobile/remote/quick/start")
def mobile_remote_quick_start(request: Request, user: User = Depends(current_user)):
    if not _is_loopback_client(request):
        raise HTTPException(403, "Esta acción solo se ejecuta desde la PC de Recepción")
    try:
        remote_start_quick_tunnel(DATA_DIR, origin=f"http://127.0.0.1:{LOCAL_HTTP_PORT}", wait_seconds=18)
    except Exception as exc:
        raise HTTPException(502, f"No se pudo publicar la agenda: {exc}")
    doctor, reception = _ensure_mobile_tokens()
    payload = _mobile_remote_payload(doctor, reception)
    payload["message"] = (
        "Acceso remoto de prueba listo. Este enlace cambia si se reinicia el túnel; para el enlace definitivo configura el túnel estable."
        if payload.get("active_base_url") else
        "Cloudflare está conectando. Pulsa Actualizar estado en unos segundos."
    )
    return payload


@app.post("/api/mobile/remote/stable/restart")
def mobile_remote_stable_restart(request: Request, user: User = Depends(current_user)):
    if not _is_loopback_client(request):
        raise HTTPException(403, "Esta acción solo se ejecuta desde la PC de Recepción")
    if not REMOTE_AGENDA_BASE_URL or not REMOTE_AGENDA_TUNNEL_TOKEN:
        raise HTTPException(400, "El túnel estable todavía no está configurado en .env")
    try:
        remote_start_named_tunnel(DATA_DIR, REMOTE_AGENDA_TUNNEL_TOKEN, REMOTE_AGENDA_BASE_URL)
    except Exception as exc:
        raise HTTPException(502, f"No se pudo iniciar el túnel estable: {exc}")
    doctor, reception = _ensure_mobile_tokens()
    return _mobile_remote_payload(doctor, reception)


@app.post("/api/mobile/remote/stop")
def mobile_remote_stop(request: Request, user: User = Depends(current_user)):
    if not _is_loopback_client(request):
        raise HTTPException(403, "Esta acción solo se ejecuta desde la PC de Recepción")
    remote_stop_tunnel(DATA_DIR)
    doctor, reception = _ensure_mobile_tokens()
    return {**_mobile_remote_payload(doctor, reception), "message": "Acceso remoto detenido."}


@app.post("/api/mobile/links/rotate")
def mobile_rotate_links(request: Request, user: User = Depends(current_user)):
    if not _is_loopback_client(request):
        raise HTTPException(403, "Esta acción solo se ejecuta desde la PC de Recepción")
    global MOBILE_DOCTOR_TOKEN, MOBILE_RECEPTION_TOKEN, AGENDA_CLOUD_KEYS_SYNCED_SHA
    old_doctor, old_reception = _ensure_mobile_tokens()
    # v4.3.49: el token del doctor es permanente. Renovar accesos solo cambia
    # el token editable de recepción; el enlace de consulta del doctor conserva
    # exactamente el mismo secreto y puede quedarse guardado en Inicio.
    new_doctor = old_doctor
    new_reception = secrets.token_urlsafe(32)
    # Primero persistimos localmente. Si Neon falla, restauramos las llaves previas
    # para no mostrar enlaces nuevos que todavía no funcionen en la nube.
    try:
        _upsert_local_env({
            "MOBILE_DOCTOR_TOKEN": new_doctor,
            "MOBILE_RECEPTION_TOKEN": new_reception,
            "AGENDA_CLOUD_KEYS_SYNCED_SHA": "",
        })
        _write_cloud_agenda_keys(new_doctor, new_reception, replace_existing=True)
    except Exception as exc:
        try:
            _upsert_local_env({
                "MOBILE_DOCTOR_TOKEN": old_doctor,
                "MOBILE_RECEPTION_TOKEN": old_reception,
                "AGENDA_CLOUD_KEYS_SYNCED_SHA": AGENDA_CLOUD_KEYS_SYNCED_SHA,
            })
        except Exception:
            pass
        raise HTTPException(503, f"No se pudieron renovar los enlaces porque Neon no respondió: {_cloud_error_hint(exc)}")
    MOBILE_DOCTOR_TOKEN = new_doctor
    MOBILE_RECEPTION_TOKEN = new_reception
    AGENDA_CLOUD_KEYS_SYNCED_SHA = _agenda_cloud_signature(new_doctor, new_reception)
    _upsert_local_env({"AGENDA_CLOUD_KEYS_SYNCED_SHA": AGENDA_CLOUD_KEYS_SYNCED_SHA})
    return {
        "ok": True,
        "doctor_path": _mobile_secret_path(new_doctor),
        "reception_path": _mobile_secret_path(new_reception),
        "cloud": _agenda_cloud_payload(new_doctor, new_reception),
        "message": "Acceso editable renovado. El enlace del doctor permanece igual y seguirá funcionando.",
    }


@app.get("/api/mobile/agenda/week")
def mobile_agenda_week(anchor: date, request: Request):
    role = _mobile_token_role(request)
    # La agenda web nunca expone semanas anteriores a la actual. Incluso si
    # alguien modifica manualmente el parámetro anchor, el servidor lo limita.
    today = date.today()
    current_monday = today - timedelta(days=today.weekday())
    requested_monday = anchor - timedelta(days=anchor.weekday())
    safe_anchor = current_monday if requested_monday < current_monday else anchor
    # La lectura usa la copia local para no consultar Neon cada vez que se abre el teléfono.
    with LocalSessionLocal() as db:
        payload = agenda_week(anchor=safe_anchor, db=db, user=User(id=0, username="mobile", password_hash="", role=role))
    safe_days = []
    for day in payload.get("days", []):
        rows = []
        for row in day.get("appointments", []):
            staged = row.get("staged") or {}
            appointment = row.get("appointment") or {}
            patient = row.get("patient") or {}
            source = str(row.get("source_type") or "")
            # appointment conserva `nota` para mostrarla en la agenda web como
            # texto operativo; el celular del paciente sigue sin exponerse.
            rows.append({
                "source_type": source,
                "appointment": appointment,
                "patient": {"id": patient.get("id"), "nombre": patient.get("nombre")},
                "staged": {"id": staged.get("id"), "nombre": staged.get("nombre"), "fecha": staged.get("fecha"), "hora": staged.get("hora")} if staged else None,
                "conflict": bool(row.get("conflict")),
            })
        safe_days.append({"label": day.get("label"), "date": day.get("date"), "appointments": rows})
    return {"anchor": payload.get("anchor"), "week_start": payload.get("week_start"), "days": safe_days, "conflicts": payload.get("conflicts", 0), "role": role}


@app.post("/api/mobile/appointments")
def mobile_create_appointment(data: MobileAppointmentIn, request: Request):
    _mobile_require_reception(request)
    name, phone, values = _mobile_normalize_contact(data)
    db = _mobile_cloud_db()
    try:
        conflicts = appointment_conflicts(db, data.fecha, values["hora"], 20)
        if conflicts:
            raise HTTPException(409, occupied_message(data.fecha, values["hora"], conflicts))
        item = ConfirmafyAgendaItem(
            nombre=name, celular=phone, fecha=data.fecha, hora=values["hora"], duracion=20,
            source_hash=_mobile_source_hash(name, phone, data.fecha, values["hora"]),
        )
        db.add(item); db.flush()
        audit(db, "mobile-reception", "crear_cita_movil", f"{name} · {data.fecha} {values['hora']}")
        db.commit(); db.refresh(item)
        mirror_confirmafy_agenda_local(item)
        schedule_whatsapp_for_contact(source_type="staged", source_id=item.id, name=item.nombre, phone=item.celular or "", fecha=item.fecha, hora=item.hora)
        return {"ok": True, "id": item.id, "appointment": {"id": None, "fecha": item.fecha, "hora": item.hora, "estado": "PENDIENTE", "origen": "MOVIL"}}
    finally:
        db.close()


@app.put("/api/mobile/unlinked/{item_id}")
def mobile_update_unlinked(item_id: int, data: MobileUnlinkedUpdateIn, request: Request):
    _mobile_require_reception(request)
    db = _mobile_cloud_db()
    try:
        item = db.get(ConfirmafyAgendaItem, item_id)
        if not item or not _mobile_unlinked(item):
            raise HTTPException(404, "Cita móvil no encontrada")
        values = normalize_appointment_payload(type("MobileSlot", (), {"model_dump": lambda self: {"fecha": data.fecha, "hora": data.hora, "nota": None}})())
        # Excluimos temporalmente esta misma cita staged para validar el nuevo horario.
        original_date, original_time = item.fecha, item.hora
        item.fecha = date(1900, 1, 1)
        db.flush()
        conflicts = appointment_conflicts(db, data.fecha, values["hora"], 20)
        item.fecha, item.hora = original_date, original_time
        if conflicts:
            raise HTTPException(409, occupied_message(data.fecha, values["hora"], conflicts))
        if data.nombre is not None:
            name = " ".join(str(data.nombre or "").split()).upper()
            if len(name) < 3: raise HTTPException(400, "Escribe el nombre del paciente")
            item.nombre = name
        if data.celular is not None:
            phone = re.sub(r"\D", "", str(data.celular or ""))
            if len(phone) < 8 or len(phone) > 15: raise HTTPException(400, "Escribe un celular válido")
            item.celular = phone
        item.fecha = data.fecha; item.hora = values["hora"]
        item.source_hash = _mobile_source_hash(item.nombre, item.celular or "", item.fecha, item.hora)
        db.commit(); mirror_confirmafy_agenda_local(item)
        schedule_whatsapp_for_contact(source_type="staged", source_id=item.id, name=item.nombre, phone=item.celular or "", fecha=item.fecha, hora=item.hora)
        return {"ok": True}
    finally:
        db.close()


@app.delete("/api/mobile/unlinked/{item_id}")
def mobile_delete_unlinked(item_id: int, request: Request):
    _mobile_require_reception(request)
    db = _mobile_cloud_db()
    try:
        item = db.get(ConfirmafyAgendaItem, item_id)
        if not item or not _mobile_unlinked(item):
            raise HTTPException(404, "Cita móvil no encontrada")
        db.delete(item); db.commit(); mirror_delete_confirmafy_agenda_local(item_id); _whatsapp_cancel_pending("staged", item_id)
        return {"ok": True}
    finally:
        db.close()


@app.put("/api/mobile/appointments/{appointment_id}")
def mobile_update_linked(appointment_id: int, data: MobileRescheduleIn, request: Request):
    _mobile_require_reception(request)
    values = normalize_appointment_payload(type("MobileSlot", (), {"model_dump": lambda self: {"fecha": data.fecha, "hora": data.hora, "nota": None}})())
    db = _mobile_cloud_db()
    try:
        a = db.get(Appointment, appointment_id)
        if not a or a.origen == CONFIRMAFY_ATTENDED_ORIGIN:
            raise HTTPException(404, "Cita no encontrada")
        conflicts = appointment_conflicts(db, data.fecha, values["hora"], 20, exclude_id=appointment_id)
        if conflicts: raise HTTPException(409, occupied_message(data.fecha, values["hora"], conflicts))
        a.fecha=data.fecha; a.hora=values["hora"]; a.estado="REAGENDADA"; a.origen="MOVIL"; a.updated_at=datetime.utcnow()
        db.commit(); mirror_appointment_to_local(a)
        p = db.get(Patient, a.patient_id)
        if p: schedule_whatsapp_for_contact(source_type="appointment", source_id=a.id, name=p.nombre, phone=p.celular or "", fecha=a.fecha, hora=a.hora)
        return {"ok": True}
    finally:
        db.close()


@app.delete("/api/mobile/appointments/{appointment_id}")
def mobile_delete_linked(appointment_id: int, request: Request):
    _mobile_require_reception(request)
    db = _mobile_cloud_db()
    try:
        a = db.get(Appointment, appointment_id)
        if not a or a.origen == CONFIRMAFY_ATTENDED_ORIGIN:
            raise HTTPException(404, "Cita no encontrada")
        db.delete(a); db.commit(); mirror_delete_appointment_local(appointment_id); _whatsapp_cancel_pending("appointment", appointment_id)
        return {"ok": True}
    finally:
        db.close()


@app.get("/api/whatsapp/outbox")
def whatsapp_outbox(limit: int = 50, user: User = Depends(current_user)):
    lim = max(1, min(int(limit or 50), 200))
    with LocalSessionLocal() as db:
        rows = list(db.scalars(select(WhatsAppOutbox).order_by(WhatsAppOutbox.id.desc()).limit(lim)))
    return [{
        "id": r.id, "template": r.template_name, "source_type": r.source_type, "source_id": r.source_id,
        "phone": ("***" + r.phone[-4:]) if r.phone else "", "status": r.status,
        "due_at": r.due_at, "attempts": r.attempts, "sent_at": r.sent_at, "last_error": r.last_error,
    } for r in rows]


@app.post("/api/whatsapp/process")
def whatsapp_process(user: User = Depends(current_user)):
    return process_whatsapp_outbox_once(limit=20)


@app.get("/api/agenda/recent-patients")
def agenda_recent_patients(
    limit: int = 12, days: int = 1, anchor: Optional[date] = None,
    db: Session = Depends(get_db), user: User = Depends(current_user),
):
    """Pacientes atendidos en una ventana corta de días.

    ``anchor`` permite que el selector de Agenda muestre primero a los pacientes
    atendidos en el día de referencia. Si se intenta agendar una fecha futura,
    el frontend usa hoy como referencia para que recepción tenga a mano a los
    pacientes que acaba de atender. Todo se resuelve contra la copia local.
    """
    lim = min(max(int(limit or 12), 1), 30)
    day_count = min(max(int(days or 1), 1), 30)
    end = anchor or date.today()
    start = end - timedelta(days=day_count - 1)
    last_visit = (
        select(Visit.patient_id, func.max(Visit.fecha).label("ultima_atencion"))
        .where(Visit.fecha >= start, Visit.fecha <= end)
        .group_by(Visit.patient_id)
        .subquery()
    )
    rows = db.execute(
        select(Patient, last_visit.c.ultima_atencion)
        .join(last_visit, last_visit.c.patient_id == Patient.id)
        .order_by(last_visit.c.ultima_atencion.desc(), Patient.id.desc())
        .limit(lim)
    ).all()
    return [{**p_dict(p), "ultima_atencion": ultima} for p, ultima in rows]


@app.get("/api/agenda/pending-count")
def agenda_pending_count(db: Session = Depends(get_db), user: User = Depends(current_user)):
    n = db.scalar(select(func.count(Appointment.id)).where(Appointment.estado == "PENDIENTE")) or 0
    return {"pending": int(n)}


@app.get("/api/agenda/appointments")
def agenda_appointments(estado: str = "TODAS", db: Session = Depends(get_db), user: User = Depends(current_user)):
    stmt = select(Appointment, Patient).join(Patient).where(Appointment.origen != CONFIRMAFY_ATTENDED_ORIGIN)
    e = (estado or "TODAS").strip().upper()
    if e != "TODAS":
        if e not in {"PENDIENTE", "EXPORTADO", "CARGADO"}:
            raise HTTPException(400, "Estado de agenda inválido")
        stmt = stmt.where(Appointment.estado == e)
    stmt = stmt.order_by(Appointment.fecha.asc(), Appointment.hora.asc(), Appointment.id.asc())
    rows = db.execute(stmt).all()
    return [{"appointment": appointment_dict(a), "patient": p_dict(p), "phone_confirmafy": confirmafy_phone(p.celular)} for a, p in rows]





WHATSAPP_CLOUD_TEST_PREFIX = "mobile:whatsapp-cloud-test:"


def _wa_event_display_status(raw: str) -> tuple[str, str]:
    state = str(raw or "").upper()
    return {
        "READ": ("Leído", "success"),
        "DELIVERED": ("Entregado", "success"),
        "SENT": ("Enviado", "success"),
        "SENDING": ("Enviando", "info"),
        "FAILED": ("Error", "danger"),
        "ERROR": ("Error", "danger"),
    }.get(state, (state.replace("_", " ").title() or "Sin enviar", "muted"))


def _wa_timeline_defs(fecha: date, hora: str, created_at: Optional[datetime] = None) -> list[dict]:
    try:
        hh, mm = [int(x) for x in str(hora or "00:00")[:5].split(":")]
        appointment_at = datetime(fecha.year, fecha.month, fecha.day, hh, mm)
    except Exception:
        appointment_at = datetime.combine(fecha, datetime.min.time())
    try:
        ph, pm = [int(x) for x in WHATSAPP_PREVIOUS_DAY_TIME.split(":")]
    except Exception:
        ph, pm = 8, 0
    previous = fecha - timedelta(days=1)
    confirmation_due = datetime(previous.year, previous.month, previous.day, ph, pm)
    return [
        {
            "key": "cita_agendada", "label": "Cita agendada", "template": WHATSAPP_TEMPLATE_CITA_AGENDADA,
            "approved": bool(WHATSAPP_APPROVED_CITA_AGENDADA), "automatic": bool(WHATSAPP_AUTO_CITA_AGENDADA),
            "due_at": (created_at or datetime.now()).isoformat(),
            "planned": "Al guardar la cita",
        },
        {
            "key": "recordatorio_cita", "label": "Confirmación", "template": whatsapp_recordatorio_template_name(),
            "approved": bool(WHATSAPP_APPROVED_RECORDATORIO_CITA), "automatic": bool(WHATSAPP_AUTO_RECORDATORIO_CITA),
            "due_at": confirmation_due.isoformat(),
            "planned": f"{WHATSAPP_PREVIOUS_DAY_TIME} del día anterior",
        },
        {
            "key": "recordatorio_hoy", "label": "Recordatorio", "template": WHATSAPP_TEMPLATE_RECORDATORIO_HOY,
            "approved": bool(WHATSAPP_APPROVED_RECORDATORIO_HOY), "automatic": bool(WHATSAPP_AUTO_RECORDATORIO_HOY),
            "due_at": (appointment_at - timedelta(hours=WHATSAPP_TODAY_HOURS_BEFORE)).isoformat(),
            "planned": f"{WHATSAPP_TODAY_HOURS_BEFORE} h antes de la cita",
        },
    ]


def _wa_timeline_for_source(*, source_type: str, source_id: int, fecha: date, hora: str,
                            created_at: Optional[datetime] = None, appointment_state: str = "") -> dict:
    nodes = _wa_timeline_defs(fecha, hora, created_at)
    by_key: dict[str, dict] = {}
    cloud_error = ""
    if cloud_configured() and CloudSessionLocal and not FORCE_OFFLINE:
        try:
            with CloudSessionLocal() as cdb:
                rows = cdb.execute(text("""
                    SELECT template_name, status, created_at, sent_at, delivered_at, read_at, error_text, due_at
                    FROM whatsapp_cloud.events
                    WHERE source_type = :source_type
                      AND source_id = :source_id
                      AND appointment_date = :appointment_date
                      AND left(appointment_time::text, 5) = :appointment_time
                    ORDER BY created_at ASC
                    LIMIT 30
                """), {
                    "source_type": source_type,
                    "source_id": int(source_id),
                    "appointment_date": fecha.isoformat(),
                    "appointment_time": str(hora or "")[:5],
                }).mappings().all()
            for row in rows:
                template = str(row.get("template_name") or "")
                if template == WHATSAPP_TEMPLATE_CITA_AGENDADA:
                    key = "cita_agendada"
                elif template in {WHATSAPP_TEMPLATE_RECORDATORIO_CITA, WHATSAPP_TEMPLATE_RECORDATORIO_CITA_LOGO, whatsapp_recordatorio_template_name()}:
                    key = "recordatorio_cita"
                elif template == WHATSAPP_TEMPLATE_RECORDATORIO_HOY:
                    key = "recordatorio_hoy"
                else:
                    continue
                by_key[key] = dict(row)
        except Exception as exc:
            cloud_error = str(exc)[:180]

    now = datetime.now()
    final = []
    appointment_state = str(appointment_state or "").upper()
    for node in nodes:
        event = by_key.get(node["key"])
        item = dict(node)
        item["event_found"] = bool(event)
        item["response"] = ""
        if event:
            raw_state = str(event.get("status") or "").upper()
            label, tone = _wa_event_display_status(raw_state)
            item.update({
                "status": raw_state, "status_label": label, "tone": tone,
                "timestamp": (
                    event.get("read_at") or event.get("delivered_at") or event.get("sent_at") or event.get("created_at")
                ).isoformat() if (event.get("read_at") or event.get("delivered_at") or event.get("sent_at") or event.get("created_at")) else None,
                "error": str(event.get("error_text") or "")[:220],
            })
        elif node["key"] == "cita_agendada" and not _wa_cita_agendada_allowed(fecha, hora, created_at):
            item.update({"status": "SKIPPED_RULE", "status_label": "Omitido por regla", "tone": "muted", "timestamp": None, "error": "", "planned": "No se envía si faltan menos de 24 h o si ya es el día de confirmación"})
        elif not node["approved"]:
            item.update({"status": "META_PENDING", "status_label": "Pendiente de Meta", "tone": "muted", "timestamp": None, "error": ""})
        elif not node["automatic"]:
            item.update({"status": "NOT_AUTOMATIC", "status_label": "No automático", "tone": "muted", "timestamp": None, "error": ""})
        else:
            try:
                due = datetime.fromisoformat(str(node["due_at"]))
                label = "Programado" if due > now else "Esperando worker"
            except Exception:
                label = "Programado"
            item.update({"status": "SCHEDULED", "status_label": label, "tone": "info", "timestamp": None, "error": ""})
        if node["key"] == "recordatorio_cita":
            if appointment_state in {"CONFIRMADA", "CONFIRMADO"}:
                item["response"] = "Paciente confirmó la cita"
            elif appointment_state == "NO_ASISTIRA":
                item["response"] = "Paciente indicó que no asistirá"
        final.append(item)
    return {"available": not bool(cloud_error), "cloud_error": cloud_error, "items": final}


@app.get("/api/agenda/appointments/{appointment_id}/whatsapp-timeline")
def agenda_appointment_whatsapp_timeline(appointment_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    row = db.execute(select(Appointment, Patient).join(Patient).where(Appointment.id == appointment_id)).first()
    if not row:
        raise HTTPException(404, "Cita no encontrada")
    a, _p = row
    return _wa_timeline_for_source(
        source_type="appointment", source_id=a.id, fecha=a.fecha, hora=a.hora,
        created_at=a.created_at, appointment_state=a.estado,
    )


@app.get("/api/agenda/confirmafy-staged/{item_id}/whatsapp-timeline")
def agenda_staged_whatsapp_timeline(item_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = db.get(ConfirmafyAgendaItem, item_id)
    if not item or str(item.source_hash or "").startswith(WHATSAPP_CLOUD_TEST_PREFIX):
        raise HTTPException(404, "Cita no encontrada")
    return _wa_timeline_for_source(
        source_type="staged", source_id=item.id, fecha=item.fecha, hora=item.hora,
        created_at=item.created_at, appointment_state="PENDIENTE",
    )


@app.get("/api/agenda/appointments/{appointment_id}")
def agenda_appointment_detail(appointment_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    row = db.execute(
        select(Appointment, Patient).join(Patient).where(Appointment.id == appointment_id)
    ).first()
    if not row:
        raise HTTPException(404, "Cita no encontrada")
    a, p = row
    return {"appointment": appointment_dict(a), "patient": p_dict(p), "phone_confirmafy": confirmafy_phone(p.celular)}



def _sync_agenda_states_from_cloud(db: Session, dates: list[date], min_interval: float = 5.0) -> int:
    """Trae solo el estado de las citas visibles desde Neon.

    WhatsApp Cloud actualiza Neon aunque la PC del consultorio esté apagada. La
    Agenda normal lee SQLite para ser rápida, así que sin este puente un "Sí" o
    "No" podía tardar hasta la próxima copia completa en verse en pantalla.

    Esta sincronización es deliberadamente pequeña: consulta únicamente id,
    estado y updated_at de los tres días visibles y se limita a una vez cada
    pocos segundos por semana. No descarga pacientes, atenciones ni facturación.
    """
    if not dates or not cloud_configured() or FORCE_OFFLINE or not CloudSessionLocal:
        return 0
    if queue_count() > 0:
        # Si existen cambios locales pendientes, evitamos mezclar dos fuentes
        # hasta que la cola termine de sincronizar.
        return 0
    key = ",".join(sorted(d.isoformat() for d in dates))
    now = time.time()
    with _state_lock:
        last = float(_agenda_status_sync_at.get(key) or 0.0)
    if now - last < float(min_interval):
        return 0
    if not check_cloud(force=False):
        return 0
    if not _agenda_status_sync_lock.acquire(blocking=False):
        return 0
    try:
        # Revalidamos el límite después de obtener el lock para evitar dos
        # consultas iguales disparadas casi al mismo tiempo por la interfaz.
        now = time.time()
        with _state_lock:
            last = float(_agenda_status_sync_at.get(key) or 0.0)
        if now - last < float(min_interval):
            return 0
        with CloudSessionLocal() as cdb:
            rows = cdb.execute(
                select(Appointment.id, Appointment.estado, Appointment.updated_at)
                .where(Appointment.fecha.in_(dates))
            ).all()
        changed = 0
        for appointment_id, cloud_state, cloud_updated_at in rows:
            local_row = db.get(Appointment, int(appointment_id))
            if not local_row:
                continue
            new_state = str(cloud_state or "PENDIENTE")
            if str(local_row.estado or "PENDIENTE") != new_state:
                local_row.estado = new_state
                changed += 1
            if cloud_updated_at is not None:
                local_row.updated_at = cloud_updated_at
        if changed:
            db.commit()
        with _state_lock:
            _agenda_status_sync_at[key] = time.time()
        return changed
    except Exception as exc:
        # La agenda local sigue funcionando aunque Neon no responda.
        with _state_lock:
            _state["last_error"] = f"No se pudo sincronizar estado de Agenda: {_cloud_error_hint(exc)}"[:300]
        return 0
    finally:
        _agenda_status_sync_lock.release()


_agenda_status_kick_lock = threading.Lock()
_agenda_status_kick_running: set[tuple[str, ...]] = set()

def _kick_agenda_status_sync(dates) -> None:
    key = tuple(str(d) for d in dates)
    with _agenda_status_kick_lock:
        if key in _agenda_status_kick_running:
            return
        _agenda_status_kick_running.add(key)

    def worker():
        try:
            with LocalSessionLocal() as ldb:
                _sync_agenda_states_from_cloud(ldb, dates)
        except Exception:
            pass
        finally:
            with _agenda_status_kick_lock:
                _agenda_status_kick_running.discard(key)

    threading.Thread(target=worker, name="agenda-state-sync-bg", daemon=True).start()


@app.get("/api/agenda/week")
def agenda_week(anchor: date, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Agenda semanal unificada.

    Las citas de Confirmafy sin vincular viven en una tabla independiente y se
    mezclan solo para visualizar la agenda. Esta lectura es local-first, de modo
    que navegar entre semanas no toca Neon.
    """
    monday = anchor - timedelta(days=anchor.weekday())
    day_defs = [
        ("Jueves", monday + timedelta(days=3)),
        ("Viernes", monday + timedelta(days=4)),
        ("Sábado", monday + timedelta(days=5)),
    ]
    dates = [d for _, d in day_defs]
    # Refresca únicamente CONFIRMADA / NO_ASISTIRA y demás estados cambiados
    # desde WhatsApp Cloud antes de dibujar la semana.
    _kick_agenda_status_sync(dates)
    linked_rows = db.execute(
        select(Appointment, Patient).join(Patient)
        .where(Appointment.fecha.in_(dates), Appointment.origen != CONFIRMAFY_ATTENDED_ORIGIN)
        .order_by(Appointment.fecha.asc(), Appointment.hora.asc(), Appointment.id.asc())
    ).all()
    attended_hashes = active_confirmafy_attended_hashes(db, dates)
    staged_rows = [a for a in db.scalars(
        select(ConfirmafyAgendaItem)
        .where(ConfirmafyAgendaItem.fecha.in_(dates))
        .order_by(ConfirmafyAgendaItem.fecha.asc(), ConfirmafyAgendaItem.hora.asc(), ConfirmafyAgendaItem.id.asc())
    ) if str(a.source_hash or "") not in attended_hashes
       and not str(a.source_hash or "").startswith("mobile:whatsapp-cloud-test:")]

    grouped = {d.isoformat(): [] for d in dates}
    timeline: dict[date, list[tuple[int, int, str, str]]] = {}
    for a, p in linked_rows:
        try: start_m = hhmm_to_minutes(a.hora)
        except Exception: continue
        key = f"linked:{a.id}"
        timeline.setdefault(a.fecha, []).append((start_m, start_m + int(a.duracion or 20), key, p.nombre if p else "Paciente"))
    for a in staged_rows:
        try: start_m = hhmm_to_minutes(a.hora)
        except Exception: continue
        key = f"staged:{a.id}"
        timeline.setdefault(a.fecha, []).append((start_m, start_m + int(a.duracion or 20), key, a.nombre))

    conflict_keys: set[str] = set()
    for _, entries in timeline.items():
        entries.sort(key=lambda x: (x[0], x[1], x[2]))
        for i, (st, en, key, _) in enumerate(entries):
            for bst, ben, bkey, _ in entries[i + 1:]:
                if bst >= en: break
                if st < ben and bst < en:
                    conflict_keys.add(key); conflict_keys.add(bkey)

    for a, p in linked_rows:
        legacy_confirmafy = str(a.origen or "").upper() == "CONFIRMAFY_IMPORTADO"
        grouped.setdefault(a.fecha.isoformat(), []).append({
            # Las citas antiguas importadas con el flujo previo todavía pueden
            # tener patient_id. Visualmente las tratamos igual que una cita
            # externa sin vincular para que recepción vuelva a confirmar la
            # identidad cara a cara antes de registrar la atención.
            "source_type": "CONFIRMAFY_LEGACY" if legacy_confirmafy else "PATIENT_APPOINTMENT",
            "appointment": appointment_dict(a), "patient": p_dict(p),
            "phone_confirmafy": confirmafy_phone(p.celular),
            "conflict": f"linked:{a.id}" in conflict_keys,
        })
    for a in staged_rows:
        grouped.setdefault(a.fecha.isoformat(), []).append({
            "source_type": "MOBILE_UNLINKED" if _mobile_unlinked(a) else "LEGACY_UNLINKED",
            "staged": confirmafy_agenda_dict(a),
            "appointment": {
                "id": None, "patient_id": None, "fecha": a.fecha, "hora": a.hora,
                "duracion": int(a.duracion or 20), "nota": None, "estado": "CARGADO",
                "origen": "CONFIRMAFY_SIN_VINCULAR",
            },
            "patient": {"id": None, "cedula": None, "nombre": a.nombre, "celular": a.celular,
                        "correo": None, "lugar": None, "notas": None},
            "phone_confirmafy": confirmafy_phone(a.celular),
            "conflict": f"staged:{a.id}" in conflict_keys,
        })
    for key in grouped:
        grouped[key].sort(key=lambda row: (str((row.get("appointment") or {}).get("hora") or ""), str((row.get("patient") or {}).get("nombre") or "")))

    return {
        "anchor": anchor, "week_start": monday,
        "days": [{"label": label, "date": d, "appointments": grouped.get(d.isoformat(), [])} for label, d in day_defs],
        "conflicts": len(conflict_keys),
    }


@app.get("/api/agenda/dashboard")
def agenda_dashboard(
    estado: str = "PENDIENTE", limit: int = 12, recent_days: int = 1, anchor: Optional[date] = None,
    db: Session = Depends(get_db), user: User = Depends(current_user),
):
    """Carga Agenda con el mínimo de consultas.

    v4.2.4: la agenda semanal se movió a Nueva atención. El parámetro ``anchor``
    queda opcional solo para compatibilidad con un navegador que aún conserve
    momentáneamente el JavaScript anterior durante una actualización.
    """
    appointments = agenda_appointments(estado=estado, db=db, user=user)
    normalized = (estado or "PENDIENTE").strip().upper()
    payload = {
        "recent_patients": agenda_recent_patients(limit=limit, days=recent_days, db=db, user=user),
        "appointments": appointments,
        # Al abrir Agenda en Pendientes, la propia lista ya contiene el total.
        # Así evitamos una consulta COUNT adicional a SQLite/Neon.
        "pending": len(appointments) if normalized == "PENDIENTE" else agenda_pending_count(db=db, user=user)["pending"],
    }
    if anchor is not None:
        payload["week"] = agenda_week(anchor=anchor, db=db, user=user)
    return payload


@app.get("/api/agenda/slots")
def agenda_slots(
    fecha: date,
    exclude_id: Optional[int] = None,
    user: User = Depends(current_user),
):
    """Horarios de reagenda calculados contra la copia SQLite local.

    v4.3.11: abrir el selector de hora no necesita despertar Neon. La copia local
    basta para pintar los bloques ocupados; al guardar, ``agenda_create`` /
    ``agenda_update`` vuelven a validar el cruce contra la base activa, por lo que
    una cita creada desde otra PC nunca puede sobrescribirse por accidente.

    La ruta se mantiene deliberadamente autocontenida para evitar depender de
    estados temporales del modal (y corregir el error de ``valid_selection`` que
    podía aparecer al abrir Reagendar en algunas instalaciones actualizadas).
    """
    with LocalSessionLocal() as ldb:
        stmt = (
            select(Appointment, Patient.nombre)
            .outerjoin(Patient, Patient.id == Appointment.patient_id)
            .where(Appointment.fecha == fecha, Appointment.origen != CONFIRMAFY_ATTENDED_ORIGIN)
        )
        if exclude_id is not None:
            stmt = stmt.where(Appointment.id != int(exclude_id))
        day_rows = ldb.execute(stmt.order_by(Appointment.hora.asc(), Appointment.id.asc())).all()
        attended_hashes = active_confirmafy_attended_hashes(ldb, [fecha])
        staged_rows = [item for item in ldb.scalars(
            select(ConfirmafyAgendaItem)
            .where(ConfirmafyAgendaItem.fecha == fecha)
            .order_by(ConfirmafyAgendaItem.hora.asc(), ConfirmafyAgendaItem.id.asc())
        ) if str(item.source_hash or "") not in attended_hashes]

    occupied: list[tuple[int, int, str]] = []
    for appointment, patient_name in day_rows:
        try:
            start_minute = hhmm_to_minutes(appointment.hora)
        except Exception:
            continue
        duration = max(1, int(appointment.duracion or 20))
        occupied.append((start_minute, start_minute + duration, patient_name or "Cita ocupada"))
    for item in staged_rows:
        try:
            start_minute = hhmm_to_minutes(item.hora)
        except Exception:
            continue
        duration = max(1, int(item.duracion or 20))
        occupied.append((start_minute, start_minute + duration, item.nombre or "Cita Confirmafy"))

    slots = []
    # Todas las citas son de 20 minutos. Se respeta el almuerzo 12:30–14:00
    # (por eso 12:20 tampoco se ofrece, porque terminaría dentro del almuerzo)
    # y la última cita comienza a las 17:00.
    for minute in range(8 * 60, 17 * 60 + 1, 20):
        end_minute = minute + 20
        if minute < 14 * 60 and end_minute > 12 * 60 + 30:
            continue
        occupied_names = list(dict.fromkeys(
            name for old_start, old_end, name in occupied
            if minute < old_end and old_start < end_minute
        ))
        hora = f"{minute // 60:02d}:{minute % 60:02d}"
        slots.append({
            "time": hora,
            "available": not occupied_names,
            "occupied_by": occupied_names,
        })
    return {"date": fecha, "duration": 20, "slots": slots}


@app.post("/api/agenda/appointments")
def agenda_create(data: AppointmentIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = db.get(Patient, data.patient_id)
    if not p:
        raise HTTPException(404, "Paciente no encontrado")
    if not confirmafy_phone(p.celular):
        raise HTTPException(400, "Completa el celular del paciente antes de reagendar")
    values = normalize_appointment_payload(data)
    conflicts = appointment_conflicts(db, values["fecha"], values["hora"], 20)
    if conflicts:
        raise HTTPException(409, occupied_message(values["fecha"], values["hora"], conflicts))
    a = Appointment(
        patient_id=data.patient_id, fecha=values["fecha"], hora=values["hora"], duracion=20,
        nota=values["nota"], estado="PENDIENTE", origen="REAGENDADO",
    )
    db.add(a)
    db.flush()
    if is_offline_db(db):
        payload = {"patient_id": a.patient_id, "fecha": a.fecha.isoformat(), "hora": a.hora, "nota": a.nota, "estado": a.estado, "origen": a.origen}
        add_queue(db, "appointment.create", "appointment", payload, user.username, a.id)
        audit(db, user, "crear_cita_offline", f"Cita local {a.id}, paciente {p.id}, {a.fecha} {a.hora}")
        db.commit()
        schedule_whatsapp_for_contact(source_type="appointment", source_id=a.id, name=p.nombre, phone=p.celular or "", fecha=a.fecha, hora=a.hora)
        result = appointment_dict(a); result["offline"] = True
        return result
    audit(db, user, "crear_cita", f"Cita {a.id}, paciente {p.id}, {a.fecha} {a.hora}")
    db.commit()
    mirror_appointment_to_local(a)
    schedule_whatsapp_for_contact(source_type="appointment", source_id=a.id, name=p.nombre, phone=p.celular or "", fecha=a.fecha, hora=a.hora)
    result = appointment_dict(a); result["offline"] = False
    return result


@app.put("/api/agenda/appointments/{appointment_id}")
def agenda_update(appointment_id: int, data: AppointmentUpdateIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = db.get(Appointment, appointment_id)
    if not a:
        raise HTTPException(404, "Cita no encontrada")
    values = normalize_appointment_payload(data)
    conflicts = appointment_conflicts(db, values["fecha"], values["hora"], 20, appointment_id)
    if conflicts:
        raise HTTPException(409, occupied_message(values["fecha"], values["hora"], conflicts))
    a.fecha = values["fecha"]; a.hora = values["hora"]; a.duracion = 20; a.nota = values["nota"]
    a.estado = "PENDIENTE"; a.exported_at = None; a.loaded_at = None; a.updated_at = datetime.utcnow()
    if is_offline_db(db):
        add_queue(db, "appointment.update", "appointment", {"appointment_id": appointment_id, "fecha": a.fecha.isoformat(), "hora": a.hora, "nota": a.nota}, user.username, appointment_id)
        audit(db, user, "reagendar_cita_offline", f"Cita local {appointment_id}: {a.fecha} {a.hora}")
        db.commit()
        p = db.get(Patient, a.patient_id)
        if p: schedule_whatsapp_for_contact(source_type="appointment", source_id=a.id, name=p.nombre, phone=p.celular or "", fecha=a.fecha, hora=a.hora)
        result = appointment_dict(a); result["offline"] = True
        return result
    audit(db, user, "reagendar_cita", f"Cita {appointment_id}: {a.fecha} {a.hora}")
    db.commit(); mirror_appointment_to_local(a)
    p = db.get(Patient, a.patient_id)
    if p: schedule_whatsapp_for_contact(source_type="appointment", source_id=a.id, name=p.nombre, phone=p.celular or "", fecha=a.fecha, hora=a.hora)
    result = appointment_dict(a); result["offline"] = False
    return result


def set_appointment_state(appointment_id: int, state: str, db: Session, user: User):
    a = db.get(Appointment, appointment_id)
    if not a: raise HTTPException(404, "Cita no encontrada")
    state = state.upper()
    now = datetime.utcnow()
    if state == "CARGADO":
        a.estado = "CARGADO"; a.exported_at = a.exported_at or now; a.loaded_at = now; op = "appointment.loaded"
    elif state == "PENDIENTE":
        a.estado = "PENDIENTE"; a.exported_at = None; a.loaded_at = None; op = "appointment.pending"
    else:
        raise HTTPException(400, "Estado inválido")
    a.updated_at = now
    if is_offline_db(db):
        add_queue(db, op, "appointment", {"appointment_id": appointment_id}, user.username, appointment_id)
        audit(db, user, "estado_cita_offline", f"Cita local {appointment_id}: {a.estado}")
        db.commit()
        result=appointment_dict(a); result["offline"]=True
        return result
    audit(db, user, "estado_cita", f"Cita {appointment_id}: {a.estado}")
    db.commit(); mirror_appointment_to_local(a)
    result=appointment_dict(a); result["offline"]=False
    return result


@app.post("/api/agenda/appointments/{appointment_id}/loaded")
def agenda_mark_loaded(appointment_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return set_appointment_state(appointment_id, "CARGADO", db, user)


@app.post("/api/agenda/appointments/{appointment_id}/pending")
def agenda_mark_pending(appointment_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return set_appointment_state(appointment_id, "PENDIENTE", db, user)


@app.delete("/api/agenda/appointments/{appointment_id}")
def agenda_delete(appointment_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Elimina realmente la cita y libera el horario.

    v4.3.73 corrige el comportamiento heredado de v4.3.46: el botón
    "Eliminar cita" ya no convierte la cita en CANCELADA/"No asistirá".
    NO_ASISTIRA queda reservado exclusivamente para la respuesta real del
    paciente al mensaje de confirmación de WhatsApp.
    """
    a = db.get(Appointment, appointment_id)
    if not a:
        raise HTTPException(404, "Cita no encontrada")
    detail = f"Cita {appointment_id}, paciente {a.patient_id}, {a.fecha} {a.hora}"
    if is_offline_db(db):
        add_queue(db, "appointment.delete", "appointment", {"appointment_id": appointment_id}, user.username, appointment_id)
        audit(db, user, "eliminar_cita_offline", detail)
        db.delete(a)
        db.commit()
        _whatsapp_cancel_pending("appointment", appointment_id)
        return {"ok": True, "offline": True, "deleted": True}
    audit(db, user, "eliminar_cita", detail)
    db.delete(a)
    db.commit()
    mirror_delete_appointment_local(appointment_id)
    _whatsapp_cancel_pending("appointment", appointment_id)
    return {"ok": True, "offline": False, "deleted": True}


def _decode_confirmafy_csv(raw: bytes) -> list[dict]:
    """Lee un CSV exportado por Confirmafy sin modificar datos."""
    text_value = None
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            text_value = raw.decode(enc)
            break
        except Exception:
            continue
    if text_value is None:
        raise HTTPException(400, "No se pudo leer el archivo CSV")
    try:
        reader = csv.DictReader(io.StringIO(text_value))
        headers = {str(h or "").strip().lower(): h for h in (reader.fieldnames or [])}
    except Exception:
        raise HTTPException(400, "El archivo no parece ser un CSV válido")
    aliases = {
        "name": ["name", "nombre", "cliente", "patient", "paciente"],
        "phone": ["phone", "telefono", "teléfono", "whatsapp", "celular"],
        "date": ["date", "fecha"],
        "time": ["time", "hora"],
        "duration": ["duration", "duracion", "duración"],
    }
    resolved = {}
    for key, options in aliases.items():
        for opt in options:
            if opt in headers:
                resolved[key] = headers[opt]
                break
    missing = [x for x in ("name", "phone", "date", "time") if x not in resolved]
    if missing:
        raise HTTPException(400, "El CSV debe tener las columnas name, phone, date y time")
    rows=[]
    for line_no,row in enumerate(reader, start=2):
        rows.append({
            "line": line_no,
            "name": " ".join(str(row.get(resolved["name"]) or "").replace("\t", " ").split()).upper(),
            "phone": normalize_lookup_phone(str(row.get(resolved["phone"]) or "")),
            "date": str(row.get(resolved["date"]) or "").strip(),
            "time": str(row.get(resolved["time"]) or "").strip(),
            "duration": str(row.get(resolved.get("duration", "")) or "20").strip(),
        })
    return rows


def _parse_confirmafy_links(raw_links: Optional[str]) -> dict[int, int]:
    if not raw_links:
        return {}
    try:
        data = json.loads(raw_links)
    except Exception:
        raise HTTPException(400, "Los vínculos manuales de pacientes no son válidos")
    if not isinstance(data, dict):
        raise HTTPException(400, "Los vínculos manuales de pacientes no son válidos")
    out: dict[int, int] = {}
    for key, value in data.items():
        try:
            line = int(key); pid = int(value)
        except Exception:
            continue
        if line > 0 and pid > 0:
            out[line] = pid
    return out


def _analyze_confirmafy_import(db: Session, raw: bytes, apply_changes: bool, username: str = "admin", patient_links: Optional[dict[int, int]] = None) -> dict:
    """Importa únicamente la agenda externa; no lee ni modifica patients.

    v4.3.7: Confirmafy queda completamente desacoplado de la ficha clínica durante
    la importación. Nombre y celular se guardan como datos de la cita. Recién al
    pulsar Atender se busca/vincula/crea el paciente, con recepción frente a él.
    """
    source_rows = _decode_confirmafy_csv(raw)
    candidates = []
    duplicates = invalid = 0
    invalid_examples = []
    seen_file = set()
    for row in source_rows:
        name = row["name"]
        phone = row["phone"]
        if not name:
            invalid += 1
            if len(invalid_examples) < 8: invalid_examples.append({"line": row["line"], "reason": "Falta nombre"})
            continue
        raw_date = str(row["date"] or "").strip().lower()
        fecha = None
        try:
            fecha = date.fromisoformat(raw_date[:10])
        except Exception:
            month_map = {"ene":1,"feb":2,"mar":3,"abr":4,"may":5,"jun":6,"jul":7,"ago":8,"sep":9,"sept":9,"oct":10,"nov":11,"dic":12}
            parts = raw_date.replace("/", " ").replace("-", " ").split()
            try:
                if len(parts) >= 3 and parts[0].isdigit() and len(parts[0]) == 4 and parts[1][:4] in month_map:
                    fecha = date(int(parts[0]), month_map[parts[1][:4]], int(parts[2]))
                elif len(parts) >= 3 and parts[2].isdigit() and len(parts[2]) == 4:
                    mon = int(parts[1]) if parts[1].isdigit() else month_map.get(parts[1][:4])
                    fecha = date(int(parts[2]), int(mon), int(parts[0]))
            except Exception:
                fecha = None
        if fecha is None:
            invalid += 1
            if len(invalid_examples) < 8: invalid_examples.append({"line": row["line"], "reason": "Fecha inválida"})
            continue
        raw_time = str(row["time"] or "").replace("\xa0", " ").lower().strip()
        m = re.search(r"(\d{1,2}):(\d{2})", raw_time)
        if not m:
            invalid += 1
            if len(invalid_examples) < 8: invalid_examples.append({"line": row["line"], "reason": "Hora inválida"})
            continue
        hh, mm = int(m.group(1)), int(m.group(2))
        if re.search(r"(?:^|\s)p\s*\.?\s*m\.?", raw_time) and hh < 12: hh += 12
        if re.search(r"(?:^|\s)a\s*\.?\s*m\.?", raw_time) and hh == 12: hh = 0
        if hh > 23 or mm > 59:
            invalid += 1
            if len(invalid_examples) < 8: invalid_examples.append({"line": row["line"], "reason": "Hora inválida"})
            continue
        hora = f"{hh:02d}:{mm:02d}"
        normalized_name = normalize_lookup_name(name)
        source_hash = hashlib.sha1(f"{normalized_name}|{phone}|{fecha.isoformat()}|{hora}".encode("utf-8")).hexdigest()
        if source_hash in seen_file:
            duplicates += 1; continue
        seen_file.add(source_hash)
        candidates.append({"line": row["line"], "name": name, "phone": phone, "fecha": fecha, "hora": hora, "source_hash": source_hash})

    dates = sorted({x["fecha"] for x in candidates})
    existing_staged = list(db.scalars(select(ConfirmafyAgendaItem).where(ConfirmafyAgendaItem.fecha.in_(dates)))) if dates else []
    existing_linked = db.execute(
        select(Appointment, Patient).join(Patient).where(Appointment.fecha.in_(dates))
    ).all() if dates else []
    staged_hashes = {str(x.source_hash) for x in existing_staged}
    schedule: dict[date, list[tuple[int, int, str]]] = {}
    for a, p in existing_linked:
        try: st = hhmm_to_minutes(a.hora)
        except Exception: continue
        schedule.setdefault(a.fecha, []).append((st, st + int(a.duracion or 20), p.nombre if p else "Paciente"))
    for a in existing_staged:
        try: st = hhmm_to_minutes(a.hora)
        except Exception: continue
        schedule.setdefault(a.fecha, []).append((st, st + int(a.duracion or 20), a.nombre))

    imported = conflicts = 0
    conflict_examples = []
    created_items: list[ConfirmafyAgendaItem] = []
    for item in candidates:
        if item["source_hash"] in staged_hashes:
            duplicates += 1; continue
        start_m = hhmm_to_minutes(item["hora"]); end_m = start_m + 20
        occupied = [nm for st, en, nm in schedule.get(item["fecha"], []) if start_m < en and st < end_m]
        if occupied:
            conflicts += 1
            if len(conflict_examples) < 10:
                conflict_examples.append({"line": item["line"], "name": item["name"], "date": item["fecha"].isoformat(), "time": item["hora"], "occupied_by": occupied[:3]})
            continue
        if apply_changes:
            staged = ConfirmafyAgendaItem(
                nombre=item["name"], celular=item["phone"] or None, fecha=item["fecha"], hora=item["hora"],
                duracion=20, source_hash=item["source_hash"],
            )
            db.add(staged); db.flush(); created_items.append(staged)
            if is_offline_db(db):
                add_queue(db, "confirmafy_staged.create", "confirmafy_staged", {
                    "nombre": staged.nombre, "celular": staged.celular, "fecha": staged.fecha.isoformat(),
                    "hora": staged.hora, "source_hash": staged.source_hash,
                }, username, staged.id)
        staged_hashes.add(item["source_hash"])
        schedule.setdefault(item["fecha"], []).append((start_m, end_m, item["name"]))
        imported += 1

    if apply_changes:
        audit(db, username, "importar_agenda_confirmafy", f"{imported} citas externas; 0 pacientes creados o modificados; {duplicates} duplicadas; {conflicts} conflictos; {invalid} inválidas")
        db.commit()
        if not is_offline_db(db):
            for item in created_items: mirror_confirmafy_agenda_local(item)

    return {
        "rows": len(source_rows), "importable": imported, "duplicates": duplicates,
        "conflicts": conflicts, "invalid": invalid, "unmatched": 0, "new_patients": 0,
        "manual_links_used": 0, "legacy_duplicates_detected": 0, "legacy_duplicates_cleaned": 0,
        "legacy_appointments_moved": 0, "legacy_cleanup_deferred": False,
        "conflict_examples": conflict_examples, "invalid_examples": invalid_examples,
        "unmatched_examples": [], "offline": is_offline_db(db), "patients_touched": 0,
    }


@app.delete("/api/agenda/unlinked/{item_id}")
def agenda_delete_unlinked(item_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = db.get(ConfirmafyAgendaItem, item_id)
    if not item:
        raise HTTPException(404, "La cita ya no existe")
    if is_offline_db(db):
        add_queue(db, "confirmafy_staged.delete", "confirmafy_staged", {"item_id": item_id}, user.username, item_id)
    db.delete(item)
    audit(db, user, "eliminar_cita_sin_vincular" + ("_offline" if is_offline_db(db) else ""), f"Cita {item_id}")
    db.commit()
    if not is_offline_db(db): mirror_delete_confirmafy_agenda_local(item_id)
    return {"ok": True}


@app.post("/api/agenda/confirmafy-legacy/{appointment_id}/stage")
def agenda_confirmafy_legacy_stage(appointment_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Convierte una cita heredada de Confirmafy en cita externa sin paciente.

    Versiones anteriores vinculaban la agenda importada a ``patients`` antes
    de que la persona llegara. Desde v4.3.9, al pulsar una de esas citas se
    desprende de la ficha antigua y pasa al mismo flujo seguro de
    ``ConfirmafyAgendaItem``. No crea, fusiona ni modifica pacientes.
    """
    row = db.execute(
        select(Appointment, Patient).join(Patient).where(Appointment.id == appointment_id)
    ).first()
    if not row:
        raise HTTPException(404, "La cita ya no existe. Vuelve a abrir Nueva atención para refrescar la agenda.")
    a, p = row
    if str(a.origen or "").upper() != "CONFIRMAFY_IMPORTADO":
        raise HTTPException(400, "Esta cita no pertenece a una importación de Confirmafy")

    phone = normalize_lookup_phone(p.celular or "")
    normalized_name = normalize_lookup_name(p.nombre or "PACIENTE")
    source_hash = hashlib.sha1(
        f"legacy|{normalized_name}|{phone}|{a.fecha.isoformat()}|{a.hora}".encode("utf-8")
    ).hexdigest()
    staged = db.scalar(select(ConfirmafyAgendaItem).where(ConfirmafyAgendaItem.source_hash == source_hash))
    if not staged:
        staged = ConfirmafyAgendaItem(
            nombre=(p.nombre or "PACIENTE").strip().upper(),
            celular=phone or None, fecha=a.fecha, hora=a.hora,
            duracion=int(a.duracion or 20), source_hash=source_hash,
        )
        db.add(staged)
        db.flush()
        if is_offline_db(db):
            add_queue(db, "confirmafy_staged.create", "confirmafy_staged", {
                "nombre": staged.nombre, "celular": staged.celular, "fecha": staged.fecha.isoformat(),
                "hora": staged.hora, "source_hash": staged.source_hash,
            }, user.username, staged.id)

    old_id = int(a.id)
    if is_offline_db(db):
        add_queue(db, "appointment.delete", "appointment", {"appointment_id": old_id}, user.username, old_id)
    db.delete(a)
    audit(db, user.username, "desvincular_cita_confirmafy_heredada",
          f"Cita {old_id} preparada para confirmar identidad al atender; no se modificó ningún paciente")
    db.commit()

    if not is_offline_db(db):
        mirror_confirmafy_agenda_local(staged)
        mirror_delete_appointment_local(old_id)
    invalidate = True
    return {"ok": True, "staged": confirmafy_agenda_dict(staged), "patient_changed": False}


@app.get("/api/agenda/confirmafy-staged/{item_id}")
def agenda_confirmafy_staged_detail(item_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = db.get(ConfirmafyAgendaItem, item_id)
    if not item: raise HTTPException(404, "La cita de Confirmafy ya no existe")
    return {"staged": confirmafy_agenda_dict(item)}


@app.post("/api/agenda/confirmafy-staged/{item_id}/attended")
def agenda_confirmafy_staged_attended(
    item_id: int, data: ConfirmafyAttendedIn,
    db: Session = Depends(get_db), user: User = Depends(current_user),
):
    """Marca la cita externa como atendida sin destruirla.

    v4.3.16 conserva la fila original de Confirmafy. Se crea una cita interna
    oculta como marcador. Mientras exista una atención de ese paciente en la
    fecha, la cita externa no se muestra. Si esa atención se borra por error o
    por corrección, la cita vuelve a aparecer automáticamente en Nueva atención.
    """
    item = db.get(ConfirmafyAgendaItem, item_id)
    if not item:
        return {"ok": True, "already_removed": True}
    patient = db.get(Patient, int(data.patient_id))
    if not patient:
        raise HTTPException(404, "Paciente no encontrado")
    marker_note = confirmafy_marker_note(item.source_hash)
    marker = db.scalar(select(Appointment).where(
        Appointment.origen == CONFIRMAFY_ATTENDED_ORIGIN,
        Appointment.nota == marker_note,
    ))
    created = marker is None
    if marker is None:
        marker = Appointment(
            patient_id=patient.id, fecha=item.fecha, hora=item.hora, duracion=int(item.duracion or 20),
            nota=marker_note, estado="ATENDIDO", origen=CONFIRMAFY_ATTENDED_ORIGIN,
        )
        db.add(marker); db.flush()
    else:
        marker.patient_id = patient.id
        marker.fecha = item.fecha
        marker.hora = item.hora
        marker.duracion = int(item.duracion or 20)
        marker.estado = "ATENDIDO"
        marker.updated_at = datetime.utcnow()

    if is_offline_db(db):
        if created:
            add_queue(db, "appointment.create", "appointment", {
                "patient_id": marker.patient_id, "fecha": marker.fecha.isoformat(),
                "hora": marker.hora, "nota": marker.nota, "estado": marker.estado,
                "origen": marker.origen,
            }, user.username, marker.id)
        else:
            add_queue(db, "appointment.update", "appointment", {
                "appointment_id": marker.id, "fecha": marker.fecha.isoformat(),
                "hora": marker.hora, "nota": marker.nota, "estado": marker.estado,
                "origen": marker.origen, "patient_id": marker.patient_id,
            }, user.username, marker.id)
    label = f"{item.nombre} · {item.fecha} {item.hora} · paciente {patient.id}"
    audit(db, user, "resolver_cita_confirmafy_al_atender" + ("_offline" if is_offline_db(db) else ""), label)
    db.commit()
    if not is_offline_db(db):
        mirror_appointment_to_local(marker)
    return {"ok": True, "staged_preserved": True, "marker_id": int(marker.id)}


@app.post("/api/agenda/import-confirmafy/preview")
async def agenda_import_confirmafy_preview(file: UploadFile = File(...), links: str = Form(""), db: Session = Depends(get_db), user: User = Depends(current_user)):
    raw=await file.read()
    if not raw or len(raw)>5_000_000:
        raise HTTPException(400,"Selecciona un CSV válido de Confirmafy")
    return _analyze_confirmafy_import(db,raw,False,user.username,_parse_confirmafy_links(links))


@app.post("/api/agenda/import-confirmafy")
async def agenda_import_confirmafy(file: UploadFile = File(...), links: str = Form(""), db: Session = Depends(get_db), user: User = Depends(current_user)):
    raw=await file.read()
    if not raw or len(raw)>5_000_000:
        raise HTTPException(400,"Selecciona un CSV válido de Confirmafy")
    return _analyze_confirmafy_import(db,raw,True,user.username,_parse_confirmafy_links(links))


@app.post("/api/agenda/export.csv")
def agenda_export_csv(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = db.execute(
        select(Appointment, Patient).join(Patient).where(Appointment.estado == "PENDIENTE").order_by(Appointment.fecha, Appointment.hora, Appointment.id)
    ).all()
    if not rows:
        raise HTTPException(404, "No hay citas pendientes para exportar")
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(["name", "phone", "date", "time", "duration"])
    exported = []
    now = datetime.utcnow()
    for a, p in rows:
        phone = confirmafy_phone(p.celular)
        if not phone:
            continue
        w.writerow([p.nombre, phone, a.fecha.isoformat(), a.hora, 20])
        a.estado = "EXPORTADO"; a.exported_at = now; a.loaded_at = None; a.updated_at = now
        exported.append(a)
        if is_offline_db(db):
            add_queue(db, "appointment.export", "appointment", {"appointment_id": a.id}, user.username, a.id)
    if not exported:
        raise HTTPException(400, "Las citas pendientes no tienen celular válido")
    audit(db, user, "exportar_agenda_confirmafy" + ("_offline" if is_offline_db(db) else ""), f"{len(exported)} citas")
    db.commit()
    if not is_offline_db(db):
        for a in exported: mirror_appointment_to_local(a)
    data = "\ufeff" + out.getvalue()
    filename = f"confirmafy_reagendados_{date.today().isoformat()}.csv"
    return Response(content=data.encode("utf-8"), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def _upsert_local_env(values: dict[str, str]) -> None:
    """Actualiza claves concretas del .env sin tocar DATABASE_URL ni otros secretos."""
    env_path = Path(BASE_DIR) / ".env"
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


def _azur_config_payload() -> dict:
    configured = bool(AZUR_BASE_URL and AZUR_API_KEY)
    domain = ""
    try:
        domain = urlparse(AZUR_BASE_URL).hostname or "" if AZUR_BASE_URL else ""
    except Exception:
        domain = ""
    return {
        "configured": configured,
        "base_url": AZUR_BASE_URL,
        "domain": domain,
        "api_key_saved": bool(AZUR_API_KEY),
        "api_key_masked": azur_mask_api_key(AZUR_API_KEY),
        "tipo_iva": AZUR_TIPO_IVA,
        "forma_pago": AZUR_FORMA_PAGO,
        "live_emission_enabled": bool(AZUR_LIVE_EMISSION),
    }


@app.get("/api/azur/status")
def azur_status(user: User = Depends(current_user)):
    return _azur_config_payload()


@app.post("/api/azur/config")
def azur_save_config(data: AzurConfigIn, user: User = Depends(current_user)):
    global AZUR_BASE_URL, AZUR_API_KEY
    if user.role != "admin":
        raise HTTPException(403, "Solo el administrador puede configurar AZUR")
    try:
        base_url = azur_normalize_base_url(data.base_url)
    except AzurError as exc:
        raise HTTPException(400, str(exc))
    new_key = (data.api_key or "").strip()
    if not new_key and not AZUR_API_KEY:
        raise HTTPException(400, "Ingresa la API key de AZUR")
    values = {"AZUR_BASE_URL": base_url}
    if new_key:
        # Nunca registramos el valor en auditoría ni respuesta.
        values["AZUR_API_KEY"] = new_key
    _upsert_local_env(values)
    AZUR_BASE_URL = base_url
    if new_key:
        AZUR_API_KEY = new_key
    return {"ok": True, **_azur_config_payload()}


@app.post("/api/azur/test")
def azur_test(user: User = Depends(current_user)):
    if not AZUR_BASE_URL or not AZUR_API_KEY:
        raise HTTPException(400, "Configura primero la dirección de AZUR y la API key")
    try:
        result = azur_test_connection(AZUR_BASE_URL, AZUR_API_KEY, timeout=12)
    except AzurError as exc:
        raise HTTPException(502, str(exc))
    result["base_url"] = AZUR_BASE_URL
    return result


def _azur_invoice_number_from_access_key(access_key: Optional[str]) -> Optional[str]:
    """Deriva establecimiento-punto-secuencial desde la clave SRI de 49 dígitos.

    La clave de acceso ecuatoriana codifica estos campos de forma inequívoca y
    es una fuente más fiable que campos genéricos como ``numero`` devueltos por
    algunos tenants de AZUR. No altera el comprobante; solo corrige la etiqueta
    mostrada/guardada en Recepción.
    """
    digits = re.sub(r"\D", "", str(access_key or ""))
    if len(digits) != 49:
        return None
    establishment = digits[24:27]
    point = digits[27:30]
    sequential = digits[30:39]
    if not (establishment.isdigit() and point.isdigit() and sequential.isdigit()):
        return None
    return f"{establishment}-{point}-{sequential}"


def _azur_group_key(patient_id: int, fecha: date, first_visit_id: Optional[int] = None) -> str:
    base = f"{int(patient_id)}:{fecha.isoformat()}"
    return f"{base}:{int(first_visit_id)}" if first_visit_id is not None else base


def _azur_group_key_for_rows(patient_id: int, fecha: date, rows: list[tuple[BillingRecord, Visit]]) -> str:
    first_visit_id = min((int(v.id) for _b, v in rows), default=None)
    return _azur_group_key(patient_id, fecha, first_visit_id)


def _azur_pack_response(payload: object, rows: Optional[list[tuple[BillingRecord, Visit]]] = None, existing_raw: Optional[str] = None) -> str:
    data = dict(payload) if isinstance(payload, dict) else {"data": payload}
    ids = [int(v.id) for _b, v in (rows or [])]
    if not ids and existing_raw:
        try:
            old = json.loads(existing_raw)
            if isinstance(old, dict) and isinstance(old.get("_billing_visit_ids"), list):
                ids = [int(x) for x in old.get("_billing_visit_ids") if str(x).isdigit()]
        except Exception:
            pass
    if ids:
        data["_billing_visit_ids"] = ids
    return json.dumps(data, ensure_ascii=False)[:10000]


def _azur_rows_from_record(db: Session, record: AzurEmission) -> list[tuple[BillingRecord, Visit]]:
    ids = []
    try:
        stored = json.loads(record.response_json or "{}")
        if isinstance(stored, dict):
            ids = [int(x) for x in (stored.get("_billing_visit_ids") or []) if str(x).isdigit()]
    except Exception:
        ids = []
    if ids:
        return db.execute(
            select(BillingRecord, Visit)
            .join(Visit, BillingRecord.visit_id == Visit.id)
            .where(Visit.id.in_(ids))
            .order_by(Visit.id.asc())
        ).all()
    if record.numero_factura:
        matched = db.execute(
            select(BillingRecord, Visit)
            .join(Visit, BillingRecord.visit_id == Visit.id)
            .where(Visit.patient_id == int(record.patient_id), Visit.fecha == record.fecha, BillingRecord.numero_factura == record.numero_factura)
            .order_by(Visit.id.asc())
        ).all()
        if matched:
            return matched
    # Compatibilidad con emisiones antiguas que no guardaban los ids de líneas.
    # Congelamos por el momento en que nació la emisión: una atención creada
    # después jamás puede entrar retroactivamente en ese comprobante.
    if record.created_at:
        return db.execute(
            select(BillingRecord, Visit)
            .join(Visit, BillingRecord.visit_id == Visit.id)
            .where(
                Visit.patient_id == int(record.patient_id),
                Visit.fecha == record.fecha,
                Visit.created_at <= record.created_at,
            )
            .order_by(Visit.id.asc())
        ).all()
    return billing_group_records(db, int(record.patient_id), record.fecha)


def _azur_mass_unlocked(db: Session) -> bool:
    """La emisión masiva se habilita solo después de validar 1 factura real.

    Esto evita que una integración recién configurada pueda disparar un lote
    antes de comprobar en producción el ciclo completo emisión -> autorización.
    """
    return bool(db.scalar(select(AzurEmission.id).where(AzurEmission.estado == "AUTORIZADA").limit(1)))


def _billing_preference_for_patient(db: Session, patient_id: int) -> Optional[BillingPreference]:
    return db.scalar(select(BillingPreference).where(BillingPreference.patient_id == int(patient_id), BillingPreference.enabled == 1))


def _apply_billing_preference(data: BillingGroupIn, db: Session) -> BillingGroupIn:
    if bool(data.factura_otro):
        return data
    pref = _billing_preference_for_patient(db, data.patient_id)
    if not pref:
        return data
    return data.model_copy(update={
        "factura_otro": True,
        "factura_identificacion": pref.identificacion,
        "factura_nombre": pref.nombre,
        "factura_direccion": pref.direccion,
        "factura_telefono": pref.telefono,
        "factura_correo": pref.correo,
    })


def _azur_recipient(data: BillingGroupIn, p: Patient) -> dict:
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
        ident_type = "04"  # RUC
        ident = ident_digits
    elif len(ident_digits) == 10:
        ident_type = "05"  # Cédula
        ident = ident_digits
    elif ident_raw:
        ident_type = "08"  # Identificación del exterior
        ident = ident_raw
    else:
        raise HTTPException(400, "Falta identificación para emitir en AZUR")
    if not name:
        raise HTTPException(400, "Falta nombre o razón social para emitir en AZUR")
    if email and "@" not in email:
        raise HTTPException(400, "El correo de facturación no es válido")
    buyer = {
        "tipo_identificacion": ident_type,
        "identificacion": ident,
        "razon_social": name,
        "direccion": address or "NO REGISTRADA",
    }
    # AZUR permite emitir sin correo; solo se envía el campo cuando existe.
    if email:
        buyer["correo"] = email
    if phone:
        buyer["celular"] = phone
    return buyer


def _azur_payload_for_group(data: BillingGroupIn, p: Patient, rows: list[tuple[BillingRecord, Visit]]) -> dict:
    try:
        tipo_iva = int(AZUR_TIPO_IVA)
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
        "emisor": {
            "fecha_emision": data.fecha.strftime("%Y/%m/%d"),
            "manejo_interno_secuencia": "SI",
        },
        "comprador": _azur_recipient(data, p),
        "items": items,
        "pagos": [{"tipo": AZUR_FORMA_PAGO, "total": total, "tiempo": "dias", "plazo": 0}],
        "informacion_adicional": [{"nombre": "Origen", "detalle": "Recepcion Dr. Armando Revelo"}],
    }


@app.post("/api/billing/azur/preview")
def billing_azur_preview(data: BillingGroupIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = db.get(Patient, data.patient_id)
    if not p:
        raise HTTPException(404, "Paciente no encontrado")
    data = _apply_billing_preference(data, db)
    validate_billing_recipient(data, p)
    rows = billing_group_records(db, data.patient_id, data.fecha)
    if not rows:
        raise HTTPException(404, "No hay atenciones abiertas para facturar ese día")
    payload = _azur_payload_for_group(data, p, rows)
    group_key = _azur_group_key_for_rows(data.patient_id, data.fecha, rows)
    existing = db.scalar(select(AzurEmission).where(AzurEmission.group_key == group_key))
    return {
        "configured": bool(AZUR_BASE_URL and AZUR_API_KEY),
        "domain": _azur_config_payload().get("domain"),
        "payload": payload,
        "already_sent": bool(existing and existing.clave_acceso),
        "live_enabled": bool(AZUR_LIVE_EMISSION),
        "azur": {
            "estado": existing.estado, "clave_acceso": existing.clave_acceso, "numero_factura": existing.numero_factura,
        } if existing else None,
    }


@app.post("/api/billing/azur/emit")
def billing_azur_emit(data: BillingGroupIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if not AZUR_LIVE_EMISSION:
        raise HTTPException(403, "La emisión real está desactivada")
    if is_offline_db(db):
        raise HTTPException(503, "Emitir en AZUR requiere conexión a Internet")
    if not AZUR_BASE_URL or not AZUR_API_KEY:
        raise HTTPException(400, "AZUR todavía no está configurado. Ve a Configuración > AZUR")
    p = db.get(Patient, data.patient_id)
    if not p:
        raise HTTPException(404, "Paciente no encontrado")
    data = _apply_billing_preference(data, db)
    validate_billing_recipient(data, p)
    rows = billing_group_records(db, data.patient_id, data.fecha)
    if not rows:
        raise HTTPException(404, "No hay atenciones aprobadas abiertas para ese día")
    if any(str(b.estado or "").upper() != "APROBADA" for b, _ in rows):
        raise HTTPException(409, "Primero aprueba la pre-factura nueva")
    group_key = _azur_group_key_for_rows(data.patient_id, data.fecha, rows)
    existing = db.scalar(select(AzurEmission).where(AzurEmission.group_key == group_key))
    if existing and existing.clave_acceso:
        raise HTTPException(409, "Esta factura ya fue enviada a AZUR. Consulta su estado; no se reenviará para evitar duplicados")
    payload = _azur_payload_for_group(data, p, rows)
    request_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    try:
        result = azur_emit_invoice(AZUR_BASE_URL, AZUR_API_KEY, payload, timeout=20)
    except AzurError as exc:
        raise HTTPException(502, str(exc))
    response = result.get("data") if isinstance(result, dict) else {}
    response = response if isinstance(response, dict) else {}
    if response.get("creado") is not True:
        raise HTTPException(502, "AZUR no confirmó la creación del comprobante")
    access_key = str(response.get("claveacceso") or response.get("clave_acceso") or "").strip() or None
    invoice_number = str(response.get("numero_factura") or response.get("numero_comprobante") or response.get("numero") or "").strip() or None
    if not access_key:
        raise HTTPException(502, "AZUR respondió creado=true, pero no devolvió clave de acceso. No se modificó el estado local")
    invoice_number = _azur_invoice_number_from_access_key(access_key) or invoice_number
    now = datetime.utcnow()
    record = existing or AzurEmission(group_key=group_key, patient_id=data.patient_id, fecha=data.fecha)
    if not existing:
        db.add(record)
    record.estado = "EN_PROCESO"
    record.clave_acceso = access_key
    record.numero_factura = invoice_number
    record.request_hash = request_hash
    record.response_json = _azur_pack_response(response, rows)
    record.updated_at = now
    audit(db, user, "enviar_factura_azur", f"Paciente {data.patient_id}, fecha {data.fecha}, grupo {group_key}, pendiente autorización")
    db.commit()
    mirror_azur_emission_to_local(record)
    return {"ok": True, "estado": record.estado, "clave_acceso": access_key, "numero_factura": invoice_number,
            "message": "AZUR recibió la factura. Falta confirmar la autorización del SRI; las líneas de este comprobante quedaron identificadas por separado."}


@app.post("/api/billing/azur/check-status")
def billing_azur_check_status(data: BillingGroupIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if is_offline_db(db):
        raise HTTPException(503, "Consultar AZUR requiere conexión a Internet")
    if not AZUR_BASE_URL or not AZUR_API_KEY:
        raise HTTPException(400, "AZUR todavía no está configurado")
    open_rows = billing_group_records(db, data.patient_id, data.fecha)
    record = None
    if open_rows:
        group_key = _azur_group_key_for_rows(data.patient_id, data.fecha, open_rows)
        record = db.scalar(select(AzurEmission).where(AzurEmission.group_key == group_key))
    if not record:
        record = db.scalar(
            select(AzurEmission)
            .where(AzurEmission.patient_id == data.patient_id, AzurEmission.fecha == data.fecha, AzurEmission.estado != "AUTORIZADA")
            .order_by(AzurEmission.updated_at.desc(), AzurEmission.id.desc())
        )
    if not record or not record.clave_acceso:
        raise HTTPException(404, "Esta factura no tiene una consulta pendiente en AZUR")
    try:
        result = azur_query_comprobante(AZUR_BASE_URL, AZUR_API_KEY, record.clave_acceso, timeout=15)
    except AzurError as exc:
        raise HTTPException(502, str(exc))
    state = str(result.get("estado") or "CONSULTADA").upper()
    number = _azur_invoice_number_from_access_key(record.clave_acceso) or str(result.get("numero_factura") or record.numero_factura or "").strip() or None
    record.estado = state
    if number:
        record.numero_factura = number
    record.updated_at = datetime.utcnow()
    record.response_json = _azur_pack_response(result.get("data") or {}, None, record.response_json)
    rows = _azur_rows_from_record(db, record)
    if state == "AUTORIZADA":
        now = datetime.utcnow()
        for b, _v in rows:
            b.estado = "EMITIDA"
            if number:
                b.numero_factura = number
            b.emitted_at = now
            if not b.approved_at:
                b.approved_at = now
        audit(db, user, "autorizar_factura_azur", f"Paciente {data.patient_id}, fecha {data.fecha}, grupo {record.group_key}")
    elif state == "RECHAZADA":
        audit(db, user, "rechazo_factura_azur", f"Paciente {data.patient_id}, fecha {data.fecha}, grupo {record.group_key}")
    db.commit()
    mirror_azur_emission_to_local(record)
    if state == "AUTORIZADA":
        for b, _ in rows:
            mirror_billing_to_local(b)
    return {
        "ok": True, "estado": state, "estado_origen": result.get("estado_origen"), "numero_factura": number,
        "clave_acceso": record.clave_acceso, "numero_autorizacion": result.get("numero_autorizacion"),
        "pdf_url": result.get("pdf_url"), "xml_url": result.get("xml_url"), "mass_emission_unlocked": _azur_mass_unlocked(db),
        "message": ("Factura AUTORIZADA por AZUR/SRI." if state == "AUTORIZADA" else
                    "AZUR reportó la factura como rechazada. No se reenviará automáticamente." if state == "RECHAZADA" else
                    "La factura todavía está en proceso. Puedes consultar nuevamente más tarde."),
    }


@app.post("/api/billing/azur/check-all-status")
def billing_azur_check_all_status(db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Actualiza en lote los comprobantes enviados recientemente y cualquiera que siga pendiente.

    No reenvía facturas. Solo consulta por la clave de acceso ya registrada en AZUR.
    """
    if is_offline_db(db):
        raise HTTPException(503, "Consultar AZUR requiere conexión a Internet")
    if not AZUR_BASE_URL or not AZUR_API_KEY:
        raise HTTPException(400, "AZUR todavía no está configurado")
    history_from = date.today() - timedelta(days=6)
    records = list(db.scalars(
        select(AzurEmission)
        .where(
            AzurEmission.clave_acceso.is_not(None),
            AzurEmission.estado.in_(["EN_PROCESO", "CONSULTADA"])
        )
        .order_by(AzurEmission.fecha.desc(), AzurEmission.id.desc())
    ))
    checked=[]; failed=[]; authorized=processing=rejected=0
    for record in records:
        try:
            result = azur_query_comprobante(AZUR_BASE_URL, AZUR_API_KEY, record.clave_acceso, timeout=15)
            state = str(result.get("estado") or "CONSULTADA").upper()
            number = _azur_invoice_number_from_access_key(record.clave_acceso) or str(result.get("numero_factura") or record.numero_factura or "").strip() or None
            record.estado = state
            if number:
                record.numero_factura = number
            record.updated_at = datetime.utcnow()
            try:
                record.response_json = json.dumps(result.get("data") or {}, ensure_ascii=False)[:10000]
            except Exception:
                pass
            rows = _azur_rows_from_record(db, record)
            if state == "AUTORIZADA":
                now = datetime.utcnow()
                for b, _v in rows:
                    b.estado = "EMITIDA"
                    if number:
                        b.numero_factura = number
                    b.emitted_at = now
                    if not b.approved_at:
                        b.approved_at = now
                authorized += 1
            elif state == "RECHAZADA":
                rejected += 1
            else:
                processing += 1
            db.commit()
            mirror_azur_emission_to_local(record)
            if state == "AUTORIZADA":
                for b, _v in rows:
                    mirror_billing_to_local(b)
            checked.append({"patient_id": int(record.patient_id), "fecha": record.fecha, "estado": state, "numero_factura": number})
        except AzurError as exc:
            db.rollback()
            p = db.get(Patient, int(record.patient_id))
            failed.append({"patient_id": int(record.patient_id), "nombre": p.nombre if p else None, "fecha": record.fecha, "numero_factura": record.numero_factura, "reason": str(exc)})
        except Exception as exc:
            db.rollback()
            p = db.get(Patient, int(record.patient_id))
            failed.append({"patient_id": int(record.patient_id), "nombre": p.nombre if p else None, "fecha": record.fecha, "numero_factura": record.numero_factura, "reason": str(exc)[:300]})
    audit(db, user, "actualizar_estados_azur_lote", f"Consultadas {len(checked)}, autorizadas {authorized}, rechazadas {rejected}, fallidas {len(failed)}")
    db.commit()
    return {
        "ok": True,
        "checked": checked,
        "failed": failed,
        "counts": {
            "checked": len(checked),
            "authorized": authorized,
            "processing": processing,
            "rejected": rejected,
            "failed": len(failed),
        },
    }


@app.get("/api/billing/azur/batch-preview")
def billing_azur_batch_preview(db: Session = Depends(get_db), user: User = Depends(current_user)):
    grouped = db.execute(
        select(Visit.patient_id, Visit.fecha, func.min(Visit.id))
        .join(BillingRecord, BillingRecord.visit_id == Visit.id)
        .where(Visit.fecha >= BILLING_QUEUE_START_DATE, BillingRecord.estado.in_(["PENDIENTE", "APROBADA"]))
        .group_by(Visit.patient_id, Visit.fecha)
        .order_by(Visit.fecha.asc(), func.min(Visit.id).asc())
    ).all()
    ready=[]; skipped=[]
    for patient_id, fecha, _ in grouped:
        p = db.get(Patient, int(patient_id))
        if not p:
            skipped.append({"patient_id": int(patient_id), "fecha": fecha, "reason": "Paciente no encontrado"}); continue
        rows = billing_group_records(db, int(patient_id), fecha)
        if not rows or any(str(b.estado or "").upper() not in {"PENDIENTE", "APROBADA"} for b, _ in rows):
            skipped.append({"patient_id": int(patient_id), "nombre": p.nombre, "fecha": fecha, "reason": "La factura tiene estados que ya no están disponibles para emitir"}); continue
        existing = db.scalar(select(AzurEmission).where(AzurEmission.group_key == _azur_group_key_for_rows(int(patient_id), fecha, rows)))
        if existing and existing.clave_acceso:
            skipped.append({"patient_id": int(patient_id), "nombre": p.nombre, "fecha": fecha, "reason": "Ya fue enviada a AZUR; consulta su estado"}); continue
        data = _apply_billing_preference(BillingGroupIn(patient_id=int(patient_id), fecha=fecha), db)
        try:
            validate_billing_recipient(data, p)
            _azur_payload_for_group(data, p, rows)
        except HTTPException as exc:
            skipped.append({"patient_id": int(patient_id), "nombre": p.nombre, "fecha": fecha, "reason": str(exc.detail)}); continue
        ready.append({"patient_id": int(patient_id), "nombre": p.nombre, "fecha": fecha, "total": round(sum(float(v.valor or 0) for _b,v in rows),2)})
    return {"ok": True, "unlocked": True, "ready": ready, "skipped": skipped,
            "counts": {"ready": len(ready), "skipped": len(skipped)}}


@app.post("/api/billing/azur/emit-all-pending")
def billing_azur_emit_all_pending(db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Envía en serie facturas completas; la autorización se consulta después."""
    if not AZUR_LIVE_EMISSION:
        raise HTTPException(403, "La emisión real de AZUR está desactivada")
    if is_offline_db(db):
        raise HTTPException(503, "La emisión masiva requiere conexión a Internet")
    if not AZUR_BASE_URL or not AZUR_API_KEY:
        raise HTTPException(400, "AZUR todavía no está configurado")
    grouped = db.execute(
        select(Visit.patient_id, Visit.fecha, func.min(Visit.id))
        .join(BillingRecord, BillingRecord.visit_id == Visit.id)
        .where(Visit.fecha >= BILLING_QUEUE_START_DATE, BillingRecord.estado.in_(["PENDIENTE", "APROBADA"]))
        .group_by(Visit.patient_id, Visit.fecha)
        .order_by(Visit.fecha.asc(), func.min(Visit.id).asc())
    ).all()
    sent=[]; skipped=[]; failed=[]
    for patient_id, fecha, _ in grouped:
        p = db.get(Patient, int(patient_id))
        if not p:
            skipped.append({"patient_id": int(patient_id), "fecha": fecha, "reason": "Paciente no encontrado"}); continue
        rows = billing_group_records(db, int(patient_id), fecha)
        if not rows or any(str(b.estado or "").upper() not in {"PENDIENTE", "APROBADA"} for b, _ in rows):
            skipped.append({"patient_id": int(patient_id), "nombre": p.nombre, "fecha": fecha, "reason": "La factura tiene estados que ya no están disponibles para emitir"}); continue
        data = _apply_billing_preference(BillingGroupIn(patient_id=int(patient_id), fecha=fecha), db)
        group_key = _azur_group_key_for_rows(int(patient_id), fecha, rows)
        existing = db.scalar(select(AzurEmission).where(AzurEmission.group_key == group_key))
        if existing and existing.clave_acceso:
            skipped.append({"patient_id": int(patient_id), "nombre": p.nombre, "fecha": fecha, "reason": "Ya fue enviada a AZUR; consulta su estado"}); continue
        try:
            validate_billing_recipient(data, p)
            payload = _azur_payload_for_group(data, p, rows)
        except HTTPException as exc:
            skipped.append({"patient_id": int(patient_id), "nombre": p.nombre, "fecha": fecha, "reason": str(exc.detail)}); continue
        request_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        try:
            result = azur_emit_invoice(AZUR_BASE_URL, AZUR_API_KEY, payload, timeout=25)
            response = result.get("data") if isinstance(result, dict) else {}
            response = response if isinstance(response, dict) else {}
            access_key = str(response.get("claveacceso") or response.get("clave_acceso") or "").strip() or None
            invoice_number = str(response.get("numero_factura") or response.get("numero_comprobante") or response.get("numero") or "").strip() or None
            if response.get("creado") is not True or not access_key:
                raise AzurError("AZUR no devolvió creado=true con una clave de acceso")
            invoice_number = _azur_invoice_number_from_access_key(access_key) or invoice_number
            now = datetime.utcnow()
            record = existing or AzurEmission(group_key=group_key, patient_id=int(patient_id), fecha=fecha)
            if not existing:
                db.add(record)
            record.estado="EN_PROCESO"; record.clave_acceso=access_key; record.numero_factura=invoice_number; record.request_hash=request_hash; record.updated_at=now
            record.response_json=_azur_pack_response(response, rows)
            touched=[]
            for b, _v in rows:
                b.estado = "EMITIDA"
                b.approved_at = now
                b.numero_factura = invoice_number
                b.emitted_at = now
                touched.append(b)
            db.commit()
            mirror_azur_emission_to_local(record)
            for b in touched:
                mirror_billing_to_local(b)
            sent.append({"patient_id": int(patient_id), "nombre": p.nombre, "fecha": fecha, "numero_factura": invoice_number, "clave_acceso": access_key})
        except AzurError as exc:
            db.rollback(); failed.append({"patient_id": int(patient_id), "nombre": p.nombre, "fecha": fecha, "reason": str(exc)})
        except Exception as exc:
            db.rollback(); failed.append({"patient_id": int(patient_id), "nombre": p.nombre, "fecha": fecha, "reason": str(exc)[:300]})
    audit(db, user, "enviar_facturas_azur_lote", f"Enviadas {len(sent)}, omitidas {len(skipped)}, fallidas {len(failed)}")
    db.commit()
    return {"ok": True, "sent": sent, "emitted": sent, "skipped": skipped, "failed": failed,
            "counts": {"sent": len(sent), "emitted": len(sent), "skipped": len(skipped), "failed": len(failed)},
            "message": "Las facturas enviadas quedaron EN PROCESO. La autorización del SRI debe consultarse; no se reenviarán."}

def billing_group_records(db: Session, patient_id: int, fecha: date):
    # Grupo operativo abierto. Las líneas EMITIDAS pertenecen a comprobantes ya
    # cerrados y jamás vuelven a mezclarse con una atención agregada después.
    return db.execute(
        select(BillingRecord, Visit)
        .join(Visit, BillingRecord.visit_id == Visit.id)
        .where(
            Visit.patient_id == patient_id,
            Visit.fecha == fecha,
            BillingRecord.estado != "EMITIDA",
        )
        .order_by(Visit.id.asc())
    ).all()


def billing_required_missing(p: Patient) -> list[str]:
    missing = []
    if not (p.cedula or "").strip(): missing.append("cédula")
    return missing


def validate_billing_recipient(data: BillingGroupIn, p: Patient) -> None:
    """Valida el receptor sin tocar la ficha del paciente.

    Los datos alternos viajan solo en la acción actual; la UI los conserva localmente
    por factura para evitar agregar lecturas/escrituras a Neon.
    """
    if not bool(data.factura_otro):
        missing = billing_required_missing(p)
        if missing:
            raise HTTPException(400, "Completa antes de aprobar: " + ", ".join(missing))
        return
    ident = re.sub(r"\D", "", str(data.factura_identificacion or ""))
    name = " ".join(str(data.factura_nombre or "").split())
    email = str(data.factura_correo or "").strip().lower()
    if len(ident) not in {10, 13}:
        raise HTTPException(400, "La identificación para facturar debe tener 10 dígitos (cédula) o 13 dígitos (RUC)")
    if len(name) < 3:
        raise HTTPException(400, "Ingresa el nombre o razón social para la factura")
    if email and "@" not in email:
        raise HTTPException(400, "El correo de facturación no es válido")


def _billing_action_counts(db: Session) -> dict[str, int]:
    """Cuenta una sola cola visible: POR EMITIR.

    PENDIENTE y APROBADA se conservan internamente por compatibilidad, pero desde
    v4.3.75 ambas significan una única acción para Recepción: revisar y emitir.
    """
    grouped = (
        select(
            Visit.patient_id.label("patient_id"),
            Visit.fecha.label("fecha"),
            func.max(case((BillingRecord.estado.in_(["PENDIENTE", "APROBADA"]), 1), else_=0)).label("needs_action"),
        )
        .join(BillingRecord, BillingRecord.visit_id == Visit.id)
        .where(Visit.fecha >= BILLING_QUEUE_START_DATE)
        .group_by(Visit.patient_id, Visit.fecha)
        .subquery()
    )
    total = int(db.scalar(select(func.coalesce(func.sum(grouped.c.needs_action), 0))) or 0)
    return {"pending": total, "approved": 0, "total": total}


def _billing_pending_count(db: Session) -> int:
    """Facturas que todavía requieren acción humana."""
    return _billing_action_counts(db)["total"]


@app.get("/api/pending-summary")
def pending_summary(db: Session = Depends(get_db), user: User = Depends(current_user)):
    billing = _billing_action_counts(db)
    return {
        "billing": billing["total"],
        "billing_pending": billing["pending"],
        "billing_approved": billing["approved"],
        "agenda": int(db.scalar(select(func.count(Appointment.id)).where(Appointment.estado == "PENDIENTE")) or 0),
    }


@app.get("/api/patients/{pid}/billing-preference")
def get_billing_preference(pid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return {"preference": billing_preference_dict(_billing_preference_for_patient(db, pid))}


@app.put("/api/patients/{pid}/billing-preference")
def save_billing_preference(pid: int, data: BillingPreferenceIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if is_offline_db(db):
        raise HTTPException(503, "Guardar la preferencia de facturación requiere conexión a Internet")
    patient = db.get(Patient, pid)
    if not patient: raise HTTPException(404, "Paciente no encontrado")
    existing = db.scalar(select(BillingPreference).where(BillingPreference.patient_id == pid))
    if not data.enabled:
        if existing:
            existing.enabled = 0; existing.updated_at = datetime.utcnow(); db.commit(); mirror_billing_preference_to_local(existing)
        else:
            mirror_delete_billing_preference_local(pid)
        return {"ok": True, "preference": None}
    ident = re.sub(r"\D", "", str(data.identificacion or ""))
    name = " ".join(str(data.nombre or "").split()).upper()
    email = str(data.correo or "").strip().lower()
    if len(ident) not in {10, 13}: raise HTTPException(400, "La identificación debe tener 10 dígitos o el RUC 13 dígitos")
    if len(name) < 3: raise HTTPException(400, "Ingresa el nombre o razón social")
    if email and "@" not in email: raise HTTPException(400, "El correo de facturación no es válido")
    values = dict(enabled=1, identificacion=ident, nombre=name,
                  direccion=" ".join(str(data.direccion or "").split()).upper() or None,
                  telefono=re.sub(r"\D", "", str(data.telefono or "")) or None,
                  correo=email, updated_at=datetime.utcnow())
    if existing:
        for key, value in values.items(): setattr(existing, key, value)
        pref=existing
    else:
        pref=BillingPreference(patient_id=pid, **values); db.add(pref)
    audit(db, user, "guardar_preferencia_facturacion", f"Paciente {pid}")
    db.commit(); db.refresh(pref); mirror_billing_preference_to_local(pref)
    return {"ok": True, "preference": billing_preference_dict(pref)}


@app.delete("/api/patients/{pid}/billing-preference")
def delete_billing_preference(pid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if is_offline_db(db): raise HTTPException(503, "Desactivar esta preferencia requiere conexión a Internet")
    pref = db.scalar(select(BillingPreference).where(BillingPreference.patient_id == pid))
    if pref: db.delete(pref)
    audit(db, user, "eliminar_preferencia_facturacion", f"Paciente {pid}")
    db.commit(); mirror_delete_billing_preference_local(pid)
    return {"ok": True}


@app.get("/api/billing/pending-count")
def billing_pending_count(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return {"pending": _billing_pending_count(db)}


@app.get("/api/billing/next")
def billing_next(db: Session = Depends(get_db), user: User = Depends(current_user)):
    target = db.execute(
        select(Visit.patient_id, Visit.fecha, func.min(Visit.id).label("first_visit"))
        .join(BillingRecord, BillingRecord.visit_id == Visit.id)
        .where(Visit.fecha >= BILLING_QUEUE_START_DATE, BillingRecord.estado == "PENDIENTE")
        .group_by(Visit.patient_id, Visit.fecha)
        .order_by(Visit.fecha.asc(), func.min(Visit.id).asc())
        .limit(1)
    ).first()
    if not target:
        return {"items": []}
    patient_id, fecha, _ = target
    p = db.get(Patient, patient_id)
    rows = billing_group_records(db, patient_id, fecha)
    rows = [(b, v) for b, v in rows if str(b.estado or "").upper() == "PENDIENTE"]
    return {
        "items": [{"billing": billing_dict(b), "visit": v_dict(v), "patient": p_dict(p)} for b, v in rows],
        "patient": p_dict(p),
        "fecha": fecha,
        "billing_preference": billing_preference_dict(_billing_preference_for_patient(db, int(patient_id))),
    }


@app.get("/api/billing")
def billing_list(
    estado: str = "TODAS", desde: Optional[date] = None, hasta: Optional[date] = None,
    db: Session = Depends(get_db), user: User = Depends(current_user)
):
    """Facturación sin mezclar comprobantes cerrados con líneas nuevas.

    Si un paciente tiene una factura EMITIDA y luego se agrega otra atención el
    mismo día, PENDIENTE/APROBADA muestran únicamente la atención nueva. La
    factura anterior sigue disponible en el historial EMITIDA.
    """
    stmt = (
        select(BillingRecord, Visit, Patient)
        .join(Visit, BillingRecord.visit_id == Visit.id)
        .join(Patient, Visit.patient_id == Patient.id)
        .where(Visit.fecha >= BILLING_QUEUE_START_DATE)
    )
    if desde:
        stmt = stmt.where(Visit.fecha >= desde)
    if hasta:
        stmt = stmt.where(Visit.fecha <= hasta)
    all_rows = db.execute(stmt.order_by(Visit.fecha.desc(), Visit.id.desc())).all()

    groups = {}
    for row in all_rows:
        b, v, p = row
        groups.setdefault((int(p.id), v.fecha), []).append(row)

    patient_ids = sorted({key[0] for key in groups})
    emissions = list(db.scalars(select(AzurEmission).where(AzurEmission.patient_id.in_(patient_ids)))) if patient_ids else []
    emission_groups = {}
    for x in emissions:
        key = (int(x.patient_id), x.fecha)
        if key in groups:
            emission_groups.setdefault(key, []).append(x)
    for values in emission_groups.values():
        values.sort(key=lambda x: (x.updated_at or x.created_at or datetime.min, x.id or 0), reverse=True)

    states = {key: {str(b.estado or "").upper() for b, _v, _p in rows} for key, rows in groups.items()}
    history_from = date.today() - timedelta(days=6)
    counts = {
        "PENDIENTE": sum(1 for st in states.values() if "PENDIENTE" in st or "APROBADA" in st),
        "APROBADA": 0,
        "EMITIDA": sum(1 for st in states.values() if "EMITIDA" in st),
        "RECHAZADA": sum(1 for key in groups if any(str(x.estado or "").upper() == "RECHAZADA" for x in emission_groups.get(key, []))),
    }

    requested = (estado or "TODAS").strip().upper()
    rows = []
    if requested in {"PENDIENTE", "APROBADA"}:
        # Compatibilidad: ambos filtros antiguos muestran la única cola POR EMITIR.
        for key, grouped_rows in groups.items():
            st = states[key]
            if "PENDIENTE" in st:
                rows.extend(r for r in grouped_rows if str(r[0].estado or "").upper() == "PENDIENTE")
            elif "APROBADA" in st:
                rows.extend(r for r in grouped_rows if str(r[0].estado or "").upper() == "APROBADA")
    elif requested == "EMITIDA":
        rows = [r for r in all_rows if str(r[0].estado or "").upper() == "EMITIDA"]
        if not desde and not hasta:
            rows = [r for r in rows if r[1].fecha >= history_from]
    elif requested == "RECHAZADA":
        rejected = {key for key in groups if any(str(x.estado or "").upper() == "RECHAZADA" for x in emission_groups.get(key, []))}
        rows = [r for r in all_rows if (int(r[2].id), r[1].fecha) in rejected and str(r[0].estado or "").upper() != "EMITIDA"]
    else:
        # En TODAS mostramos el grupo que requiere acción. Una factura vieja
        # emitida del mismo día no se suma al total de la atención nueva.
        for key, grouped_rows in groups.items():
            st = states[key]
            if "PENDIENTE" in st:
                rows.extend(r for r in grouped_rows if str(r[0].estado or "").upper() == "PENDIENTE")
            elif "APROBADA" in st:
                rows.extend(r for r in grouped_rows if str(r[0].estado or "").upper() == "APROBADA")
            else:
                rows.extend(r for r in grouped_rows if str(r[0].estado or "").upper() == "EMITIDA" and (desde or hasta or r[1].fecha >= history_from))
        rows.sort(key=lambda r: (r[1].fecha, r[1].id), reverse=True)

    def azur_for_row(b: BillingRecord, v: Visit, p: Patient):
        candidates = emission_groups.get((int(p.id), v.fecha), [])
        if not candidates:
            return None
        state = str(b.estado or "").upper()
        if state == "EMITIDA":
            if b.numero_factura:
                for x in candidates:
                    if str(x.numero_factura or "") == str(b.numero_factura or ""):
                        return x
            for x in candidates:
                if str(x.estado or "").upper() == "AUTORIZADA":
                    return x
            return None
        for x in candidates:
            if str(x.estado or "").upper() not in {"AUTORIZADA"}:
                return x
        return None

    visible_patient_ids = sorted({int(p.id) for _b, _v, p in rows})
    prefs = list(db.scalars(select(BillingPreference).where(BillingPreference.patient_id.in_(visible_patient_ids), BillingPreference.enabled == 1))) if visible_patient_ids else []
    items = []
    for b, v, p in rows:
        az = azur_for_row(b, v, p)
        items.append({
            "billing": billing_dict(b),
            "visit": v_dict(v),
            "patient": p_dict(p),
            "azur": azur_emission_dict(az) if az else None,
            "billing_group_key": f"{int(p.id)}:{v.fecha.isoformat()}:{str(b.estado or '').upper()}",
        })
    return {
        "items": items,
        "counts": counts,
        "history_window_days": 7,
        "history_from": history_from,
        "billing_preferences": {str(x.patient_id): billing_preference_dict(x) for x in prefs},
    }


@app.post("/api/billing/approve")
def billing_approve(data: BillingGroupIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """v4.3.75: revisar + aprobar + enviar a AZUR en una sola operación.

    La interfaz ya no expone un estado APROBADA intermedio. Internamente las
    líneas quedan APROBADA únicamente después de que AZUR acepta el comprobante,
    mientras la autorización del SRI se consulta con el flujo existente. Si AZUR
    falla, las líneas permanecen como estaban para poder corregir/reintentar sin
    dejar una pre-factura atrapada a mitad del proceso.
    """
    if not AZUR_LIVE_EMISSION:
        raise HTTPException(403, "La emisión real de AZUR está desactivada")
    if is_offline_db(db):
        raise HTTPException(503, "Revisar y emitir requiere conexión a Internet")
    if not AZUR_BASE_URL or not AZUR_API_KEY:
        raise HTTPException(400, "AZUR todavía no está configurado")

    p = db.get(Patient, data.patient_id)
    if not p:
        raise HTTPException(404, "Paciente no encontrado")
    data = _apply_billing_preference(data, db)
    validate_billing_recipient(data, p)

    rows = billing_group_records(db, data.patient_id, data.fecha)
    if not rows:
        raise HTTPException(404, "No hay atenciones por facturar para ese día")
    invalid = [str(b.estado or "").upper() for b, _v in rows if str(b.estado or "").upper() not in {"PENDIENTE", "APROBADA"}]
    if invalid:
        raise HTTPException(409, "Esta factura ya no está disponible para emitir")

    group_key = _azur_group_key_for_rows(int(data.patient_id), data.fecha, rows)
    existing = db.scalar(select(AzurEmission).where(AzurEmission.group_key == group_key))
    if existing and existing.clave_acceso:
        raise HTTPException(409, "Esta factura ya fue enviada a AZUR. Usa Actualizar estado para consultar el SRI.")

    payload = _azur_payload_for_group(data, p, rows)
    request_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    try:
        result = azur_emit_invoice(AZUR_BASE_URL, AZUR_API_KEY, payload, timeout=25)
        response = result.get("data") if isinstance(result, dict) else {}
        response = response if isinstance(response, dict) else {}
        access_key = str(response.get("claveacceso") or response.get("clave_acceso") or "").strip() or None
        invoice_number = str(response.get("numero_factura") or response.get("numero_comprobante") or response.get("numero") or "").strip() or None
        if response.get("creado") is not True or not access_key:
            raise AzurError("AZUR no devolvió creado=true con una clave de acceso")
    except AzurError as exc:
        db.rollback()
        raise HTTPException(502, str(exc))
    except Exception as exc:
        db.rollback()
        raise HTTPException(502, f"No se pudo enviar la factura a AZUR: {str(exc)[:260]}")

    invoice_number = _azur_invoice_number_from_access_key(access_key) or invoice_number
    now = datetime.utcnow()
    record = existing or AzurEmission(group_key=group_key, patient_id=int(data.patient_id), fecha=data.fecha)
    if not existing:
        db.add(record)
    record.estado = "EN_PROCESO"
    record.clave_acceso = access_key
    record.numero_factura = invoice_number
    record.request_hash = request_hash
    record.updated_at = now
    record.response_json = _azur_pack_response(response, rows)

    touched = []
    for b, _v in rows:
        b.estado = "EMITIDA"
        b.approved_at = now
        b.numero_factura = invoice_number
        b.emitted_at = now
        touched.append(b)

    audit(db, user, "revisar_emitir_factura_azur", f"Paciente {data.patient_id}, {data.fecha}, AZUR {invoice_number or access_key[-8:]}")
    db.commit()
    mirror_azur_emission_to_local(record)
    for b in touched:
        mirror_billing_to_local(b)
    return {
        "ok": True,
        "estado": "EN_PROCESO",
        "numero_factura": invoice_number,
        "clave_acceso": access_key,
        "message": "Factura revisada y enviada a AZUR. Queda EN PROCESO hasta confirmar autorización del SRI.",
    }


@app.post("/api/billing/approve-all-pending")
def billing_approve_all_pending(db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Aprueba todos los grupos pendientes que tengan un receptor válido.

    Los grupos incompletos se omiten y permanecen PENDIENTES para revisarlos luego.
    """
    grouped = db.execute(
        select(Visit.patient_id, Visit.fecha, func.min(Visit.id))
        .join(BillingRecord, BillingRecord.visit_id == Visit.id)
        .where(Visit.fecha >= BILLING_QUEUE_START_DATE, BillingRecord.estado == "PENDIENTE")
        .group_by(Visit.patient_id, Visit.fecha)
        .order_by(Visit.fecha.asc(), func.min(Visit.id).asc())
    ).all()
    approved=[]; skipped=[]; touched=[]
    now = datetime.utcnow()
    for patient_id, fecha, _ in grouped:
        p = db.get(Patient, int(patient_id))
        if not p:
            skipped.append({"patient_id": int(patient_id), "fecha": fecha, "reason": "Paciente no encontrado"}); continue
        rows = billing_group_records(db, int(patient_id), fecha)
        if not rows or any(b.estado != "PENDIENTE" for b, _v in rows):
            skipped.append({"patient_id": int(patient_id), "nombre": p.nombre, "fecha": fecha, "reason": "La factura tiene estados mezclados"}); continue
        data = _apply_billing_preference(BillingGroupIn(patient_id=int(patient_id), fecha=fecha), db)
        try:
            validate_billing_recipient(data, p)
        except HTTPException as exc:
            skipped.append({"patient_id": int(patient_id), "nombre": p.nombre, "fecha": fecha, "reason": str(exc.detail)}); continue
        for b, v in rows:
            b.estado = "APROBADA"
            b.approved_at = now
            b.numero_factura = None
            b.emitted_at = None
            touched.append(b)
            if is_offline_db(db):
                add_queue(db, "billing.approve", "billing", {"visit_id": v.id}, user.username, b.id)
        approved.append({"patient_id": int(patient_id), "nombre": p.nombre, "fecha": fecha})
    audit(db, user, "aprobar_prefacturas_lote" + ("_offline" if is_offline_db(db) else ""), f"Aprobadas {len(approved)}, omitidas {len(skipped)}")
    db.commit()
    if not is_offline_db(db):
        for b in touched:
            mirror_billing_to_local(b)
    return {
        "ok": True,
        "approved": approved,
        "skipped": skipped,
        "counts": {"approved": len(approved), "skipped": len(skipped)},
        "offline": is_offline_db(db),
    }


@app.post("/api/billing/pending")
def billing_back_to_pending(data: BillingGroupIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = billing_group_records(db, data.patient_id, data.fecha)
    if not rows:
        raise HTTPException(404, "No hay atenciones de facturación para ese día")
    if any(b.estado == "EMITIDA" for b, _ in rows):
        raise HTTPException(409, "Una factura emitida no puede volver a pendiente desde aquí")
    touched = []
    for b, v in rows:
        b.estado = "PENDIENTE"
        b.approved_at = None
        b.numero_factura = None
        b.emitted_at = None
        touched.append(b)
        if is_offline_db(db):
            add_queue(db, "billing.pending", "billing", {"visit_id": v.id}, user.username, b.id)
    audit(db, user, "reabrir_prefactura" + ("_offline" if is_offline_db(db) else ""), f"Paciente {data.patient_id}, fecha {data.fecha}")
    db.commit()
    if not is_offline_db(db):
        for b in touched: mirror_billing_to_local(b)
    return {"ok": True, "estado": "PENDIENTE", "offline": is_offline_db(db)}


@app.post("/api/billing/emit")
def billing_emit(data: BillingEmitIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    number = (data.numero_factura or "").strip()
    if not number:
        raise HTTPException(400, "Ingresa el número de factura emitida")
    rows = billing_group_records(db, data.patient_id, data.fecha)
    if not rows:
        raise HTTPException(404, "No hay atenciones aprobadas para ese día")
    if any(b.estado != "APROBADA" for b, _ in rows):
        raise HTTPException(409, "Primero debes aprobar la pre-factura completa")
    touched = []
    for b, v in rows:
        b.estado = "EMITIDA"
        b.numero_factura = number
        b.emitted_at = datetime.utcnow()
        if not b.approved_at:
            b.approved_at = datetime.utcnow()
        touched.append(b)
        if is_offline_db(db):
            add_queue(db, "billing.emit", "billing", {"visit_id": v.id, "numero_factura": number}, user.username, b.id)
    audit(db, user, "marcar_factura_emitida" + ("_offline" if is_offline_db(db) else ""), f"Paciente {data.patient_id}, fecha {data.fecha}, factura {number}")
    db.commit()
    if not is_offline_db(db):
        for b in touched: mirror_billing_to_local(b)
    return {"ok": True, "estado": "EMITIDA", "numero_factura": number, "offline": is_offline_db(db)}




# ---------------------------------------------------------------------------
# v4.4.0 — Centro operativo: Papelera, Actividad, ficha rápida y Agenda inteligente
# ---------------------------------------------------------------------------

TRASH_RETENTION_DAYS = 7


def _ops_json_value(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _ops_parse_date(value):
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return date.fromisoformat(str(value)[:10])


def _ops_parse_datetime(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _ops_ensure_trash_table(db: Session) -> None:
    try:
        TrashItem.__table__.create(bind=db.get_bind(), checkfirst=True)
    except Exception:
        pass


def _ops_patient_snapshot(p: Patient) -> dict:
    return {
        "id": int(p.id), "cedula": p.cedula, "nombre": p.nombre,
        "fecha_nacimiento": _ops_json_value(p.fecha_nacimiento), "celular": p.celular,
        "correo": p.correo, "lugar": p.lugar, "notas": p.notas,
        "created_at": _ops_json_value(p.created_at),
    }


def _ops_visit_snapshot(db: Session, v: Visit) -> dict:
    billing = db.scalar(select(BillingRecord).where(BillingRecord.visit_id == v.id))
    out = {
        "id": int(v.id), "patient_id": int(v.patient_id), "fecha": _ops_json_value(v.fecha),
        "tipo": v.tipo, "procedimiento": v.procedimiento, "valor": float(v.valor or 0),
        "observacion": v.observacion, "source_row": v.source_row,
        "created_at": _ops_json_value(v.created_at),
    }
    if billing:
        out["billing"] = {
            "id": int(billing.id), "visit_id": int(billing.visit_id), "estado": billing.estado,
            "numero_factura": billing.numero_factura,
            "approved_at": _ops_json_value(billing.approved_at),
            "emitted_at": _ops_json_value(billing.emitted_at),
            "created_at": _ops_json_value(billing.created_at),
        }
    return out


def _ops_appointment_snapshot(a: Appointment) -> dict:
    return {
        "id": int(a.id), "patient_id": int(a.patient_id), "fecha": _ops_json_value(a.fecha),
        "hora": a.hora, "duracion": int(a.duracion or 20), "nota": a.nota,
        "estado": a.estado, "origen": a.origen,
        "exported_at": _ops_json_value(a.exported_at), "loaded_at": _ops_json_value(a.loaded_at),
        "created_at": _ops_json_value(a.created_at), "updated_at": _ops_json_value(a.updated_at),
    }


def _ops_staged_snapshot(a: ConfirmafyAgendaItem) -> dict:
    return {
        "id": int(a.id), "nombre": a.nombre, "celular": a.celular,
        "fecha": _ops_json_value(a.fecha), "hora": a.hora, "duracion": int(a.duracion or 20),
        "source_hash": a.source_hash, "created_at": _ops_json_value(a.created_at),
    }


def _ops_capture_trash(db: Session, user, entity_type: str, entity_id: int, patient_id: Optional[int], label: str, snapshot: dict) -> TrashItem:
    """Guarda la Papelera únicamente en SQLite local.

    La eliminación clínica sigue usando la base principal como siempre, pero la
    red de seguridad no añade INSERTs ni lecturas a Neon.
    """
    username = getattr(user, "username", None) or "admin"
    with LocalSessionLocal() as ldb:
        _ops_ensure_trash_table(ldb)
        item = TrashItem(
            entity_type=str(entity_type), entity_id=int(entity_id),
            patient_id=int(patient_id) if patient_id else None,
            label=str(label or entity_type)[:240],
            snapshot_json=json.dumps(snapshot, ensure_ascii=False, default=_ops_json_value),
            deleted_by=username, origin=_workstation_label(),
        )
        ldb.add(item)
        ldb.commit(); ldb.refresh(item)
        return item


def _ops_discard_local_trash(trash_id: int) -> None:
    try:
        with LocalSessionLocal() as ldb:
            item=ldb.get(TrashItem, int(trash_id))
            if item:
                ldb.delete(item); ldb.commit()
    except Exception:
        pass


def _ops_capture_patient(db: Session, user, p: Patient) -> TrashItem:
    visits = list(db.scalars(select(Visit).where(Visit.patient_id == p.id).order_by(Visit.id)))
    appointments = list(db.scalars(select(Appointment).where(Appointment.patient_id == p.id).order_by(Appointment.id)))
    pref = db.scalar(select(BillingPreference).where(BillingPreference.patient_id == p.id))
    snapshot = {
        "patient": _ops_patient_snapshot(p),
        "visits": [_ops_visit_snapshot(db, v) for v in visits],
        "appointments": [_ops_appointment_snapshot(a) for a in appointments],
        "billing_preference": ({
            "id": int(pref.id), "patient_id": int(pref.patient_id), "enabled": int(pref.enabled or 0),
            "identificacion": pref.identificacion, "nombre": pref.nombre, "direccion": pref.direccion,
            "telefono": pref.telefono, "correo": pref.correo, "updated_at": _ops_json_value(pref.updated_at),
        } if pref else None),
    }
    return _ops_capture_trash(db, user, "patient", p.id, p.id, p.nombre, snapshot)


def _ops_capture_visit(db: Session, user, v: Visit) -> TrashItem:
    p = db.get(Patient, v.patient_id)
    service = str(v.procedimiento or "CONSULTA")
    label = f"{p.nombre if p else 'Paciente'} · {service} · {v.fecha.isoformat()}"
    return _ops_capture_trash(db, user, "visit", v.id, v.patient_id, label, {"visit": _ops_visit_snapshot(db, v)})


def _ops_capture_appointment(db: Session, user, a: Appointment) -> TrashItem:
    p = db.get(Patient, a.patient_id)
    label = f"{p.nombre if p else 'Paciente'} · {a.fecha.isoformat()} {a.hora}"
    return _ops_capture_trash(db, user, "appointment", a.id, a.patient_id, label, {"appointment": _ops_appointment_snapshot(a)})


def _ops_capture_staged(db: Session, user, a: ConfirmafyAgendaItem) -> TrashItem:
    label = f"{a.nombre} · {a.fecha.isoformat()} {a.hora}"
    return _ops_capture_trash(db, user, "staged_appointment", a.id, None, label, {"staged": _ops_staged_snapshot(a)})


def _ops_trash_dict(item: TrashItem) -> dict:
    now = datetime.utcnow()
    age = max(0, (now - item.deleted_at).days) if item.deleted_at else 0
    return {
        "id": item.id, "entity_type": item.entity_type, "entity_id": item.entity_id,
        "patient_id": item.patient_id, "label": item.label,
        "deleted_at": item.deleted_at, "deleted_by": item.deleted_by, "origin": item.origin,
        "restored_at": item.restored_at, "restored_by": item.restored_by,
        "days_left": max(0, TRASH_RETENTION_DAYS - age),
    }


def _ops_restore_visit(db: Session, snap: dict) -> Visit:
    vid = int(snap["id"])
    existing = db.get(Visit, vid)
    if existing:
        return existing
    if not db.get(Patient, int(snap["patient_id"])):
        raise HTTPException(409, "Primero restaura la ficha del paciente asociada.")
    v = Visit(
        id=vid, patient_id=int(snap["patient_id"]), fecha=_ops_parse_date(snap.get("fecha")),
        tipo=str(snap.get("tipo") or "S")[:1], procedimiento=snap.get("procedimiento"),
        valor=snap.get("valor") or 0, observacion=snap.get("observacion"),
        source_row=snap.get("source_row"), created_at=_ops_parse_datetime(snap.get("created_at")) or datetime.utcnow(),
    )
    db.add(v); db.flush()
    billing = snap.get("billing") or None
    if billing and not db.scalar(select(BillingRecord).where(BillingRecord.visit_id == vid)):
        db.add(BillingRecord(
            id=int(billing["id"]), visit_id=vid, estado=billing.get("estado") or "PENDIENTE",
            numero_factura=billing.get("numero_factura"), approved_at=_ops_parse_datetime(billing.get("approved_at")),
            emitted_at=_ops_parse_datetime(billing.get("emitted_at")),
            created_at=_ops_parse_datetime(billing.get("created_at")) or datetime.utcnow(),
        ))
    return v


def _ops_restore_appointment(db: Session, snap: dict) -> Appointment:
    aid = int(snap["id"])
    existing = db.get(Appointment, aid)
    if existing:
        return existing
    if not db.get(Patient, int(snap["patient_id"])):
        raise HTTPException(409, "Primero restaura la ficha del paciente asociada.")
    a = Appointment(
        id=aid, patient_id=int(snap["patient_id"]), fecha=_ops_parse_date(snap.get("fecha")),
        hora=str(snap.get("hora") or "")[:5], duracion=int(snap.get("duracion") or 20),
        nota=snap.get("nota"), estado=snap.get("estado") or "PENDIENTE", origen=snap.get("origen") or "RECEPCION",
        exported_at=_ops_parse_datetime(snap.get("exported_at")), loaded_at=_ops_parse_datetime(snap.get("loaded_at")),
        created_at=_ops_parse_datetime(snap.get("created_at")) or datetime.utcnow(),
        updated_at=_ops_parse_datetime(snap.get("updated_at")) or datetime.utcnow(),
    )
    db.add(a); db.flush()
    return a


def _ops_restore_patient(db: Session, snapshot: dict) -> Patient:
    snap = snapshot.get("patient") or {}
    pid = int(snap["id"])
    if db.get(Patient, pid):
        raise HTTPException(409, "La ficha del paciente ya existe. No se duplicó nada.")
    p = Patient(
        id=pid, cedula=snap.get("cedula"), nombre=snap.get("nombre") or "PACIENTE RESTAURADO",
        fecha_nacimiento=_ops_parse_date(snap.get("fecha_nacimiento")), celular=snap.get("celular"),
        correo=snap.get("correo"), lugar=snap.get("lugar"), notas=snap.get("notas"),
        created_at=_ops_parse_datetime(snap.get("created_at")) or datetime.utcnow(),
    )
    db.add(p); db.flush()
    restored_visits=[]; restored_apps=[]
    for v in snapshot.get("visits") or []:
        restored_visits.append(_ops_restore_visit(db, v))
    for a in snapshot.get("appointments") or []:
        restored_apps.append(_ops_restore_appointment(db, a))
    pref = snapshot.get("billing_preference") or None
    if pref and not db.scalar(select(BillingPreference).where(BillingPreference.patient_id == pid)):
        db.add(BillingPreference(
            id=int(pref["id"]), patient_id=pid, enabled=int(pref.get("enabled") or 0),
            identificacion=pref.get("identificacion"), nombre=pref.get("nombre"), direccion=pref.get("direccion"),
            telefono=pref.get("telefono"), correo=pref.get("correo") or "",
            updated_at=_ops_parse_datetime(pref.get("updated_at")) or datetime.utcnow(),
        ))
    return p


@app.delete("/api/safety/patients/{pid}")
def ops_safe_delete_patient(pid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = db.get(Patient, pid)
    if not p:
        raise HTTPException(404, "Paciente no encontrado")
    item = _ops_capture_patient(db, user, p)
    try:
        result = delete_patient(pid, db, user)
    except Exception:
        _ops_discard_local_trash(item.id); raise
    return {**result, "trash_id": item.id, "undo": True, "trash_label": item.label}


@app.delete("/api/safety/visits/{visit_id}")
def ops_safe_delete_visit(visit_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    v = db.get(Visit, visit_id)
    if not v:
        raise HTTPException(404, "Atención no encontrada")
    item = _ops_capture_visit(db, user, v)
    try:
        result = delete_visit(visit_id, db, user)
    except Exception:
        _ops_discard_local_trash(item.id); raise
    return {**result, "trash_id": item.id, "undo": True, "trash_label": item.label}


@app.delete("/api/safety/appointments/{appointment_id}")
def ops_safe_delete_appointment(appointment_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = db.get(Appointment, appointment_id)
    if not a:
        raise HTTPException(404, "Cita no encontrada")
    item = _ops_capture_appointment(db, user, a)
    try:
        result = agenda_delete(appointment_id, db, user)
    except Exception:
        _ops_discard_local_trash(item.id); raise
    return {**result, "trash_id": item.id, "undo": True, "trash_label": item.label}


@app.delete("/api/safety/unlinked/{item_id}")
def ops_safe_delete_unlinked(item_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    staged = db.get(ConfirmafyAgendaItem, item_id)
    if not staged:
        raise HTTPException(404, "La cita ya no existe")
    item = _ops_capture_staged(db, user, staged)
    try:
        result = agenda_delete_unlinked(item_id, db, user)
    except Exception:
        _ops_discard_local_trash(item.id); raise
    return {**result, "trash_id": item.id, "undo": True, "trash_label": item.label}


@app.get("/api/ops/trash")
def ops_trash(include_restored: bool = False, limit: int = 100, user: User = Depends(current_user)):
    """Lectura estrictamente local: abrir Papelera jamás despierta Neon."""
    with LocalSessionLocal() as db:
        _ops_ensure_trash_table(db)
        cutoff = datetime.utcnow() - timedelta(days=TRASH_RETENTION_DAYS)
        try:
            old = list(db.scalars(select(TrashItem).where(TrashItem.deleted_at < cutoff)))
            for item in old:
                db.delete(item)
            if old:
                db.commit()
        except Exception:
            db.rollback()
        stmt = select(TrashItem)
        if not include_restored:
            stmt = stmt.where(TrashItem.restored_at.is_(None))
        stmt = stmt.order_by(TrashItem.deleted_at.desc(), TrashItem.id.desc()).limit(min(max(int(limit or 100),1),250))
        return [_ops_trash_dict(x) for x in db.scalars(stmt)]


@app.post("/api/ops/trash/{trash_id}/restore")
def ops_restore_trash(trash_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Lee el snapshot de SQLite y solo toca Neon si realmente se pide Restaurar."""
    with LocalSessionLocal() as ldb:
        _ops_ensure_trash_table(ldb)
        item = ldb.get(TrashItem, trash_id)
        if not item:
            raise HTTPException(404, "Ese elemento ya no está en la Papelera")
        if item.restored_at:
            return {"ok": True, "already_restored": True, "item": _ops_trash_dict(item)}
        try:
            snapshot = json.loads(item.snapshot_json or "{}")
        except Exception:
            raise HTTPException(500, "La copia de recuperación está dañada")
        entity_type=item.entity_type; entity_id=int(item.entity_id); label=item.label

    restored = None
    if entity_type == "patient":
        restored = _ops_restore_patient(db, snapshot)
    elif entity_type == "visit":
        restored = _ops_restore_visit(db, snapshot.get("visit") or {})
    elif entity_type == "appointment":
        restored = _ops_restore_appointment(db, snapshot.get("appointment") or {})
    elif entity_type == "staged_appointment":
        snap = snapshot.get("staged") or {}
        sid = int(snap["id"])
        restored = db.get(ConfirmafyAgendaItem, sid)
        if not restored:
            restored = ConfirmafyAgendaItem(
                id=sid, nombre=snap.get("nombre") or "PACIENTE", celular=snap.get("celular"),
                fecha=_ops_parse_date(snap.get("fecha")), hora=str(snap.get("hora") or "")[:5],
                duracion=int(snap.get("duracion") or 20), source_hash=snap.get("source_hash") or f"restored:{sid}",
                created_at=_ops_parse_datetime(snap.get("created_at")) or datetime.utcnow(),
            )
            db.add(restored); db.flush()
    else:
        raise HTTPException(400, "Tipo de elemento no recuperable")

    audit(db, user, "restaurar_desde_papelera", f"{entity_type} {entity_id}: {label}; papelera local {trash_id}")
    db.commit()
    try:
        if entity_type == "patient" and isinstance(restored, Patient):
            mirror_patient_to_local(restored)
            for v in db.scalars(select(Visit).where(Visit.patient_id == restored.id)):
                mirror_visit_to_local(v)
            for a in db.scalars(select(Appointment).where(Appointment.patient_id == restored.id)):
                mirror_appointment_to_local(a)
        elif entity_type == "visit" and isinstance(restored, Visit):
            mirror_visit_to_local(restored)
            billing=db.scalar(select(BillingRecord).where(BillingRecord.visit_id == restored.id))
            if billing: mirror_billing_to_local(billing)
        elif entity_type == "appointment" and isinstance(restored, Appointment):
            mirror_appointment_to_local(restored)
        elif entity_type == "staged_appointment" and isinstance(restored, ConfirmafyAgendaItem):
            mirror_confirmafy_agenda_local(restored)
    except Exception:
        pass
    with LocalSessionLocal() as ldb:
        local_item=ldb.get(TrashItem, trash_id)
        if local_item:
            local_item.restored_at=datetime.utcnow(); local_item.restored_by=getattr(user,"username",None) or "admin"
            ldb.commit(); result_item=_ops_trash_dict(local_item)
        else:
            result_item={"id":trash_id,"entity_type":entity_type,"entity_id":entity_id,"label":label}
    return {"ok": True, "item": result_item, "entity_type": entity_type, "entity_id": entity_id}


@app.delete("/api/ops/trash/{trash_id}")
def ops_delete_trash_forever(trash_id: int, user: User = Depends(current_user)):
    """Vaciar Papelera es una operación SQLite; no consulta ni escribe Neon."""
    with LocalSessionLocal() as db:
        _ops_ensure_trash_table(db)
        item = db.get(TrashItem, trash_id)
        if not item:
            raise HTTPException(404, "Ese elemento ya no está en la Papelera")
        db.delete(item); db.commit()
    return {"ok": True}


@app.get("/api/ops/activity")
def ops_activity(limit: int = 120, q: str = "", user: User = Depends(current_user)):
    """Actividad local-first estricta: esta pantalla nunca consulta Neon."""
    lim = min(max(int(limit or 120), 1), 300)
    with LocalSessionLocal() as db:
        stmt = select(Audit)
        raw = str(q or "").strip()
        if raw:
            pattern = f"%{raw}%"
            stmt = stmt.where(or_(Audit.action.ilike(pattern), Audit.detail.ilike(pattern), Audit.username.ilike(pattern)))
        stmt = stmt.order_by(Audit.ts.desc(), Audit.id.desc()).limit(lim)
        out=[]
        for row in db.scalars(stmt):
            detail = str(row.detail or "")
            origin = "PC NO REGISTRADA"
            match = re.match(r"^\[PC:([^\]]+)\]\s*(.*)$", detail, flags=re.S)
            if match:
                origin = match.group(1).strip() or origin
                detail = match.group(2).strip()
            out.append({"id": row.id, "ts": row.ts, "username": row.username, "action": row.action, "detail": detail, "origin": origin})
        return out


@app.get("/api/ops/diagnostics")
def ops_diagnostics(request: Request, user: User = Depends(current_user)):
    if not _is_loopback_client(request):
        raise HTTPException(403, "Esta comprobación solo puede ejecutarse desde la PC de Recepción")
    from concurrent.futures import ThreadPoolExecutor, as_completed
    probes = {"local": _probe_local_service, "neon": _probe_neon_service, "azur": _probe_azur_service, "whatsapp": _probe_whatsapp_service, "mensajes": _probe_messages_service, "agenda": _probe_agenda_service, "updates": _probe_updates_service}
    services={}
    with ThreadPoolExecutor(max_workers=3, thread_name_prefix="rp-diagnostico") as pool:
        futures={pool.submit(fn):key for key,fn in probes.items()}
        for future in as_completed(futures):
            key=futures[future]
            try: services[key]=future.result()
            except Exception as exc: services[key]={"name":key,"status":"ERROR","detail":str(exc)[:180]}
    safe_lines=[]
    for key in ("local","neon","azur","whatsapp","mensajes","agenda","updates"):
        item=services.get(key) or {}
        safe_lines.append(f"{item.get('name') or key}: {item.get('status') or item.get('state') or 'SIN DATOS'}")
    return {"version":APP_VERSION,"workstation":_workstation_label(),"services":services,"safe_text":f"Recepción v{APP_VERSION} | "+" | ".join(safe_lines)}


@app.get("/api/procedures")
def procedures(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return [
        {"id": x.id, "nombre": str(x.nombre or "").upper(), "valor_default": float(x.valor_default) if x.valor_default is not None else None}
        for x in db.scalars(select(Procedure).where(Procedure.activo == 1).order_by(Procedure.nombre))
    ]


@app.post("/api/procedures")
def add_procedure(data: ProcedureIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if is_offline_db(db):
        raise HTTPException(503, "Agregar procedimientos nuevos requiere conexión a Internet")
    name = data.nombre.strip().upper()
    if not name:
        raise HTTPException(400, "El nombre del procedimiento es obligatorio")
    if db.scalar(select(Procedure).where(Procedure.nombre == name)):
        raise HTTPException(409, "Ese procedimiento ya existe")
    p = Procedure(nombre=name, valor_default=data.valor_default)
    db.add(p)
    audit(db, user, "crear_procedimiento", name)
    db.commit()
    mirror_procedure_local(p)
    return {"ok": True}


@app.put("/api/procedures/{procedure_id}")
def update_procedure_value(procedure_id: int, data: ProcedureValueIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = db.get(Procedure, procedure_id)
    if not p:
        raise HTTPException(404, "Procedimiento no encontrado")
    p.valor_default = data.valor_default
    if is_offline_db(db):
        add_queue(
            db, "procedure.update", "procedure",
            {"procedure_id": procedure_id, "valor_default": data.valor_default},
            user.username, procedure_id,
        )
        audit(db, user, "editar_valor_procedimiento_offline", f"{p.nombre}: {data.valor_default}")
        db.commit()
        return {"ok": True, "id": p.id, "nombre": p.nombre, "valor_default": float(p.valor_default) if p.valor_default is not None else None, "offline": True}
    audit(db, user, "editar_valor_procedimiento", f"{p.nombre}: {data.valor_default}")
    db.commit()
    mirror_procedure_local(p)
    return {"ok": True, "id": p.id, "nombre": p.nombre, "valor_default": float(p.valor_default) if p.valor_default is not None else None, "offline": False}


@app.delete("/api/procedures/{procedure_id}")
def delete_procedure(procedure_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if is_offline_db(db):
        raise HTTPException(503, "Eliminar o archivar procedimientos requiere conexión a Internet")
    proc = db.get(Procedure, procedure_id)
    if not proc: raise HTTPException(404, "Procedimiento no encontrado")
    used = int(db.scalar(select(func.count(Visit.id)).where(func.upper(func.coalesce(Visit.procedimiento, "")) == str(proc.nombre or "").upper())) or 0)
    name = proc.nombre
    if used:
        proc.activo = 0
        audit(db, user, "archivar_procedimiento", f"{name}; {used} atención(es) históricas")
        db.commit(); mirror_procedure_local(proc)
        return {"ok": True, "archived": True, "used": used, "message": "El procedimiento se archivó porque tiene historial. Ya no aparecerá en nuevas atenciones."}
    db.delete(proc)
    audit(db, user, "eliminar_procedimiento", name)
    db.commit()
    try:
        with LocalSessionLocal() as ldb:
            local=ldb.get(Procedure,procedure_id)
            if local: ldb.delete(local)
            ldb.commit()
    except Exception: pass
    return {"ok": True, "archived": False, "used": 0, "message": "Procedimiento eliminado."}


@app.post("/api/change-password")
def change_password(data: PasswordIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if is_offline_db(db):
        raise HTTPException(503, "Por seguridad, el cambio de contraseña requiere conexión a Internet")
    db_user = db.scalar(select(User).where(User.username == user.username))
    if not db_user or not verify_password(data.current_password, db_user.password_hash):
        raise HTTPException(400, "Contraseña actual incorrecta")
    if len(data.new_password) < 8:
        raise HTTPException(400, "La nueva contraseña debe tener al menos 8 caracteres")
    db_user.password_hash = hash_password(data.new_password)
    audit(db, db_user, "cambiar_contrasena")
    db.commit()
    mirror_user_local(db_user)
    invalidate_user_cache(user.username)
    return {"ok": True}


def _safe_update_member_path(root: Path, member: str) -> Path:
    dest = (root / member).resolve()
    if root.resolve() not in dest.parents and dest != root.resolve():
        raise HTTPException(400, "Paquete de actualización inválido")
    return dest


def _app_backup_zip() -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = Path(UPDATE_BACKUP_DIR) / f"app_antes_actualizacion_{stamp}.zip"
    excluded = {".venv", ".env", "data", "__pycache__", "backup", "backups"}
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        base = Path(BASE_DIR)
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(base)
            if rel.parts and rel.parts[0] in excluded:
                continue
            if any(part.startswith("backup_antes_") for part in rel.parts):
                continue
            zf.write(path, rel.as_posix())
    backups = sorted(Path(UPDATE_BACKUP_DIR).glob("app_antes_actualizacion_*.zip"), key=lambda x: x.stat().st_mtime, reverse=True)
    for old in backups[5:]:
        try:
            old.unlink()
        except Exception:
            pass
    return str(dest)


def _whatsapp_manual_test_missing(template_key: str = "recordatorio_cita") -> list[str]:
    """Configuración mínima para probar una plantilla sin activar automatización local."""
    missing = []
    if not WHATSAPP_GRAPH_VERSION:
        missing.append("WHATSAPP_GRAPH_VERSION")
    if not WHATSAPP_PHONE_NUMBER_ID:
        missing.append("WHATSAPP_PHONE_NUMBER_ID")
    if not WHATSAPP_ACCESS_TOKEN:
        missing.append("WHATSAPP_ACCESS_TOKEN")
    if template_key == "recordatorio_cita" and not WHATSAPP_TEMPLATE_RECORDATORIO_CITA:
        missing.append("WHATSAPP_TEMPLATE_RECORDATORIO_CITA")
    if template_key == "cita_agendada":
        if not WHATSAPP_TEMPLATE_CITA_AGENDADA:
            missing.append("WHATSAPP_TEMPLATE_CITA_AGENDADA")
        if not WHATSAPP_HEADER_IMAGE_ID:
            missing.append("WHATSAPP_HEADER_IMAGE_ID")
    if template_key == "recordatorio_hoy":
        if not WHATSAPP_TEMPLATE_RECORDATORIO_HOY:
            missing.append("WHATSAPP_TEMPLATE_RECORDATORIO_HOY")
        if not WHATSAPP_HEADER_IMAGE_ID:
            missing.append("WHATSAPP_HEADER_IMAGE_ID")
    return missing


def _whatsapp_test_payload(template_key: str, phone: str, name: str, test_date: date, raw_time: str) -> tuple[dict, str, str, list[str]]:
    clean_name = re.sub(r"\s+", " ", str(name or "Prueba").strip())[:80] or "Prueba"
    if template_key == "recordatorio_cita":
        template = WHATSAPP_TEMPLATE_RECORDATORIO_CITA
        language = WHATSAPP_LANGUAGE_RECORDATORIO_CITA  # plantilla aprobada: es_ES
        body = [clean_name, whatsapp_recordatorio_datetime_label(test_date, raw_time)]
        header = None
        replies = ["TEST_CONFIRMAR", "TEST_CANCELAR"]
    elif template_key == "cita_agendada":
        template = WHATSAPP_TEMPLATE_CITA_AGENDADA
        language = WHATSAPP_LANGUAGE_CITA_AGENDADA  # Español (Ecuador)
        body = [clean_name, whatsapp_date_label(test_date), whatsapp_time_label(raw_time)]
        header = WHATSAPP_HEADER_IMAGE_ID
        replies = []
    elif template_key == "recordatorio_hoy":
        template = WHATSAPP_TEMPLATE_RECORDATORIO_HOY
        language = WHATSAPP_LANGUAGE_RECORDATORIO_HOY  # Español (Ecuador)
        body = [clean_name, whatsapp_time_label(raw_time)]
        header = WHATSAPP_HEADER_IMAGE_ID
        replies = []
    else:
        raise HTTPException(400, "Plantilla de prueba no válida")
    payload = whatsapp_build_template_payload(
        to=phone, template_name=template, language_code=language, body_params=body,
        header_image_id=header, quick_reply_payloads=replies,
    )
    return payload, template, language, body




WHATSAPP_CLOUD_TEST_TEMPLATES = {"recordatorio_cita", "cita_agendada", "recordatorio_hoy"}


def _whatsapp_cloud_test_parse_source_hash(value: str) -> tuple[str, str]:
    raw = str(value or "")
    if not raw.startswith(WHATSAPP_CLOUD_TEST_PREFIX):
        return "", ""
    rest = raw[len(WHATSAPP_CLOUD_TEST_PREFIX):]
    parts = rest.split(":")
    if len(parts) >= 2 and parts[0] in WHATSAPP_CLOUD_TEST_TEMPLATES:
        return parts[0], parts[-1]
    return "recordatorio_cita", rest


def _whatsapp_cloud_test_source_hash(template_key: str, token: str) -> str:
    return f"{WHATSAPP_CLOUD_TEST_PREFIX}{template_key}:{token}"


def _whatsapp_cloud_test_template_name(template_key: str) -> str:
    if template_key == "cita_agendada":
        return WHATSAPP_TEMPLATE_CITA_AGENDADA
    if template_key == "recordatorio_hoy":
        return WHATSAPP_TEMPLATE_RECORDATORIO_HOY
    return whatsapp_recordatorio_template_name()


def _whatsapp_cloud_test_approved(template_key: str) -> bool:
    if template_key == "cita_agendada":
        return bool(WHATSAPP_APPROVED_CITA_AGENDADA)
    if template_key == "recordatorio_hoy":
        return bool(WHATSAPP_APPROVED_RECORDATORIO_HOY)
    return bool(WHATSAPP_APPROVED_RECORDATORIO_CITA)


def _wa_cita_agendada_allowed(fecha: date, hora: str, created_at: Optional[datetime]) -> bool:
    # No se envía con menos de 24 h ni si ya es el día de confirmación.
    created = created_at or datetime.now()
    try:
        hh, mm = [int(x) for x in str(hora or "00:00")[:5].split(":")]
        appointment_at = datetime(fecha.year, fecha.month, fecha.day, hh, mm)
    except Exception:
        appointment_at = datetime.combine(fecha, datetime.min.time())
    return (appointment_at - created) >= timedelta(hours=24) and created.date() < (fecha - timedelta(days=1))


def _whatsapp_cloud_test_ready() -> tuple[bool, str]:
    if not WHATSAPP_CLOUD_MODE:
        return False, "WhatsApp Cloud 24/7 está desactivado"
    if not cloud_configured() or not CloudSessionLocal or FORCE_OFFLINE:
        return False, "Neon no está disponible"
    return True, ""


def _cleanup_old_whatsapp_cloud_tests() -> None:
    if not cloud_configured() or not CloudSessionLocal or FORCE_OFFLINE:
        return
    try:
        with CloudSessionLocal() as cdb:
            cdb.execute(text("""
                DELETE FROM public.confirmafy_agenda_items
                WHERE source_hash LIKE :prefix
                  AND created_at < now() - interval '2 hours'
            """), {"prefix": WHATSAPP_CLOUD_TEST_PREFIX + "%"})
            cdb.commit()
    except Exception:
        pass


@app.post("/api/whatsapp/cloud-test")
def whatsapp_cloud_test(payload: dict, request: Request, user: User = Depends(current_user)):
    if not _is_loopback_client(request):
        raise HTTPException(403, "La prueba solo puede iniciarse desde la PC de Recepción")
    ready, reason = _whatsapp_cloud_test_ready()
    if not ready:
        raise HTTPException(503, reason)
    template_key = str(payload.get("template") or "recordatorio_cita").strip().lower()
    if template_key not in WHATSAPP_CLOUD_TEST_TEMPLATES:
        raise HTTPException(400, "Plantilla de prueba no válida")
    if not _whatsapp_cloud_test_approved(template_key):
        raise HTTPException(409, f"La plantilla {template_key} todavía no está aprobada en la configuración de Recepción")
    phone = confirmafy_phone(str(payload.get("phone") or WHATSAPP_TEST_PHONE or ""))
    if not re.fullmatch(r"\d{10,15}", phone or ""):
        raise HTTPException(400, "Ingresa un número válido. Ecuador: 09xxxxxxxx o 5939xxxxxxxx.")
    name = re.sub(r"\s+", " ", str(payload.get("name") or "Prueba").strip())[:60] or "Prueba"
    raw_date = str(payload.get("date") or "").strip()
    raw_time = str(payload.get("time") or "").strip()[:5]
    try:
        test_date = date.fromisoformat(raw_date)
    except Exception:
        raise HTTPException(400, "Selecciona una fecha válida para la prueba")
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", raw_time):
        raise HTTPException(400, "Selecciona una hora válida para la prueba")
    try:
        hh, mm = [int(x) for x in raw_time.split(":")]
        if datetime(test_date.year, test_date.month, test_date.day, hh, mm) <= datetime.now():
            raise HTTPException(400, "La fecha y hora mostradas en la prueba deben estar en el futuro")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(400, "Fecha u hora inválida")
    _cleanup_old_whatsapp_cloud_tests()
    token = secrets.token_urlsafe(16).replace("-", "").replace("_", "")[:19]
    source_hash = _whatsapp_cloud_test_source_hash(template_key, token)
    item = ConfirmafyAgendaItem(nombre=name.upper(), celular=phone, fecha=test_date, hora=raw_time, duracion=20, source_hash=source_hash)
    try:
        with CloudSessionLocal() as cdb:
            cdb.add(item); cdb.commit(); cdb.refresh(item)
            source_id = int(item.id)
    except Exception as exc:
        raise HTTPException(503, f"No se pudo registrar la prueba en Cloud: {str(exc)[:180]}")
    return {"ok": True, "mode": "cloud", "test_id": source_id, "token": token, "to": phone, "template": template_key, "worker_cycle_minutes": 5, "message": "Prueba registrada en Cloud. No se usó ningún token de Meta en esta PC. El worker enviará únicamente la plantilla elegida."}

@app.get("/api/whatsapp/cloud-test/{test_id}")
def whatsapp_cloud_test_status(test_id: int, token: str, user: User = Depends(current_user)):
    ready, reason = _whatsapp_cloud_test_ready()
    if not ready:
        return {"ok": False, "status": "UNAVAILABLE", "status_label": reason, "terminal": True}
    try:
        with CloudSessionLocal() as cdb:
            item = cdb.execute(text("""SELECT source_hash FROM public.confirmafy_agenda_items WHERE id=:source_id AND source_hash LIKE :prefix LIMIT 1"""), {"source_id": int(test_id), "prefix": WHATSAPP_CLOUD_TEST_PREFIX + "%"}).mappings().first()
            if not item:
                return {"ok": False, "status": "CLEANED", "status_label": "Prueba finalizada o vencida", "terminal": True}
            template_key, stored_token = _whatsapp_cloud_test_parse_source_hash(str(item.get("source_hash") or ""))
            if not stored_token or not hmac.compare_digest(stored_token, str(token or "")):
                return {"ok": False, "status": "CLEANED", "status_label": "Prueba finalizada o vencida", "terminal": True}
            template_name = _whatsapp_cloud_test_template_name(template_key)
            event = cdb.execute(text("""SELECT status, message_id, created_at, sent_at, delivered_at, read_at, error_text FROM whatsapp_cloud.events WHERE source_type='staged' AND source_id=:source_id AND template_name=:template ORDER BY created_at DESC LIMIT 1"""), {"source_id": int(test_id), "template": template_name}).mappings().first()
        if not event:
            return {"ok": True, "status": "QUEUED", "status_label": "Esperando al worker Cloud", "terminal": False, "template": template_key}
        st = str(event.get("status") or "").upper()
        label, _tone = _wa_event_display_status(st)
        timestamp = event.get("read_at") or event.get("delivered_at") or event.get("sent_at") or event.get("created_at")
        return {"ok": st not in {"ERROR", "FAILED"}, "status": st, "status_label": label, "terminal": st in {"SENT", "DELIVERED", "READ", "ERROR", "FAILED"}, "message_id": str(event.get("message_id") or ""), "timestamp": timestamp.isoformat() if timestamp else None, "error": str(event.get("error_text") or "")[:240], "template": template_key}
    except Exception as exc:
        return {"ok": False, "status": "ERROR", "status_label": "No se pudo consultar Cloud", "terminal": False, "error": str(exc)[:220]}

@app.delete("/api/whatsapp/cloud-test/{test_id}")
def whatsapp_cloud_test_finish(test_id: int, token: str, user: User = Depends(current_user)):
    if not cloud_configured() or not CloudSessionLocal:
        raise HTTPException(503, "Neon no está disponible")
    try:
        with CloudSessionLocal() as cdb:
            item = cdb.execute(text("""SELECT source_hash FROM public.confirmafy_agenda_items WHERE id=:source_id AND source_hash LIKE :prefix LIMIT 1"""), {"source_id": int(test_id), "prefix": WHATSAPP_CLOUD_TEST_PREFIX + "%"}).mappings().first()
            if item:
                _template_key, stored_token = _whatsapp_cloud_test_parse_source_hash(str(item.get("source_hash") or ""))
                if stored_token and hmac.compare_digest(stored_token, str(token or "")):
                    # v4.4.19: no borrar inmediatamente la cita técnica. El Worker
                    # necesita esta fila temporal para poder interpretar texto/audio
                    # y devolver el acuse de prueba después de que llegó la plantilla.
                    # Sigue totalmente excluida de Agenda/Inicio y el limpiador la
                    # elimina automáticamente al cumplir 2 horas.
                    pass
        return {"ok": True, "message": "Prueba técnica cerrada en pantalla. Se conservará temporalmente solo para validar respuestas y se eliminará automáticamente."}
    except Exception as exc:
        raise HTTPException(503, f"No se pudo finalizar la prueba: {str(exc)[:180]}")

@app.post("/api/whatsapp/test-message")
def whatsapp_test_message(payload: dict, user: User = Depends(current_user)):
    """Envía UNA de las tres plantillas configuradas sin tocar outbox ni worker."""
    template_key = str(payload.get("template") or "recordatorio_cita").strip().lower()
    if template_key not in {"recordatorio_cita", "cita_agendada", "recordatorio_hoy"}:
        raise HTTPException(400, "Plantilla de prueba no válida")
    missing = _whatsapp_manual_test_missing(template_key)
    if missing:
        raise HTTPException(400, "Falta configurar para esta prueba: " + ", ".join(missing))

    phone = confirmafy_phone(str(payload.get("phone") or WHATSAPP_TEST_PHONE or ""))
    if not re.fullmatch(r"\d{10,15}", phone or ""):
        raise HTTPException(400, "Ingresa un número válido. Ecuador: 09xxxxxxxx o 5939xxxxxxxx.")
    name = re.sub(r"\s+", " ", str(payload.get("name") or "Prueba").strip())[:80] or "Prueba"
    raw_date = str(payload.get("date") or "").strip()
    raw_time = str(payload.get("time") or "").strip()[:5]
    try:
        test_date = date.fromisoformat(raw_date)
    except Exception:
        raise HTTPException(400, "Selecciona una fecha válida para la prueba")
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", raw_time):
        raise HTTPException(400, "Selecciona una hora válida para la prueba")

    wa_payload, template, language, body = _whatsapp_test_payload(template_key, phone, name, test_date, raw_time)
    try:
        response = whatsapp_send_template(
            graph_version=WHATSAPP_GRAPH_VERSION, phone_number_id=WHATSAPP_PHONE_NUMBER_ID,
            access_token=WHATSAPP_ACCESS_TOKEN, payload=wa_payload, timeout=20.0,
        )
    except WhatsAppError as exc:
        raise HTTPException(502, str(exc))
    message_id = ""
    try:
        message_id = str((response.get("messages") or [{}])[0].get("id") or "")
    except Exception:
        pass
    return {
        "ok": True, "to": phone, "template_key": template_key, "template": template,
        "language": language, "body_preview": body,
        "buttons": ["Sí", "No"] if template_key == "recordatorio_cita" else [],
        "message_id": message_id, "automatic_sending_enabled": bool(WHATSAPP_ENABLED and not WHATSAPP_CLOUD_MODE),
        "message": "Prueba enviada a Meta. La automatización Cloud no fue modificada.",
    }


@app.post("/api/whatsapp/test-recordatorio-cita")
def whatsapp_test_recordatorio_cita(payload: dict, user: User = Depends(current_user)):
    # Compatibilidad con v4.3.36-v4.3.38.
    data = dict(payload or {})
    data["template"] = "recordatorio_cita"
    return whatsapp_test_message(data, user)


@app.get("/api/whatsapp/cloud-status")
def whatsapp_cloud_delivery_status(user: User = Depends(current_user)):
    """Resumen bajo demanda de entregas cloud. No crea hilos ni sondeos de fondo."""
    if not cloud_configured() or not CloudSessionLocal:
        return {"available": False, "message": "Neon no está configurado en esta PC.", "summary": {}, "items": []}
    try:
        with CloudSessionLocal() as cdb:
            rows = cdb.execute(text("""
                SELECT template_name, appointment_date, appointment_time, patient_name, status,
                       created_at, sent_at, delivered_at, read_at, error_text
                FROM whatsapp_cloud.events
                WHERE created_at >= now() - interval '7 days'
                ORDER BY created_at DESC
                LIMIT 40
            """)).mappings().all()
    except Exception as exc:
        return {"available": False, "message": f"No se pudo consultar el estado Cloud: {exc}", "summary": {}, "items": []}

    summary = {"TOTAL": 0, "SENT": 0, "DELIVERED": 0, "READ": 0, "FAILED": 0, "ERROR": 0, "SENDING": 0}
    items = []
    for r in rows:
        st = str(r.get("status") or "").upper()
        summary["TOTAL"] += 1
        summary[st] = summary.get(st, 0) + 1
        items.append({
            "template": str(r.get("template_name") or ""),
            "date": str(r.get("appointment_date") or "")[:10],
            "time": str(r.get("appointment_time") or "")[:5],
            "patient": str(r.get("patient_name") or ""),
            "status": st,
            "created_at": r.get("created_at").isoformat() if r.get("created_at") else None,
            "sent_at": r.get("sent_at").isoformat() if r.get("sent_at") else None,
            "delivered_at": r.get("delivered_at").isoformat() if r.get("delivered_at") else None,
            "read_at": r.get("read_at").isoformat() if r.get("read_at") else None,
            "error": str(r.get("error_text") or "")[:240],
        })
    bad = summary.get("FAILED", 0) + summary.get("ERROR", 0)
    return {
        "available": True, "summary": summary, "items": items,
        "message": "Sin errores de entrega en los últimos 7 días." if bad == 0 else f"Hay {bad} mensaje(s) con error para revisar.",
    }


@app.get("/api/whatsapp/status")
def whatsapp_status(user: User = Depends(current_user)):
    ready, missing = whatsapp_ready()
    with LocalSessionLocal() as db:
        counts = {str(status): int(count) for status, count in db.execute(
            select(WhatsAppOutbox.status, func.count(WhatsAppOutbox.id)).group_by(WhatsAppOutbox.status)
        ).all()}
    return {
        "enabled": bool(WHATSAPP_ENABLED and not WHATSAPP_CLOUD_MODE),
        "cloud_mode": bool(WHATSAPP_CLOUD_MODE),
        "state": "CLOUD_24_7" if WHATSAPP_CLOUD_MODE else ("ACTIVO" if WHATSAPP_ENABLED and ready else ("CONFIGURACION_INCOMPLETA" if WHATSAPP_ENABLED else "PENDIENTE_APROBACION")),
        "ready": ready, "missing": missing,
        "templates": {
            "cita_agendada": {"name": WHATSAPP_TEMPLATE_CITA_AGENDADA, "language": WHATSAPP_LANGUAGE_CITA_AGENDADA, "automatic": WHATSAPP_AUTO_CITA_AGENDADA, "approved": WHATSAPP_APPROVED_CITA_AGENDADA},
            "recordatorio_cita": {"name": whatsapp_recordatorio_template_name(), "language": WHATSAPP_LANGUAGE_RECORDATORIO_CITA, "automatic": WHATSAPP_AUTO_RECORDATORIO_CITA, "approved": WHATSAPP_APPROVED_RECORDATORIO_CITA},
            "recordatorio_hoy": {"name": WHATSAPP_TEMPLATE_RECORDATORIO_HOY, "language": WHATSAPP_LANGUAGE_RECORDATORIO_HOY, "automatic": WHATSAPP_AUTO_RECORDATORIO_HOY, "approved": WHATSAPP_APPROVED_RECORDATORIO_HOY},
        },
        "recordatorio_cita_approved_structure": {"body_params": 2, "variables": ["nombre", "fecha_y_hora"], "buttons": ["Sí", "No"]},
        "manual_test": {
            "ready": _whatsapp_cloud_test_ready()[0] if WHATSAPP_CLOUD_MODE else not bool(_whatsapp_manual_test_missing("recordatorio_cita")),
            "missing": [] if (WHATSAPP_CLOUD_MODE and _whatsapp_cloud_test_ready()[0]) else ((_whatsapp_cloud_test_ready()[1:] or [""])[0:1] if WHATSAPP_CLOUD_MODE else _whatsapp_manual_test_missing("recordatorio_cita")),
            "default_phone": WHATSAPP_TEST_PHONE,
            "works_with_automatic_sending_disabled": True,
            "mode": "cloud" if WHATSAPP_CLOUD_MODE else "local",
            "requires_local_meta_token": False if WHATSAPP_CLOUD_MODE else True,
        },
        "previous_day_time": WHATSAPP_PREVIOUS_DAY_TIME,
        "today_hours_before": WHATSAPP_TODAY_HOURS_BEFORE,
        "outbox": counts,
        "message": ("WhatsApp Cloud 24/7 activo. La PC no envía automáticamente y no puede duplicar los mensajes de Cloudflare." if WHATSAPP_CLOUD_MODE else ("Preparado. No se envía nada mientras WHATSAPP_ENABLED=0." if not WHATSAPP_ENABLED else ("WhatsApp habilitado." if ready else "WhatsApp habilitado pero faltan datos de Meta en .env."))),
    }


# ---------------------------------------------------------------------------
# v4.3.58 — Configuración profesional + comprobación pasiva de servicios
# ---------------------------------------------------------------------------
V458_SETTINGS_CSS = "/* v4.3.58 — Configuración profesional y estado de servicios */\n#config.v458-settings .config-title-row{margin-bottom:12px}\n#config.v458-settings .config-tabs{gap:7px;flex-wrap:wrap;margin-bottom:14px}\n#config.v458-settings .config-tabs button{padding:8px 12px;border-radius:10px;white-space:nowrap}\n.v458-service-panel{margin:0 0 14px!important;padding:15px!important;border:1px solid rgba(76,108,155,.22)!important}\n.v458-service-head{display:flex;align-items:flex-start;justify-content:space-between;gap:14px;margin-bottom:12px}\n.v458-service-head h3{margin:0 0 3px;font-size:17px}.v458-service-head p{margin:0}\n.v458-service-actions{display:flex;gap:8px;align-items:center;flex-wrap:wrap;justify-content:flex-end}\n.v458-service-time{font-size:12px;color:#6f7f96;white-space:nowrap}\n.v458-service-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px}\n.v458-service-card{border:1px solid #dfe6ef;border-radius:12px;padding:11px 12px;background:#fbfcfe;min-height:92px;display:flex;flex-direction:column;gap:5px}\n.v458-service-card .v458-service-top{display:flex;align-items:center;justify-content:space-between;gap:8px}\n.v458-service-card b{font-size:14px;color:#20324d}.v458-service-card small{font-size:12px;line-height:1.35;color:#687890}\n.v458-status{font-size:10px;font-weight:800;letter-spacing:.04em;border-radius:999px;padding:4px 7px;background:#eef2f7;color:#53647b}\n.v458-status.online{background:#e7f7ed;color:#16703c}.v458-status.degraded{background:#fff4db;color:#936117}.v458-status.offline{background:#ffe9e8;color:#a13731}.v458-status.no-configurado{background:#eef1f5;color:#667287}.v458-status.checking{background:#e9f1ff;color:#315f9d}\n.v458-service-card.online{border-color:#bfe5ca;background:#fbfffc}.v458-service-card.degraded{border-color:#eedda8}.v458-service-card.offline{border-color:#efc3bf}\n.v458-config-section-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin:2px 0 10px}.v458-config-section-head h2{font-size:18px;margin:0}.v458-config-section-head p{margin:3px 0 0;color:#718097;font-size:13px}\n.v458-link-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:10px}\n.v458-link-card{border:1px solid #dce5f0;border-radius:12px;padding:12px;background:#fbfcff;display:flex;flex-direction:column;gap:8px}.v458-link-card .label{display:flex;align-items:center;justify-content:space-between;gap:8px}.v458-link-card .label b{font-size:14px}.v458-link-card .label span{font-size:10px;font-weight:800;border-radius:999px;padding:3px 7px;background:#eef4ff;color:#315f9d}.v458-link-card code{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;background:#f1f4f8;padding:7px 8px;border-radius:8px;font-size:11px}.v458-link-actions{display:flex;gap:7px;flex-wrap:wrap}\n.v458-agenda-state{border-radius:10px;padding:9px 11px;background:#f2f7ff;color:#315f75;font-size:13px}.v458-agenda-state.ready{background:#eaf8ef;color:#22683e}\n.v458-advanced{margin-top:10px;border:1px solid #e2e8f0;border-radius:11px;background:#fafbfd}.v458-advanced>summary{cursor:pointer;padding:10px 12px;font-weight:700;color:#56677f;list-style:none}.v458-advanced>summary::-webkit-details-marker{display:none}.v458-advanced>summary:after{content:'▾';float:right;color:#8491a4}.v458-advanced[open]>summary:after{content:'▴'}.v458-advanced>.panel{border:0!important;box-shadow:none!important;margin:0!important;padding-top:5px!important}\n.v458-wa-overview{margin-bottom:10px!important}.v458-template-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px;margin-top:10px}.v458-template-card{border:1px solid #dfe5ed;border-radius:11px;padding:10px 11px;background:#fbfcfe}.v458-template-card .top{display:flex;justify-content:space-between;gap:8px;align-items:flex-start}.v458-template-card b{font-size:13px}.v458-template-card code{display:block;margin-top:6px;font-size:11px;color:#5e6d80;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.v458-template-card small{display:block;margin-top:5px;line-height:1.3;color:#718097}.v458-template-badge{font-size:9px;font-weight:800;border-radius:999px;padding:3px 6px;background:#eef1f5;color:#687488}.v458-template-badge.approved{background:#e5f7eb;color:#19703f}.v458-delivery-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:7px;margin-top:10px}.v458-delivery-grid>div{border:1px solid #e2e7ee;border-radius:9px;padding:8px;text-align:center;background:#fff}.v458-delivery-grid span{display:block;font-size:10px;color:#78869a}.v458-delivery-grid b{font-size:16px;color:#2a3c55}.v458-delivery-note{margin-top:8px;font-size:12px;color:#6d7c90}\n.v458-program-card{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px;margin:10px 0}.v458-program-card>div{border:1px solid #e1e7ef;border-radius:10px;padding:10px;background:#fbfcfe}.v458-program-card span{display:block;color:#75849a;font-size:11px}.v458-program-card b{display:block;margin-top:3px;color:#263b57}\n#config.v458-settings .v451-update-box{display:none!important}\n#config.v458-settings .v458-hidden-obsolete{display:none!important}\n@media(max-width:1050px){.v458-service-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.v458-template-grid{grid-template-columns:1fr}.v458-delivery-grid{grid-template-columns:repeat(3,minmax(0,1fr))}}\n@media(max-width:720px){.v458-service-head{flex-direction:column}.v458-service-actions{justify-content:flex-start}.v458-service-grid,.v458-link-grid,.v458-program-card{grid-template-columns:1fr}.v458-delivery-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}"
V458_SETTINGS_JS = '(()=>{\n\'use strict\';\nconst V=\'4.3.58\';\nconst $=(s,r=document)=>r.querySelector(s);\nconst $$=(s,r=document)=>[...r.querySelectorAll(s)];\nconst escH=v=>String(v??\'\').replace(/[&<>"\']/g,c=>({\'&\':\'&amp;\',\'<\':\'&lt;\',\'>\':\'&gt;\',\'"\':\'&quot;\',"\'":\'&#39;\'}[c]));\nconst norm=v=>String(v||\'\').replace(/\\s+/g,\' \').trim();\nconst lower=v=>norm(v).toLowerCase();\nconst apiCall=async(url,opt={})=>{\n  if(typeof window.api===\'function\')return window.api(url,opt);\n  const r=await fetch(url,{headers:{\'Content-Type\':\'application/json\',...(opt.headers||{})},...opt});\n  const d=await r.json().catch(()=>({}));\n  if(!r.ok)throw new Error(d.detail||d.message||\'No se pudo completar la operación\');\n  return d;\n};\nfunction statusClass(state){return lower(state).replace(/_/g,\'-\').replace(/\\s+/g,\'-\')||\'no-configurado\'}\nfunction servicePlaceholder(){\n  const names=[[\'local\',\'Recepción local\'],[\'neon\',\'Neon\'],[\'azur\',\'AZUR\'],[\'whatsapp\',\'WhatsApp Meta\'],[\'mensajes\',\'Mensajes 24/7\'],[\'agenda\',\'Agenda web 24/7\'],[\'updates\',\'Actualizaciones\']];\n  return names.map(([key,label])=>`<div class="v458-service-card" data-service="${key}"><div class="v458-service-top"><b>${label}</b><span class="v458-status">SIN COMPROBAR</span></div><small>Pulsa “Comprobar servicios”.</small></div>`).join(\'\');\n}\nfunction createServicePanel(config){\n  if($(\'#v458ServicePanel\',config))return;\n  const panel=document.createElement(\'div\');panel.id=\'v458ServicePanel\';panel.className=\'panel v458-service-panel\';\n  panel.innerHTML=`<div class="v458-service-head"><div><h3>Estado de servicios</h3><p class="muted">Comprobación manual y segura. No envía mensajes, no emite facturas y no modifica citas.</p></div><div class="v458-service-actions"><span id="v458ServiceTime" class="v458-service-time">Sin comprobar</span><button id="v458CheckServices" class="primary-soft" type="button">↻ Comprobar servicios</button></div></div><div id="v458ServiceGrid" class="v458-service-grid">${servicePlaceholder()}</div>`;\n  const title=$(\'.config-title-row\',config);(title?.parentNode||config).insertBefore(panel,title?.nextSibling||config.firstChild);\n  $(\'#v458CheckServices\',panel)?.addEventListener(\'click\',checkServices);\n}\nfunction renderServices(data){\n  const grid=$(\'#v458ServiceGrid\');if(!grid)return;\n  const order=[\'local\',\'neon\',\'azur\',\'whatsapp\',\'mensajes\',\'agenda\',\'updates\'];\n  grid.innerHTML=order.map(key=>{\n    const s=(data.services||{})[key]||{label:key,status:\'NO_CONFIGURADO\',detail:\'Sin información\'};\n    const cls=statusClass(s.status),lat=s.latency_ms!=null?` · ${Math.round(Number(s.latency_ms))} ms`:\'\';\n    return `<div class="v458-service-card ${cls}" data-service="${escH(key)}"><div class="v458-service-top"><b>${escH(s.label||key)}</b><span class="v458-status ${cls}">${escH(String(s.status||\'\').replace(\'_\',\' \'))}</span></div><small>${escH(s.detail||\'\')}${escH(lat)}</small></div>`;\n  }).join(\'\');\n  const t=$(\'#v458ServiceTime\');if(t)t.textContent=data.checked_at?`Última comprobación: ${new Date(data.checked_at).toLocaleTimeString(\'es-EC\',{hour:\'2-digit\',minute:\'2-digit\'})}`:\'Comprobado ahora\';\n}\nasync function checkServices(){\n  const btn=$(\'#v458CheckServices\'),grid=$(\'#v458ServiceGrid\');\n  if(btn){btn.disabled=true;btn.textContent=\'Comprobando…\'}\n  if(grid)$$(\'.v458-status\',grid).forEach(x=>{x.className=\'v458-status checking\';x.textContent=\'COMPROBANDO\'});\n  try{renderServices(await apiCall(\'/api/services/check\',{method:\'POST\',body:\'{}\'}));}\n  catch(e){if(grid)grid.innerHTML=`<div class="desktop-runtime-status err">No se pudo completar la comprobación: ${escH(e.message||e)}</div>`}\n  finally{if(btn){btn.disabled=false;btn.textContent=\'↻ Comprobar servicios\'}}\n}\nwindow.checkServices=checkServices;\n\nfunction panelHeading(panel){return lower(panel?.querySelector(\'h1,h2,h3,h4\')?.textContent||\'\')}\nfunction makeTab(tabs,key,label,after){\n  let b=tabs.querySelector(`[data-config-tab="${key}"]`);if(b)return b;\n  b=document.createElement(\'button\');b.type=\'button\';b.dataset.configTab=key;b.textContent=label;b.onclick=()=>window.showConfigTab(key,b);\n  after?.after(b)||tabs.appendChild(b);return b;\n}\nfunction wrapAdvanced(panel,label){\n  if(!panel||panel.closest(\'details.v458-advanced\'))return;\n  const d=document.createElement(\'details\');d.className=\'v458-advanced\';const s=document.createElement(\'summary\');s.textContent=label;d.appendChild(s);panel.replaceWith(d);d.appendChild(panel);\n}\nfunction linkCard(label,url,badge,description){\n  if(!url)return\'\';\n  return `<div class="v458-link-card"><div class="label"><b>${escH(label)}</b><span>${escH(badge)}</span></div><small>${escH(description)}</small><code title="${escH(url)}">${escH(url)}</code><div class="v458-link-actions"><button type="button" data-copy-url="${escH(url)}">Copiar enlace</button><button type="button" class="primary-soft" data-open-url="${escH(url)}">Abrir</button></div></div>`;\n}\nfunction bindLinkButtons(root){\n  $$(\'[data-copy-url]\',root).forEach(b=>b.addEventListener(\'click\',async()=>{const u=b.dataset.copyUrl||\'\';try{await navigator.clipboard.writeText(u);b.textContent=\'Copiado ✓\';setTimeout(()=>b.textContent=\'Copiar enlace\',1200)}catch{prompt(\'Copia el enlace:\',u)}}));\n  $$(\'[data-open-url]\',root).forEach(b=>b.addEventListener(\'click\',()=>window.open(b.dataset.openUrl||\'\',\'_blank\',\'noopener\')));\n}\nfunction professionalCloudAgenda(cloud={}){\n  const box=$(\'#cloudAgendaLinks\'),pill=$(\'#cloudAgendaPill\');if(!box)return;\n  const registered=!!cloud.registered;\n  if(pill){pill.textContent=registered?\'ONLINE 24/7\':\'POR VERIFICAR\';pill.classList.toggle(\'ready\',registered)}\n  box.innerHTML=`<div class="v458-agenda-state ${registered?\'ready\':\'\'}"><b>${registered?\'Agenda web activa\':\'Agenda web preparada\'}</b> · ${escH(cloud.architecture||\'GitHub Pages + Neon\')}${cloud.last_error?`<br><small>${escH(cloud.last_error)}</small>`:\'\'}</div><div class="v458-link-grid">${linkCard(\'Doctor\',cloud.doctor_url,\'SOLO LECTURA\',\'Enlace permanente para consultar la agenda.\')}${linkCard(\'Recepción / Ayudante\',cloud.reception_url,\'EDITABLE\',\'Puede agendar, reagendar y cancelar. Este acceso sí puede renovarse.\')}</div><small>Los enlaces funcionan aunque esta PC esté apagada. El secreto viaja en el fragmento # y no se guarda en logs HTTP.</small>`;\n  bindLinkButtons(box);\n}\nwindow.renderCloudAgenda=professionalCloudAgenda;\nwindow.rotateMobileLinks=async function(){\n  if(!(await window.rpConfirm(\'¿Renovar el enlace editable de Recepción / Ayudante?\\n\\nEl enlace del Doctor permanecerá exactamente igual. El enlace editable anterior dejará de funcionar.\',\'Renovar acceso web\')))return;\n  try{const d=await apiCall(\'/api/mobile/links/rotate\',{method:\'POST\',body:\'{}\'});alert(d.message||\'Acceso editable renovado.\');if(\'mobileConfigCache\' in window)window.mobileConfigCache=null;await window.loadMobileConfigLinks?.(true)}catch(e){alert(e.message||e)}\n};\n\nfunction renderTemplateCards(d={}){\n  const grid=$(\'#v458TemplateGrid\');if(!grid)return;\n  const defs=[[\'recordatorio_cita\',\'Confirmación de cita\'],[\'cita_agendada\',\'Cita agendada\'],[\'recordatorio_hoy\',\'Recordatorio del día\']];\n  grid.innerHTML=defs.map(([key,label])=>{const x=d.templates?.[key]||{},approved=!!x.approved,auto=!!x.automatic;return `<div class="v458-template-card"><div class="top"><b>${escH(label)}</b><span class="v458-template-badge ${approved?\'approved\':\'\'}">${approved?\'APROBADA\':\'EN ESPERA\'}</span></div><code>${escH(x.name||key)} · ${escH(x.language||\'\')}</code><small>${approved?(auto?\'Activa en la automatización 24/7.\':\'Aprobada, pero no activada automáticamente.\'):\'No se usa automáticamente hasta que Meta la apruebe.\'}</small></div>`}).join(\'\');\n}\nfunction renderDelivery(cloud={}){\n  const host=$(\'#v458Delivery\');if(!host)return;const s=cloud.summary||{};\n  if(!cloud.available){host.innerHTML=`<div class="desktop-runtime-status">${escH(cloud.message||\'Sin datos recientes de entrega.\')}</div>`;return}\n  host.innerHTML=`<div class="v458-delivery-grid"><div><span>Total</span><b>${Number(s.TOTAL||0)}</b></div><div><span>Enviados</span><b>${Number(s.SENT||0)}</b></div><div><span>Entregados</span><b>${Number(s.DELIVERED||0)}</b></div><div><span>Leídos</span><b>${Number(s.READ||0)}</b></div><div><span>Errores</span><b>${Number(s.FAILED||0)+Number(s.ERROR||0)}</b></div></div><div class="v458-delivery-note">${escH(cloud.message||\'\')}</div>`;\n}\nwindow.loadWhatsappStatus=async function(){\n  const pill=$(\'#whatsappStatusPill\'),text=$(\'#whatsappStatusText\'),testPill=$(\'#whatsappTestPill\');\n  try{\n    const [d,cloud]=await Promise.all([apiCall(\'/api/whatsapp/status\'),apiCall(\'/api/whatsapp/cloud-status\').catch(e=>({available:false,message:e.message}))]);\n    if(pill){pill.textContent=d.cloud_mode?\'ONLINE 24/7\':(d.enabled?\'ACTIVO\':\'LOCAL APAGADO\');pill.classList.toggle(\'ready\',!!(d.cloud_mode||d.enabled))}\n    if(text){text.innerHTML=d.cloud_mode?\'<b>WhatsApp Cloud 24/7 activo.</b> La PC no envía automáticamente, por lo que no puede duplicar los mensajes del worker Cloud. Las respuestas Sí / No se sincronizan mediante Neon.\':escH(d.message||\'\')}\n    renderTemplateCards(d);renderDelivery(cloud);\n    if(testPill){const ready=!!d.manual_test?.ready;testPill.textContent=ready?\'DISPONIBLE\':\'FALTA CONFIGURAR\';testPill.classList.toggle(\'ready\',ready)}\n    const dateInput=$(\'#waTestDate\');if(dateInput&&!dateInput.value){const x=new Date();x.setDate(x.getDate()+1);dateInput.value=x.toISOString().slice(0,10)}\n  }catch(e){if(text)text.textContent=e.message||e}\n};\n\nfunction prepareAgendaSection(sec){\n  if(!sec)return;\n  const cloud=$(\'.remote-agenda-panel\',sec)||$$(\'.panel\',sec).find(p=>panelHeading(p).includes(\'agenda cloud\'));\n  if(cloud){const h=cloud.querySelector(\'h3\');if(h)h.textContent=\'Agenda web 24/7\';const p=cloud.querySelector(\'.config-panel-head p\');if(p)p.textContent=\'Accesos permanentes para consultar y administrar la agenda desde cualquier lugar.\';const actions=$(\'.remote-agenda-actions\',cloud);if(actions){const buttons=$$(\'button\',actions);if(buttons[0])buttons[0].textContent=\'↻ Verificar ahora\';if(buttons[1])buttons[1].textContent=\'🔑 Renovar acceso editable\'}}\n  const local=$$(\'.panel\',sec).find(p=>panelHeading(p).includes(\'acceso local de respaldo\'));if(local)wrapAdvanced(local,\'Respaldo local dentro del consultorio (avanzado)\');\n}\nfunction prepareWhatsappSection(config,agendaSec,tabs){\n  let sec=config.querySelector(\'[data-config-section="whatsapp"]\');\n  if(!sec){sec=document.createElement(\'div\');sec.className=\'config-section hidden\';sec.dataset.configSection=\'whatsapp\';agendaSec.after(sec)}\n  const moved=$$(\'.panel\',agendaSec).filter(p=>panelHeading(p).includes(\'whatsapp\')||p.classList.contains(\'whatsapp-test-panel\'));\n  moved.forEach(p=>sec.appendChild(p));\n  if(!$(\'#v458WaOverview\',sec)){\n    const over=document.createElement(\'div\');over.id=\'v458WaOverview\';over.className=\'panel compact-config-panel v458-wa-overview\';over.innerHTML=`<div class="config-panel-head"><div><h3>WhatsApp Cloud 24/7</h3><p class="muted">Conexión, plantillas aprobadas y entregas recientes en un solo lugar.</p></div><span class="performance-pill ready">CLOUD</span></div><div id="v458TemplateGrid" class="v458-template-grid"></div><div id="v458Delivery"></div>`;sec.insertBefore(over,sec.firstChild)\n  }\n  const test=$(\'.whatsapp-test-panel\',sec);if(test){const note=$(\'.config-info-note span\',test);if(note)note.textContent=\'Solo diagnóstico manual. No cambia la automatización, no crea citas y no toca pacientes. Las respuestas Sí / No del sistema real se procesan por Cloud 24/7 y se sincronizan con Neon.\';wrapAdvanced(test,\'Prueba controlada de WhatsApp (avanzado)\')}\n  const agendaBtn=tabs.querySelector(\'[data-config-tab="agenda"]\');makeTab(tabs,\'whatsapp\',\'WhatsApp\',agendaBtn);\n}\nfunction prepareProgramSection(sec){\n  if(!sec)return;\n  $$(\'.v451-update-box\',sec).forEach(x=>x.remove());\n  const perf=$(\'.performance-panel\',sec);if(perf){perf.innerHTML=`<div class="config-panel-head"><div><h3>Inicio y rendimiento</h3><p class="muted">Arquitectura actual del iniciador.</p></div><span class="performance-pill">⚡ ESTABLE</span></div><div class="v458-program-card"><div><span>Ventana principal</span><b>WebView2</b><small>Edge se usa solo como respaldo automático.</small></div><div><span>Protección</span><b>Una sola instancia</b><small>Un segundo clic no abre otro backend ni otra ventana.</small></div><div><span>Ahorro de nube</span><b>AFK automático</b><small>Neon descansa cuando Recepción no se está usando.</small></div></div>`}\n  const up=$(\'.updater-panel\',sec);if(up){up.innerHTML=`<div class="config-panel-head"><div><h3>Actualizaciones automáticas</h3><p class="muted">El launcher verifica SHA, staging y rollback antes de iniciar el programa.</p></div><span id="currentVersionBadge" class="version-badge">v${V}</span></div><div class="actions"><button id="v458CheckChannel" class="primary-soft" type="button">↻ Comprobar canal</button><button type="button" onclick="restartReception()">Reiniciar Recepción</button></div><div id="updateStatus" class="muted update-status">El launcher instala las versiones nuevas al abrir Recepción.</div>`;$(\'#v458CheckChannel\',up)?.addEventListener(\'click\',checkUpdateChannel)}\n}\nasync function checkUpdateChannel(){const b=$(\'#v458CheckChannel\'),s=$(\'#updateStatus\');try{if(b){b.disabled=true;b.textContent=\'Comprobando…\'}const d=await apiCall(\'/api/program/update-now\',{method:\'POST\',body:\'{}\'});if(s)s.textContent=d.message||\'Canal comprobado.\'}catch(e){if(s)s.textContent=e.message||e}finally{if(b){b.disabled=false;b.textContent=\'↻ Comprobar canal\'}}}\n\nfunction installTabLoader(){\n  window.showConfigTab=function(tab=\'general\',button=null){\n    $$(\'[data-config-section]\').forEach(x=>x.classList.toggle(\'hidden\',x.dataset.configSection!==tab));\n    $$(\'[data-config-tab]\').forEach(x=>x.classList.toggle(\'active\',x.dataset.configTab===tab));\n    if(button)button.classList.add(\'active\');\n    let task=null;\n    try{\n      if(tab===\'general\')task=window.loadReceptionConfig?.();\n      else if(tab===\'agenda\')task=window.loadMobileConfigLinks?.(false);\n      else if(tab===\'whatsapp\')task=window.loadWhatsappStatus?.();\n      else if(tab===\'procedimientos\')task=window.loadProcedures?.();\n      else if(tab===\'facturacion\')task=window.loadAzurStatus?.();\n      else if(tab===\'sistema\')task=window.refreshProtectionStatus?.(false);\n      else if(tab===\'actualizaciones\')task=window.loadUpdateInfo?.();\n    }catch(_e){}\n    Promise.resolve(task).catch(()=>{});\n  };\n}\nfunction upgrade(){\n  const config=$(\'#config\');if(!config||config.dataset.v458===\'1\')return;\n  config.dataset.v458=\'1\';config.classList.add(\'v458-settings\');\n  const subtitle=$(\'.config-title-row .muted\',config);if(subtitle)subtitle.textContent=\'Conexiones, agenda, WhatsApp y preferencias organizadas para revisar todo rápido.\';\n  createServicePanel(config);\n  const tabs=$(\'.config-tabs\',config),agendaSec=config.querySelector(\'[data-config-section="agenda"]\');if(!tabs||!agendaSec)return;\n  const agendaBtn=tabs.querySelector(\'[data-config-tab="agenda"]\');if(agendaBtn)agendaBtn.textContent=\'Agenda 24/7\';\n  const fact=tabs.querySelector(\'[data-config-tab="facturacion"]\');if(fact)fact.textContent=\'AZUR\';\n  const sys=tabs.querySelector(\'[data-config-tab="sistema"]\');if(sys)sys.textContent=\'Nube y respaldo\';\n  prepareAgendaSection(agendaSec);prepareWhatsappSection(config,agendaSec,tabs);prepareProgramSection(config.querySelector(\'[data-config-section="actualizaciones"]\'));\n  installTabLoader();\n  // Renderiza de nuevo Agenda con los botones Abrir/Copiar si ya había datos cargados.\n  try{if(window.mobileConfigCache?.cloud)professionalCloudAgenda(window.mobileConfigCache.cloud)}catch(_e){}\n}\nif(document.readyState===\'loading\')document.addEventListener(\'DOMContentLoaded\',upgrade,{once:true});else upgrade();\nsetTimeout(upgrade,250);\n})();'
UPDATE_CHANNEL_URL = "https://raw.githubusercontent.com/fanserick-star/recepcion-dr-revelo-updates/main/latest-v3.json"


def _service_result(label: str, status: str, detail: str, *, latency_ms: Optional[float] = None, **extra) -> dict:
    data = {"label": label, "status": status, "detail": str(detail or "")[:240]}
    if latency_ms is not None:
        data["latency_ms"] = round(float(latency_ms), 1)
    data.update(extra)
    return data


def _probe_local_service() -> dict:
    pending = queue_count()
    return _service_result(
        "Recepción local", "ONLINE",
        f"Programa v{APP_VERSION} listo · {pending} cambio(s) pendiente(s) de sincronizar." if pending else f"Programa v{APP_VERSION} listo · copia local disponible.",
    )


def _probe_neon_service() -> dict:
    if not cloud_configured():
        return _service_result("Neon", "NO_CONFIGURADO", "DATABASE_URL no está configurado en esta PC.")
    if FORCE_OFFLINE:
        return _service_result("Neon", "OFFLINE", "Modo sin conexión forzado para diagnóstico.")
    started = time.perf_counter()
    ok = check_cloud(force=True)
    with _state_lock:
        probe_ms = _state.get("last_probe_ms")
        error = str(_state.get("last_error") or "")
    latency = probe_ms if probe_ms is not None else (time.perf_counter() - started) * 1000.0
    return _service_result("Neon", "ONLINE" if ok else "OFFLINE", "Base en la nube disponible." if ok else (error or "Neon no respondió."), latency_ms=latency)


def _probe_azur_service() -> dict:
    if not AZUR_BASE_URL or not AZUR_API_KEY:
        return _service_result("AZUR", "NO_CONFIGURADO", "Falta configurar la dirección o la API key de AZUR.")
    started = time.perf_counter()
    try:
        azur_test_connection(AZUR_BASE_URL, AZUR_API_KEY, timeout=8)
        return _service_result("AZUR", "ONLINE", f"Conexión autenticada con {urlparse(AZUR_BASE_URL).hostname or 'AZUR'}. No se emitió ninguna factura.", latency_ms=(time.perf_counter()-started)*1000)
    except Exception as exc:
        return _service_result("AZUR", "OFFLINE", str(exc)[:220], latency_ms=(time.perf_counter()-started)*1000)


def _probe_whatsapp_service() -> dict:
    if WHATSAPP_CLOUD_MODE:
        if not cloud_configured() or not CloudSessionLocal or FORCE_OFFLINE:
            return _service_result("WhatsApp Cloud", "OFFLINE", "El canal Cloud necesita Neon para consultar los envíos.")
        started = time.perf_counter()
        try:
            with CloudSessionLocal() as cdb:
                row = cdb.execute(text("""
                    SELECT status, updated_at
                    FROM whatsapp_cloud.events
                    ORDER BY updated_at DESC NULLS LAST, created_at DESC
                    LIMIT 1
                """)).mappings().first()
            detail = "Credenciales Meta administradas en Cloudflare; esta PC no guarda token de WhatsApp."
            if row:
                st = str(row.get("status") or "").upper()
                updated = row.get("updated_at")
                when = updated.isoformat(timespec="minutes") if updated else ""
                detail += f" Último evento: {st or 'registrado'}" + (f" · {when}" if when else "") + "."
            return _service_result("WhatsApp Cloud", "ONLINE", detail, latency_ms=(time.perf_counter()-started)*1000)
        except Exception as exc:
            return _service_result("WhatsApp Cloud", "DEGRADADO", f"Cloud configurado, pero no se pudo leer el registro de mensajes: {str(exc)[:160]}", latency_ms=(time.perf_counter()-started)*1000)

    missing = [name for name, value in (("WHATSAPP_GRAPH_VERSION", WHATSAPP_GRAPH_VERSION), ("WHATSAPP_PHONE_NUMBER_ID", WHATSAPP_PHONE_NUMBER_ID), ("WHATSAPP_ACCESS_TOKEN", WHATSAPP_ACCESS_TOKEN)) if not value]
    if missing:
        return _service_result("WhatsApp Meta", "NO_CONFIGURADO", "Falta configurar: " + ", ".join(missing))
    started = time.perf_counter()
    url = f"https://graph.facebook.com/{WHATSAPP_GRAPH_VERSION}/{WHATSAPP_PHONE_NUMBER_ID}?fields=display_phone_number,verified_name"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}", "User-Agent": f"Recepcion-Dr-Revelo/{APP_VERSION}", "Cache-Control": "no-cache"})
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            payload = json.loads(response.read(512_000).decode("utf-8-sig"))
        verified = str(payload.get("verified_name") or "Meta").strip()[:80]
        number = re.sub(r"\D", "", str(payload.get("display_phone_number") or ""))
        suffix = (" · ••••" + number[-4:]) if len(number) >= 4 else ""
        return _service_result("WhatsApp Meta", "ONLINE", f"Meta respondió correctamente · {verified}{suffix}. No se envió ningún mensaje.", latency_ms=(time.perf_counter()-started)*1000)
    except urllib.error.HTTPError as exc:
        detail = "Meta rechazó la comprobación. Revisa el token o Phone Number ID." if exc.code in (400, 401, 403) else f"Meta respondió HTTP {exc.code}."
        return _service_result("WhatsApp Meta", "OFFLINE", detail, latency_ms=(time.perf_counter()-started)*1000)
    except Exception as exc:
        return _service_result("WhatsApp Meta", "OFFLINE", f"No se pudo consultar Meta: {str(exc)[:170]}", latency_ms=(time.perf_counter()-started)*1000)


def _probe_messages_service() -> dict:
    if not WHATSAPP_CLOUD_MODE:
        return _service_result("Mensajes 24/7", "DEGRADADO", "El modo Cloud 24/7 está desactivado; la PC no debe duplicar envíos del worker.")
    if not cloud_configured() or not CloudSessionLocal:
        return _service_result("Mensajes 24/7", "OFFLINE", "Necesita Neon para registrar envíos y respuestas.")
    started = time.perf_counter()
    try:
        with CloudSessionLocal() as cdb:
            total = cdb.execute(text("SELECT count(*) FROM whatsapp_cloud.events WHERE created_at >= now() - interval '24 hours'" )).scalar()
        return _service_result("Mensajes 24/7", "ONLINE", f"Canal Cloud conectado a Neon · {int(total or 0)} evento(s) en las últimas 24 h. No se envió nada en esta prueba.", latency_ms=(time.perf_counter()-started)*1000)
    except Exception as exc:
        return _service_result("Mensajes 24/7", "DEGRADADO", f"No se pudo leer el registro Cloud: {str(exc)[:170]}", latency_ms=(time.perf_counter()-started)*1000)


def _probe_agenda_service() -> dict:
    if not AGENDA_CLOUD_BASE_URL:
        return _service_result("Agenda web 24/7", "NO_CONFIGURADO", "No hay URL pública de Agenda configurada.")
    started = time.perf_counter()
    req = urllib.request.Request(AGENDA_CLOUD_BASE_URL, headers={"User-Agent": f"Recepcion-Dr-Revelo/{APP_VERSION}", "Cache-Control": "no-cache"})
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            code = getattr(response, "status", 200)
            response.read(32_768)
        registered = bool(MOBILE_DOCTOR_TOKEN and MOBILE_RECEPTION_TOKEN and AGENDA_CLOUD_KEYS_SYNCED_SHA and hmac.compare_digest(AGENDA_CLOUD_KEYS_SYNCED_SHA, _agenda_cloud_signature(MOBILE_DOCTOR_TOKEN, MOBILE_RECEPTION_TOKEN)))
        status = "ONLINE" if code == 200 and registered else "DEGRADADO"
        detail = "Página pública disponible y accesos registrados en Neon." if registered else "Página pública disponible; pulsa Verificar ahora en Agenda para confirmar los accesos de esta PC."
        return _service_result("Agenda web 24/7", status, detail, latency_ms=(time.perf_counter()-started)*1000)
    except Exception as exc:
        return _service_result("Agenda web 24/7", "OFFLINE", f"La página pública no respondió: {str(exc)[:170]}", latency_ms=(time.perf_counter()-started)*1000)


def _read_update_channel_status() -> dict:
    local = _read_json_file(os.path.join(BASE_DIR, "update_manifest.json"))
    local_version = str(local.get("version") or APP_VERSION).strip()
    started = time.perf_counter()
    req = urllib.request.Request(UPDATE_CHANNEL_URL + f"?rp_ts={time.time_ns()}", headers={"User-Agent": f"Recepcion-Dr-Revelo/{APP_VERSION}", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=8) as response:
        remote = json.loads(response.read(512_000).decode("utf-8-sig"))
    latest = str(remote.get("version") or "").strip()
    if remote.get("product") != "recepcion-pacientes" or not latest:
        raise RuntimeError("El canal respondió con un manifiesto no válido")
    def vt(value):
        out=[]
        for part in str(value or "0").split("."):
            m=re.match(r"^(\d+)",part);out.append(int(m.group(1)) if m else 0)
        return tuple((out+[0,0,0,0])[:4])
    return {"local": local_version, "latest": latest, "update_available": vt(latest)>vt(local_version), "latency_ms": (time.perf_counter()-started)*1000}


def _probe_updates_service() -> dict:
    started=time.perf_counter()
    try:
        info=_read_update_channel_status()
        detail=(f"Actualización {info['latest']} disponible; se instalará al volver a abrir Recepción." if info["update_available"] else f"Canal accesible · paquete {info['local']} al día.")
        return _service_result("Actualizaciones", "ONLINE", detail, latency_ms=info.get("latency_ms"), update_available=info["update_available"], latest=info["latest"])
    except Exception as exc:
        return _service_result("Actualizaciones", "OFFLINE", f"No se pudo consultar el canal: {str(exc)[:170]}", latency_ms=(time.perf_counter()-started)*1000)


@app.post("/api/services/check")
def services_check(request: Request, user: User = Depends(current_user)):
    """Comprueba servicios externos solo cuando el usuario pulsa el botón.

    Todas las sondas son de lectura: no envían WhatsApp, no crean citas y no emiten facturas.
    """
    if not _is_loopback_client(request):
        raise HTTPException(403, "Esta comprobación solo se ejecuta desde la PC de Recepción")
    from concurrent.futures import ThreadPoolExecutor, as_completed
    checks = {
        "neon": _probe_neon_service,
        "azur": _probe_azur_service,
        "whatsapp": _probe_whatsapp_service,
        "mensajes": _probe_messages_service,
        "agenda": _probe_agenda_service,
        "updates": _probe_updates_service,
    }
    services = {"local": _probe_local_service()}
    with ThreadPoolExecutor(max_workers=3, thread_name_prefix="rp-services") as pool:
        future_map = {pool.submit(fn): key for key, fn in checks.items()}
        for future in as_completed(future_map):
            key = future_map[future]
            try:
                services[key] = future.result()
            except Exception as exc:
                label = {"neon":"Neon","azur":"AZUR","whatsapp":"WhatsApp Cloud" if WHATSAPP_CLOUD_MODE else "WhatsApp Meta","mensajes":"Mensajes 24/7","agenda":"Agenda web 24/7","updates":"Actualizaciones"}.get(key, key)
                services[key] = _service_result(label, "OFFLINE", f"Comprobación fallida: {str(exc)[:170]}")
    return {"ok": True, "checked_at": datetime.now().astimezone().isoformat(timespec="seconds"), "services": services}


@app.get("/v458/settings.css")
def v458_settings_css():
    return Response(content=V458_SETTINGS_CSS, media_type="text/css; charset=utf-8", headers={"Cache-Control":"no-store"})


@app.get("/v458/settings.js")
def v458_settings_js():
    return Response(content=V458_SETTINGS_JS, media_type="application/javascript; charset=utf-8", headers={"Cache-Control":"no-store"})


# ---------------------------------------------------------------------------
# v4.3.59 — Estado en pestaña + prueba Cloud + timeline por cita
# ---------------------------------------------------------------------------
V459_SETTINGS_CSS = "/* v4.3.59 — Estado en pestaña + timeline WhatsApp por cita */\n#config.v458-settings .v459-services-section .v458-service-panel{margin:0!important}\n.v459-whatsapp-timeline{margin:14px 0 4px;padding:13px 14px;border:1px solid #dfe6ef;border-radius:13px;background:#fbfcfe}\n.v459-whatsapp-timeline h3{font-size:14px;margin:0 0 11px;color:#253a57}\n.v459-wa-flow{position:relative;display:flex;flex-direction:column;gap:0}\n.v459-wa-step{position:relative;display:grid;grid-template-columns:24px minmax(0,1fr);gap:10px;min-height:64px;padding-bottom:10px}\n.v459-wa-step:last-child{min-height:44px;padding-bottom:0}\n.v459-wa-step:not(:last-child):before{content:'';position:absolute;left:10px;top:22px;bottom:-2px;width:2px;background:#dce4ee}\n.v459-wa-dot{width:21px;height:21px;border-radius:50%;display:grid;place-items:center;background:#eef2f7;border:2px solid #cbd5e2;color:#718096;font-size:10px;font-weight:900;z-index:1}\n.v459-wa-step.success .v459-wa-dot{background:#e6f7ec;border-color:#8ed1a6;color:#187342}.v459-wa-step.info .v459-wa-dot{background:#eaf2ff;border-color:#9cbcf0;color:#2e61a4}.v459-wa-step.danger .v459-wa-dot{background:#ffeceb;border-color:#e6a29d;color:#a03a34}\n.v459-wa-copy{display:flex;flex-direction:column;gap:3px}.v459-wa-title{display:flex;align-items:center;justify-content:space-between;gap:8px}.v459-wa-title b{font-size:13px;color:#273b56}.v459-wa-badge{font-size:9px;font-weight:800;border-radius:999px;padding:3px 7px;background:#eef2f6;color:#66768b;white-space:nowrap}.v459-wa-step.success .v459-wa-badge{background:#e6f7ec;color:#187342}.v459-wa-step.info .v459-wa-badge{background:#eaf2ff;color:#2e61a4}.v459-wa-step.danger .v459-wa-badge{background:#ffeceb;color:#a03a34}.v459-wa-copy small{font-size:11px;line-height:1.35;color:#728095}.v459-wa-response{font-size:11px;font-weight:700;color:#2c6f49;margin-top:2px}\n.v459-timeline-loading{font-size:12px;color:#738198;padding:8px 0}\n.v459-cloud-test-note{margin-top:8px;padding:9px 10px;border-radius:9px;background:#eef6ff;color:#45627e;font-size:12px;line-height:1.4}\n#v459FinishCloudTest{margin-left:7px}\n@media(max-width:760px){.v459-wa-title{align-items:flex-start;flex-direction:column;gap:4px}}\n"
V459_SETTINGS_JS = '(()=>{\n\'use strict\';\nconst V=\'4.3.59\';\nconst q=(s,r=document)=>r.querySelector(s), qa=(s,r=document)=>[...r.querySelectorAll(s)];\nconst eh=v=>String(v??\'\').replace(/[&<>"\']/g,c=>({\'&\':\'&amp;\',\'<\':\'&lt;\',\'>\':\'&gt;\',\'"\':\'&quot;\',"\'":\'&#39;\'}[c]));\nconst call=async(url,opt={})=>{if(typeof window.api===\'function\')return window.api(url,opt);const r=await fetch(url,{headers:{\'Content-Type\':\'application/json\',...(opt.headers||{})},...opt});const d=await r.json().catch(()=>({}));if(!r.ok)throw Error(d.detail||d.message||\'Error\');return d};\nconst lower=v=>String(v||\'\').trim().toLowerCase();\n\nfunction moveServicesToTab(){\n const config=q(\'#config\'),tabs=q(\'.config-tabs\',config),panel=q(\'#v458ServicePanel\',config);if(!config||!tabs||!panel)return;\n let sec=q(\'[data-config-section="services"]\',config);if(!sec){sec=document.createElement(\'div\');sec.dataset.configSection=\'services\';sec.className=\'config-section hidden v459-services-section\';const general=q(\'[data-config-section="general"]\',config);general?.after(sec)||config.appendChild(sec)}\n sec.appendChild(panel);\n let btn=q(\'[data-config-tab="services"]\',tabs);if(!btn){btn=document.createElement(\'button\');btn.type=\'button\';btn.dataset.configTab=\'services\';btn.textContent=\'Estado de servicios\';const generalBtn=q(\'[data-config-tab="general"]\',tabs);generalBtn?.after(btn)||tabs.prepend(btn);btn.onclick=()=>window.showConfigTab?.(\'services\',btn)}\n const badge=q(\'#currentVersionBadge\');if(badge)badge.textContent=\'v\'+V;\n}\n\nfunction cleanWhatsappConfig(){\n const sec=q(\'[data-config-section="whatsapp"]\');if(!sec)return;\n q(\'#v458Delivery\',sec)?.remove();\n const over=q(\'#v458WaOverview\',sec);if(over){const p=q(\'.config-panel-head p\',over);if(p)p.textContent=\'Conexión Cloud y estado de las plantillas. El historial de cada paciente se consulta directamente desde Agenda.\'}\n qa(\'.panel\',sec).forEach(p=>{const h=lower(q(\'h1,h2,h3,h4\',p)?.textContent);if(h===\'mensajes de whatsapp\'||h.startsWith(\'mensajes de whatsapp \'))p.remove()});\n const test=q(\'.whatsapp-test-panel\',sec);if(test){const h=q(\'h3\',test);if(h)h.textContent=\'Prueba Cloud controlada\';const p=q(\'.config-panel-head p\',test);if(p)p.textContent=\'Prueba el mismo worker 24/7 sin guardar tokens de Meta en esta PC.\';const note=q(\'.config-info-note span\',test);if(note)note.textContent=\'La solicitud viaja por Neon y el worker Cloud. No crea pacientes ni modifica citas reales. Puede tardar hasta 5 minutos porque usa el ciclo real del worker.\'}\n}\n\nfunction fmtStamp(v){if(!v)return\'\';try{return new Date(v).toLocaleString(\'es-EC\',{day:\'2-digit\',month:\'2-digit\',hour:\'2-digit\',minute:\'2-digit\'})}catch{return\'\'}}\nfunction timelineHtml(data){\n const items=data?.items||[];if(!items.length)return \'<div class="v459-timeline-loading">Sin información de mensajes para esta cita.</div>\';\n return `<div class="v459-wa-flow">${items.map((x,i)=>{const detail=x.error?`Error: ${eh(x.error)}`:(x.timestamp?fmtStamp(x.timestamp):(x.planned||\'\'));return `<div class="v459-wa-step ${eh(x.tone||\'muted\')}"><span class="v459-wa-dot">${i+1}</span><div class="v459-wa-copy"><div class="v459-wa-title"><b>${eh(x.label)}</b><span class="v459-wa-badge">${eh(x.status_label||\'—\')}</span></div><small>${eh(detail)}</small>${x.response?`<div class="v459-wa-response">${eh(x.response)}</div>`:\'\'}</div></div>`}).join(\'\')}</div>`\n}\nasync function loadTimeline(source,id,host){try{const d=await call(source===\'appointment\'?`/api/agenda/appointments/${id}/whatsapp-timeline`:`/api/agenda/confirmafy-staged/${id}/whatsapp-timeline`);host.innerHTML=timelineHtml(d)}catch(e){host.innerHTML=`<div class="v459-timeline-loading">No se pudo consultar el estado Cloud: ${eh(e.message||e)}</div>`}}\n\nwindow.openLinkedAgendaDetail=async function(appointmentId,patientId,fecha){\n try{const row=await call(`/api/agenda/appointments/${Number(appointmentId)}`),a=row.appointment||{},p=row.patient||{},state=String(a.estado||\'PENDIENTE\').toUpperCase();let status=\'Pendiente\',cls=\'pending\';if([\'CONFIRMADA\',\'CONFIRMADO\'].includes(state)){status=\'Confirmada\';cls=\'confirmed\'}else if([\'NO_ASISTIRA\',\'CANCELADA\',\'CANCELADO\'].includes(state)){status=\'No asistirá\';cls=\'cancelled\'}else if(state===\'REAGENDADA\'){status=\'Reagendada\';cls=\'rescheduled\'};\n  const date=typeof window.fmtDate===\'function\'?window.fmtDate(a.fecha):String(a.fecha||\'\'),time=typeof window.fmtTime===\'function\'?window.fmtTime(a.hora):String(a.hora||\'\');\n  window.openModal(`<div class="native-appointment-detail"><div class="modal-form-heading v467-agenda-heading"><h2>${eh(p.nombre||\'Paciente\')}</h2><div class="v467-agenda-meta"><span>${eh(date)} · ${eh(time)}</span>${p.celular?`<span class="v467-agenda-phone">Tel. ${eh(p.celular)}</span>`:\'\'}</div></div><div class="native-detail-status ${cls}">${eh(status)}</div>${a.nota?`<div class="native-detail-note">${eh(a.nota)}</div>`:\'\'}<section class="v459-whatsapp-timeline"><h3>Mensajes de WhatsApp</h3><div id="v459TimelineHost" class="v459-timeline-loading">Consultando estado Cloud…</div></section><div class="actions wrap-actions"><button onclick="openPatient(${Number(p.id)},\'patients\')">Ver paciente</button><button onclick="attendFromAgenda(${Number(p.id)},\'${String(fecha||a.fecha).slice(0,10)}\')">✓ Atender</button><button onclick="openAgendaPatient(${Number(p.id)},${Number(a.id)})">✎ Editar cita</button><button class="danger ghost" onclick="deleteAgendaAppointment(${Number(a.id)})">Eliminar cita</button></div></div>`);\n  requestAnimationFrame(()=>{const x=q(\'.native-appointment-detail\'),body=x?.parentElement,outer=x?.closest(\'.modal-content,.modal-card,[role="dialog"]\')||body?.parentElement;body?.classList.add(\'v467-agenda-modal-shell\');outer?.classList.add(\'v471-agenda-outer\')});\n   const host=q(\'#v459TimelineHost\');if(host)loadTimeline(\'appointment\',Number(a.id),host)\n }catch(e){window.rpNotice(e.message||e)}\n};\nwindow.openUnlinkedAgendaDetail=async function(itemId,fecha){\n try{const d=await call(`/api/agenda/confirmafy-staged/${Number(itemId)}`),st=d.staged||{},date=typeof window.fmtDate===\'function\'?window.fmtDate(st.fecha):String(st.fecha||\'\'),time=typeof window.fmtTime===\'function\'?window.fmtTime(st.hora):String(st.hora||\'\');\n  window.openModal(`<div class="native-appointment-detail"><div class="modal-form-heading v467-agenda-heading"><h2>${eh(st.nombre||\'Paciente\')}</h2><div class="v467-agenda-meta"><span>${eh(date)} · ${eh(time)}</span>${st.celular?`<span class="v467-agenda-phone">Tel. ${eh(st.celular)}</span>`:\'\'}</div></div><div class="native-detail-status pending">Pendiente · sin ficha vinculada</div><p class="muted">La identidad se resolverá cuando el paciente sea atendido.</p><section class="v459-whatsapp-timeline"><h3>Mensajes de WhatsApp</h3><div id="v459TimelineHost" class="v459-timeline-loading">Consultando estado Cloud…</div></section><div class="actions wrap-actions"><button class="primary" onclick="attendConfirmafyStaged(${Number(itemId)},\'${String(fecha||st.fecha).slice(0,10)}\')">✓ Atender</button><button class="danger ghost" onclick="deleteUnlinkedAppointment(${Number(itemId)})">Eliminar cita</button></div></div>`);\n  requestAnimationFrame(()=>{const x=q(\'.native-appointment-detail\'),body=x?.parentElement,outer=x?.closest(\'.modal-content,.modal-card,[role="dialog"]\')||body?.parentElement;body?.classList.add(\'v467-agenda-modal-shell\');outer?.classList.add(\'v471-agenda-outer\')});\n   const host=q(\'#v459TimelineHost\');if(host)loadTimeline(\'staged\',Number(itemId),host)\n }catch(e){window.rpNotice(e.message||e)}\n};\n\nlet cloudTest=null,cloudTestTimer=null,cloudTestNotified=false;\nfunction testTemplate(){return window.__v464WaTemplateValue||q(\'#waTestTemplate\')?.value||\'recordatorio_cita\'}\nasync function pollCloudTest(){if(!cloudTest)return;try{const d=await call(`/api/whatsapp/cloud-test/${cloudTest.id}?token=${encodeURIComponent(cloudTest.token)}`),r=q(\'#whatsappTestResult\');if(r){const extra=d.timestamp?\' · \'+fmtStamp(d.timestamp):\'\';r.textContent=`${d.status_label||d.status}${extra}${d.error?\' · \'+d.error:\'\'}`};if(d.terminal){clearInterval(cloudTestTimer);cloudTestTimer=null;if(d.ok&&!cloudTestNotified){cloudTestNotified=true;window.rpNotice(\'✅ El worker Cloud procesó la prueba.\\n\\nRevisa WhatsApp en el teléfono destino. Puedes probar los botones Sí / No y luego pulsar “Finalizar prueba”.\')}}}catch(e){const r=q(\'#whatsappTestResult\');if(r)r.textContent=\'No se pudo consultar la prueba: \'+(e.message||e)}}\nwindow.finishWhatsappCloudTest=async function(){if(!cloudTest)return;try{await call(`/api/whatsapp/cloud-test/${cloudTest.id}?token=${encodeURIComponent(cloudTest.token)}`,{method:\'DELETE\'});cloudTest=null;clearInterval(cloudTestTimer);cloudTestTimer=null;const r=q(\'#whatsappTestResult\');if(r)r.textContent=\'Prueba finalizada. La fila técnica fue retirada de la agenda Cloud.\';q(\'#v459FinishCloudTest\')?.remove()}catch(e){window.rpNotice(e.message||e)}};\nwindow.sendWhatsappTest=async function(){\n const phone=(q(\'#waTestPhone\')?.value||\'\').trim(),name=(q(\'#waTestName\')?.value||\'Prueba\').trim(),date=q(\'#waTestDate\')?.value||\'\',time=q(\'#waTestTime\')?.value||\'\',template=testTemplate(),result=q(\'#whatsappTestResult\'),btn=q(\'#waTestSendBtn\');\n if(!phone){window.rpNotice(\'Ingresa el número que recibirá la prueba.\');return}if(!date||!time){window.rpNotice(\'Selecciona fecha y hora para mostrar en el mensaje.\');return}if(![\'recordatorio_cita\',\'cita_agendada\',\'recordatorio_hoy\'].includes(template)){window.rpNotice(\'Plantilla de prueba no válida.\');return}\n if(!(await window.rpConfirm(`¿Enviar UNA prueba Cloud a ${phone}?\\n\\nNo se usará ningún token de Meta de esta PC y no se tocará ningún paciente real.`,\'Confirmar prueba WhatsApp\')))return;\n try{if(btn){btn.disabled=true;btn.textContent=\'Registrando en Cloud…\'}if(result)result.textContent=\'Registrando prueba técnica en Neon…\';const d=await call(\'/api/whatsapp/cloud-test\',{method:\'POST\',body:JSON.stringify({phone,name,date,time,template})});cloudTest={id:d.test_id,token:d.token};cloudTestNotified=false;if(result)result.textContent=\'✅ Solicitud registrada. Esperando al worker Cloud (ciclo de hasta 5 minutos)…\';let finish=q(\'#v459FinishCloudTest\');if(!finish&&btn){finish=document.createElement(\'button\');finish.id=\'v459FinishCloudTest\';finish.type=\'button\';finish.textContent=\'Finalizar prueba\';finish.onclick=window.finishWhatsappCloudTest;btn.after(finish)}clearInterval(cloudTestTimer);cloudTestTimer=setInterval(pollCloudTest,5000);pollCloudTest()}catch(e){if(result)result.textContent=\'❌ \'+(e.message||e);window.rpNotice(e.message||e)}finally{if(btn){btn.disabled=false;btn.textContent=\'☁ Enviar prueba por Cloud\'}}\n};\n\nwindow.loadWhatsappStatus=async function(){\n const pill=q(\'#whatsappStatusPill\'),text=q(\'#whatsappStatusText\'),testPill=q(\'#whatsappTestPill\');\n try{const d=await call(\'/api/whatsapp/status\');if(pill){pill.textContent=d.cloud_mode?\'ONLINE 24/7\':(d.enabled?\'ACTIVO\':\'LOCAL APAGADO\');pill.classList.toggle(\'ready\',!!(d.cloud_mode||d.enabled))}if(text)text.innerHTML=d.cloud_mode?\'<b>WhatsApp Cloud 24/7 activo.</b> Las credenciales de Meta permanecen en Cloudflare; esta PC no necesita token local. Las respuestas Sí / No se sincronizan mediante Neon.\':eh(d.message||\'\');\n  if(typeof window.renderTemplateCards===\'function\')window.renderTemplateCards(d);else{const grid=q(\'#v458TemplateGrid\');if(grid){const defs=[[\'recordatorio_cita\',\'Confirmación de cita\'],[\'cita_agendada\',\'Cita agendada\'],[\'recordatorio_hoy\',\'Recordatorio del día\']];grid.innerHTML=defs.map(([k,l])=>{const x=d.templates?.[k]||{},ok=!!x.approved;return `<div class="v458-template-card"><div class="top"><b>${eh(l)}</b><span class="v458-template-badge ${ok?\'approved\':\'\'}">${ok?\'APROBADA\':\'EN ESPERA\'}</span></div><code>${eh(x.name||k)} · ${eh(x.language||\'\')}</code><small>${ok?(x.automatic?\'Activa en la automatización 24/7.\':\'Aprobada, no automática.\'):\'No se usa hasta que Meta la apruebe.\'}</small></div>`}).join(\'\')}}\n  if(testPill){const ready=!!d.manual_test?.ready;testPill.textContent=ready?\'CLOUD LISTO\':\'NO DISPONIBLE\';testPill.classList.toggle(\'ready\',ready)}const dateInput=q(\'#waTestDate\');if(dateInput&&!dateInput.value){const x=new Date();x.setDate(x.getDate()+1);dateInput.value=x.toISOString().slice(0,10)}const btn=q(\'#waTestSendBtn\');if(btn)btn.textContent=\'☁ Enviar prueba por Cloud\';const sel=q(\'#waTestTemplate\');if(sel){[...sel.options].forEach(o=>{const k=o.value||\'\';o.disabled=k!==\'recordatorio_cita\'});sel.value=\'recordatorio_cita\'}\n }catch(e){if(text)text.textContent=e.message||e}\n};\n\nfunction upgrade(){moveServicesToTab();cleanWhatsappConfig();const sub=q(\'.config-title-row .muted\',\'#config\');if(sub)sub.textContent=\'Preferencias, servicios, agenda y conexiones organizadas por pestañas.\';setTimeout(()=>window.loadWhatsappStatus?.(),50)}\nif(document.readyState===\'loading\')document.addEventListener(\'DOMContentLoaded\',()=>setTimeout(upgrade,20),{once:true});else setTimeout(upgrade,20);setTimeout(upgrade,350);\n})();\n;(()=>{\n  function installV464TemplatePicker(){\n    const sel=document.querySelector(\'#waTestTemplate\');\n    if(!sel||sel.dataset.v464Picker===\'1\')return;\n    sel.dataset.v464Picker=\'1\';\n    sel.style.display=\'none\';\n    const current=window.__v464WaTemplateValue||sel.value||\'recordatorio_cita\';\n    window.__v464WaTemplateValue=current;\n    const wrap=document.createElement(\'div\');wrap.className=\'v464-template-picker\';wrap.setAttribute(\'role\',\'group\');wrap.setAttribute(\'aria-label\',\'Mensaje a probar\');\n    const defs=[[\'recordatorio_cita\',\'Confirmación\'],[\'cita_agendada\',\'Cita agendada\'],[\'recordatorio_hoy\',\'Recordatorio de hoy\']];\n    const paint=()=>wrap.querySelectorAll(\'button\').forEach(b=>b.classList.toggle(\'active\',b.dataset.template===window.__v464WaTemplateValue));\n    defs.forEach(([value,label])=>{const b=document.createElement(\'button\');b.type=\'button\';b.dataset.template=value;b.textContent=label;b.addEventListener(\'click\',()=>{window.__v464WaTemplateValue=value;sel.value=value;paint();});wrap.appendChild(b)});\n    sel.insertAdjacentElement(\'afterend\',wrap);paint();\n  }\n  function installV464PickerStyle(){if(document.getElementById(\'v464PickerStyle\'))return;const st=document.createElement(\'style\');st.id=\'v464PickerStyle\';st.textContent=`.v464-template-picker{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-top:4px}.v464-template-picker button{border:1px solid #cfd9e6;background:#fff;color:#38516f;border-radius:11px;padding:10px 9px;font-weight:800;cursor:pointer}.v464-template-picker button.active{background:#2767ad;color:#fff;border-color:#2767ad;box-shadow:0 4px 14px rgba(39,103,173,.18)}@media(max-width:850px){.v464-template-picker{grid-template-columns:1fr}}`;document.head.appendChild(st)}\n  function boot(){installV464PickerStyle();installV464TemplatePicker()}\n  if(document.readyState===\'loading\')document.addEventListener(\'DOMContentLoaded\',boot,{once:true});else boot();\n  setTimeout(boot,250);setTimeout(boot,900);\n  let v472PickerTimer=0;new MutationObserver(()=>{if(v472PickerTimer)return;v472PickerTimer=setTimeout(()=>{v472PickerTimer=0;installV464TemplatePicker()},160)}).observe(document.documentElement,{childList:true,subtree:true});\n})();\n'


@app.get("/v459/settings.css")
def v459_settings_css():
    return Response(content=V459_SETTINGS_CSS, media_type="text/css; charset=utf-8", headers={"Cache-Control":"no-store"})


@app.get("/v459/settings.js")
def v459_settings_js():
    return Response(content=V459_SETTINGS_JS, media_type="application/javascript; charset=utf-8", headers={"Cache-Control":"no-store"})




# ---------------------------------------------------------------------------
# v4.3.60 — visibilidad de versión + estados de Agenda con alto contraste
# ---------------------------------------------------------------------------
V460_OVERLAY_CSS = r"""
#connectionBadge .v460-version{margin-left:auto;padding-left:8px;border-left:1px solid currentColor;font-size:9px;font-weight:900;letter-spacing:.035em;white-space:nowrap;opacity:.88}
.native-slot.occupied.pending{background:#fff1b8!important;border-color:#dfaa14!important;box-shadow:inset 5px 0 0 #c88c00!important;color:#624800!important}
.native-slot.occupied.pending b,.native-slot.occupied.pending span{color:#624800!important}.native-slot.occupied.pending span{font-weight:850!important}
.native-slot.occupied.confirmed{background:#cdf2db!important;border-color:#35a967!important;box-shadow:inset 5px 0 0 #138c46!important;color:#0d5b2c!important}
.native-slot.occupied.confirmed b,.native-slot.occupied.confirmed span{color:#0d5b2c!important}.native-slot.occupied.confirmed span{font-weight:900!important}
.native-slot.occupied.cancelled{background:#ffd5da!important;border-color:#df5d6e!important;box-shadow:inset 5px 0 0 #c82e43!important;color:#81202d!important}
.native-slot.occupied.cancelled b,.native-slot.occupied.cancelled span{color:#81202d!important}.native-slot.occupied.cancelled span{font-weight:900!important}
.native-slot.occupied.rescheduled{background:#dce9ff!important;border-color:#648fd6!important;box-shadow:inset 5px 0 0 #356cc0!important;color:#214d91!important}
.native-slot.occupied.rescheduled b,.native-slot.occupied.rescheduled span{color:#214d91!important}.native-slot.occupied.rescheduled span{font-weight:900!important}
.native-detail-status.confirmed{background:#cdf2db!important;border:1px solid #35a967!important;color:#0d5b2c!important;font-weight:900!important}
.native-detail-status.cancelled{background:#ffd5da!important;border:1px solid #df5d6e!important;color:#81202d!important;font-weight:900!important}
.native-detail-status.pending{background:#fff1b8!important;border:1px solid #dfaa14!important;color:#624800!important;font-weight:900!important}
.native-detail-status.rescheduled{background:#dce9ff!important;border:1px solid #648fd6!important;color:#214d91!important;font-weight:900!important}
.v459-wa-step.success .v459-wa-copy{border-left:3px solid #2e9d5a;padding-left:8px}
.v459-wa-step.danger .v459-wa-copy{border-left:3px solid #cf3345;padding-left:8px}
"""

V460_OVERLAY_JS = '\n(()=>{\n\'use strict\';\nconst VERSION=\'4.4.27\';\nconst norm=v=>String(v||\'\').normalize(\'NFD\').replace(/[\\u0300-\\u036f]/g,\'\').toLowerCase().replace(/\\s+/g,\' \').trim();\nconst esc=v=>String(v??\'\').replace(/[&<>"\']/g,c=>({\'&\':\'&amp;\',\'<\':\'&lt;\',\'>\':\'&gt;\',\'"\':\'&quot;\',"\'":\'&#39;\'}[c]));\n\nfunction paintVersion(){\n  const badge=document.querySelector(\'#connectionBadge\');\n  if(badge){let v=badge.querySelector(\'.v460-version\');if(!v){v=document.createElement(\'span\');v.className=\'v460-version\';badge.appendChild(v)}if(v.textContent!==`v${VERSION}`)v.textContent=`v${VERSION}`;}\n  const configBadge=document.querySelector(\'#currentVersionBadge\');if(configBadge&&configBadge.textContent!==`v${VERSION}`)configBadge.textContent=`v${VERSION}`;\n}\nfunction installStyle(){\n if(document.querySelector(\'#v463UiStyle\'))return;\n const st=document.createElement(\'style\');st.id=\'v463UiStyle\';st.textContent=`\n .v463-notice-backdrop{position:fixed;inset:0;z-index:2147483000;background:rgba(22,31,46,.36);display:grid;place-items:center;padding:20px;backdrop-filter:blur(2px)}\n .v463-notice{width:min(440px,92vw);background:#fff;border:1px solid #dce4ee;border-radius:18px;box-shadow:0 20px 60px rgba(25,39,60,.24);padding:21px 22px 18px;font-family:inherit;color:#26384f}\n .v463-notice-head{display:flex;align-items:center;gap:11px;margin-bottom:10px}.v463-notice-icon{width:35px;height:35px;border-radius:50%;display:grid;place-items:center;background:#edf5ff;color:#2465a8;font-size:19px;font-weight:900}.v463-notice h3{margin:0;font-size:18px}.v463-notice-body{white-space:pre-wrap;line-height:1.45;font-size:14px;color:#53657a;max-height:45vh;overflow:auto}.v463-notice-actions{display:flex;justify-content:flex-end;gap:9px;margin-top:17px}.v463-notice button{border-radius:10px;padding:9px 15px;font-weight:800}.v463-notice .primary{background:#2767ad;color:#fff;border:1px solid #2767ad}\n .v463-use-patient-email{display:flex;align-items:center;gap:8px;margin:7px 0 4px;padding:8px 10px;border-radius:10px;background:#eef6ff;color:#385d82;font-size:12px;font-weight:700}.v463-use-patient-email input{width:16px;height:16px}\n `;document.head.appendChild(st);\n}\nfunction prettyAlert(message,title=\'Recepción\'){\n installStyle();document.querySelector(\'.v463-notice-backdrop\')?.remove();\n const back=document.createElement(\'div\');back.className=\'v463-notice-backdrop\';back.innerHTML=`<div class="v463-notice" role="alertdialog" aria-modal="true"><div class="v463-notice-head"><span class="v463-notice-icon">i</span><h3>${esc(title)}</h3></div><div class="v463-notice-body">${esc(message)}</div><div class="v463-notice-actions"><button class="primary" type="button">Aceptar</button></div></div>`;\n const close=()=>back.remove();back.querySelector(\'button\').onclick=close;back.onclick=e=>{if(e.target===back)close()};document.body.appendChild(back);back.querySelector(\'button\').focus();\n}\nwindow.rpNotice=prettyAlert;const v464BindAlert=()=>{window.alert=(message)=>prettyAlert(message)};v464BindAlert();setTimeout(v464BindAlert,0);setTimeout(v464BindAlert,500);setTimeout(v464BindAlert,1500);\nwindow.rpConfirm=(message,title=\'Confirmar\')=>new Promise(resolve=>{installStyle();document.querySelector(\'.v463-notice-backdrop\')?.remove();const back=document.createElement(\'div\');back.className=\'v463-notice-backdrop\';back.innerHTML=`<div class="v463-notice" role="dialog" aria-modal="true"><div class="v463-notice-head"><span class="v463-notice-icon">?</span><h3>${esc(title)}</h3></div><div class="v463-notice-body">${esc(message)}</div><div class="v463-notice-actions"><button type="button" data-no>Cancelar</button><button class="primary" type="button" data-yes>Aceptar</button></div></div>`;const done=v=>{back.remove();resolve(v)};back.querySelector(\'[data-no]\').onclick=()=>done(false);back.querySelector(\'[data-yes]\').onclick=()=>done(true);document.body.appendChild(back);back.querySelector(\'[data-yes]\').focus();});\n\nconst patientCache=new Map();\nfunction cacheBilling(data){for(const item of data?.items||[]){const p=item?.patient||{};if(!p.id)continue;patientCache.set(String(p.id),p);if(p.nombre)patientCache.set(\'n:\'+norm(p.nombre),p)}}\nif(window.fetch&&!window.fetch.__v463){const original=window.fetch.bind(window);const wrapped=async(...args)=>{const r=await original(...args);try{const u=String(args[0]?.url||args[0]||\'\');if(u.includes(\'/api/billing\'))r.clone().json().then(cacheBilling).catch(()=>{})}catch{}return r};wrapped.__v463=true;window.fetch=wrapped;}\nfunction patientFromHost(host){const text=norm(host?.textContent);let best=null;for(const [key,p] of patientCache){if(!key.startsWith(\'n:\')||!key.slice(2)||!text.includes(key.slice(2)))continue;if(!best||String(p.nombre||\'\').length>String(best.nombre||\'\').length)best=p}return best;}\nfunction emailInput(host){const direct=[...host.querySelectorAll(\'input\')].find(x=>x.type===\'email\'||/correo|email/i.test(`${x.id} ${x.name} ${x.placeholder}`));if(direct)return direct;for(const label of host.querySelectorAll(\'label\')){if(!/correo|email/i.test(label.textContent||\'\'))continue;const x=label.querySelector(\'input\')||document.getElementById(label.htmlFor);if(x)return x}return null;}\nfunction enhanceOtherBillingEmail(){\n for(const host of document.querySelectorAll(\'.modal,.modal-content,.modal-card,[role="dialog"]\')){\n  const txt=norm(host.textContent);if(!txt.includes(\'factur\')||!(txt.includes(\'otro\')||txt.includes(\'otra\')))continue;if(host.querySelector(\'.v463-use-patient-email\'))continue;\n  const input=emailInput(host);if(!input)continue;const p=patientFromHost(host);if(!p?.correo)continue;\n  const box=document.createElement(\'label\');box.className=\'v463-use-patient-email\';box.innerHTML=`<input type="checkbox"> Usar correo registrado del paciente · ${esc(p.correo)}`;input.parentElement?.appendChild(box);box.querySelector(\'input\').onchange=e=>{if(e.target.checked){input.value=p.correo;input.dispatchEvent(new Event(\'input\',{bubbles:true}));input.dispatchEvent(new Event(\'change\',{bubbles:true}))}};\n }\n}\nfunction hideResolvedAzurButtons(){\n for(const btn of document.querySelectorAll(\'button\')){const t=norm(btn.textContent);if(!(t.includes(\'actualizar\')&&t.includes(\'estado\')))continue;let node=btn.parentElement,hide=false;for(let i=0;i<5&&node;i++,node=node.parentElement){const badges=[...node.querySelectorAll(\'[class*="status"],[class*="badge"],.pill,.tag\')].map(x=>norm(x.textContent));if(badges.some(x=>x===\'emitida\'||x.includes(\'autorizada\'))){hide=true;break}const all=norm(node.textContent);if(all.length<1800&&(/\\bemitida\\b/.test(all)||all.includes(\'autorizada por azur\'))){hide=true;break}}if(hide){btn.style.display=\'none\';btn.dataset.v463Hidden=\'1\'}}\n}\nlet v472UiTimer=0;function scheduleV472UiRefresh(){if(v472UiTimer)return;v472UiTimer=setTimeout(()=>{v472UiTimer=0;paintVersion();hideResolvedAzurButtons();enhanceOtherBillingEmail()},140)}function watch(){paintVersion();installStyle();hideResolvedAzurButtons();enhanceOtherBillingEmail();const root=document.body;if(root&&!root.dataset.v463Watch){root.dataset.v463Watch=\'1\';new MutationObserver(scheduleV472UiRefresh).observe(root,{childList:true,subtree:true})}}\nif(document.readyState===\'loading\')document.addEventListener(\'DOMContentLoaded\',watch,{once:true});else watch();setTimeout(watch,250);\n})();\n\n;(()=>{\n  const normV465=s=>String(s||\'\').normalize(\'NFD\').replace(/[\\u0300-\\u036f]/g,\'\').replace(/\\s+/g,\' \').trim().toLowerCase();\n  let v465BillingTimer=0;\n  function hideV465BillingQueue(){\n    const wanted=\'cola de facturacion\';\n    const selectors=\'h1,h2,h3,h4,h5,h6,legend,.card-title,.panel-title,.section-title,strong,b\';\n    let title=[...document.querySelectorAll(selectors)].find(el=>normV465(el.textContent).startsWith(wanted));\n    if(!title){\n      title=[...document.querySelectorAll(\'div,span\')].find(el=>{const t=normV465(el.textContent);return t.startsWith(wanted)&&t.length<90&&el.children.length<=2});\n    }\n    if(!title)return false;\n    let box=title.closest(\'.billing-queue,.billing-next,.queue-card,.card,.panel,.box\');\n    if(!box){\n      const p=title.parentElement;\n      if(p&&normV465(p.textContent).startsWith(wanted)&&normV465(p.textContent).length<1200)box=p;\n    }\n    if(!box||box.dataset.v465BillingQueueHidden===\'1\')return !!box;\n    box.dataset.v465BillingQueueHidden=\'1\';\n    box.style.display=\'none\';\n    box.setAttribute(\'aria-hidden\',\'true\');\n    return true;\n  }\n  function scheduleV465BillingCleanup(){\n    if(v465BillingTimer)return;\n    v465BillingTimer=setTimeout(()=>{v465BillingTimer=0;hideV465BillingQueue()},100);\n  }\n  function bootV465Billing(){hideV465BillingQueue();setTimeout(hideV465BillingQueue,250);setTimeout(hideV465BillingQueue,900)}\n  if(document.readyState===\'loading\')document.addEventListener(\'DOMContentLoaded\',bootV465Billing,{once:true});else bootV465Billing();\n  const root=document.documentElement;\n  if(root)new MutationObserver(scheduleV465BillingCleanup).observe(root,{childList:true,subtree:true});\n})();\n\n;(()=>{\n  const v466BillingPrompt=/factur|azur|sri|comprobante/i;\n  const v466NativeConfirm=window.confirm.bind(window);\n  let v466ClickTarget=null;\n  let v466ClickAt=0;\n  let v466AllowTarget=null;\n  let v466Pending=false;\n\n  function v466ActionTarget(e){\n    const path=typeof e.composedPath===\'function\'?e.composedPath():[];\n    for(const el of path){\n      if(!el||el===document||el===window||typeof el.matches!==\'function\')continue;\n      if(el.matches(\'button,input[type="button"],input[type="submit"],a,[role="button"]\'))return el;\n    }\n    const t=e.target;\n    return t&&typeof t.closest===\'function\'?(t.closest(\'button,input[type="button"],input[type="submit"],a,[role="button"]\')||t):t;\n  }\n\n  document.addEventListener(\'click\',e=>{\n    const target=v466ActionTarget(e);\n    if(!target)return;\n    v466ClickTarget=target;\n    v466ClickAt=Date.now();\n    const stamp=v466ClickAt;\n    setTimeout(()=>{if(v466ClickAt===stamp&&Date.now()-stamp>=10000)v466ClickTarget=null},10050);\n  },true);\n\n  function v466InstallConfirmBridge(){\n    if(window.confirm&&window.confirm.__v466BillingBridge)return;\n    const bridge=function(message){\n      const text=String(message??\'\');\n      if(!v466BillingPrompt.test(text))return v466NativeConfirm(text);\n      const target=(v466ClickTarget&&Date.now()-v466ClickAt<10000)?v466ClickTarget:null;\n      if(v466AllowTarget&&target===v466AllowTarget){v466AllowTarget=null;return true;}\n      if(v466Pending)return false;\n      if(!target||typeof window.rpConfirm!==\'function\')return v466NativeConfirm(text);\n      v466Pending=true;\n      const title=/azur|sri/i.test(text)?\'Confirmar emisión en AZUR\':\'Confirmar facturación\';\n      const originalClickAt=v466ClickAt;\n      Promise.resolve(window.rpConfirm(text,title)).then(ok=>{\n        v466Pending=false;\n        if(!ok)return;\n        const wait=Math.max(0,720-(Date.now()-originalClickAt));\n        setTimeout(()=>{\n          v466AllowTarget=target;\n          try{target.click()}finally{setTimeout(()=>{if(v466AllowTarget===target)v466AllowTarget=null},0)}\n        },wait);\n      }).catch(()=>{v466Pending=false});\n      return false;\n    };\n    bridge.__v466BillingBridge=true;\n    window.confirm=bridge;\n  }\n\n  v466InstallConfirmBridge();\n  setTimeout(v466InstallConfirmBridge,0);\n  setTimeout(v466InstallConfirmBridge,500);\n})();\n\n;(()=>{\n  function installV467CompactStyle(){\n    if(document.getElementById(\'v467CompactStyle\'))return;\n    const st=document.createElement(\'style\');st.id=\'v467CompactStyle\';st.textContent=`\n      /* Ficha de Agenda: compacta, centrada y con teléfono solo al abrir la cita. */\n      .v467-agenda-modal-shell{width:min(520px,calc(100vw - 56px))!important;max-width:520px!important;height:auto!important;min-height:0!important;max-height:calc(100vh - 44px)!important;padding:16px 18px!important;border-radius:17px!important;overflow:auto!important}\n      .native-appointment-detail{width:100%!important;max-width:none!important}\n      .native-appointment-detail .v467-agenda-heading{margin:0 0 9px!important}\n      .native-appointment-detail .v467-agenda-heading h2{margin:0 0 5px!important;font-size:22px!important;line-height:1.16!important;letter-spacing:-.2px}\n      .v467-agenda-meta{display:flex;flex-wrap:wrap;align-items:center;gap:6px 14px;color:#607087;font-size:13px;font-weight:650}\n      .v467-agenda-phone{display:inline-flex;align-items:center;padding:3px 8px;border:1px solid #dbe5ef;border-radius:999px;background:#f6f9fc;color:#334e68;font-weight:750}\n      .native-appointment-detail .native-detail-status{margin:5px 0 8px!important;padding:5px 9px!important;font-size:11px!important}\n      .native-appointment-detail>.muted{margin:4px 0 9px!important;font-size:12px!important}\n      .native-appointment-detail .native-detail-note{margin:7px 0!important;padding:8px 10px!important}\n      .native-appointment-detail .v459-whatsapp-timeline{margin-top:8px!important;padding:10px 11px!important;border-radius:12px!important}\n      .native-appointment-detail .v459-whatsapp-timeline h3{margin:0 0 7px!important;font-size:13px!important}\n      .native-appointment-detail .v459-wa-flow{gap:2px!important}\n      .native-appointment-detail .v459-wa-step{padding:6px 0!important;min-height:0!important}\n      .native-appointment-detail .v459-wa-dot{width:22px!important;height:22px!important;min-width:22px!important;font-size:11px!important}\n      .native-appointment-detail .v459-wa-title{min-height:22px!important;gap:8px!important}\n      .native-appointment-detail .v459-wa-title b{font-size:13px!important}\n      .native-appointment-detail .v459-wa-copy small{font-size:11px!important;line-height:1.35!important}\n      .native-appointment-detail .v459-wa-badge{font-size:10px!important;padding:3px 6px!important}\n      .native-appointment-detail .actions{margin-top:9px!important;gap:6px!important;justify-content:flex-end!important}\n      .native-appointment-detail .actions button{padding:8px 12px!important;font-size:12px!important;border-radius:9px!important}\n\n      /* Configuración: ancho de lectura cómodo en monitor ancho. */\n      #config.v458-settings{width:min(1120px,calc(100% - 32px))!important;max-width:1120px!important;margin-left:auto!important;margin-right:auto!important}\n      #config.v458-settings .config-title-row{margin-bottom:12px!important}\n      #config.v458-settings .config-title-row h2{margin-bottom:4px!important}\n      #config.v458-settings .config-tabs{gap:3px!important;padding:4px 5px!important;margin-bottom:12px!important;overflow-x:auto!important}\n      #config.v458-settings .config-tabs button{padding:8px 11px!important;font-size:12px!important;white-space:nowrap!important}\n      #config.v458-settings [data-config-section]{width:100%!important;max-width:980px!important;margin-left:auto!important;margin-right:auto!important}\n      #config.v458-settings [data-config-section]>.panel,\n      #config.v458-settings [data-config-section] details>.panel{padding:15px 17px!important;border-radius:14px!important}\n      #config.v458-settings .config-panel-head{margin-bottom:10px!important}\n      #config.v458-settings .config-panel-head h3{margin-bottom:3px!important}\n      #config.v458-settings .v458-template-grid{gap:9px!important}\n      #config.v458-settings .v458-template-card{padding:11px 12px!important;border-radius:12px!important}\n      #config.v458-settings .v458-service-grid{gap:9px!important}\n      #config.v458-settings .v458-service-card{padding:11px 12px!important;border-radius:12px!important}\n      #config.v458-settings .v458-link-grid{gap:10px!important}\n      #config.v458-settings .v458-link-card{padding:12px!important}\n      @media(max-width:900px){\n        .v467-agenda-modal-shell{width:calc(100vw - 28px)!important;padding:15px!important}\n        #config.v458-settings{width:calc(100% - 18px)!important}\n        #config.v458-settings [data-config-section]{max-width:none!important}\n      }\n    `;document.head.appendChild(st)\n  }\n  function bootV467Compact(){installV467CompactStyle()}\n  if(document.readyState===\'loading\')document.addEventListener(\'DOMContentLoaded\',bootV467Compact,{once:true});else bootV467Compact();\n})();\n\n;(()=>{\n  function clearAgendaModalShell(){\n    document.querySelectorAll(\'.v467-agenda-modal-shell,.v471-agenda-outer\').forEach(el=>el.classList.remove(\'v467-agenda-modal-shell\',\'v471-agenda-outer\'));\n  }\n  function installV469ModalGuard(){\n    if(window.__v469ModalGuard)return;\n    const original=window.openModal;\n    if(typeof original!==\'function\')return;\n    window.__v469ModalGuard=true;\n    window.openModal=function(...args){\n      clearAgendaModalShell();\n      return original.apply(this,args);\n    };\n    const close=window.closeModal;\n    if(typeof close===\'function\'&&!close.__v469Wrapped){\n      const wrapped=function(...args){clearAgendaModalShell();return close.apply(this,args)};\n      wrapped.__v469Wrapped=true;window.closeModal=wrapped;\n    }\n  }\n  function bootV469(){clearAgendaModalShell();installV469ModalGuard()}\n  if(document.readyState===\'loading\')document.addEventListener(\'DOMContentLoaded\',bootV469,{once:true});else bootV469();\n  setTimeout(bootV469,120);setTimeout(bootV469,500);\n})();\n\n;(()=>{\n  function installV471AgendaOuterStyle(){\n    if(document.getElementById(\'v471AgendaOuterStyle\'))return;\n    const st=document.createElement(\'style\');st.id=\'v471AgendaOuterStyle\';st.textContent=`\n      .v471-agenda-outer{width:min(590px,calc(100vw - 40px))!important;max-width:590px!important;min-width:0!important;height:auto!important;min-height:0!important;max-height:calc(100vh - 24px)!important}\n      @media(max-width:680px){.v471-agenda-outer{width:calc(100vw - 24px)!important;max-width:none!important}}\n    `;document.head.appendChild(st)\n  }\n  if(document.readyState===\'loading\')document.addEventListener(\'DOMContentLoaded\',installV471AgendaOuterStyle,{once:true});else installV471AgendaOuterStyle();\n})();\n'

V473_HOTFIX_JS = r""";(()=>{
  if(window.__v473Hotfix)return;
  window.__v473Hotfix=true;

  // CANCELADA era el estado que dejaba el antiguo botón Eliminar. No debe
  // presentarse como si el paciente hubiese respondido "No" por WhatsApp.
  const baseAgendaStatusInfo=window.agendaStatusInfo;
  window.agendaStatusInfo=function(state){
    const s=String(state||'PENDIENTE').toUpperCase();
    if(['CANCELADA','CANCELADO'].includes(s))return {label:'Cancelada',cls:'cancelled'};
    return typeof baseAgendaStatusInfo==='function'?baseAgendaStatusInfo(state):{label:'Pendiente',cls:'pending'};
  };

  function confirmationDue(fecha){
    const m=/^(\d{4})-(\d{2})-(\d{2})$/.exec(String(fecha||'').slice(0,10));
    if(!m)return null;
    const due=new Date(Number(m[1]),Number(m[2])-1,Number(m[3]),8,0,0,0);
    due.setDate(due.getDate()-1);
    return due;
  }
  function statusForDate(state,fecha){
    const s=String(state||'PENDIENTE').toUpperCase();
    if(['CONFIRMADA','CONFIRMADO'].includes(s))return {label:'Confirmada',cls:'confirmed'};
    if(s==='NO_ASISTIRA')return {label:'No asistirá',cls:'cancelled'};
    if(['CANCELADA','CANCELADO'].includes(s))return {label:'Cancelada',cls:'cancelled'};
    if(s==='REAGENDADA')return {label:'Reagendada',cls:'rescheduled'};
    const due=confirmationDue(fecha);
    if(due&&Date.now()<due.getTime())return {label:'Agendada',cls:'scheduled'};
    return {label:'Pendiente',cls:'pending'};
  }
  window.v473AgendaStatusForDate=statusForDate;

  // En la cuadrícula, "Pendiente" solo aparece desde la hora en que corresponde
  // enviar la confirmación. Una cita futura todavía no confirmada dice "Agendada".
  window.nativeAgendaRowCell=function(row,date,time){
    if(!row)return `<button class="native-slot free" onclick="openAgendaSlotPicker('${date}','${time}')"><b class="native-free-time">${esc(fmtTime(time))}</b><span>Disponible</span></button>`;
    const a=row.appointment||{},p=row.patient||{},staged=row.staged||{},source=String(row.source_type||''),unlinked=source==='MOBILE_UNLINKED'||source==='LEGACY_UNLINKED'||source==='CONFIRMAFY_STAGED'||source==='CONFIRMAFY_LEGACY';
    const name=staged.nombre||p.nombre||'PACIENTE',status=statusForDate(a.estado,date),sourceBadge=unlinked?'<small class="native-unlinked">SIN VINCULAR</small>':'';
    const action=unlinked?`openUnlinkedAgendaDetail(${Number(staged.id||0)},'${date}')`:`openLinkedAgendaDetail(${Number(a.id||0)},${Number(p.id||0)},'${date}')`;
    return `<button class="native-slot occupied ${status.cls}" onclick="${action}"><b>${esc(name)}</b><span>${esc(status.label)}</span>${sourceBadge}</button>`;
  };

  // El detalle usa la misma regla de fecha que la cuadrícula.
  const baseOpenLinked=window.openLinkedAgendaDetail;
  if(typeof baseOpenLinked==='function')window.openLinkedAgendaDetail=async function(appointmentId,patientId,fecha){
    await baseOpenLinked(appointmentId,patientId,fecha);
    try{
      const row=agendaAppointmentById.get(Number(appointmentId)),a=row?.appointment||{};
      const st=statusForDate(a.estado,a.fecha||fecha),el=document.querySelector('.native-appointment-detail .native-detail-status');
      if(el){el.className=`native-detail-status ${st.cls}`;el.textContent=st.label}
    }catch(_e){}
  };

  // Emisión masiva: confirmar una sola vez y ejecutar la llamada directamente.
  // No se vuelve a hacer click programáticamente sobre el botón, evitando el bucle.
  window.emitAllPendingInvoices=async function(){
    try{
      const pre=await api('/api/billing/azur/batch-preview');
      const c=pre.counts||{},ready=Number(c.ready||0),skipped=Number(c.skipped||0);
      if(!pre.unlocked){alert('🔒 Emisión masiva bloqueada por seguridad.\n\nPrimero emite UNA factura individual real y confirma que AZUR/SRI la marque AUTORIZADA.');return}
      if(!ready){alert(`No hay facturas completas listas para emitir.\n\nOmitidas: ${skipped}`);return}
      const examples=(pre.skipped||[]).slice(0,5).map(x=>`• ${x.nombre||'Paciente'}: ${x.reason}`).join('\n');
      const text=`¿Emitir ${ready} factura${ready===1?'':'s'} aprobada${ready===1?'':'s'} en AZUR?\n\nSe enviarán una por una para evitar duplicados. Las enviadas quedarán EN PROCESO hasta consultar la autorización del SRI.`+(skipped?`\n\nSe omitirán ${skipped} por datos incompletos o estado.`:'')+(examples?`\n\nEjemplos omitidos:\n${examples}`:'');
      const ok=typeof window.rpConfirm==='function'?await window.rpConfirm(text,'Confirmar emisión en AZUR'):window.confirm(text);
      if(!ok)return;
      const result=await singleFlightMutation('billing:azur:emit-all',()=>api('/api/billing/azur/emit-all-pending',{method:'POST',body:'{}'}),'Enviando facturas…');
      if(!result)return;
      const r=result.counts||{};let detail=`Enviadas a AZUR: ${r.sent??r.emitted??0}\nOmitidas: ${r.skipped||0}\nFallidas: ${r.failed||0}`;
      const omit=(result.skipped||[]).slice(0,8);if(omit.length)detail+='\n\nOmitidas:\n'+omit.map(x=>`• ${x.nombre||'Paciente'}: ${x.reason}`).join('\n');
      const failed=(result.failed||[]).slice(0,5);if(failed.length)detail+='\n\nFallidas:\n'+failed.map(x=>`• ${x.nombre||'Paciente'}: ${x.reason}`).join('\n');
      alert('Lote enviado. Las enviadas quedan EN PROCESO hasta confirmar autorización SRI.\n\n'+detail);
      await loadBilling();await refreshPendingBadges();
    }catch(e){alert(e.message||'No se pudo completar la emisión masiva.')}
  };
})();"""
V460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\n" + V473_HOTFIX_JS

V474_CAPTURE_FIX_JS = r""";(()=>{
  if(window.__v474CaptureFix)return;
  window.__v474CaptureFix=true;
  let billingBusy=false, deleteBusy=false;

  async function req(url, options={}){
    const opts={credentials:'same-origin',...options};
    if(options.body && !opts.headers)opts.headers={'Content-Type':'application/json'};
    const r=await fetch(url,opts);
    let data={};
    try{data=await r.json()}catch(_e){}
    if(!r.ok)throw new Error(data?.detail||data?.message||`Error HTTP ${r.status}`);
    return data;
  }
  function notice(msg,title='Recepción'){
    if(typeof window.rpNotice==='function')window.rpNotice(String(msg||''),title);
    else window.alert(String(msg||''));
  }
  async function ask(msg,title){
    if(typeof window.rpConfirm==='function')return !!(await window.rpConfirm(msg,title));
    return window.confirm(msg);
  }

  async function emitAll(btn){
    if(billingBusy)return;
    billingBusy=true;
    const old=btn?.textContent;
    try{
      if(btn){btn.disabled=true;btn.textContent='Revisando…'}
      const pre=await req('/api/billing/azur/batch-preview');
      const c=pre.counts||{}, ready=Number(c.ready||0), skipped=Number(c.skipped||0);
      if(!ready){notice(`No hay facturas completas listas para emitir.\n\nOmitidas: ${skipped}`,'Facturación');return}
      const text=`¿Emitir ${ready} factura${ready===1?'':'s'} aprobada${ready===1?'':'s'} en AZUR?\n\nSe enviarán una por una para evitar duplicados. Las enviadas quedarán EN PROCESO hasta consultar la autorización del SRI.`;
      if(!(await ask(text,'Confirmar emisión en AZUR')))return;
      if(btn)btn.textContent='Enviando…';
      const result=await req('/api/billing/azur/emit-all-pending',{method:'POST',body:'{}',headers:{'Content-Type':'application/json'}});
      const r=result.counts||{};
      let detail=`Enviadas a AZUR: ${r.sent??r.emitted??0}\nOmitidas: ${r.skipped||0}\nFallidas: ${r.failed||0}`;
      const failed=(result.failed||[]).slice(0,5);
      if(failed.length)detail+='\n\nFallidas:\n'+failed.map(x=>`• ${x.nombre||'Paciente'}: ${x.reason}`).join('\n');
      notice('Lote procesado. Las enviadas quedan EN PROCESO hasta confirmar autorización SRI.\n\n'+detail,'AZUR');
      try{if(typeof window.loadBilling==='function')await window.loadBilling()}catch(_e){}
      try{if(typeof window.refreshPendingBadges==='function')await window.refreshPendingBadges()}catch(_e){}
    }catch(e){notice(e?.message||'No se pudo completar la emisión masiva.','Error de AZUR')}
    finally{billingBusy=false;if(btn){btn.disabled=false;btn.textContent=old||'Emitir todas'}}
  }

  async function removeAppointment(btn, kind, id){
    if(deleteBusy)return;
    deleteBusy=true;
    try{
      if(!(await ask('¿Eliminar esta cita y liberar el horario? La ficha del paciente no se borrará.','Eliminar cita')))return;
      if(btn)btn.disabled=true;
      const url=kind==='staged'?`/api/agenda/confirmafy-staged/${id}`:`/api/agenda/appointments/${id}`;
      await req(url,{method:'DELETE'});
      try{if(typeof window.closeModal==='function')window.closeModal()}catch(_e){}
      try{
        if(typeof window.loadAgendaWeek==='function')await window.loadAgendaWeek();
        else if(typeof window.loadAgenda==='function')await window.loadAgenda();
        else location.reload();
      }catch(_e){location.reload()}
    }catch(e){notice(e?.message||'No se pudo eliminar la cita.','Agenda')}
    finally{deleteBusy=false;if(btn)btn.disabled=false}
  }

  document.addEventListener('click',e=>{
    const btn=e.target?.closest?.('button');
    if(!btn)return;
    const label=String(btn.textContent||'').replace(/\s+/g,' ').trim();
    if(/emitir\s+todas/i.test(label)){
      e.preventDefault();e.stopPropagation();e.stopImmediatePropagation();
      void emitAll(btn);return;
    }
    if(/^eliminar cita$/i.test(label)){
      const onclick=String(btn.getAttribute('onclick')||'');
      let m=onclick.match(/deleteAgendaAppointment\((\d+)\)/i), kind='appointment';
      if(!m){m=onclick.match(/deleteUnlinkedAppointment\((\d+)\)/i);kind='staged'}
      if(!m)return;
      e.preventDefault();e.stopPropagation();e.stopImmediatePropagation();
      void removeAppointment(btn,kind,Number(m[1]));
    }
  },true);
})();"""
V460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\n" + V474_CAPTURE_FIX_JS

V475_BILLING_CSS = r"""
/* v4.3.75 — Facturación simplificada */
.v475-hidden{display:none!important}
.v475-sri-compact{background:transparent!important;border:0!important;border-top:1px solid #e5ebf2!important;border-radius:0!important;padding:10px 0 2px!important;margin:8px 0 0!important;box-shadow:none!important}
.v475-sri-line{display:flex;align-items:center;gap:8px;font-size:12px;color:#52647a;line-height:1.3}
.v475-sri-chip{display:inline-flex;align-items:center;justify-content:center;min-width:34px;padding:3px 7px;border-radius:999px;background:#eef3f8;color:#50657e;font-size:9px;font-weight:900;letter-spacing:.06em}
.v475-sri-line strong{font-size:12px;color:#344960;font-weight:800}
.v475-sri-compact.authorized .v475-sri-chip{background:#e7f6ec;color:#237045}
.v475-sri-compact.authorized .v475-sri-line strong{color:#286849}
.v475-sri-compact.process .v475-sri-chip{background:#eef4ff;color:#456b9c}
.v475-sri-compact.rejected .v475-sri-chip{background:#fff0ef;color:#a04a45}
.v475-action-button{font-weight:800!important}
"""
V475_BILLING_JS = r""";(()=>{
  if(window.__v475BillingUi)return;
  window.__v475BillingUi=true;
  const norm=v=>String(v||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/\s+/g,' ').trim().toLowerCase();
  let busy=false;

  function exactElements(text){
    const wanted=norm(text);
    return [...document.querySelectorAll('span,b,strong,label,small,option,button,h2,h3,p')].filter(el=>norm(el.textContent)===wanted);
  }
  function cardFor(el){
    return el?.closest?.('[class*="stat"],[class*="summary"],[class*="metric"],[class*="counter"],.card') || el?.parentElement?.parentElement || el?.parentElement;
  }
  function simplifyMetrics(){
    for(const el of exactElements('Pendientes')) el.textContent='Por emitir';
    for(const el of exactElements('Aprobadas')){
      const card=cardFor(el); if(card)card.classList.add('v475-hidden'); else el.classList.add('v475-hidden');
    }
  }
  function simplifySelects(){
    for(const sel of document.querySelectorAll('select')){
      const opts=[...sel.options], labels=opts.map(o=>norm(o.textContent));
      if(!labels.some(x=>x==='emitidas') || !labels.some(x=>x==='pendientes'))continue;
      for(const o of opts){
        const t=norm(o.textContent);
        if(t==='pendientes')o.textContent='Por emitir';
        if(t==='aprobadas')o.remove();
      }
      if(String(sel.value||'').toUpperCase()==='APROBADA'){
        sel.value='PENDIENTE';
        setTimeout(()=>sel.dispatchEvent(new Event('change',{bubbles:true})),0);
      }
    }
  }
  function simplifyActions(){
    for(const btn of document.querySelectorAll('button')){
      const t=norm(btn.textContent);
      if(t==='aprobar' || t==='aprobar factura' || t==='confirmar aprobacion' || t==='confirmar aprobación'){
        btn.textContent='Revisar y emitir';btn.classList.add('v475-action-button');
      }
      if(t.includes('aprobar todas') || t.includes('emitir todas') || t==='volver a pendiente')btn.classList.add('v475-hidden');
    }
    const billingScope=document.querySelector('#facturacion');
    if(billingScope){
      for(const el of [...billingScope.querySelectorAll('span,b,strong,small')]){
        const t=norm(el.textContent);
        if(t==='pendiente' || t==='aprobada')el.textContent='POR EMITIR';
      }
    }
  }
  function compactSri(){
    for(const label of [...document.querySelectorAll('b,strong,span')]){
      if(norm(label.textContent)!=='estado azur / sri')continue;
      let box=label.parentElement;
      if(!box)continue;
      if(box.parentElement && /actualizar estado|consulta nuevamente|autorizada por sri|en proceso|rechaz/i.test(norm(box.parentElement.textContent)))box=box.parentElement;
      if(box.dataset.v475Sri==='1')continue;
      const txt=norm(box.textContent);
      let state='Estado registrado', cls='process';
      if(txt.includes('autorizada')){state='Autorizada por SRI';cls='authorized'}
      else if(txt.includes('rechaz')){state='Rechazada por SRI';cls='rejected'}
      else if(txt.includes('proceso')){state='En proceso en SRI';cls='process'}
      else if(txt.includes('devuelta')){state='Devuelta por SRI';cls='rejected'}
      box.dataset.v475Sri='1';
      box.classList.add('v475-sri-compact',cls);
      box.innerHTML=`<div class="v475-sri-line"><span class="v475-sri-chip">SRI</span><strong>${state}</strong></div>`;
    }
  }
  function copyText(){
    for(const p of [...document.querySelectorAll('p')]){
      const t=norm(p.textContent);
      if(t==='revisa, aprueba y emite directamente en azur.')p.textContent='Revisa los datos y emite directamente en AZUR.';
    }
  }
  function apply(){if(busy)return;busy=true;try{copyText();simplifySelects();simplifyMetrics();simplifyActions();compactSri()}finally{busy=false}}

  // El endpoint /api/billing/approve ahora realiza toda la operación. Solo
  // adaptamos mensajes viejos de la interfaz para que no diga "aprobada".
  const oldNotice=window.rpNotice;
  if(typeof oldNotice==='function')window.rpNotice=function(msg,title){
    let text=String(msg||'');
    if(/factura.+aprob/i.test(text))text='Factura revisada y enviada a AZUR.';
    return oldNotice.call(this,text,title);
  };

  const observer=new MutationObserver(()=>queueMicrotask(apply));
  observer.observe(document.documentElement,{childList:true,subtree:true});
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',apply,{once:true});else apply();
  setTimeout(apply,250);setTimeout(apply,900);
})();"""
V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\n" + V475_BILLING_CSS
V460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\n" + V475_BILLING_JS

V476_CSS = r"""#facturacion .billing-filters{display:none!important}#facturacion .billing-title-actions button:not(.external-billing-link){display:none!important}#facturacion .billing-summary{display:grid!important;grid-template-columns:repeat(2,minmax(0,1fr))!important;gap:12px!important;margin:15px 0 18px!important}#facturacion .billing-summary>button{min-height:70px!important;border:1px solid #d7e0eb!important;border-radius:15px!important;background:#fff!important;padding:12px 16px!important;display:flex!important;align-items:center!important;justify-content:space-between!important;gap:12px!important;text-align:left!important;color:#30435b!important}#facturacion .billing-summary>button.active{border-color:#77a1d0!important;background:#edf5ff!important;color:#244f82!important}#facturacion .billing-summary>button b{font-size:24px!important}#facturacion .billing-summary>button span{font-size:13px!important;font-weight:850!important}.v476-sri{display:flex;align-items:center;gap:8px;flex-wrap:wrap;border-top:1px solid #e4eaf1;margin-top:10px;padding-top:9px;font-size:12px}.v476-sri i{font-style:normal;border-radius:999px;padding:3px 8px;background:#eef3f8;color:#50657e;font-size:9px;font-weight:900}.v476-sri.ok i{background:#e7f6ec;color:#237045}.v476-sri.ok b{color:#286849}.v476-sri.wait i{background:#eef4ff;color:#456b9c}.v476-sri.wait b{color:#456b9c}.v476-sri.bad i{background:#fff0ef;color:#a04a45}.v476-sri.bad b{color:#93443f}@media(max-width:760px){#facturacion .billing-summary{grid-template-columns:1fr!important}}"""
V476_JS = r""";(()=>{if(window.__v476)return;window.__v476=true;const n=v=>String(v||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/\s+/g,' ').trim().toLowerCase(),e=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function az(g){return(g.items||[]).map(x=>x.azur).find(Boolean)||null}function sri(g){const a=az(g);if(!a)return'';const s=String(a.estado||'').toUpperCase();let t='En proceso en SRI',c='wait';if(s==='AUTORIZADA'){t='Autorizada por SRI';c='ok'}else if(s==='RECHAZADA'||s==='DEVUELTA'){t=s==='RECHAZADA'?'Rechazada por SRI':'Devuelta por SRI';c='bad'}return`<div class="v476-sri ${c}"><i>SRI</i><b>${e(t)}</b></div>`}
window.billingCardHtml=function(g){const view=String(document.querySelector('#bEstado')?.value||'PENDIENTE').toUpperCase(),st=billingGroupStatus(g),miss=billingMissingFields(g.patient),total=billingTotal(g),a=billingRecipientDraft(g.patient.id,g.fecha),z=az(g),invoice=billingInvoiceNumber(g)||String(z?.numero_factura||'');let actions='';const other=`<button onclick="openBillingRecipientEditor(${g.patient.id},'${g.fecha}')">👤 ${a?.alternate?'Editar datos de factura':'Facturar con otros datos'}</button>`;if(view==='EMITIDA'){actions=`<button onclick="copyBillingData(${g.patient.id},'${g.fecha}')">📋 Ver datos de factura</button>`;if(z&&['EN_PROCESO','CONSULTADA'].includes(String(z.estado||'').toUpperCase()))actions+=`<button onclick="checkAzurInvoiceStatus(${g.patient.id},'${g.fecha}')">↻ Consultar SRI</button>`}else{const emit=`<button class="primary billing-approve" onclick="approveBilling(${g.patient.id},'${g.fecha}')">✓ Revisar y emitir</button>`;actions=a?.alternate?other+emit:(miss.length?`<button class="complete-patient-list-btn" onclick="editPatientFromBilling(${g.patient.id})">✎ Completar datos</button>${other}`:other+emit)}const warn=view!=='EMITIDA'&&miss.length&&!a?.alternate?`<div class="billing-warning">⚠ Falta ${e(miss.join(' y '))} para emitir con los datos del paciente. También puedes facturar con otros datos.</div>`:'',num=invoice?`<div class="billing-invoice-number"><span>Factura</span><b>${e(invoice)}</b></div>`:'',badge=view==='EMITIDA'?'EMITIDA':'POR EMITIR',cls=view==='EMITIDA'?'emitida':'pendiente';return`<article class="billing-card ${cls}"><div class="billing-card-head"><div><div class="billing-patient-name">${e(g.patient.nombre)}</div><div class="billing-meta"><span><b>Cédula:</b> ${e(g.patient.cedula||'Sin cédula')}</span><span><b>Correo:</b> ${e(g.patient.correo||'Sin correo')}</span><span><b>Fecha:</b> ${fmtDate(g.fecha)}</span></div></div><span class="billing-status ${cls}">${badge}</span></div>${billingRecipientSummary(g)}${warn}<div class="billing-lines">${billingServicesHtml(g)}</div>${sri(g)}<div class="billing-card-foot"><div class="billing-total"><span>Total</span><strong>${money(total)}</strong></div>${num}<div class="billing-actions">${actions}</div></div></article>`};
function clean(){const s=document.querySelector('#facturacion');if(!s)return;s.querySelector('.billing-filters')?.setAttribute('hidden','');s.querySelectorAll('.billing-title-actions button:not(.external-billing-link)').forEach(b=>b.style.display='none');const p=s.querySelector('.billing-title-row p.muted');if(p)p.textContent='Revisa los datos y emite directamente en AZUR.'}
function tabs(){const h=document.querySelector('#billingSummary');if(!h)return;const bs=[...h.querySelectorAll('button')],pend=bs.find(b=>n(b.textContent).includes('pendiente')||n(b.textContent).includes('por emitir')),app=bs.find(b=>n(b.textContent).includes('aprobada')),emit=bs.find(b=>n(b.textContent).includes('emitida'));if(pend){pend.querySelector('span')&&(pend.querySelector('span').textContent='Por emitir');pend.classList.toggle('active',String(document.querySelector('#bEstado')?.value||'PENDIENTE').toUpperCase()!=='EMITIDA')}if(app)app.remove();if(emit)emit.classList.toggle('active',String(document.querySelector('#bEstado')?.value||'').toUpperCase()==='EMITIDA')}
const oldLoad=window.loadBilling;window.loadBilling=async function(){await oldLoad();clean();tabs()};const oldSet=window.setBillingStatus;window.setBillingStatus=async function(s){s=String(s||'PENDIENTE').toUpperCase();if(s==='APROBADA')s='PENDIENTE';if(s==='EMITIDA'){try{await api('/api/billing/azur/check-all-status',{method:'POST',body:'{}'})}catch(_e){}}await oldSet(s);clean();tabs()};window.approveBilling=async function(id,f){const d=billingRecipientDraft(id,f),who=d?.alternate?`\n\nLa factura se emitirá a: ${d.nombre} (${billingRecipientKind(d.identificacion)} ${d.identificacion})`:'';const q='¿Revisar y emitir esta factura en AZUR?'+who+'\n\nAl aceptar se enviará el comprobante; no habrá un paso de aprobación separado.',ok=typeof window.rpConfirm==='function'?await window.rpConfirm(q,'Revisar y emitir'):window.confirm(q);if(!ok)return;try{await singleFlightMutation(`billing:approve:${id}:${f}`,async()=>{await api('/api/billing/approve',{method:'POST',body:JSON.stringify({patient_id:id,fecha:f,...billingRecipientPayload(id,f)})});await window.loadBilling();refreshPendingBadges()},'Emitiendo en AZUR…')}catch(x){alert(x.message)}};if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',clean,{once:true});else clean();})();"""
V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\n" + V476_CSS
V460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\n" + V476_JS

V477_ATTENTION_CSS = r"""
/* v4.3.77 — Remaster de Nueva atención */
.modalbox.modalbox-wide.v477-attention-modalbox{width:min(790px,94vw)!important;max-height:90vh!important;padding:21px 23px 20px!important;border-radius:18px!important}
.v477-attention-remaster{display:grid;gap:12px}
.v477-attention-top{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;padding-right:42px}
.v477-attention-top .modal-form-heading{padding-right:0!important;margin:0!important}
.v477-attention-top .modal-form-heading h2{font-size:22px!important;letter-spacing:-.015em}
.v477-attention-top .modal-form-heading p{margin-top:4px!important;font-size:11px!important}
.v477-new-patient-btn{flex:0 0 auto;min-height:39px;padding:9px 13px!important;border-radius:11px!important;font-size:11px!important;font-weight:850!important;white-space:nowrap}
.v477-attention-remaster .attention-start-search{margin:0!important;gap:4px!important}
.v477-attention-remaster .attention-start-search>label{font-size:11px!important;color:#53647b!important}
.v477-attention-remaster .attention-start-search .search{height:46px!important;padding:10px 13px!important;border-radius:12px!important;background:#fff!important;font-size:14px!important}
.v477-attention-remaster .attention-start-search>small{display:none!important}
.v477-attention-remaster .attention-week-block{margin:0!important;padding:0!important;border:0!important;background:transparent!important}
.v477-today-head{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:11px 13px;margin:1px 0 7px;border:1px solid #dfe7f1;border-radius:12px;background:#f7f9fc}
.v477-today-title{display:grid;gap:2px;min-width:0}
.v477-today-kicker{font-size:8px;font-weight:900;letter-spacing:.12em;color:#6d7d92;text-transform:uppercase}
.v477-today-title b{font-size:13px;color:#1c314f;text-transform:capitalize}
.v477-today-meta{display:flex;align-items:center;gap:7px;flex-wrap:wrap;justify-content:flex-end}
.v477-today-meta strong{font-size:10px;color:#586c85;white-space:nowrap}
.v477-today-meta .attention-week-conflict-note{font-size:8px;padding:3px 6px}
.v477-attention-remaster .attention-week-calendar{display:block!important}
.v477-attention-remaster .attention-week-day{border:1px solid #dce5ef!important;border-radius:13px!important;overflow:hidden!important;box-shadow:none!important;background:#fff!important}
.v477-attention-remaster .attention-week-day>header{padding:8px 11px!important;background:#edf5ff!important;border-bottom:1px solid #dce8f6!important}
.v477-attention-remaster .attention-week-day>header b{font-size:12px!important}
.v477-attention-remaster .attention-week-day>header span{font-size:9px!important}
.v477-attention-remaster .attention-week-day>header strong{min-width:27px!important;height:25px!important;border-radius:8px!important;font-size:10px!important}
.v477-attention-remaster .attention-week-list{display:grid!important;grid-template-columns:repeat(2,minmax(0,1fr))!important;gap:7px!important;padding:8px!important;max-height:330px!important;overflow:auto!important}
.v477-attention-remaster .attention-week-row{grid-template-columns:54px minmax(0,1fr)!important;min-height:49px!important;padding:8px 10px!important;border-radius:10px!important;border:1px solid #e3e9f1!important;background:#fff!important}
.v477-attention-remaster .attention-week-row:hover,.v477-attention-remaster .attention-week-row:focus{background:#f2f7ff!important;border-color:#a9c6ec!important;box-shadow:0 0 0 2px #e2edfb!important}
.v477-attention-remaster .attention-week-time{font-size:12px!important;color:#1d66a7!important}
.v477-attention-remaster .attention-week-person b{font-size:11.5px!important;line-height:1.2!important;-webkit-line-clamp:1!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important;display:block!important}
.v477-attention-remaster .attention-week-person small{font-size:9px!important;color:#738196!important}
.v477-attention-remaster .attention-week-row.confirmafy-unlinked{padding-right:10px!important;padding-bottom:8px!important}
.v477-attention-remaster .attention-week-unlinked-badge{display:none!important}
.v477-attention-remaster .attention-week-empty,.v477-attention-remaster .attention-week-loading{padding:22px 14px!important;border:1px dashed #d6e0eb;border-radius:12px;background:#fbfcfe;font-size:11px!important}
.v477-no-clinic{display:grid;justify-items:center;gap:4px;padding:25px 15px!important}
.v477-no-clinic b{font-size:13px;color:#314762}.v477-no-clinic span{font-size:10px;color:#77869a;text-align:center}
.v477-attention-remaster .attention-results{margin-top:0!important;max-height:390px!important}
@media(max-width:720px){.modalbox.modalbox-wide.v477-attention-modalbox{width:min(94vw,620px)!important;padding:18px!important}.v477-attention-top{padding-right:34px;align-items:stretch;flex-direction:column;gap:9px}.v477-new-patient-btn{align-self:flex-start}.v477-attention-remaster .attention-week-list{grid-template-columns:1fr!important;max-height:none!important}.v477-today-head{align-items:flex-start;flex-direction:column;gap:6px}.v477-today-meta{justify-content:flex-start}}
"""
V477_ATTENTION_JS = r""";(()=>{
  if(window.__v477AttentionRemaster)return;
  window.__v477AttentionRemaster=true;

  const dayName=(d)=>{
    try{return new Intl.DateTimeFormat('es-EC',{weekday:'long',day:'2-digit',month:'long'}).format(d)}catch(_e){return 'Hoy'}
  };
  const applyShell=()=>{
    const modal=document.querySelector('#modal .modalbox');
    if(modal&&modal.querySelector('.v477-attention-remaster'))modal.classList.add('v477-attention-modalbox');
  };

  window.renderAttentionWeek=function(d={}){
    const box=$('#attentionWeekCalendar');if(!box)return;
    const days=d.days||[],today=toISO(new Date());
    const day=days.find(x=>String(x?.date||'').slice(0,10)===today)||null;
    const title=$('#v477TodayTitle'),label=$('#attentionWeekLabel');
    if(title)title.textContent=day?.label?`${day.label} · ${fmtDate(day.date)}`:dayName(new Date());
    if(label)label.textContent=day?`${(day.appointments||[]).length} cita${(day.appointments||[]).length===1?'':'s'}`:'Sin consulta';
    const conflict=$('#attentionWeekConflict');
    if(conflict){
      const n=day?(day.appointments||[]).filter(x=>x?.conflict).length:0;
      conflict.textContent=n?`⚠ ${n} duplicada${n===1?'':'s'}`:'';
      conflict.classList.toggle('hidden',n<=0);
    }
    if(!day){
      box.innerHTML='<div class="attention-week-empty wide v477-no-clinic"><b>Hoy no hay consulta programada</b><span>Puedes buscar un paciente arriba para registrar una atención manualmente.</span></div>';
      return;
    }
    const rows=(day.appointments||[]).map(attentionWeekRow).join('')||'<div class="attention-week-empty">No hay pacientes agendados para hoy.</div>';
    box.innerHTML=`<article class="attention-week-day today v477-today-card"><header><div><b>Pacientes de hoy</b><span>${fmtDate(day.date)}</span></div><strong>${(day.appointments||[]).length}</strong></header><div class="attention-week-list">${rows}</div></article>`;
  };

  window.newAttention=async function(){
    currentPatientSource='general';
    attentionSearchSeq++;
    attentionWeekAnchor=toISO(new Date());
    const todayText=dayName(new Date());
    openModal(`<div class="new-attention-start-modal v477-attention-remaster"><div class="v477-attention-top"><div class="modal-form-heading"><h2>Nueva atención</h2><p>Selecciona al paciente de hoy o búscalo por sus datos.</p></div><button class="primary v477-new-patient-btn" onclick="newPatient(true)">＋ Paciente nuevo</button></div><div class="attention-start-search"><label for="aSearch">Buscar paciente</label><input id="aSearch" class="search uppercase-search" autocomplete="off" autocapitalize="characters" spellcheck="false" placeholder="Cédula, apellidos y nombres, celular o correo" oninput="upperSearchInput(this);attentionSearch()"></div><div id="attentionWeekBlock" class="attention-week-block"><div class="v477-today-head"><div class="v477-today-title"><span class="v477-today-kicker">Agenda de hoy</span><b id="v477TodayTitle">${esc(todayText)}</b></div><div class="v477-today-meta"><strong id="attentionWeekLabel"></strong><span id="attentionWeekConflict" class="attention-week-conflict-note hidden"></span></div></div><div id="attentionWeekCalendar" class="attention-week-calendar"><div class="attention-week-loading">Cargando agenda de hoy…</div></div></div><div id="aResults" class="results attention-results hidden"></div></div>`);
    applyShell();
    loadAttentionWeek(false,attentionWeekAnchor);
    setTimeout(()=>$('#aSearch')?.focus(),0);
  };

  const oldClose=window.closeModal;
  if(typeof oldClose==='function')window.closeModal=function(){
    document.querySelector('#modal .modalbox')?.classList.remove('v477-attention-modalbox');
    return oldClose.apply(this,arguments);
  };
})();"""
V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\n" + V477_ATTENTION_CSS
V460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\n" + V477_ATTENTION_JS

V478_REMIX_CSS = r"""
/* v4.3.78 — Inicio compacto + Agenda mañana/tarde */
#inicio .home-title-row{align-items:center!important;margin:0 0 7px!important;gap:16px!important}
#inicio .page-heading{gap:1px!important}
#inicio .page-eyebrow{font-size:8px!important;letter-spacing:.11em!important}
#inicio .page-heading h1{font-size:25px!important;line-height:1.05!important;margin:1px 0!important}
#inicio .page-heading p{font-size:10px!important;margin:2px 0 0!important}
#inicio .new-attention-main{min-height:43px!important;padding:10px 20px!important;border-radius:12px!important;font-size:12px!important}
#inicio .home-week-nav{justify-content:flex-end!important;margin:0 0 6px!important;gap:5px!important}
#inicio .tiny-week-label{font-size:9px!important;padding:4px 8px!important}
#inicio .tiny-week-btn{min-width:29px!important;min-height:28px!important;padding:4px 7px!important;font-size:9px!important;border-radius:9px!important}
#inicio .week-cards{display:grid!important;grid-template-columns:repeat(3,minmax(0,1fr)) minmax(190px,.85fr)!important;gap:8px!important;margin:0 0 8px!important}
#inicio .week-card.v478-week-chip{min-height:58px!important;padding:9px 11px!important;border-radius:12px!important;display:grid!important;grid-template-columns:minmax(0,1fr) auto!important;grid-template-areas:'day count' 'meta total'!important;gap:2px 9px!important;align-items:center!important;box-shadow:none!important;transform:none!important}
#inicio .v478-week-chip .week-day{grid-area:day;font-size:12px!important;font-weight:900!important;line-height:1.1!important}
#inicio .v478-week-chip .v478-week-count{grid-area:count;font-size:20px!important;line-height:1!important;color:#1f5fbf!important;font-weight:900!important}
#inicio .v478-week-chip .v478-week-meta{grid-area:meta;font-size:8.5px!important;color:#748297!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important}
#inicio .v478-week-chip .v478-week-total{grid-area:total;font-size:10px!important;font-weight:850!important;color:#304760!important;white-space:nowrap!important}
#inicio .week-card.v478-week-chip.active{background:#edf5ff!important;border-color:#75a2d7!important;box-shadow:inset 0 0 0 1px #bad2ec!important}
#inicio .week-card.v478-week-chip.active:after{left:11px!important;right:11px!important;height:2px!important}
#inicio .v478-week-total-card{min-height:58px;border:1px solid #dbe4ee;border-radius:12px;background:#f7f9fc;padding:9px 12px;display:grid;grid-template-columns:1fr auto;grid-template-areas:'kicker money' 'patients money';gap:2px 10px;align-items:center}
#inicio .v478-week-total-card span{grid-area:kicker;font-size:8px;font-weight:900;letter-spacing:.11em;color:#738197}
#inicio .v478-week-total-card strong{grid-area:patients;font-size:11px;color:#293e5b}
#inicio .v478-week-total-card b{grid-area:money;font-size:15px;color:#214f84;white-space:nowrap}
#inicio #weekSummary{display:none!important}
#inicio .selected-day-title{margin:2px 0 6px!important;padding:0!important}
#inicio .v478-day-head{width:100%;display:flex;align-items:end;justify-content:space-between;gap:12px}
#inicio .v478-day-head-main{display:grid;gap:1px}
#inicio .v478-day-kicker{font-size:8px;font-weight:900;letter-spacing:.1em;color:#7b8798;text-transform:uppercase}
#inicio .v478-day-head h2{font-size:17px!important;line-height:1.1!important;margin:0!important}
#inicio .v478-day-stats{display:flex;align-items:center;gap:6px;flex-wrap:wrap;justify-content:flex-end}
#inicio .v478-day-stats span,#inicio .v478-day-stats b{border:1px solid #dfe6ef;background:#f8fafc;border-radius:999px;padding:5px 8px;font-size:9px;color:#53667f;white-space:nowrap}
#inicio .v478-day-stats b{color:#214f84;background:#edf5ff;border-color:#d3e2f4}
#inicio #todayTable{overflow:visible!important;border-radius:13px!important;box-shadow:none!important}
#inicio .home-patient-table{font-size:12px!important}
#inicio .home-patient-table thead th{position:sticky!important;top:0;z-index:4;background:#edf3f9!important;padding:7px 8px!important;font-size:8.5px!important;letter-spacing:.055em!important}
#inicio .home-patient-table td{padding:6px 8px!important;vertical-align:middle!important}
#inicio .home-patient-table th:nth-child(1){width:5%!important}#inicio .home-patient-table th:nth-child(2){width:42%!important}#inicio .home-patient-table th:nth-child(3){width:18%!important}#inicio .home-patient-table th:nth-child(4){width:11%!important}#inicio .home-patient-table th:nth-child(5){width:24%!important}
#inicio .row-number{font-size:11px!important}.v478-home-table .patient-name-line>a{font-size:12px!important;line-height:1.15!important}.v478-home-table .new-patient-badge{font-size:7px!important;padding:2px 5px!important}.v478-home-table .service-badge{font-size:8.5px!important;padding:4px 7px!important}.v478-home-table .money-pill{font-size:9px!important;min-width:58px!important;padding:4px 6px!important}
.v478-home-actions{display:flex;align-items:center;justify-content:flex-end;gap:4px;white-space:nowrap}.v478-home-actions>button,.v478-more-summary{border:1px solid #dbe3ed!important;background:#fff!important;color:#425774!important;border-radius:8px!important;padding:5px 7px!important;font-size:8px!important;font-weight:800!important;min-height:27px!important;line-height:1!important}.v478-home-actions>button:hover,.v478-more-summary:hover{background:#f3f7fb!important}.v478-home-more{position:relative;display:inline-block}.v478-home-more>summary{list-style:none;cursor:pointer}.v478-home-more>summary::-webkit-details-marker{display:none}.v478-home-more-menu{display:none;position:absolute;right:0;top:31px;z-index:20;min-width:132px;padding:5px;border:1px solid #dbe3ed;border-radius:9px;background:#fff;box-shadow:0 8px 24px rgba(35,55,80,.15)}.v478-home-more[open] .v478-home-more-menu{display:block}.v478-home-more-menu button{width:100%;border:0;background:#fff4f3;color:#9a3f38;border-radius:7px;padding:7px 8px;font-size:8.5px;font-weight:850;text-align:left}.v478-home-more-menu button:hover{background:#ffe9e7}
#inicio .sub-visit-row td{padding-top:4px!important;padding-bottom:4px!important}.v478-home-table .sub-visit-label{font-size:9px!important}

/* Nueva atención — AGENDA grande y separación por jornada */
.modalbox.modalbox-wide.v477-attention-modalbox{width:min(820px,94vw)!important;padding:19px 21px 18px!important}
.v478-attention .v477-attention-top{margin-bottom:0!important}.v478-attention .v477-attention-top .modal-form-heading h2{font-size:21px!important}.v478-attention .attention-start-search .search{height:44px!important}
.v478-agenda-shell{border:1px solid #dce5ef;border-radius:14px;background:#fff;overflow:hidden}
.v478-agenda-brand{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:12px 14px;border-bottom:1px solid #dfe8f2;background:linear-gradient(90deg,#edf5ff,#f9fbfe)}
.v478-agenda-title{display:flex;align-items:baseline;gap:9px;min-width:0}.v478-agenda-title span{font-size:8px;font-weight:900;letter-spacing:.11em;color:#708098;white-space:nowrap}.v478-agenda-title strong{font-size:24px;line-height:1;color:#1d4f86;letter-spacing:-.025em}.v478-agenda-date{display:flex;align-items:center;gap:7px;flex-wrap:wrap;justify-content:flex-end}.v478-agenda-date b{font-size:10px;color:#344b69}.v478-agenda-date span{border:1px solid #cedced;background:#fff;border-radius:999px;padding:4px 7px;font-size:8.5px;font-weight:850;color:#536a86;white-space:nowrap}
.v478-shifts{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0}.v478-shift{min-width:0}.v478-shift+ .v478-shift{border-left:1px solid #e2e9f1}.v478-shift-head{display:flex;align-items:center;justify-content:space-between;padding:9px 12px;background:#fafbfd;border-bottom:1px solid #e7ecf2}.v478-shift-head b{font-size:10px;letter-spacing:.09em;color:#475d78}.v478-shift-head span{font-size:8px;font-weight:850;color:#74849a;background:#eef2f7;border-radius:999px;padding:3px 6px}.v478-shift-list{display:grid;gap:5px;padding:7px;align-content:start}.v478-shift .attention-week-row{grid-template-columns:48px minmax(0,1fr)!important;min-height:46px!important;padding:7px 9px!important;margin:0!important;border-radius:9px!important}.v478-shift .attention-week-time{font-size:11px!important}.v478-shift .attention-week-person b{font-size:10.5px!important}.v478-shift .attention-week-person small{font-size:8.5px!important}.v478-shift-empty{padding:18px 10px;text-align:center;font-size:9px;color:#8995a5}.v478-agenda-conflict{margin-left:6px;color:#995b16!important;background:#fff5e8!important;border-color:#f1d3a9!important}
@media(max-width:900px){#inicio .week-cards{grid-template-columns:repeat(2,minmax(0,1fr))!important}.v478-home-actions{flex-wrap:wrap}.v478-shifts{grid-template-columns:1fr}.v478-shift+.v478-shift{border-left:0;border-top:1px solid #e2e9f1}}
@media(max-width:620px){#inicio .week-cards{grid-template-columns:1fr!important}#inicio .v478-day-head{align-items:flex-start;flex-direction:column}.v478-agenda-brand{align-items:flex-start;flex-direction:column}.v478-agenda-date{justify-content:flex-start}.v478-agenda-title strong{font-size:21px}.v478-home-actions>button,.v478-more-summary{padding:5px 6px!important}}
"""
V478_REMIX_JS = r""";(()=>{
  if(window.__v478Remix)return;window.__v478Remix=true;
  const eh=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

  window.renderWeekCards=function(days){
    const totalPatients=(days||[]).reduce((s,d)=>s+Number(weeklyData[d.iso]?.count||0),0);
    const totalMoney=(days||[]).reduce((s,d)=>s+Number(weeklyData[d.iso]?.total||0),0);
    const box=$('#weekCards');if(!box)return;
    box.innerHTML=(days||[]).map(d=>{const info=weeklyData[d.iso]||{count:0,total:0};return `<button class="week-card v478-week-chip ${selectedHomeDate===d.iso?'active':''}" data-date="${d.iso}" onclick="selectHomeDay('${d.iso}')"><span class="week-day">${eh(d.label)}</span><strong class="v478-week-count">${Number(info.count||0)}</strong><span class="v478-week-meta">${fmtDate(d.iso)} · ${Number(info.count||0)===1?'paciente':'pacientes'}</span><span class="v478-week-total">${money(info.total||0)}</span></button>`}).join('')+`<div class="v478-week-total-card"><span>TOTAL SEMANA</span><strong>${totalPatients} ${totalPatients===1?'paciente':'pacientes'}</strong><b>${money(totalMoney)}</b></div>`;
    const old=$('#weekSummary');if(old)old.innerHTML='';
  };

  function homeActionIcon(kind){
    if(kind==='receipt')return '<svg class="v488-home-action-svg" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 3h12v18l-3-2-3 2-3-2-3 2V3z"></path><path d="M9 8h6M9 12h6M9 16h4"></path></svg>';
    if(kind==='print')return '<svg class="v488-home-action-svg" viewBox="0 0 24 24" aria-hidden="true"><path d="M7 8V3h10v5"></path><rect x="5" y="14" width="14" height="7" rx="1.5"></rect><path d="M5 16H3V9h18v7h-2"></path><circle cx="18" cy="11.5" r=".7"></circle></svg>';
    return '<svg class="v488-home-action-svg" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3M7 7l1 14h8l1-14M10 11v6M14 11v6"></path></svg>';
  }
  function homeMore(v){const id=Number(v?.id||0),fecha=String(v?.fecha||selectedHomeDate||'').slice(0,10);return `<button class="v486-home-delete" type="button" onclick="deleteVisitFromHome(${id},'${eh(fecha)}')">${homeActionIcon('trash')}<span>Borrar</span></button>`}
  function homeActions(g,fecha,primary){const hasConsultation=(g.visits||[]).some(v=>!String(v.procedimiento||'').trim());const pid=Number(g.patient?.id||0);return `<div class="v478-home-actions">${hasConsultation?`<button type="button" onclick="viewReceiptFromHome(${pid},'${eh(fecha)}')">${homeActionIcon('receipt')}<span>Ver recibo</span></button><button type="button" onclick="reprintReceiptFromHome(${pid},'${eh(fecha)}')">${homeActionIcon('print')}<span>Reimprimir</span></button>`:''}${homeMore(primary)}</div>`}
  function remasterHomeTable(rows){
    if(!rows?.length)return '<div class="panel muted empty-state">No hay pacientes registrados en este día.</div>';
    const groups=groupHomeVisits(rows);const head='<tr><th class="number-col">N.º</th><th>Paciente</th><th>Atención</th><th>Valor</th><th class="home-actions-col">Acciones</th></tr>';
    const body=groups.map((g,index)=>{const consultations=g.visits.filter(v=>!String(v.procedimiento||'').trim()),proceduresOnly=g.visits.filter(v=>String(v.procedimiento||'').trim()),primary=consultations[0]||proceduresOnly[0],extras=consultations.length?[...consultations.slice(1),...proceduresOnly]:proceduresOnly.slice(1),num=groups.length-index,fecha=String(primary?.fecha||selectedHomeDate||'').slice(0,10),main=`<tr class="patient-main-row"><td class="row-number" rowspan="${1+extras.length}">${num}.</td><td class="patient-cell" rowspan="${1+extras.length}">${patientNameCell(primary,true,g.isNew)}</td><td>${serviceBadge(primary)}</td><td class="money-cell"><span class="money-pill">${money(primary.valor)}</span></td><td class="home-action-cell">${homeActions(g,fecha,primary)}</td></tr>`,sub=extras.map(v=>`<tr class="sub-visit-row"><td><span class="sub-visit-label">↳</span> ${serviceBadge(v)}</td><td class="money-cell sub-money"><span class="money-pill subtle">${money(v.valor)}</span></td><td class="home-action-cell sub-actions"><div class="v478-home-actions">${homeMore(v)}</div></td></tr>`).join('');return main+sub}).join('');
    return `<table class="home-patient-table v478-home-table"><thead>${head}</thead><tbody>${body}</tbody></table>`;
  }

  window.renderHomeDayPayload=function(iso,d){
    if(!d)return;const label=d.label||weeklyData[iso]?.label||'Día',count=Number(d.count||0),today=toISO(new Date())===String(iso).slice(0,10),title=$('#selectedDayTitle');
    if(title)title.innerHTML=`<div class="v478-day-head"><div class="v478-day-head-main"><span class="v478-day-kicker">${today?'HOY':'DÍA SELECCIONADO'}</span><h2>${eh(label)} ${fmtDate(iso)}</h2></div><div class="v478-day-stats"><span>${count} ${count===1?'paciente':'pacientes'}</span><b>${money(d.total||0)}</b></div></div>`;
    const tableBox=$('#todayTable');if(tableBox){try{tableBox.innerHTML=remasterHomeTable(d.visits||[])}catch(err){console.error(err);tableBox.innerHTML='<div class="panel home-render-error">No se pudo dibujar este día.</div>'}tableBox.scrollLeft=0;tableBox.scrollTop=0}
  };

  function apptMinutes(row){const raw=String(row?.appointment?.hora||row?.staged?.hora||'00:00').slice(0,5),m=/^(\d{1,2}):(\d{2})$/.exec(raw);return m?Number(m[1])*60+Number(m[2]):0}
  function shiftBlock(title,rows){return `<section class="v478-shift"><div class="v478-shift-head"><b>${title}</b><span>${rows.length} ${rows.length===1?'cita':'citas'}</span></div><div class="v478-shift-list">${rows.length?rows.map(attentionWeekRow).join(''):'<div class="v478-shift-empty">Sin citas en esta jornada.</div>'}</div></section>`}
  window.renderAttentionWeek=function(d={}){
    const box=$('#attentionWeekCalendar');if(!box)return;const today=toISO(new Date()),days=d.days||[],day=days.find(x=>String(x?.date||'').slice(0,10)===today)||null;
    if(!day){box.innerHTML='<div class="attention-week-empty wide v477-no-clinic"><b>Hoy no hay consulta programada</b><span>Puedes buscar un paciente arriba para registrar una atención manualmente.</span></div>';return}
    const rows=day.appointments||[],morning=rows.filter(x=>apptMinutes(x)<14*60),afternoon=rows.filter(x=>apptMinutes(x)>=14*60),conflicts=rows.filter(x=>x?.conflict).length;
    box.innerHTML=`<div class="v478-agenda-shell"><div class="v478-agenda-brand"><div class="v478-agenda-title"><span>PACIENTES DE HOY</span><strong>AGENDA</strong></div><div class="v478-agenda-date"><b>${eh(day.label)} · ${fmtDate(day.date)}</b><span>${rows.length} ${rows.length===1?'cita':'citas'}</span>${conflicts?`<span class="v478-agenda-conflict">⚠ ${conflicts} duplicada${conflicts===1?'':'s'}</span>`:''}</div></div><div class="v478-shifts">${shiftBlock('MAÑANA',morning)}${shiftBlock('TARDE',afternoon)}</div></div>`;
  };

  window.newAttention=async function(){
    currentPatientSource='general';attentionSearchSeq++;attentionWeekAnchor=toISO(new Date());
    openModal(`<div class="new-attention-start-modal v477-attention-remaster v478-attention"><div class="v477-attention-top"><div class="modal-form-heading"><h2>Nueva atención</h2><p>Selecciona un paciente de la agenda de hoy o búscalo por sus datos.</p></div><button class="primary v477-new-patient-btn" onclick="newPatient(true)">＋ Paciente nuevo</button></div><div class="attention-start-search"><label for="aSearch">Buscar paciente</label><input id="aSearch" class="search uppercase-search" autocomplete="off" autocapitalize="characters" spellcheck="false" placeholder="Cédula, apellidos y nombres, celular o correo" oninput="upperSearchInput(this);attentionSearch()"></div><div id="attentionWeekBlock" class="attention-week-block"><div id="attentionWeekCalendar" class="attention-week-calendar"><div class="attention-week-loading">Cargando agenda de hoy…</div></div></div><div id="aResults" class="results attention-results hidden"></div></div>`);
    requestAnimationFrame(()=>document.querySelector('#modal .modalbox')?.classList.add('v477-attention-modalbox'));
    loadAttentionWeek(false,attentionWeekAnchor);setTimeout(()=>$('#aSearch')?.focus(),0);
  };
})();"""
V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\n" + V478_REMIX_CSS
V460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\n" + V478_REMIX_JS

V479_POLISH_CSS = r"""
/* v4.3.79 — pulido Agenda + Facturación inteligente */
.v478-agenda-brand{position:relative!important;padding:11px 14px 11px 17px!important;background:#eef6ff!important;border-bottom:1px solid #d7e6f6!important}
.v478-agenda-brand:before{content:'';position:absolute;left:0;top:0;bottom:0;width:4px;background:#4e86c5}
.v478-agenda-title{gap:8px!important;align-items:center!important}
.v478-agenda-title span{display:none!important}
.v478-agenda-title strong{font-size:15px!important;line-height:1.15!important;color:#285f98!important;letter-spacing:.005em!important;font-weight:900!important}
.v478-agenda-date b{font-size:10px!important;color:#405774!important}.v478-agenda-date span{background:#fff!important;border-color:#cbdced!important;color:#426383!important}
.v478-shift-head{background:#fbfcfe!important}.v478-shift:first-child .v478-shift-head{box-shadow:inset 3px 0 0 #e4ad45}.v478-shift:last-child .v478-shift-head{box-shadow:inset 3px 0 0 #6c8fca}

#facturacion .billing-summary{grid-template-columns:repeat(3,minmax(0,1fr))!important}
#facturacion .billing-summary.v479-no-reject{grid-template-columns:repeat(2,minmax(0,1fr))!important}
#facturacion .billing-summary.v479-no-reject>button{width:100%!important;min-width:0!important}
#facturacion .billing-summary>button.v479-rejected{border-color:#efc7c4!important;background:#fff8f7!important;color:#874743!important}
#facturacion .billing-summary>button.v479-rejected b{color:#a24d47!important}
@media(max-width:760px){#facturacion .billing-summary,#facturacion .billing-summary.v479-no-reject{grid-template-columns:1fr!important}}
"""
V479_POLISH_JS = r""";(()=>{
 if(window.__v479Polish)return;window.__v479Polish=true;
 const norm=v=>String(v||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/\s+/g,' ').trim().toLowerCase();
 function polishAgenda(){
   const title=document.querySelector('.v478-agenda-title strong');
   if(title)title.textContent='Agenda de hoy';
 }
 function billingSummary(){
   const box=document.querySelector('#billingSummary');if(!box)return;
   const buttons=[...box.querySelectorAll(':scope > button')];
   const rejected=buttons.find(b=>norm(b.textContent).includes('rechaz'));
   if(!rejected){box.classList.add('v479-no-reject');return}
   rejected.classList.add('v479-rejected');
   const numNode=rejected.querySelector('b,strong');
   const raw=(numNode?.textContent||rejected.textContent||'').match(/\d+/);
   const count=raw?Number(raw[0]):0;
   rejected.style.display=count>0?'':'none';
   box.classList.toggle('v479-no-reject',count<=0);
 }
 const oldRender=window.renderAttentionWeek;
 if(typeof oldRender==='function')window.renderAttentionWeek=function(d){const r=oldRender.apply(this,arguments);polishAgenda();return r};
 const oldLoad=window.loadBilling;
 if(typeof oldLoad==='function')window.loadBilling=async function(){const r=await oldLoad.apply(this,arguments);billingSummary();return r};
 const oldSet=window.setBillingStatus;
 if(typeof oldSet==='function')window.setBillingStatus=async function(){const r=await oldSet.apply(this,arguments);billingSummary();return r};
 function boot(){polishAgenda();billingSummary()}
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(boot,40),{once:true});else setTimeout(boot,40);
 setTimeout(boot,400);
})();"""
V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\n" + V479_POLISH_CSS
V460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\n" + V479_POLISH_JS

V480_POLISH_CSS = r"""
/* v4.3.80 — Inicio más legible + resumen semanal separado + rechazadas condicional */
#inicio .week-cards{grid-template-columns:repeat(3,minmax(0,1fr))!important;gap:10px!important;margin-bottom:7px!important}
#inicio .week-card.v478-week-chip{min-height:67px!important;padding:11px 13px!important}
#inicio .v478-week-chip .week-day{font-size:14px!important;line-height:1.15!important}
#inicio .v478-week-chip .v478-week-count{font-size:23px!important}
#inicio .v478-week-chip .v478-week-meta{font-size:10px!important}
#inicio .v478-week-chip .v478-week-total{font-size:11.5px!important}
#inicio #weekSummary{display:flex!important;justify-content:flex-end!important;margin:0 0 10px!important;padding:0!important;background:transparent!important;border:0!important}
#inicio .v480-week-summary{min-width:285px;display:grid;grid-template-columns:1fr auto;grid-template-areas:'label money' 'patients money';align-items:center;gap:2px 18px;padding:9px 13px;border:1px solid #d8e3ef;border-radius:11px;background:#f4f7fb;box-shadow:none}
#inicio .v480-week-summary span{grid-area:label;font-size:9px;font-weight:900;letter-spacing:.1em;color:#6d7e94;text-transform:uppercase}
#inicio .v480-week-summary strong{grid-area:patients;font-size:11.5px;color:#344b68}
#inicio .v480-week-summary b{grid-area:money;font-size:17px;color:#214f84;white-space:nowrap}
#inicio .v478-week-total-card{display:none!important}
#inicio .v478-day-head h2{font-size:19px!important}
#inicio .v478-day-kicker{font-size:9px!important}
#inicio .v478-day-stats span,#inicio .v478-day-stats b{font-size:10px!important;padding:5px 9px!important}
#inicio .home-patient-table{font-size:13px!important}
#inicio .home-patient-table thead th{font-size:9.5px!important;padding:8px 9px!important}
#inicio .home-patient-table td{padding:7px 9px!important}
#inicio .row-number{font-size:12px!important}
.v478-home-table .patient-name-line>a{font-size:13.5px!important;line-height:1.18!important}
.v478-home-table .new-patient-badge{font-size:8px!important;padding:3px 6px!important}
.v478-home-table .service-badge{font-size:9.5px!important;padding:4px 8px!important}
.v478-home-table .money-pill{font-size:10px!important;min-width:62px!important;padding:5px 7px!important}
.v478-home-actions>button,.v478-more-summary{font-size:9px!important;padding:6px 8px!important;min-height:29px!important}
.v478-home-more-menu button{font-size:9px!important}
.v478-home-table .sub-visit-label{font-size:10px!important}

/* Rechazadas en cero: se elimina físicamente del layout, aunque cambie la etiqueta HTML. */
#facturacion #billingSummary [data-v480-zero-rejected="1"]{display:none!important}
#facturacion .billing-summary.v480-two-cards{grid-template-columns:repeat(2,minmax(0,1fr))!important}
#facturacion .billing-summary.v480-two-cards>*{min-width:0!important;width:100%!important}
#facturacion .billing-summary.v480-three-cards{grid-template-columns:repeat(3,minmax(0,1fr))!important}
@media(max-width:760px){#facturacion .billing-summary.v480-two-cards,#facturacion .billing-summary.v480-three-cards{grid-template-columns:1fr!important}#inicio .week-cards{grid-template-columns:1fr!important}#inicio .v480-week-summary{width:100%;min-width:0}}
"""
V480_POLISH_JS = r""";(()=>{
 if(window.__v480Polish)return;window.__v480Polish=true;
 const norm=v=>String(v||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/\s+/g,' ').trim().toLowerCase();
 const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 let billingGuard=false,observer=null;

 window.renderWeekCards=function(days){
   const data=days||[],totalPatients=data.reduce((s,d)=>s+Number(weeklyData[d.iso]?.count||0),0),totalMoney=data.reduce((s,d)=>s+Number(weeklyData[d.iso]?.total||0),0);
   const box=$('#weekCards');if(!box)return;
   box.innerHTML=data.map(d=>{const info=weeklyData[d.iso]||{count:0,total:0};return `<button class="week-card v478-week-chip ${selectedHomeDate===d.iso?'active':''}" data-date="${d.iso}" onclick="selectHomeDay('${d.iso}')"><span class="week-day">${esc(d.label)}</span><strong class="v478-week-count">${Number(info.count||0)}</strong><span class="v478-week-meta">${fmtDate(d.iso)} · ${Number(info.count||0)===1?'paciente':'pacientes'}</span><span class="v478-week-total">${money(info.total||0)}</span></button>`}).join('');
   const summary=$('#weekSummary');if(summary)summary.innerHTML=`<div class="v480-week-summary"><span>Resumen semanal</span><strong>${totalPatients} ${totalPatients===1?'paciente':'pacientes'}</strong><b>${money(totalMoney)}</b></div>`;
 };

 function extractCount(el){
   if(!el)return 0;
   const candidates=[...el.querySelectorAll('b,strong,[class*="count"],[class*="number"],[class*="value"]'),el];
   for(const node of candidates){const m=String(node?.textContent||'').trim().match(/(^|\s)(\d+)(\s|$)/);if(m)return Number(m[2]||0)}
   const m=String(el.textContent||'').match(/\d+/);return m?Number(m[0]):0;
 }
 function polishBillingSummary(){
   if(billingGuard)return;billingGuard=true;
   try{
     const box=document.querySelector('#billingSummary');if(!box)return;
     const children=[...box.children];let rejected=null;
     for(const el of children){if(norm(el.textContent).includes('rechaz')){rejected=el;break}}
     let count=0;
     if(rejected){count=extractCount(rejected);if(count<=0)rejected.setAttribute('data-v480-zero-rejected','1');else rejected.removeAttribute('data-v480-zero-rejected')}
     const visible=children.filter(el=>el!==rejected||count>0);
     box.classList.toggle('v480-two-cards',visible.length===2);
     box.classList.toggle('v480-three-cards',visible.length>=3);
     box.classList.toggle('v479-no-reject',!!rejected&&count<=0);
   }finally{billingGuard=false}
 }
 function observeBilling(){
   const box=document.querySelector('#billingSummary');if(!box||box.dataset.v480Observed==='1')return;
   box.dataset.v480Observed='1';observer=new MutationObserver(()=>queueMicrotask(polishBillingSummary));observer.observe(box,{childList:true,subtree:true,characterData:true});polishBillingSummary();
 }
 const oldLoad=window.loadBilling;if(typeof oldLoad==='function')window.loadBilling=async function(){const r=await oldLoad.apply(this,arguments);observeBilling();polishBillingSummary();return r};
 const oldSet=window.setBillingStatus;if(typeof oldSet==='function')window.setBillingStatus=async function(){const r=await oldSet.apply(this,arguments);observeBilling();polishBillingSummary();return r};
 function boot(){observeBilling();polishBillingSummary()}
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(boot,40),{once:true});else setTimeout(boot,40);
 setTimeout(boot,300);setTimeout(boot,1000);
})();"""
V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\n" + V480_POLISH_CSS
V460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\n" + V480_POLISH_JS

V481_PATIENT_CSS = r"""
/* v4.3.81 — Remaster completo de Paciente nuevo */
#modal .modalbox.v481-patient-modal{width:min(780px,94vw)!important;max-height:92vh!important;padding:20px 22px 18px!important;border-radius:18px!important;overflow:auto!important}
.v481-patient-modal .v481-remastered-form{display:grid!important;gap:12px!important}
.v481-patient-modal .modal-form-heading{margin-bottom:2px!important;padding-right:38px!important}
.v481-patient-modal .modal-form-heading h2{font-size:23px!important;letter-spacing:-.015em!important;margin-bottom:3px!important}
.v481-patient-modal .modal-form-heading p{font-size:10.5px!important;color:#6e7f94!important;margin:0!important}
.v481-section{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px 12px;padding:12px 13px;border:1px solid #dce5ef;border-radius:14px;background:#fbfcfe}
.v481-section.v481-identity{background:#f8fbff;border-color:#d6e4f4}
.v481-section.v481-contact{background:#fbfcfe}
.v481-section-head{grid-column:1/-1;display:flex;align-items:end;justify-content:space-between;gap:12px;padding-bottom:7px;margin-bottom:1px;border-bottom:1px solid #e5ebf2}
.v481-section-head div{display:grid;gap:1px}.v481-section-head b{font-size:9px;letter-spacing:.11em;color:#3c5f86}.v481-section-head span{font-size:9px;color:#7b899b}.v481-section-head .v481-section-icon{width:28px;height:28px;border-radius:9px;display:grid;place-items:center;background:#eaf3fd;color:#2f679e;font-size:14px}
.v481-patient-modal label,.v481-patient-modal .field,.v481-patient-modal .form-field,.v481-patient-modal .form-group{min-width:0}
.v481-patient-modal label{font-size:10px!important;color:#53667e!important;font-weight:800!important}
.v481-patient-modal input:not([type="checkbox"]),.v481-patient-modal textarea,.v481-patient-modal select{width:100%!important;min-height:43px!important;border-radius:11px!important;padding:9px 11px!important;font-size:12.5px!important;background:#fff!important}
.v481-patient-modal textarea{min-height:72px!important;resize:vertical!important}
.v481-role-name{grid-column:1/-1!important}.v481-role-name input{font-size:14px!important;font-weight:800!important;text-transform:uppercase!important;letter-spacing:.01em!important}
.v481-role-id{grid-column:1/-1!important}.v481-role-id input{font-size:14px!important;font-weight:850!important;letter-spacing:.035em!important}
.v481-role-foreign{grid-column:1/-1!important;padding:2px 1px!important}.v481-role-foreign label,.v481-role-foreign{font-size:9.5px!important}
.v481-id-status{grid-column:1/-1;display:flex;align-items:center;gap:7px;min-height:31px;padding:7px 9px;border-radius:10px;border:1px solid #e0e7ef;background:#fff;color:#68798f;font-size:9.5px;font-weight:800}
.v481-id-status.ok{border-color:#b9dfc9;background:#f2fbf6;color:#237247}.v481-id-status.bad{border-color:#ecc4c0;background:#fff6f5;color:#9a4a43}.v481-id-status.foreign{border-color:#cbd9ec;background:#f4f8fd;color:#446687}
.v481-age-pill{display:inline-flex;align-items:center;margin-top:5px;padding:3px 7px;border-radius:999px;background:#edf4fb;color:#3f6388;font-size:8.5px;font-weight:850}
.v481-field-invalid input{border-color:#d7847d!important;box-shadow:0 0 0 2px rgba(190,75,65,.08)!important}.v481-inline-error{display:block;margin-top:4px;font-size:8.5px;color:#a44d45;font-weight:750}
.v481-duplicate-card{grid-column:1/-1;display:none;align-items:flex-start;justify-content:space-between;gap:12px;padding:10px 11px;border-radius:11px;border:1px solid #edd1a9;background:#fff9ef;color:#74521f}.v481-duplicate-card.show{display:flex}.v481-duplicate-card.danger{border-color:#e9bbb7;background:#fff5f4;color:#873f39}.v481-duplicate-card .copy{display:grid;gap:2px;min-width:0}.v481-duplicate-card b{font-size:10.5px}.v481-duplicate-card span{font-size:9px;line-height:1.3}.v481-duplicate-card button{flex:0 0 auto;border:1px solid currentColor;background:#fff;border-radius:8px;padding:6px 8px;font-size:8.5px;font-weight:850;cursor:pointer}
.v481-more-details{border:1px solid #dfe6ee;border-radius:12px;background:#fafbfd;overflow:hidden}.v481-more-details>summary{cursor:pointer;list-style:none;padding:10px 12px;font-size:9.5px;font-weight:900;color:#536981;display:flex;align-items:center;justify-content:space-between}.v481-more-details>summary::-webkit-details-marker{display:none}.v481-more-details>summary:after{content:'Abrir';font-size:8px;color:#77879a}.v481-more-details[open]>summary:after{content:'Ocultar'}.v481-more-body{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px 12px;padding:0 12px 12px}.v481-role-notes{grid-column:1/-1!important}
.v481-patient-modal .actions,.v481-patient-modal .form-actions,.v481-patient-modal .modal-actions{position:sticky;bottom:-18px;z-index:5;margin:4px -2px -1px!important;padding:10px 2px 1px!important;background:linear-gradient(to bottom,rgba(255,255,255,.82),#fff 32%)!important;display:flex!important;justify-content:flex-end!important;gap:7px!important}.v481-create-btn{min-width:145px!important;min-height:39px!important;border-radius:10px!important;font-size:10.5px!important;font-weight:900!important}.v481-create-btn:disabled{opacity:.48!important;cursor:not-allowed!important}
@media(max-width:680px){#modal .modalbox.v481-patient-modal{width:94vw!important;padding:17px!important}.v481-section,.v481-more-body{grid-template-columns:1fr}.v481-role-name,.v481-role-id,.v481-role-foreign,.v481-role-notes{grid-column:1!important}.v481-duplicate-card{flex-direction:column}.v481-section-head{align-items:flex-start}}
"""
V481_PATIENT_JS = r""";(()=>{
 if(window.__v481PatientRemaster)return;window.__v481PatientRemaster=true;
 const norm=v=>String(v||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/\s+/g,' ').trim().toLowerCase();
 const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const digits=v=>String(v||'').replace(/\D/g,'');
 let installTries=0;

 function ecuadorPhone(v){const d=digits(v);if(d.startsWith('593')&&d.length===12)return '0'+d.slice(3);return d}
 function validEcuadorCedula(value){
   const d=digits(value);if(d.length!==10)return false;
   const province=Number(d.slice(0,2)),third=Number(d[2]);if(province<1||province>24||third>=6)return false;
   let sum=0;for(let i=0;i<9;i++){let n=Number(d[i])*(i%2===0?2:1);if(n>9)n-=9;sum+=n}
   const check=(10-(sum%10))%10;return check===Number(d[9]);
 }
 function labelText(el){
   const id=el.id||'';const direct=el.closest('label');
   const byFor=id?[...document.querySelectorAll('label[for]')].find(l=>l.htmlFor===id):null;
   return norm([el.name,el.id,el.placeholder,el.getAttribute('aria-label'),direct?.textContent,byFor?.textContent].filter(Boolean).join(' '));
 }
 function field(root,words,type){
   const els=[...root.querySelectorAll('input,textarea,select')].filter(x=>!['button','submit','hidden'].includes(String(x.type||'').toLowerCase()));
   if(type){const exact=els.find(x=>String(x.type||'').toLowerCase()===type&&words.some(w=>labelText(x).includes(w)));if(exact)return exact}
   return els.find(x=>words.some(w=>labelText(x).includes(w)))||null;
 }
 function wrap(el,root){
   if(!el)return null;
   const w=el.closest('label,.field,.form-field,.form-group,.input-group,.control');
   if(w&&w!==root&&root.contains(w))return w;
   const p=el.parentElement;return p&&p!==root?p:el;
 }
 function topUnique(list){
   const x=[...new Set(list.filter(Boolean))];return x.filter(a=>!x.some(b=>a!==b&&b.contains(a)));
 }
 function heading(title,subtitle,icon){const h=document.createElement('div');h.className='v481-section-head';h.innerHTML=`<div><b>${esc(title)}</b><span>${esc(subtitle)}</span></div><span class="v481-section-icon">${icon}</span>`;return h}
 function makeSection(parent,before,title,subtitle,icon,wrappers,cls){
   wrappers=topUnique(wrappers).filter(w=>w.parentElement===parent);if(!wrappers.length)return null;
   const s=document.createElement('section');s.className='v481-section '+cls;s.appendChild(heading(title,subtitle,icon));parent.insertBefore(s,before||wrappers[0]);wrappers.forEach(w=>s.appendChild(w));return s;
 }
 async function searchPatients(q){
   try{
     if(!q)return [];
     const url=`/api/patients?q=${encodeURIComponent(q)}&limit=12`;
     let d;
     if(typeof window.api==='function')d=await window.api(url);else{const r=await fetch(url,{credentials:'same-origin'});if(!r.ok)return [];d=await r.json()}
     return Array.isArray(d)?d:(Array.isArray(d?.items)?d.items:(Array.isArray(d?.patients)?d.patients:(Array.isArray(d?.results)?d.results:[])));
   }catch(_e){return []}
 }
 function patientCore(x){return x?.patient&&typeof x.patient==='object'?x.patient:x||{}}
 function patientName(x){const p=patientCore(x);return String(p.nombre||p.name||'Paciente registrado')}
 function patientPhone(x){const p=patientCore(x);return String(p.celular||p.phone||'')}
 function patientCedula(x){const p=patientCore(x);return String(p.cedula||p.identificacion||'')}
 function patientDate(x){const p=patientCore(x);return String(x?.last_visit_date||p.last_visit_date||p.ultima_atencion||'')}
 function ageFromISO(v){
   const m=/^(\d{4})-(\d{2})-(\d{2})/.exec(String(v||''));if(!m)return null;
   const b=new Date(Number(m[1]),Number(m[2])-1,Number(m[3]));if(Number.isNaN(b.getTime()))return null;
   const t=new Date();let a=t.getFullYear()-b.getFullYear();if(t.getMonth()<b.getMonth()||(t.getMonth()===b.getMonth()&&t.getDate()<b.getDate()))a--;return a>=0&&a<130?a:null;
 }
 function findActionButton(root){return [...root.querySelectorAll('button')].reverse().find(b=>/guardar|crear paciente|registrar paciente/.test(norm(b.textContent)))||null}

 function remaster(fromAttention){
   const modal=document.querySelector('#modal .modalbox');if(!modal||modal.dataset.v481Patient==='1')return;
   const name=field(modal,['apellidos y nombres','nombre completo','nombre','paciente']);
   const cedula=field(modal,['cedula','identificacion']);
   if(!name||!cedula)return;
   modal.dataset.v481Patient='1';modal.classList.add('v481-patient-modal');
   const root=name.closest('form')||cedula.closest('form')||name.parentElement?.parentElement||modal;
   root.classList.add('v481-remastered-form');
   const birth=field(modal,['fecha de nacimiento','nacimiento'],'date');
   const phone=field(modal,['celular','telefono','whatsapp']);
   const email=field(modal,['correo','email']);
   const place=field(modal,['lugar','ciudad','direccion']);
   const notes=field(modal,['notas','observacion']);
   const foreign=field(modal,['extranjero','extranjera'],'checkbox')||[...modal.querySelectorAll('input[type="checkbox"]')].find(x=>labelText(x).includes('extranj'))||null;
   const wId=wrap(cedula,root),wName=wrap(name,root),wBirth=wrap(birth,root),wForeign=wrap(foreign,root),wPhone=wrap(phone,root),wEmail=wrap(email,root),wPlace=wrap(place,root),wNotes=wrap(notes,root);
   [[wId,'v481-role-id'],[wName,'v481-role-name'],[wBirth,'v481-role-birth'],[wForeign,'v481-role-foreign'],[wPhone,'v481-role-phone'],[wEmail,'v481-role-email'],[wPlace,'v481-role-place'],[wNotes,'v481-role-notes']].forEach(([w,c])=>w?.classList?.add(c));
   const commonParent=wName?.parentElement===wId?.parentElement?wName.parentElement:root;
   if(commonParent&&commonParent!==modal){
     const idWrappers=topUnique([wId,wForeign,wName,wBirth]).filter(w=>w?.parentElement===commonParent);
     if(idWrappers.length){makeSection(commonParent,idWrappers[0],'IDENTIDAD','Datos principales del paciente','ID',idWrappers,'v481-identity')}
     const contactWrappers=topUnique([wPhone,wEmail]).filter(w=>w?.parentElement===commonParent);
     if(contactWrappers.length){makeSection(commonParent,contactWrappers[0],'CONTACTO','Información para comunicarnos con el paciente','☎',contactWrappers,'v481-contact')}
     const extras=topUnique([wPlace,wNotes]).filter(w=>w?.parentElement===commonParent);
     if(extras.length){
       const det=document.createElement('details');det.className='v481-more-details';if(extras.some(w=>w.querySelector('input,textarea')?.value))det.open=true;
       const sum=document.createElement('summary');sum.textContent='＋ Más datos';const body=document.createElement('div');body.className='v481-more-body';det.append(sum,body);commonParent.insertBefore(det,extras[0]);extras.forEach(w=>body.appendChild(w));
     }
   }
   const idSection=modal.querySelector('.v481-identity')||wId?.parentElement;
   const idStatus=document.createElement('div');idStatus.className='v481-id-status';idStatus.textContent='Ingresa la cédula para validarla localmente.';
   const duplicate=document.createElement('div');duplicate.className='v481-duplicate-card';duplicate.innerHTML='<div class="copy"><b></b><span></span></div>';
   if(idSection){idSection.appendChild(idStatus);idSection.appendChild(duplicate)}
   let agePill=null;if(birth&&wBirth){agePill=document.createElement('span');agePill.className='v481-age-pill';agePill.textContent='Edad —';wBirth.appendChild(agePill)}
   let emailError=null;if(email&&wEmail){emailError=document.createElement('small');emailError.className='v481-inline-error';emailError.textContent='Correo no válido';emailError.style.display='none';wEmail.appendChild(emailError)}
   const save=findActionButton(modal);const initialSaveLabel=norm(save?.textContent);const headingText=norm(modal.querySelector('.modal-form-heading h2,h1,h2,h3')?.textContent||'');const editMode=!!window.__v485EditingPatientId||/editar|completar/.test(headingText)||/guardar cambios|actualizar/.test(initialSaveLabel);if(save){save.classList.add('v481-create-btn');if(!editMode&&/guardar|registrar/.test(norm(save.textContent)))save.textContent='Crear paciente'}
   const state={duplicateCedula:false,phoneDuplicate:false,seqId:0,seqPhone:0};
   function showDup(kind,p){
     if(!p){duplicate.classList.remove('show','danger');duplicate.querySelector('b').textContent='';duplicate.querySelector('span').textContent='';duplicate.querySelector('button')?.remove();return}
     const nm=patientName(p),ph=patientPhone(p),last=patientDate(p);duplicate.classList.add('show');duplicate.classList.toggle('danger',kind==='cedula');
     duplicate.querySelector('b').textContent=kind==='cedula'?'⚠ Este paciente ya está registrado':'⚠ Este celular ya está registrado';
     duplicate.querySelector('span').textContent=`${nm}${ph?' · '+ph:''}${last?' · Última atención: '+String(last).slice(0,10):''}`;
     duplicate.querySelector('button')?.remove();if(kind==='cedula'&&fromAttention&&typeof window.newAttention==='function'){const b=document.createElement('button');b.type='button';b.textContent='Volver a buscarlo';b.onclick=()=>window.newAttention();duplicate.appendChild(b)}
   }
   function updateAge(){if(!agePill)return;const a=ageFromISO(birth?.value);agePill.textContent=a===null?'Edad —':`Edad: ${a} año${a===1?'':'s'}`}
   function updateStatus(){
     const foreignOn=!!foreign?.checked,raw=String(cedula.value||'').trim(),d=digits(raw);
     idStatus.className='v481-id-status';
     if(foreignOn){idStatus.classList.add('foreign');idStatus.textContent='Identificación extranjera · no se aplica validación ecuatoriana.'}
     else if(!raw){idStatus.textContent='Ingresa la cédula para validarla localmente.'}
     else if(d.length<10){idStatus.textContent=`Cédula ecuatoriana · ${d.length}/10 dígitos`}
     else if(validEcuadorCedula(d)){idStatus.classList.add('ok');idStatus.textContent='✓ Cédula ecuatoriana válida'}
     else{idStatus.classList.add('bad');idStatus.textContent='✕ La cédula no pasa la validación ecuatoriana'}
   }
   function emailOk(){if(!email||!String(email.value||'').trim())return true;return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/i.test(String(email.value||'').trim())}
   function updateSave(){
     if(!save)return;const foreignOn=!!foreign?.checked,raw=String(cedula.value||'').trim(),idOk=foreignOn||!raw||validEcuadorCedula(raw),mailOk=emailOk(),required=[...modal.querySelectorAll('input[required],textarea[required],select[required]')].every(x=>String(x.value||'').trim());
     wEmail?.classList.toggle('v481-field-invalid',!mailOk);if(emailError)emailError.style.display=mailOk?'none':'block';
     save.disabled=!String(name.value||'').trim()||!idOk||!mailOk||!required||(!editMode&&state.duplicateCedula);
   }
   async function checkCedula(){
     if(editMode){state.duplicateCedula=false;if(!state.phoneDuplicate)showDup(null,null);updateSave();return}
     const q=digits(cedula.value);state.duplicateCedula=false;if(foreign?.checked||q.length!==10||!validEcuadorCedula(q)){if(!state.phoneDuplicate)showDup(null,null);updateSave();return}
     const seq=++state.seqId,rows=await searchPatients(q);if(seq!==state.seqId)return;const hit=rows.find(x=>digits(patientCedula(x))===q)||null;state.duplicateCedula=!!hit;if(hit)showDup('cedula',hit);else if(!state.phoneDuplicate)showDup(null,null);updateSave();
   }
   async function checkPhone(){
     if(!phone)return;if(editMode){state.phoneDuplicate=false;if(!state.duplicateCedula)showDup(null,null);return}
const q=ecuadorPhone(phone.value);state.phoneDuplicate=false;if(q.length<9){if(!state.duplicateCedula)showDup(null,null);return}
     const seq=++state.seqPhone,rows=await searchPatients(q);if(seq!==state.seqPhone)return;const hit=rows.find(x=>ecuadorPhone(patientPhone(x))===q)||null;state.phoneDuplicate=!!hit;if(!state.duplicateCedula){if(hit)showDup('phone',hit);else showDup(null,null)}
   }
   let idTimer=0,phoneTimer=0;
   cedula.addEventListener('input',()=>{updateStatus();updateSave();clearTimeout(idTimer);idTimer=setTimeout(checkCedula,260)});
   cedula.addEventListener('blur',checkCedula);
   foreign?.addEventListener('change',()=>{state.duplicateCedula=false;updateStatus();updateSave();checkCedula()});
   name.addEventListener('input',()=>{const s=name.selectionStart,e=name.selectionEnd;name.value=String(name.value||'').toUpperCase();try{name.setSelectionRange(s,e)}catch(_e){}updateSave()});
   birth?.addEventListener('change',updateAge);birth?.addEventListener('input',updateAge);
   email?.addEventListener('input',updateSave);
   phone?.addEventListener('input',()=>{clearTimeout(phoneTimer);phoneTimer=setTimeout(checkPhone,340)});phone?.addEventListener('blur',()=>{const d=digits(phone.value);if(d.startsWith('593')&&d.length===12)phone.value='0'+d.slice(3);checkPhone()});
   updateAge();updateStatus();updateSave();setTimeout(checkCedula,50);if(phone?.value)setTimeout(checkPhone,80);
 }
 function install(){
   if(window.newPatient&&window.newPatient.__v481Wrapped)return true;
   if(typeof window.newPatient!=='function')return false;
   const base=window.newPatient;const wrapped=function(...args){const r=base.apply(this,args);const fromAttention=!!args[0];requestAnimationFrame(()=>remaster(fromAttention));setTimeout(()=>remaster(fromAttention),40);if(r&&typeof r.then==='function')r.finally(()=>setTimeout(()=>remaster(fromAttention),0));return r};wrapped.__v481Wrapped=true;window.v481RemasterPatient=remaster;window.newPatient=wrapped;return true;
 }
 function boot(){if(install())return;if(++installTries<12)setTimeout(boot,120)}
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();setTimeout(boot,350);
})();"""
V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\n" + V481_PATIENT_CSS
V460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\n" + V481_PATIENT_JS

V482_HOTFIX_CSS = r"""
/* v4.3.82 — recupera emisión por lotes + remaster persistente de Paciente nuevo */
#facturacion .v482-quick-head{position:relative!important;padding-right:170px!important;min-height:42px!important}
#facturacion .v482-batch-btn{position:absolute!important;right:0!important;top:0!important;display:inline-flex!important;align-items:center!important;justify-content:center!important;gap:6px!important;min-height:36px!important;padding:8px 12px!important;border:1px solid #8eb3dc!important;border-radius:10px!important;background:#edf5ff!important;color:#245785!important;font-size:10px!important;font-weight:900!important;cursor:pointer!important;white-space:nowrap!important}
#facturacion .v482-batch-btn:hover{background:#e2effd!important}
#facturacion .v482-batch-btn[hidden]{display:none!important}
@media(max-width:720px){#facturacion .v482-quick-head{padding-right:0!important;padding-bottom:46px!important}#facturacion .v482-batch-btn{left:0!important;right:auto!important;top:auto!important;bottom:4px!important}}
"""
V482_HOTFIX_JS = r""";(()=>{
 if(window.__v482Hotfix)return;window.__v482Hotfix=true;
 const norm=v=>String(v||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/\s+/g,' ').trim().toLowerCase();
 let guard=false;
 function readPending(){
   const box=document.querySelector('#billingSummary');if(!box)return 0;
   const el=[...box.children].find(x=>{const t=norm(x.textContent);return t.includes('por emitir')||t.includes('pendiente')});
   if(!el)return 0;const m=String(el.textContent||'').match(/\d+/);return m?Number(m[0]):0;
 }
 function ensureBatchButton(){
   const sec=document.querySelector('#facturacion');if(!sec)return;
   const nodes=[...sec.querySelectorAll('h2,h3,h4,b,strong,p,div')];
   const title=nodes.find(x=>norm(x.textContent)==='accion rapida')||nodes.find(x=>norm(x.textContent).startsWith('accion rapida'));
   if(!title)return;
   const host=title.parentElement;if(!host)return;host.classList.add('v482-quick-head');
   let btn=document.querySelector('#v482BatchEmit');
   if(!btn){btn=document.createElement('button');btn.id='v482BatchEmit';btn.type='button';btn.className='v482-batch-btn';btn.innerHTML='⚡ Emitir por lotes';btn.addEventListener('click',async()=>{if(typeof window.emitAllPendingInvoices==='function')await window.emitAllPendingInvoices();else alert('La emisión por lotes no está disponible.');});host.appendChild(btn)}
   btn.hidden=readPending()<2;
 }
 function patientFieldsPresent(modal){
   if(!modal)return false;const t=norm(modal.textContent);
   const inputs=[...modal.querySelectorAll('input,textarea')];
   const id=inputs.some(x=>/cedula|identificacion/.test(norm([x.name,x.id,x.placeholder,x.getAttribute('aria-label')].join(' '))))||t.includes('cedula o identificacion');
   const name=inputs.some(x=>/nombre/.test(norm([x.name,x.id,x.placeholder,x.getAttribute('aria-label')].join(' '))))||t.includes('apellidos y nombres');
   return id&&name;
 }
 function ensurePatientRemaster(){
   if(guard)return;const modal=document.querySelector('#modal .modalbox');if(!patientFieldsPresent(modal))return;
   if(modal.querySelector('.v481-section')&&modal.querySelector('.v481-remastered-form'))return;
   if(typeof window.v481RemasterPatient!=='function')return;
   guard=true;
   try{delete modal.dataset.v481Patient;modal.classList.remove('v481-patient-modal');window.v481RemasterPatient(true)}finally{guard=false}
 }
 function apply(){ensureBatchButton();ensurePatientRemaster()}
 const observer=new MutationObserver(()=>queueMicrotask(apply));
 observer.observe(document.documentElement,{childList:true,subtree:true,characterData:true});
 const oldLoad=window.loadBilling;if(typeof oldLoad==='function')window.loadBilling=async function(){const r=await oldLoad.apply(this,arguments);ensureBatchButton();return r};
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(apply,30),{once:true});else setTimeout(apply,30);
 setTimeout(apply,250);setTimeout(apply,900);
})();"""
V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\n" + V482_HOTFIX_CSS
V460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\n" + V482_HOTFIX_JS

V484_PATIENT_CSS = r"""
/* v4.3.84 — hotfix seguro + pulido de Nuevo paciente */
#modal .modalbox.v481-patient-modal{width:min(730px,94vw)!important;max-height:90vh!important;padding:18px 20px 16px!important}
.v481-patient-modal .v481-remastered-form{gap:10px!important}
.v481-patient-modal .modal-form-heading h2{font-size:22px!important}
.v481-patient-modal .modal-form-heading p{font-size:10px!important}
.v481-section{gap:8px 11px!important;padding:11px 12px!important;border-radius:13px!important}
.v481-section-head{padding-bottom:6px!important;margin-bottom:0!important;align-items:center!important}
.v481-section-head b{font-size:9px!important;letter-spacing:.1em!important}
.v481-section-head span{font-size:8.7px!important}
.v481-section-head .v481-section-icon{width:30px!important;height:30px!important;border-radius:10px!important;font-size:15px!important;background:#eef5fd!important}
.v481-identity{border-left:3px solid #8fb4dc!important}
.v481-contact{border-left:3px solid #9bcbb1!important}
.v484-location{grid-column:1/-1!important;display:grid!important;grid-template-columns:1fr!important;border-left:3px solid #d2b36f!important;background:#fffdf8!important}
.v484-location .v481-role-place{grid-column:1/-1!important}
.v484-location .v481-role-place input{width:100%!important}
.v481-patient-modal input:not([type="checkbox"]),.v481-patient-modal textarea,.v481-patient-modal select{min-height:40px!important;padding:8px 10px!important;font-size:12px!important;border-radius:10px!important}
.v481-role-id input,.v481-role-name input{font-size:12.5px!important;font-weight:750!important;letter-spacing:0!important}
.v481-role-id input::placeholder,.v481-role-name input::placeholder{font-size:10.5px!important;font-weight:600!important;letter-spacing:0!important;color:#8a96a6!important;opacity:1!important}
.v481-role-phone input::placeholder,.v481-role-email input::placeholder,.v481-role-place input::placeholder,.v481-role-birth input::placeholder{font-size:10.5px!important;font-weight:550!important;color:#929dac!important;opacity:1!important}
.v481-id-status{min-height:29px!important;padding:6px 8px!important;font-size:9px!important}
.v481-age-pill{font-size:8.5px!important;padding:3px 7px!important}
.v481-role-notes{display:none!important}
.v484-hide-more{display:none!important}
.v484-date-error{display:none;margin-top:4px;font-size:8.5px;font-weight:750;color:#a44d45}
.v484-date-error.show{display:block}
.v484-date-invalid{border-color:#d7847d!important;box-shadow:0 0 0 2px rgba(190,75,65,.08)!important}
.v481-patient-modal .actions,.v481-patient-modal .form-actions,.v481-patient-modal .modal-actions{padding-top:8px!important}
.v481-create-btn{min-height:37px!important;font-size:10px!important}
@media(max-width:680px){#modal .modalbox.v481-patient-modal{width:94vw!important;padding:15px!important}.v481-section{padding:10px!important}}
"""
V484_PATIENT_JS = r""";(()=>{
 if(window.__v484PatientHotfix)return;window.__v484PatientHotfix=true;
 const norm=v=>String(v||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/\s+/g,' ').trim().toLowerCase();
 function parseDMY(v){
   const m=/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(String(v||'').trim());if(!m)return null;
   const d=Number(m[1]),mo=Number(m[2]),y=Number(m[3]);if(y<1900||y>new Date().getFullYear()||mo<1||mo>12||d<1||d>31)return null;
   const x=new Date(y,mo-1,d);if(x.getFullYear()!==y||x.getMonth()!==mo-1||x.getDate()!==d)return null;
   return {d,mo,y,iso:`${String(y).padStart(4,'0')}-${String(mo).padStart(2,'0')}-${String(d).padStart(2,'0')}`,display:`${String(d).padStart(2,'0')}/${String(mo).padStart(2,'0')}/${String(y).padStart(4,'0')}`};
 }
 function isoToDMY(v){const m=/^(\d{4})-(\d{2})-(\d{2})$/.exec(String(v||''));return m?`${m[3]}/${m[2]}/${m[1]}`:String(v||'')}
 function age(p){if(!p)return null;const t=new Date();let a=t.getFullYear()-p.y;if(t.getMonth()+1<p.mo||(t.getMonth()+1===p.mo&&t.getDate()<p.d))a--;return a>=0&&a<130?a:null}
 function sectionHead(title,subtitle,icon){const h=document.createElement('div');h.className='v481-section-head';h.innerHTML=`<div><b>${title}</b><span>${subtitle}</span></div><span class="v481-section-icon" aria-hidden="true">${icon}</span>`;return h}
 function findSave(modal){return [...modal.querySelectorAll('button')].reverse().find(b=>/guardar|crear paciente|registrar paciente/.test(norm(b.textContent)))||null}
 function polishOnce(){
   const modal=document.querySelector('#modal .modalbox');if(!modal)return false;
   const root=modal.querySelector('.v481-remastered-form');if(!root||root.dataset.v484Polished==='1')return false;
   const cedula=root.querySelector('.v481-role-id input'),name=root.querySelector('.v481-role-name input');if(!cedula||!name)return false;
   root.dataset.v484Polished='1';modal.classList.add('v481-patient-modal');
   const identity=modal.querySelector('.v481-identity'),contact=modal.querySelector('.v481-contact');
   const ii=identity?.querySelector('.v481-section-icon');if(ii)ii.textContent='🪪';
   const ci=contact?.querySelector('.v481-section-icon');if(ci)ci.textContent='☎';
   const heading=modal.querySelector('.modal-form-heading p');if(heading)heading.textContent='Registra al paciente y continúa a su atención.';
   cedula.placeholder='Ingrese 10 dígitos';name.placeholder='Apellidos y nombres';

   const placeWrap=root.querySelector('.v481-role-place'),notesWrap=root.querySelector('.v481-role-notes');
   if(notesWrap)notesWrap.style.display='none';
   if(placeWrap){
     let sec=root.querySelector('.v484-location');
     if(!sec){sec=document.createElement('section');sec.className='v481-section v484-location';sec.appendChild(sectionHead('LUGAR','Ciudad o sector del paciente','📍'));
       const actions=root.querySelector(':scope > .actions,:scope > .form-actions,:scope > .modal-actions')||root.querySelector('.actions,.form-actions,.modal-actions');
       const more=root.querySelector(':scope > .v481-more-details')||root.querySelector('.v481-more-details');root.insertBefore(sec,actions||more||null)}
     sec.appendChild(placeWrap);const p=placeWrap.querySelector('input');if(p)p.placeholder='Ciudad o sector';
   }
   for(const det of root.querySelectorAll('.v481-more-details')){
     const useful=[...det.querySelectorAll('input,textarea,select')].filter(el=>!el.closest('.v481-role-notes')&&!el.closest('.v481-role-place'));
     if(!useful.length)det.classList.add('v484-hide-more');
   }

   const birth=root.querySelector('.v481-role-birth input');
   if(birth&&birth.dataset.v484Manual!=='1'){
     birth.dataset.v484Manual='1';const initial=isoToDMY(birth.value);birth.type='text';birth.value=initial;birth.placeholder='dd/mm/aaaa';birth.inputMode='numeric';birth.maxLength=10;birth.autocomplete='off';
     const err=document.createElement('small');err.className='v484-date-error';err.textContent='Fecha inválida · usa dd/mm/aaaa';birth.parentElement?.appendChild(err);
     const pill=root.querySelector('.v481-age-pill');
     const render=()=>{const raw=birth.value.trim(),p=parseDMY(raw);birth.classList.toggle('v484-date-invalid',!!raw&&!p);err.classList.toggle('show',!!raw&&!p);if(pill){const a=age(p);pill.textContent=a===null?'Edad —':`Edad: ${a} año${a===1?'':'s'}`}};
     birth.addEventListener('input',()=>{let d=String(birth.value||'').replace(/\D/g,'').slice(0,8);if(d.length>4)d=d.slice(0,2)+'/'+d.slice(2,4)+'/'+d.slice(4);else if(d.length>2)d=d.slice(0,2)+'/'+d.slice(2);birth.value=d;render()});birth.addEventListener('blur',render);render();
     const save=findSave(modal);if(save&&!save.dataset.v484DateGuard){save.dataset.v484DateGuard='1';save.addEventListener('click',e=>{const raw=birth.value.trim();if(!raw)return;const p=parseDMY(raw);if(!p){e.preventDefault();e.stopImmediatePropagation();render();birth.focus();return}birth.value=p.iso;setTimeout(()=>{if(document.body.contains(birth)){birth.value=p.display;render()}},700)},true)}
   }
   return true;
 }
 const previousExport=window.v481RemasterPatient;
 if(typeof previousExport==='function')window.v481RemasterPatient=function(){const r=previousExport.apply(this,arguments);queueMicrotask(polishOnce);setTimeout(polishOnce,30);return r};
 const previousNew=window.newPatient;
 if(typeof previousNew==='function')window.newPatient=async function(){const r=await previousNew.apply(this,arguments);setTimeout(polishOnce,0);setTimeout(polishOnce,60);return r};
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(polishOnce,80),{once:true});else setTimeout(polishOnce,80);
})();"""
V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\n" + V484_PATIENT_CSS
V460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\n" + V484_PATIENT_JS

V485_FIX_CSS = r"""
/* v4.3.85 — identidad compatible + Lugar debajo de Contacto */
.v481-section-icon .v485-id-card{display:block;width:20px;height:14px;border:1.5px solid currentColor;border-radius:3px;position:relative;box-sizing:border-box}
.v481-section-icon .v485-id-card:before{content:'';position:absolute;left:3px;top:3px;width:4px;height:4px;border:1px solid currentColor;border-radius:50%;box-sizing:border-box}
.v481-section-icon .v485-id-card:after{content:'';position:absolute;right:3px;top:4px;width:7px;height:1.5px;border-radius:2px;background:currentColor;box-shadow:0 3px 0 currentColor}
.v484-location.v485-location-under-contact{grid-column:2!important;align-self:start!important;margin-top:0!important;min-height:auto!important}
.v484-location.v485-location-under-contact .v481-section-head{margin-bottom:2px!important}
@media(max-width:680px){.v484-location.v485-location-under-contact{grid-column:1!important}}
"""
V485_FIX_JS = r""";(()=>{
 if(window.__v485Fixes)return;window.__v485Fixes=true;
 const norm=v=>String(v||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/\s+/g,' ').trim().toLowerCase();
 const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 let batchBusy=false;

 function visualFix(){
   const modal=document.querySelector('#modal .modalbox');if(!modal)return;
   const identity=modal.querySelector('.v481-identity'),contact=modal.querySelector('.v481-contact'),location=modal.querySelector('.v484-location');
   const icon=identity?.querySelector('.v481-section-icon');
   if(icon&&!icon.querySelector('.v485-id-card'))icon.innerHTML='<span class="v485-id-card" aria-hidden="true"></span>';
   if(location&&contact&&location.parentElement===contact.parentElement){contact.insertAdjacentElement('afterend',location);location.classList.add('v485-location-under-contact')}
 }

 async function req(url,opt={}){
   if(typeof window.api==='function')return await window.api(url,opt);
   const r=await fetch(url,{credentials:'same-origin',headers:{'Content-Type':'application/json',...(opt.headers||{})},...opt});
   const d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(d.detail||d.message||'No se pudo completar la operación');return d;
 }
 async function ask(text,title){return typeof window.rpConfirm==='function'?await window.rpConfirm(text,title):window.confirm(text)}
 function notice(text,title){if(typeof window.rpNotice==='function')return window.rpNotice(text,title);alert(text)}

 window.emitAllPendingInvoices=async function(){
   if(batchBusy)return;batchBusy=true;
   const btn=document.querySelector('#v482BatchEmit');const old=btn?.textContent;
   try{
     if(btn){btn.disabled=true;btn.textContent='Revisando…'}
     const pre=await req('/api/billing/azur/batch-preview');
     const c=pre.counts||{},ready=Number(c.ready||0),skipped=Number(c.skipped||0);
     if(!ready){notice(`No hay facturas completas listas para emitir.\n\nOmitidas: ${skipped}`,'Facturación');return}
     const examples=(pre.ready||[]).slice(0,5).map(x=>`• ${x.nombre||'Paciente'} · $${Number(x.total||0).toFixed(2)}`).join('\n');
     const text=`¿Emitir ${ready} factura${ready===1?'':'s'} por lotes en AZUR?\n\nSe enviarán una por una para evitar duplicados.${examples?'\n\n'+examples:''}`;
     if(!(await ask(text,'Emitir por lotes')))return;
     if(btn)btn.textContent='Emitiendo…';
     const result=await req('/api/billing/azur/emit-all-pending',{method:'POST',body:'{}'});
     const r=result.counts||{};
     let detail=`Enviadas a AZUR: ${r.sent??r.emitted??0}\nOmitidas: ${r.skipped||0}\nFallidas: ${r.failed||0}`;
     const failed=(result.failed||[]).slice(0,5);if(failed.length)detail+='\n\nCon error:\n'+failed.map(x=>`• ${x.nombre||'Paciente'}: ${x.reason||'Error'}`).join('\n');
     notice(detail,'Emisión por lotes');
     try{await window.loadBilling?.()}catch(_e){}try{window.refreshPendingBadges?.()}catch(_e){}
   }catch(e){notice(e?.message||String(e),'Facturación')}
   finally{batchBusy=false;if(btn){btn.disabled=false;btn.textContent=old||'⚡ Emitir por lotes'}}
 };

 const oldEdit=window.editPatientFromBilling;
 if(typeof oldEdit==='function')window.editPatientFromBilling=function(id){
   window.__v485EditingPatientId=Number(id)||id||true;
   try{return oldEdit.apply(this,arguments)}finally{setTimeout(()=>{window.__v485EditingPatientId=null},1500)}
 };

 const oldRemaster=window.v481RemasterPatient;
 if(typeof oldRemaster==='function')window.v481RemasterPatient=function(){const r=oldRemaster.apply(this,arguments);setTimeout(visualFix,0);setTimeout(visualFix,60);return r};
 const oldNew=window.newPatient;
 if(typeof oldNew==='function')window.newPatient=function(){const r=oldNew.apply(this,arguments);setTimeout(visualFix,20);setTimeout(visualFix,90);return r};
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(visualFix,80),{once:true});else setTimeout(visualFix,80);
})();"""
V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\n" + V485_FIX_CSS
V460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\n" + V485_FIX_JS

V486_FIX_CSS = r"""/* v4.3.86 — Paciente nuevo + Inicio + acceso AZUR */
.v481-contact{grid-template-columns:repeat(2,minmax(0,1fr))!important}
.v481-contact .v486-place-in-contact{grid-column:1/-1!important;margin-top:1px!important}
.v481-contact .v486-place-in-contact input{width:100%!important}
.v484-location{display:none!important}
.v486-home-delete{border-color:#efd0cd!important;color:#99453f!important;background:#fff7f6!important}
.v486-home-delete:hover{background:#ffefed!important}
#facturacion .v486-azur-link{display:inline-flex!important;align-items:center!important;gap:6px!important;min-height:34px!important;padding:7px 11px!important;border:1px solid #cfdced!important;border-radius:10px!important;background:#f5f9ff!important;color:#315f94!important;font-size:9.5px!important;font-weight:900!important;cursor:pointer!important}
#facturacion .v486-azur-link:hover{background:#eaf3ff!important}
"""
V486_FIX_JS = r""";(()=>{
 if(window.__v486Fixes)return;window.__v486Fixes=true;
 const domains=new Set(['@gmail.com','@hotmail.com','@outlook.com','@yahoo.com']);
 function patientFix(){
   const modal=document.querySelector('#modal .modalbox');if(!modal)return;
   const contact=modal.querySelector('.v481-contact');
   const location=modal.querySelector('.v484-location');
   const place=(location?.querySelector('.v481-role-place'))||modal.querySelector('.v481-role-place');
   if(contact&&place&&!contact.contains(place)){contact.appendChild(place);place.classList.add('v486-place-in-contact');if(location)location.remove()}
   if(contact&&!contact.dataset.v486EmailShortcuts){
     contact.dataset.v486EmailShortcuts='1';
     contact.addEventListener('click',ev=>{
       const b=ev.target.closest('button');if(!b)return;
       const domain=String(b.textContent||'').trim().toLowerCase();if(!domains.has(domain))return;
       const email=contact.querySelector('.v481-role-email input,input[type="email"]');if(!email)return;
       ev.preventDefault();ev.stopImmediatePropagation();
       let local=String(email.value||'').trim().toLowerCase().split('@')[0].replace(/\s+/g,'');
       if(!local){email.focus();return}
       email.value=local+domain;
       email.dispatchEvent(new Event('input',{bubbles:true}));email.dispatchEvent(new Event('change',{bubbles:true}));
       email.focus();try{email.setSelectionRange(email.value.length,email.value.length)}catch(_e){}
     },true);
   }
 }
 async function openAzur(){
   try{if(typeof window.api==='function')await window.api('/api/open-external/azur',{method:'POST',body:'{}'});else await fetch('/api/open-external/azur',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:'{}'})}
   catch(e){alert(e?.message||'No se pudo abrir AZUR')}
 }
 function ensureAzurButton(){
   const sec=document.querySelector('#facturacion');if(!sec||sec.querySelector('#v486OpenAzur'))return;
   let row=sec.querySelector('.billing-title-row')||sec.querySelector('.page-title-row')||sec.querySelector('h1')?.parentElement;if(!row)return;
   let actions=row.querySelector('.billing-title-actions');if(!actions){actions=document.createElement('div');actions.className='billing-title-actions';row.appendChild(actions)}
   const b=document.createElement('button');b.id='v486OpenAzur';b.type='button';b.className='external-billing-link v486-azur-link';b.textContent='↗ Abrir AZUR';b.onclick=openAzur;actions.appendChild(b);
 }
 const oldNew=window.newPatient;if(typeof oldNew==='function')window.newPatient=function(){const r=oldNew.apply(this,arguments);setTimeout(patientFix,20);setTimeout(patientFix,100);return r};
 const oldEdit=window.editPatientFromBilling;if(typeof oldEdit==='function')window.editPatientFromBilling=function(){const r=oldEdit.apply(this,arguments);setTimeout(patientFix,20);setTimeout(patientFix,100);return r};
 const oldBilling=window.loadBilling;if(typeof oldBilling==='function')window.loadBilling=async function(){const r=await oldBilling.apply(this,arguments);ensureAzurButton();return r};
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>{setTimeout(patientFix,80);setTimeout(ensureAzurButton,100)},{once:true});else{setTimeout(patientFix,80);setTimeout(ensureAzurButton,100)}
})();"""
V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\n" + V486_FIX_CSS
V460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\n" + V486_FIX_JS

V487_ICON_CSS = r"""/* v4.3.87 — iconos vectoriales compatibles + feedback AZUR */
.v487-section-svg{width:18px;height:18px;display:block;stroke:currentColor;fill:none;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
.v481-section-icon.v487-identity-icon{color:#356da7!important;background:#eaf3fd!important}
.v481-section-icon.v487-contact-icon{color:#397b58!important;background:#edf8f1!important}
.v486-place-in-contact{position:relative}
.v486-place-in-contact>label:first-child,.v486-place-in-contact .field-label:first-child{display:flex!important;align-items:center!important;gap:5px!important}
.v487-place-label-icon{width:12px;height:12px;display:inline-block;vertical-align:-2px;stroke:#9b6a26;fill:none;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
#facturacion .v487-azur-loading{display:none;align-items:center;gap:10px;margin:8px 0 10px;padding:10px 12px;border:1px solid #cfe0f3;border-radius:11px;background:#f4f9ff;color:#315f91;font-size:10px;font-weight:800}
#facturacion .v487-azur-loading.show{display:flex}
#facturacion .v487-azur-loading-copy{display:grid;gap:1px}
#facturacion .v487-azur-loading-copy b{font-size:10.5px;color:#285783}
#facturacion .v487-azur-loading-copy span{font-size:8.8px;color:#70869d;font-weight:650}
#facturacion .v487-azur-spinner{width:17px;height:17px;flex:0 0 17px;border:2px solid #bdd4ed;border-top-color:#3976b6;border-radius:50%;animation:v487spin .75s linear infinite}
@keyframes v487spin{to{transform:rotate(360deg)}}
"""
V487_ICON_JS = r""";(()=>{
 if(window.__v487Icons)return;window.__v487Icons=true;
 const idSvg='<svg class="v487-section-svg" viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2.5"></rect><circle cx="8" cy="10" r="2.1"></circle><path d="M5.8 15c.8-1.6 3.6-1.6 4.4 0"></path><path d="M13 9h5M13 12h5M13 15h3.5"></path></svg>';
 const phoneSvg='<svg class="v487-section-svg" viewBox="0 0 24 24" aria-hidden="true"><path d="M7.2 4.5 9.6 8 8.1 9.7c1.1 2.2 2.9 4 5.1 5.1l1.7-1.5 3.6 2.4-.6 3c-.2.9-1 1.5-1.9 1.4C9.4 19.3 4.7 14.6 3.9 8c-.1-.9.5-1.7 1.4-1.9l1.9-.4z"></path></svg>';
 const pinSvg='<svg class="v487-place-label-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 21s6-5.1 6-11a6 6 0 1 0-12 0c0 5.9 6 11 6 11z"></path><circle cx="12" cy="10" r="2"></circle></svg>';
 let azurLoadingTimer=null;
 function applyIcons(){
   const modal=document.querySelector('#modal .modalbox');if(!modal)return;
   const identity=modal.querySelector('.v481-identity'),contact=modal.querySelector('.v481-contact');
   const ii=identity?.querySelector('.v481-section-icon');if(ii){ii.classList.add('v487-identity-icon');ii.innerHTML=idSvg}
   const ci=contact?.querySelector('.v481-section-icon');if(ci){ci.classList.add('v487-contact-icon');ci.innerHTML=phoneSvg}
   const place=contact?.querySelector('.v486-place-in-contact,.v481-role-place');
   if(place&&!place.dataset.v487Pin){
     place.dataset.v487Pin='1';
     const label=place.querySelector('label,.field-label');
     if(label&&!label.querySelector('.v487-place-label-icon'))label.insertAdjacentHTML('afterbegin',pinSvg);
   }
 }
 function ensureAzurLoading(){
   const sec=document.querySelector('#facturacion');if(!sec)return null;
   let box=sec.querySelector('#v487AzurLoading');if(box)return box;
   box=document.createElement('div');box.id='v487AzurLoading';box.className='v487-azur-loading';box.innerHTML='<span class="v487-azur-spinner" aria-hidden="true"></span><span class="v487-azur-loading-copy"><b>Revisando AZUR…</b><span>Consultando el estado de las facturas emitidas y su autorización SRI.</span></span>';
   const title=sec.querySelector('.billing-title-row,.page-title-row')||sec.querySelector('h1')?.parentElement;
   if(title)title.insertAdjacentElement('afterend',box);else sec.prepend(box);
   return box;
 }
 function showAzurLoading(){const box=ensureAzurLoading();if(!box)return;box.classList.add('show');clearTimeout(azurLoadingTimer);azurLoadingTimer=setTimeout(hideAzurLoading,90000)}
 function hideAzurLoading(){const box=document.querySelector('#v487AzurLoading');box?.classList.remove('show');clearTimeout(azurLoadingTimer);azurLoadingTimer=null}
 document.addEventListener('click',ev=>{
   const b=ev.target.closest('#facturacion button');if(!b)return;
   const text=String(b.textContent||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
   if(text.includes('emitidas')||text.includes('autorizadas'))showAzurLoading();
 },true);
 const oldBilling=window.loadBilling;if(typeof oldBilling==='function')window.loadBilling=async function(){try{return await oldBilling.apply(this,arguments)}finally{hideAzurLoading()}};
 const oldNew=window.newPatient;if(typeof oldNew==='function')window.newPatient=function(){const r=oldNew.apply(this,arguments);setTimeout(applyIcons,25);setTimeout(applyIcons,110);return r};
 const oldEdit=window.editPatientFromBilling;if(typeof oldEdit==='function')window.editPatientFromBilling=function(){const r=oldEdit.apply(this,arguments);setTimeout(applyIcons,25);setTimeout(applyIcons,110);return r};
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>{setTimeout(applyIcons,100);setTimeout(ensureAzurLoading,120)},{once:true});else{setTimeout(applyIcons,100);setTimeout(ensureAzurLoading,120)}
})();"""
V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\n" + V487_ICON_CSS
V460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\n" + V487_ICON_JS

V488_HOME_CSS = r"""/* v4.3.88 — iconos visibles en acciones de Inicio */
.v478-home-actions>button{display:inline-flex!important;align-items:center!important;justify-content:center!important;gap:5px!important}
.v488-home-action-svg{width:13px;height:13px;display:block;flex:0 0 13px;stroke:currentColor;fill:none;stroke-width:1.9;stroke-linecap:round;stroke-linejoin:round}
.v486-home-delete .v488-home-action-svg{width:12px;height:12px;flex-basis:12px}
@media(max-width:760px){.v478-home-actions>button{gap:4px!important}.v488-home-action-svg{width:12px;height:12px;flex-basis:12px}}
"""
V488_REVIEW_JS = r""";(()=>{
 if(window.__v488ReviewCopy)return;window.__v488ReviewCopy=true;
 function fixReviewCopy(){
   const modal=document.querySelector('#modal .modalbox');if(!modal)return;
   const title=[...modal.querySelectorAll('h1,h2,h3')].find(x=>String(x.textContent||'').toLowerCase().includes('revisar paciente'));
   if(!title)return;
   const p=title.parentElement?.querySelector('p')||title.nextElementSibling;
   if(p&&String(p.textContent||'').toLowerCase().includes('fusion'))p.textContent='Las coincidencias de 75% o más se vinculan automáticamente. Las menores quedan para revisión manual.';
 }
 const oldOpen=window.openModal;
 if(typeof oldOpen==='function')window.openModal=function(){const r=oldOpen.apply(this,arguments);setTimeout(fixReviewCopy,0);setTimeout(fixReviewCopy,50);return r};
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(fixReviewCopy,100),{once:true});else setTimeout(fixReviewCopy,100);
})();"""
V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\n" + V488_HOME_CSS
V460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\n" + V488_REVIEW_JS

V490_ATTENTION_CSS = r"""/* v4.3.90 — remaster de Nueva atención: acción siempre visible */
.modalbox.v490-attention-remaster{width:min(900px,96vw)!important;max-height:88vh!important;padding:17px 20px 16px!important;overflow:auto!important;scrollbar-gutter:stable}
.v490-attention-remaster .v490-attention-bar{position:sticky;top:-1px;z-index:90;display:flex;align-items:center;justify-content:space-between;gap:12px;margin:9px 0 13px;padding:9px 10px 9px 12px;border:1px solid #d7e3ef;border-radius:12px;background:rgba(248,251,255,.97);box-shadow:0 5px 16px rgba(40,64,92,.10)}
.v490-attention-remaster .v490-attention-bar-left{display:flex;align-items:center;gap:9px;min-width:0}
.v490-attention-remaster .v490-attention-bar-icon{width:28px;height:28px;display:grid;place-items:center;border-radius:9px;background:#e8f4ee;color:#28704d;flex:0 0 28px}
.v490-attention-remaster .v490-attention-bar-icon svg{width:16px;height:16px;display:block;stroke:currentColor;fill:none;stroke-width:2.1;stroke-linecap:round;stroke-linejoin:round}
.v490-attention-remaster .v490-attention-copy{display:grid;gap:1px;min-width:0}.v490-attention-remaster .v490-attention-copy b{font-size:9px;line-height:1;letter-spacing:.09em;color:#5c6d82;text-transform:uppercase}.v490-attention-remaster .v490-attention-copy span{font-size:11px;font-weight:800;color:#263b55;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.v490-attention-remaster .v490-save-btn{border:0;border-radius:10px;min-height:37px;padding:8px 15px;background:#287fc4;color:#fff;font-size:10.5px;font-weight:900;box-shadow:0 4px 10px rgba(40,127,196,.18);white-space:nowrap;cursor:pointer}
.v490-attention-remaster .v490-save-btn:hover:not(:disabled){filter:brightness(.96)}.v490-attention-remaster .v490-save-btn:disabled{background:#c9d4df;color:#f8fafc;box-shadow:none;cursor:not-allowed}
.v490-attention-remaster textarea{min-height:52px!important;max-height:74px!important}
.v490-attention-remaster .modal-form-heading{margin-bottom:6px!important}.v490-attention-remaster .modal-form-heading h2{margin-bottom:2px!important}
@media(max-width:700px){.modalbox.v490-attention-remaster{width:96vw!important;padding:14px 13px 12px!important}.v490-attention-remaster .v490-attention-bar{gap:8px;padding:8px}.v490-attention-remaster .v490-attention-copy span{font-size:10px}.v490-attention-remaster .v490-save-btn{padding:8px 11px;font-size:9.5px}}
"""
V490_ATTENTION_JS = r""";(()=>{
 if(window.__v490AttentionRemaster)return;window.__v490AttentionRemaster=true;
 const norm=v=>String(v||'').replace(/\s+/g,' ').trim().toLowerCase();
 function attentionBox(){
   const boxes=[...document.querySelectorAll('#modal .modalbox,.modal .modalbox,.modalbox')];
   return boxes.find(box=>[...box.querySelectorAll('h1,h2,h3')].some(h=>norm(h.textContent)==='nueva atención')&&findOriginalSave(box))||null;
 }
 function findOriginalSave(box){
   return [...box.querySelectorAll('button,input[type="button"],input[type="submit"]')].find(el=>{
     if(el.classList?.contains('v490-save-btn'))return false;
     const t=norm(el.textContent||el.value);return t.includes('guardar atención')||t.includes('guardando');
   })||null;
 }
 function selectionText(box){
   const leaves=[...box.querySelectorAll('span,b,small,div')].filter(el=>el.children.length===0&&/seleccionad/.test(norm(el.textContent)));
   leaves.sort((a,b)=>String(a.textContent||'').length-String(b.textContent||'').length);
   if(leaves.length){
     let txt=String(leaves[0].textContent||'').replace(/puedes elegir varias\s*[·•-]?\s*/i,'').trim();
     if(txt)return txt;
   }
   const count=[...box.querySelectorAll('input[type="checkbox"]:checked,input[type="radio"]:checked')].filter(x=>!x.disabled).length;
   return count===1?'1 seleccionada':`${count} seleccionadas`;
 }
 function sync(box){
   if(!box)return;const original=findOriginalSave(box),bar=box.querySelector('.v490-attention-bar');if(!original||!bar)return;
   const clone=bar.querySelector('.v490-save-btn'),status=bar.querySelector('.v490-attention-status');
   if(status)status.textContent=selectionText(box);
   if(clone){clone.disabled=!!original.disabled;clone.textContent=norm(original.textContent||original.value).includes('guardando')?'Guardando…':'Guardar atención';}
 }
 function enhance(){
   const box=attentionBox();if(!box)return;
   box.classList.add('v490-attention-remaster');
   let bar=box.querySelector('.v490-attention-bar');
   if(!bar){
     bar=document.createElement('div');bar.className='v490-attention-bar';
     bar.innerHTML='<div class="v490-attention-bar-left"><span class="v490-attention-bar-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M5 12.5l4 4L19 7"></path></svg></span><div class="v490-attention-copy"><b>ATENCIÓN</b><span class="v490-attention-status">0 seleccionadas</span></div></div><button class="v490-save-btn" type="button">Guardar atención</button>';
     const title=[...box.querySelectorAll('h1,h2,h3')].find(h=>norm(h.textContent)==='nueva atención');
     const heading=title?.closest('.modal-form-heading')||title?.parentElement;
     if(heading&&heading.parentElement===box)heading.insertAdjacentElement('afterend',bar);else box.insertBefore(bar,box.children[1]||box.firstChild);
   }
   if(!box.dataset.v490Bound){
     box.dataset.v490Bound='1';
     box.addEventListener('click',e=>{
       const save=e.target.closest?.('.v490-save-btn');
       if(save){e.preventDefault();const original=findOriginalSave(box);if(original&&!original.disabled)original.click();return;}
       setTimeout(()=>sync(box),0);setTimeout(()=>sync(box),80);
     });
     box.addEventListener('change',()=>{setTimeout(()=>sync(box),0);setTimeout(()=>sync(box),60)});
     box.addEventListener('input',()=>setTimeout(()=>sync(box),0));
   }
   sync(box);setTimeout(()=>sync(box),80);
 }
 document.addEventListener('click',()=>{setTimeout(enhance,0);setTimeout(enhance,80);setTimeout(enhance,180)},true);
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(enhance,120),{once:true});else setTimeout(enhance,120);
})();"""
V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\n" + V490_ATTENTION_CSS
V460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\n" + V490_ATTENTION_JS

V491_ATTENTION_CSS = r"""/* v4.3.91 — Nueva atención profesional, compacta y sin redundancias */
.v490-attention-bar{display:none!important}
.modalbox.v491-attention-pro{width:min(920px,96vw)!important;max-height:88vh!important;padding:16px 18px 15px!important;overflow:auto!important;scrollbar-gutter:stable}
.v491-attention-pro .modal-form-heading{margin:0 0 9px!important}.v491-attention-pro .modal-form-heading h2{margin:0 0 2px!important;font-size:24px!important;line-height:1.05!important;letter-spacing:-.02em}.v491-attention-pro .modal-form-heading p{margin:0!important;font-size:9.5px!important;color:#6e7f91!important}
.v491-attention-pro .v491-hidden{display:none!important}
.v491-attention-pro .v491-overview-grid{display:grid!important;grid-template-columns:minmax(0,1.7fr) minmax(180px,.75fr) minmax(205px,.8fr)!important;gap:9px!important;align-items:stretch!important;margin:0 0 12px!important}
.v491-attention-pro .v491-overview-grid>.v491-patient-card,.v491-attention-pro .v491-overview-grid>.v491-type-card,.v491-attention-pro .v491-overview-grid>.v491-date-card{margin:0!important;min-height:0!important;height:auto!important}
.v491-attention-pro .v491-patient-card,.v491-attention-pro .v491-type-card,.v491-attention-pro .v491-date-card{padding:11px 12px!important;border-radius:12px!important}
.v491-attention-pro .v491-patient-card{background:#fff!important;border:1px solid #dfe6ee!important}.v491-attention-pro .v491-patient-card h3,.v491-attention-pro .v491-patient-card strong{line-height:1.12!important}
.v491-attention-pro .v491-type-card{background:#eef8f2!important;border:1px solid #cee6d7!important;display:flex!important;flex-direction:column!important;justify-content:center!important;gap:3px!important}
.v491-attention-pro .v491-type-label{display:none!important}.v491-attention-pro .v491-type-value{display:inline-flex!important;align-items:center!important;width:max-content!important;max-width:100%;padding:4px 8px!important;border-radius:999px!important;background:#dff2e7!important;color:#286946!important;font-size:9px!important;font-weight:950!important;letter-spacing:.055em!important}
.v491-attention-pro .v491-type-card small,.v491-attention-pro .v491-type-card span:not(.v491-type-value){font-size:8.5px!important;line-height:1.2!important;color:#557363!important}
.v491-attention-pro .v491-date-card{background:#f8fafc!important;border:1px solid #dfe6ee!important;display:flex!important;align-items:center!important;justify-content:space-between!important;gap:8px!important}.v491-attention-pro .v491-date-card input{min-height:36px!important;height:36px!important;font-size:10.5px!important;padding:7px 9px!important}
.v491-attention-pro .v491-attention-title{margin-top:3px!important;margin-bottom:2px!important;font-size:18px!important;letter-spacing:-.01em!important}.v491-attention-pro .v491-selection-help{font-size:8.5px!important;color:#7a8998!important;margin:0 0 7px!important}.v491-attention-pro .v491-selection-count{display:inline-flex!important;align-items:center!important;padding:4px 8px!important;border-radius:999px!important;background:#edf6f2!important;color:#376c56!important;font-size:8.5px!important;font-weight:850!important;white-space:nowrap!important}
.v491-attention-pro .v491-observation-wrap{display:none!important}
.v491-attention-pro textarea[placeholder*="Observ" i]{display:none!important}
.v491-attention-pro .modal-actions,.v491-attention-pro .form-actions{margin-top:10px!important;padding-top:9px!important;border-top:1px solid #e7edf3!important;background:#fff!important}
.v491-attention-pro button{transition:background .12s ease,border-color .12s ease,transform .08s ease}.v491-attention-pro button:active{transform:translateY(1px)}
@media(max-width:760px){.v491-attention-pro .v491-overview-grid{grid-template-columns:1fr!important}.modalbox.v491-attention-pro{width:96vw!important;padding:14px 13px!important}.v491-attention-pro .v491-date-card{justify-content:flex-start!important}}
"""
V491_ATTENTION_JS = r""";(()=>{
 if(window.__v491AttentionPro)return;window.__v491AttentionPro=true;
 const norm=v=>String(v||'').replace(/\s+/g,' ').trim().toLowerCase();
 const leaves=(box)=>[...box.querySelectorAll('label,span,b,strong,small,p,div,h1,h2,h3')].filter(el=>el.children.length===0);
 function attentionBox(){
   return [...document.querySelectorAll('#modal .modalbox,.modal .modalbox,.modalbox')].find(box=>[...box.querySelectorAll('h1,h2,h3')].some(h=>norm(h.textContent)==='nueva atención'))||null;
 }
 function leaf(box,test){return leaves(box).find(el=>test(norm(el.textContent),el))||null}
 function sectionFor(el,needles,box){
   let cur=el;
   for(let i=0;cur&&cur!==box&&i<6;i++,cur=cur.parentElement){
     const txt=norm(cur.textContent);
     if(needles.every(n=>txt.includes(n))&&txt.length<900)return cur;
   }
   return el?.parentElement||null;
 }
 function hideObservation(box){
   [...box.querySelectorAll('textarea')].forEach(ta=>{
     const ph=norm(ta.getAttribute('placeholder'));
     let lab=null;let prev=ta.previousElementSibling;
     if(prev&&/observ/.test(norm(prev.textContent)))lab=prev;
     const parent=ta.parentElement;
     if(ph.includes('observ')||lab||/observ/.test(norm(parent?.textContent||''))){
       const wrap=parent&&parent!==box?parent:ta;
       wrap.classList.add('v491-observation-wrap');
       ta.value='';
     }
   });
   leaves(box).filter(el=>/^observaci[oó]n/.test(norm(el.textContent))).forEach(el=>el.classList.add('v491-hidden'));
 }
 function compactOverview(box){
   const patientLabel=leaf(box,t=>t==='paciente');
   const typeLabel=leaf(box,t=>t==='tipo de paciente detectado');
   const dateLabel=leaf(box,t=>t==='fecha de atención');
   const pCard=patientLabel?sectionFor(patientLabel,['paciente'],box):null;
   const tCard=typeLabel?sectionFor(typeLabel,['tipo de paciente detectado'],box):null;
   let dCard=null;
   if(dateLabel){
     let cur=dateLabel;
     for(let i=0;cur&&cur!==box&&i<6;i++,cur=cur.parentElement){if(cur.querySelector?.('input')){dCard=cur;break}}
     dCard=dCard||dateLabel.parentElement;
   }
   if(pCard)pCard.classList.add('v491-patient-card');
   if(tCard){tCard.classList.add('v491-type-card');typeLabel.classList.add('v491-type-label');const val=leaf(tCard,t=>t==='subsecuente'||t==='nuevo');if(val)val.classList.add('v491-type-value')}
   if(dCard)dCard.classList.add('v491-date-card');
   if(pCard&&tCard&&dCard&&pCard!==tCard&&pCard!==dCard&&tCard!==dCard){
     const parent=pCard.parentElement;
     if(parent&&tCard.parentElement===parent&&dCard.parentElement===parent)parent.classList.add('v491-overview-grid');
   }
   const missing=leaf(box,t=>t.includes('faltan datos'));
   if(missing){const redundant=leaf(box,t=>t.includes('sin cédula o identificación registrada')||t.includes('sin cedula o identificacion registrada'));if(redundant)redundant.classList.add('v491-hidden')}
 }
 function cleanSelection(box){
   const title=leaf(box,t=>t==='selecciona la atención');if(title){title.textContent='Atención realizada';title.classList.add('v491-attention-title')}
   const redundant=leaf(box,t=>t.includes('no hay ninguna opción marcada por defecto'));if(redundant)redundant.classList.add('v491-hidden');
   const count=leaf(box,t=>t.includes('puedes elegir varias')&&t.includes('seleccionad'));
   if(count){count.textContent=String(count.textContent||'').replace(/puedes elegir varias\s*[·•-]?\s*/i,'').trim()||'0 seleccionadas';count.classList.add('v491-selection-count')}
   const procHelp=leaf(box,t=>t.includes('selecciona uno o varios si corresponde'));if(procHelp){procHelp.textContent='Puedes seleccionar uno o varios';procHelp.classList.add('v491-selection-help')}
 }
 function enhance(){
   const box=attentionBox();if(!box)return;
   box.classList.add('v491-attention-pro');
   box.querySelectorAll('.v490-attention-bar').forEach(x=>x.remove());
   hideObservation(box);compactOverview(box);cleanSelection(box);
 }
 document.addEventListener('click',()=>{setTimeout(enhance,0);setTimeout(enhance,80);setTimeout(enhance,180)},true);
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(enhance,120),{once:true});else setTimeout(enhance,120);
})();"""
V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\n" + V491_ATTENTION_CSS
V460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\n" + V491_ATTENTION_JS

V492_ATTENTION_CSS = r"""/* v4.3.92 — remaster estructural real de Nueva atención */
.v490-attention-bar{display:none!important}
.modalbox.v492-attention{width:min(980px,97vw)!important;max-height:90vh!important;padding:15px 17px 0!important;overflow:auto!important;scrollbar-gutter:stable;background:#fbfcfe!important}
.v492-attention .modal-form-heading{margin:0 0 9px!important}.v492-attention .modal-form-heading h2{font-size:23px!important;line-height:1.05!important;margin:0 0 2px!important;letter-spacing:-.025em}.v492-attention .modal-form-heading p{font-size:9.5px!important;margin:0!important;color:#708095!important}
.v492-attention .v491-overview-grid{display:block!important;margin:0!important}.v492-attention .v491-patient-card,.v492-attention .v491-type-card,.v492-attention .v491-date-card{margin:0!important}
.v492-clinical-head{display:grid;grid-template-columns:minmax(0,1fr) minmax(250px,310px);gap:10px;align-items:stretch;margin:0 0 13px;padding:10px 11px;border:1px solid #dbe4ed;border-radius:15px;background:#fff;box-shadow:0 3px 12px rgba(39,61,83,.045)}
.v492-head-main{min-width:0;display:flex;align-items:center}.v492-head-main>.v491-patient-card{width:100%!important;padding:3px 5px!important;border:0!important;background:transparent!important;box-shadow:none!important;min-height:0!important}
.v492-head-main .v491-hidden{display:none!important}.v492-head-main strong,.v492-head-main h3{font-size:16px!important;line-height:1.12!important;letter-spacing:-.01em!important}.v492-head-main button{min-height:30px!important;padding:6px 9px!important;font-size:8.5px!important;border-radius:9px!important}
.v492-head-main [class*="warn"],.v492-head-main [class*="missing"]{font-size:8.5px!important;padding:5px 8px!important;border-radius:9px!important}
.v492-head-side{display:grid;grid-template-columns:1fr;gap:6px;align-content:center;border-left:1px solid #e6edf3;padding-left:10px;min-width:0}
.v492-head-side>.v491-type-card,.v492-head-side>.v491-date-card{padding:7px 9px!important;border:0!important;border-radius:10px!important;min-height:0!important;height:auto!important;box-shadow:none!important}
.v492-head-side>.v491-type-card{background:#edf8f2!important}.v492-head-side>.v491-date-card{background:#f5f8fb!important;display:flex!important;align-items:center!important;gap:7px!important}
.v492-head-side .v491-type-value{font-size:8.5px!important;padding:3px 7px!important}.v492-head-side .v491-type-card small,.v492-head-side .v491-type-card span:not(.v491-type-value){font-size:7.8px!important}
.v492-head-side .v491-date-card label,.v492-head-side .v491-date-card>span,.v492-head-side .v491-date-card>div:first-child{font-size:8px!important;font-weight:850!important;color:#6b7b8f!important}.v492-head-side .v491-date-card input{height:31px!important;min-height:31px!important;padding:5px 7px!important;font-size:9.5px!important;background:#fff!important}
.v492-attention .v492-selection-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:1px 2px 8px}.v492-attention .v492-selection-head h3{font-size:17px!important;margin:0!important;letter-spacing:-.015em;color:#25384f}.v492-attention .v492-selection-count{display:inline-flex;align-items:center;gap:5px;padding:5px 9px;border-radius:999px;background:#edf6f2;color:#376d56;font-size:8.5px;font-weight:900;white-space:nowrap}
.v492-services-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin:0 0 10px!important;padding:0!important}
.v492-service-card{position:relative!important;min-width:0!important;min-height:64px!important;height:auto!important;margin:0!important;padding:10px 31px 9px 38px!important;border:1px solid #dce5ee!important;border-radius:12px!important;background:#fff!important;box-shadow:0 2px 7px rgba(43,63,84,.035)!important;display:flex!important;align-items:center!important;cursor:pointer!important;transition:border-color .12s ease,background .12s ease,box-shadow .12s ease,transform .08s ease!important}
.v492-service-card:hover{border-color:#b9cce0!important;background:#f8fbfe!important}.v492-service-card:active{transform:translateY(1px)}
.v492-service-card.v492-consult{border-color:#c8e3d3!important;background:#f3faf6!important}.v492-service-card.is-selected{border-color:#6fa0ce!important;background:#eef6fd!important;box-shadow:0 0 0 2px rgba(69,129,184,.10)!important}.v492-service-card.v492-consult.is-selected{border-color:#65aa83!important;background:#eaf7ef!important;box-shadow:0 0 0 2px rgba(58,145,96,.10)!important}
.v492-service-mark{position:absolute;left:10px;top:50%;transform:translateY(-50%);width:20px;height:20px;border-radius:7px;display:grid;place-items:center;background:#edf3f9;color:#4f769f;font-size:14px;font-weight:900;line-height:1}.v492-consult .v492-service-mark{background:#e0f2e7;color:#2d7850}.v492-service-card.is-selected .v492-service-mark{background:#5a8fbe;color:#fff}.v492-service-card.v492-consult.is-selected .v492-service-mark{background:#418c62;color:#fff}.v492-service-card.is-selected .v492-service-mark::before{content:'✓';font-size:12px}.v492-service-card.is-selected .v492-service-mark{font-size:0}
.v492-service-card input[type="checkbox"],.v492-service-card input[type="radio"]{position:absolute!important;right:9px!important;top:9px!important;width:16px!important;height:16px!important;margin:0!important;opacity:.38}.v492-service-card.is-selected input[type="checkbox"],.v492-service-card.is-selected input[type="radio"]{opacity:1}
.v492-service-card strong,.v492-service-card b{font-size:10.5px!important;line-height:1.08!important}.v492-service-card small,.v492-service-card span,.v492-service-card div{line-height:1.15}.v492-service-card small{font-size:8px!important;color:#748498!important}.v492-service-card .v492-editable{display:inline-flex!important;width:max-content!important;margin-top:3px!important;padding:2px 5px!important;border-radius:999px!important;background:#f0f3f7!important;color:#6a7788!important;font-size:7px!important;font-weight:850!important}
.v492-empty-source,.v492-observation-hidden{display:none!important}.v492-attention textarea[placeholder*="Observ" i]{display:none!important}
.v492-attention .v491-attention-title,.v492-attention .v491-selection-help,.v492-attention .v491-selection-count{display:none!important}
.v492-sticky-actions{position:sticky!important;bottom:0!important;z-index:80!important;margin:8px -17px 0!important;padding:9px 17px 11px!important;border-top:1px solid #dde6ef!important;background:rgba(251,252,254,.98)!important;box-shadow:0 -6px 18px rgba(36,57,78,.07)!important;backdrop-filter:blur(4px)}
.v492-sticky-actions button{min-height:36px!important;border-radius:10px!important;font-size:10px!important}.v492-sticky-actions button:last-child{padding-left:18px!important;padding-right:18px!important;font-weight:900!important}
@media(max-width:900px){.v492-services-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.v492-clinical-head{grid-template-columns:minmax(0,1fr) minmax(220px,270px)}}
@media(max-width:700px){.modalbox.v492-attention{width:97vw!important;padding:13px 12px 0!important}.v492-clinical-head{grid-template-columns:1fr}.v492-head-side{border-left:0;border-top:1px solid #e6edf3;padding-left:0;padding-top:7px;grid-template-columns:1fr 1fr}.v492-services-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.v492-sticky-actions{margin-left:-12px!important;margin-right:-12px!important;padding-left:12px!important;padding-right:12px!important}}
"""
V492_ATTENTION_JS = r""";(()=>{
 if(window.__v492Attention)return;window.__v492Attention=true;
 const norm=v=>String(v||'').replace(/\s+/g,' ').trim().toLowerCase();
 const leaves=box=>[...box.querySelectorAll('label,span,b,strong,small,p,div,h1,h2,h3')].filter(el=>el.children.length===0);
 function boxNow(){return [...document.querySelectorAll('#modal .modalbox,.modal .modalbox,.modalbox')].find(b=>[...b.querySelectorAll('h1,h2,h3')].some(h=>norm(h.textContent)==='nueva atención'))||null}
 function leaf(box,fn){return leaves(box).find(el=>fn(norm(el.textContent),el))||null}
 function cardAround(el,box,needsInput=false){
   let cur=el;
   for(let i=0;cur&&cur!==box&&i<7;i++,cur=cur.parentElement){
     if(needsInput&&cur.querySelector?.('input'))return cur;
     const txt=norm(cur.textContent);if(!needsInput&&txt.length>0&&txt.length<700&&cur.children.length>0)return cur;
   }
   return el?.parentElement||null;
 }
 function findOverview(box){
   const pLab=leaf(box,t=>t==='paciente');
   const tLab=leaf(box,t=>t==='tipo de paciente detectado');
   const dLab=leaf(box,t=>t==='fecha de atención');
   const pCard=pLab?cardAround(pLab,box,false):null;
   let tCard=tLab?cardAround(tLab,box,false):null;
   let dCard=dLab?dLab.parentElement:null;
   if(dLab){let c=dLab;for(let i=0;c&&c!==box&&i<7;i++,c=c.parentElement){if(c.querySelector?.('input[type="date"],input')){dCard=c;break}}}
   if(tCard){tCard.classList.add('v491-type-card');tLab.classList.add('v491-type-label');const v=leaf(tCard,t=>t==='subsecuente'||t==='nuevo');if(v)v.classList.add('v491-type-value')}
   if(pCard)pCard.classList.add('v491-patient-card');if(dCard)dCard.classList.add('v491-date-card');
   return {pCard,tCard,dCard};
 }
 function buildHeader(box){
   let head=box.querySelector('.v492-clinical-head');if(head)return head;
   const {pCard,tCard,dCard}=findOverview(box);if(!pCard||!tCard||!dCard)return null;
   if(pCard===tCard||pCard===dCard||tCard===dCard)return null;
   head=document.createElement('section');head.className='v492-clinical-head';
   const main=document.createElement('div');main.className='v492-head-main';
   const side=document.createElement('div');side.className='v492-head-side';
   const heading=[...box.querySelectorAll('h1,h2,h3')].find(h=>norm(h.textContent)==='nueva atención');
   const headingWrap=heading?.closest('.modal-form-heading')||heading?.parentElement;
   if(headingWrap)headingWrap.insertAdjacentElement('afterend',head);else box.prepend(head);
   main.appendChild(pCard);side.appendChild(tCard);side.appendChild(dCard);head.append(main,side);
   const patientLabel=leaf(pCard,t=>t==='paciente');if(patientLabel)patientLabel.style.display='none';
   const redundant=leaf(pCard,t=>t.includes('sin cédula o identificación registrada')||t.includes('sin cedula o identificacion registrada'));const missing=leaf(pCard,t=>t.includes('faltan datos'));if(redundant&&missing)redundant.style.display='none';
   return head;
 }
 function serviceCardForInput(inp,box){
   let cur=inp.parentElement,best=null;
   for(let i=0;cur&&cur!==box&&i<6;i++,cur=cur.parentElement){
     const text=norm(cur.textContent);const inputCount=cur.querySelectorAll?.('input[type="checkbox"],input[type="radio"]').length||0;
     if(inputCount===1&&text.length>2&&text.length<260)best=cur;
   }
   return best||inp.parentElement;
 }
 function buildServices(box){
   const groups=box.querySelector('.service-groups');
   if(!groups)return null;
   groups.classList.add('v43103-native-services');

   // Elimina restos creados por versiones antiguas si la modal fue reutilizada.
   box.querySelectorAll('.v495-consult-card,.v494-consult-proxy,.v495-consult-card,.v43102-consult-section,.v43102-procedure-head,.v492-services-grid').forEach(el=>el.remove());

   const consultation=groups.querySelector('.consultation-service-section');
   const procedures=groups.querySelector('.procedures-service-section');
   consultation?.classList.remove('v492-empty-source','v497-native-section-empty','v495-hidden-source','hidden');
   procedures?.classList.remove('v492-empty-source','v497-native-section-empty','v495-hidden-source','hidden');
   groups.classList.remove('v492-empty-source','v497-native-section-empty','v495-hidden-source','hidden');

   const consult=groups.querySelector('button.service-card[data-service="CONSULTA"],button.service-card[data-service="consulta"]');
   if(consult){
     consult.classList.remove('v492-service-card','v492-consult','v497-native-consult','v492-empty-source','v495-hidden-source','hidden');
     consult.style.removeProperty('display');consult.style.removeProperty('height');consult.style.removeProperty('visibility');consult.style.removeProperty('opacity');
     const price=consult.querySelector('.service-price');if(price)price.textContent='$40.00';
   }
   const procHeading=procedures?.querySelector('.service-group-heading b');if(procHeading)procHeading.textContent='Procedimientos y servicios';
   return groups;
 }
 function hideObservation(box){
   [...box.querySelectorAll('textarea')].forEach(ta=>{const ph=norm(ta.placeholder);if(ph.includes('observ')||norm(ta.parentElement?.textContent).includes('observ')){ta.value='';(ta.parentElement||ta).classList.add('v492-observation-hidden')}});
   leaves(box).filter(x=>/^observaci[oó]n/.test(norm(x.textContent))).forEach(x=>x.classList.add('v492-observation-hidden'));
 }
 function stickyActions(box){
   const save=[...box.querySelectorAll('button,input[type="button"],input[type="submit"]')].find(el=>!el.classList.contains('v490-save-btn')&&norm(el.textContent||el.value).includes('guardar atención'));
   if(!save)return null;let row=save.parentElement;
   for(let i=0;row&&row!==box&&i<4;i++,row=row.parentElement){const buttons=row.querySelectorAll?.('button,input[type="button"],input[type="submit"]').length||0;if(buttons>=2)break}
   row=row&&row!==box?row:save.parentElement;if(row)row.classList.add('v492-sticky-actions');return row;
 }
 function sync(box){
   const consult=box.querySelector('.service-groups button.service-card[data-service="CONSULTA"],.service-groups button.service-card[data-service="consulta"]');
   if(consult)consult.classList.toggle('is-selected',consult.classList.contains('selected'));
 }
 function enhance(){
   const box=boxNow();if(!box)return;box.classList.add('v492-attention');box.querySelectorAll('.v490-attention-bar').forEach(x=>x.remove());
   const sub=box.querySelector('.modal-form-heading p');if(sub)sub.textContent='Confirma el paciente y registra la atención realizada.';
   buildHeader(box);buildServices(box);hideObservation(box);stickyActions(box);
   const oldTitle=leaf(box,t=>t==='atención realizada'||t==='selecciona la atención');if(oldTitle&&oldTitle.closest('.v492-selection-head')==null){const parent=oldTitle.parentElement;if(parent)parent.classList.add('v492-empty-source')}
   ['consulta','procedimientos'].forEach(word=>{leaves(box).filter(x=>norm(x.textContent)===word).forEach(x=>{const p=x.parentElement;if(p&&!p.closest('.v492-service-card')&&!p.closest('.v492-selection-head'))p.classList.add('v492-empty-source')})});
   sync(box);
 }
 document.addEventListener('click',()=>{setTimeout(enhance,0);setTimeout(enhance,70);setTimeout(enhance,170)},true);
 document.addEventListener('change',()=>setTimeout(()=>{const b=boxNow();if(b){enhance();sync(b)}},0),true);
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(enhance,120),{once:true});else setTimeout(enhance,120);
})();"""
V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\n" + V492_ATTENTION_CSS
V460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\n" + V492_ATTENTION_JS

V493_ATTENTION_CSS = r"""/* v4.3.93 — CONSULTA restaurada + alertas clínicas visibles */
.v493-alert-band{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:10px;align-items:center;margin:-3px 0 11px;padding:10px 12px;border:1px solid #e1b84d;border-radius:13px;background:linear-gradient(135deg,#fff8d8 0%,#fff1b5 100%);box-shadow:0 3px 10px rgba(155,111,22,.08)}
.v493-alert-icon{font-size:22px;line-height:1;filter:saturate(1.08)}
.v493-alert-copy{display:grid;gap:3px;min-width:0}.v493-alert-title{font-size:10px;font-weight:950;color:#6e4d08;letter-spacing:.015em}.v493-alert-line{font-size:9px;line-height:1.25;color:#735b23}.v493-alert-line b{font-weight:950;color:#5d430c}
.v493-alert-actions{display:flex;align-items:center}.v493-alert-actions button{min-height:33px!important;padding:6px 11px!important;border-radius:9px!important;border:1px solid #d3a83f!important;background:#fff9df!important;color:#684d12!important;font-size:8.5px!important;font-weight:900!important;white-space:nowrap!important;box-shadow:0 2px 6px rgba(128,92,18,.08)!important}.v493-alert-actions button:hover{background:#fff3c4!important}
.v493-old-alert{display:none!important}
.v492-services-grid>.v493-consult{order:-100!important;border-color:#b9ddc7!important;background:#eff9f3!important}.v492-services-grid>.v493-consult:hover{border-color:#7fbd98!important;background:#e9f7ef!important}.v492-services-grid>.v493-consult strong,.v492-services-grid>.v493-consult b{color:#245f41!important}.v492-services-grid>.v493-consult .v492-service-mark{background:#d9efe2!important;color:#267149!important}
.v492-services-grid>.v493-consult::after{content:'$40 fijo';display:inline-flex;margin-left:auto;padding:2px 5px;border-radius:999px;background:#def1e6;color:#286b49;font-size:7px;font-weight:900;white-space:nowrap}
.v492-services-grid>.v493-consult.is-selected::after{background:#cae8d6;color:#215d3e}
@media(max-width:700px){.v493-alert-band{grid-template-columns:auto 1fr}.v493-alert-actions{grid-column:1/-1}.v493-alert-actions button{width:100%}}
"""
V493_ATTENTION_JS = r""";(()=>{
 if(window.__v493AttentionFix)return;window.__v493AttentionFix=true;
 const norm=v=>String(v||'').replace(/\s+/g,' ').trim().toLowerCase();
 const leaves=box=>[...box.querySelectorAll('label,span,b,strong,small,p,div,h1,h2,h3')].filter(el=>el.children.length===0);
 function boxNow(){return [...document.querySelectorAll('#modal .modalbox,.modal .modalbox,.modalbox')].find(b=>[...b.querySelectorAll('h1,h2,h3')].some(h=>norm(h.textContent)==='nueva atención'))||null}
 function patientName(box){
   const root=box.querySelector('.v492-head-main')||box;
   const candidates=[...root.querySelectorAll('h3,strong,b,span,div')].filter(el=>el.children.length===0).map(el=>String(el.textContent||'').replace(/\s+/g,' ').trim()).filter(t=>t&&t.length>5&&!/^(paciente|subsecuente|nuevo)$/i.test(t)&&!/^faltan datos/i.test(t)&&!/^sin c[eé]dula/i.test(t));
   candidates.sort((a,b)=>b.length-a.length);return candidates[0]||'';
 }
 function incompleteName(name){
   const words=String(name||'').trim().split(/\s+/).filter(Boolean);return words.length>0&&words.length<4;
 }
 function smallestCommon(a,b,box){
   if(!a)return null;let cur=a;
   for(let i=0;cur&&cur!==box&&i<7;i++,cur=cur.parentElement){if((!b||cur.contains(b))&&norm(cur.textContent).length<650)return cur}
   return a.parentElement;
 }
 function ensureAlert(box){
   const head=box.querySelector('.v492-clinical-head');if(!head)return;
   const all=leaves(box);const missing=all.find(el=>norm(el.textContent).includes('faltan datos'))||null;
   const complete=[...box.querySelectorAll('button')].find(b=>norm(b.textContent).includes('completar datos'))||null;
   const name=patientName(box),badName=incompleteName(name);
   let band=box.querySelector('.v493-alert-band');
   if(!missing&&!badName){if(band)band.remove();return}
   if(!band){
     band=document.createElement('section');band.className='v493-alert-band';
     band.innerHTML='<div class="v493-alert-icon" aria-hidden="true">⚠️</div><div class="v493-alert-copy"><div class="v493-alert-title">Atención al registro del paciente</div><div class="v493-alert-lines"></div></div><div class="v493-alert-actions"></div>';
     head.insertAdjacentElement('afterend',band);
   }
   const lines=band.querySelector('.v493-alert-lines');lines.innerHTML='';
   if(missing){
     let txt=String(missing.textContent||'').replace(/^\s*[⚠️⚠\s]*/,'').trim();
     const colon=txt.indexOf(':');const detail=colon>=0?txt.slice(colon+1).trim():txt.replace(/^faltan datos\s*/i,'').trim();
     const line=document.createElement('div');line.className='v493-alert-line';line.innerHTML='⚠️ <b>Faltan datos:</b> '+(detail||'completa la ficha del paciente');lines.appendChild(line);
   }
   if(badName){const line=document.createElement('div');line.className='v493-alert-line';line.innerHTML='⚠️ <b>Nombre incompleto:</b> ideal registrar dos apellidos y dos nombres';lines.appendChild(line)}
   if(complete){band.querySelector('.v493-alert-actions').appendChild(complete)}
   if(missing){missing.style.display='none'}
   const old=smallestCommon(missing,complete,box);if(old&&old!==head&&!old.classList.contains('v493-alert-band')&&!old.contains(band)){old.classList.add('v493-old-alert')}
 }
 function consultCard(box){
   const exact=leaves(box).filter(el=>norm(el.textContent)==='consulta');
   let fallback=null;
   for(const label of exact){
     let cur=label;
     for(let i=0;cur&&cur!==box&&i<7;i++,cur=cur.parentElement){
       const txt=norm(cur.textContent);
       if(txt.includes('consulta')&&(txt.includes('$40')||txt.includes('40 fijo')||txt.includes('atención médica')||txt.includes('atencion medica'))&&txt.length<350){
         fallback=cur;
         if(cur.querySelector?.('input,button')||cur.onclick||cur.getAttribute?.('role'))return cur;
       }
     }
   }
   return fallback;
 }
 function ensureConsult(box){
   const grid=box.querySelector('.v492-services-grid');if(!grid)return;
   let card=grid.querySelector('.v492-consult,.v493-consult');
   if(!card)card=consultCard(box);
   if(!card)return;
   card.classList.remove('v492-empty-source','v491-hidden');card.style.removeProperty('display');
   card.classList.add('v492-service-card','v492-consult','v493-consult');
   if(!card.querySelector('.v492-service-mark')){const mark=document.createElement('span');mark.className='v492-service-mark';mark.textContent='+';card.prepend(mark)}
   if(card.parentElement!==grid)grid.insertBefore(card,grid.firstElementChild);else if(grid.firstElementChild!==card)grid.insertBefore(card,grid.firstElementChild);
   let p=card.parentElement;while(p&&p!==box){p.classList.remove('v492-empty-source','v493-old-alert');p=p.parentElement}
 }
 function enhance(){const box=boxNow();if(!box)return;setTimeout(()=>{ensureConsult(box);ensureAlert(box)},0)}
 document.addEventListener('click',()=>{setTimeout(enhance,40);setTimeout(enhance,160)},true);
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(enhance,220),{once:true});else setTimeout(enhance,220);
})();"""
V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\n" + V493_ATTENTION_CSS
V460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\n" + V493_ATTENTION_JS

V494_ATTENTION_CSS = r"""/* v4.3.94 — CONSULTA garantizada + alerta legible + limpieza de huecos */
.v493-alert-band{grid-template-columns:34px minmax(0,1fr) auto!important;gap:12px!important;padding:13px 14px!important;border-width:1.5px!important;border-color:#d8a51f!important;background:linear-gradient(135deg,#fff3ad 0%,#ffe989 100%)!important;box-shadow:0 4px 14px rgba(139,96,8,.12)!important}
.v493-alert-icon{font-size:28px!important;line-height:1!important}
.v493-alert-copy{gap:5px!important}.v493-alert-title{font-size:13px!important;line-height:1.15!important;font-weight:950!important;color:#5c4107!important}.v493-alert-line{font-size:11.5px!important;line-height:1.3!important;color:#654d17!important}.v493-alert-line b{font-weight:950!important;color:#4d3504!important}
.v493-alert-actions button{min-height:39px!important;padding:8px 14px!important;font-size:10.5px!important;border-width:1.5px!important;background:#fff9dc!important}
.v494-consult-proxy{order:-1000!important;position:relative!important;min-height:64px!important;padding:10px 30px 9px 39px!important;border:1.5px solid #8fc9a6!important;border-radius:12px!important;background:#ebf8f0!important;box-shadow:0 2px 8px rgba(38,112,70,.07)!important;display:flex!important;align-items:center!important;cursor:pointer!important;color:#245f41!important;user-select:none!important}
.v494-consult-proxy:hover{background:#e2f5ea!important;border-color:#62ac80!important}.v494-consult-proxy:active{transform:translateY(1px)}
.v494-consult-proxy .v494-consult-mark{position:absolute;left:11px;top:50%;transform:translateY(-50%);width:21px;height:21px;border-radius:7px;background:#d8efe1;color:#28754c;display:grid;place-items:center;font-size:15px;font-weight:950}.v494-consult-proxy .v494-consult-copy{display:grid;gap:3px;min-width:0}.v494-consult-proxy .v494-consult-copy b{font-size:11px!important;line-height:1!important;color:#245f41!important}.v494-consult-proxy .v494-consult-copy small{font-size:8px!important;color:#557764!important}.v494-consult-proxy .v494-consult-price{margin-left:auto;padding:3px 6px;border-radius:999px;background:#d8efe1;color:#276b49;font-size:7.5px;font-weight:950;white-space:nowrap}
.v494-consult-proxy.is-selected{background:#dff3e7!important;border-color:#45966a!important;box-shadow:0 0 0 2px rgba(49,135,86,.11)!important}.v494-consult-proxy.is-selected .v494-consult-mark{background:#418c62;color:#fff;font-size:0}.v494-consult-proxy.is-selected .v494-consult-mark::before{content:'✓';font-size:12px}
.v494-ghost-hidden{display:none!important;height:0!important;min-height:0!important;margin:0!important;padding:0!important;border:0!important;overflow:hidden!important}
@media(max-width:700px){.v493-alert-band{grid-template-columns:32px 1fr!important}.v493-alert-actions{grid-column:1/-1!important}.v493-alert-title{font-size:12px!important}.v493-alert-line{font-size:10.5px!important}}
"""
V494_ATTENTION_JS = r""";(()=>{
 if(window.__v494AttentionHotfix)return;window.__v494AttentionHotfix=true;
 const norm=v=>String(v||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/\s+/g,' ').trim().toLowerCase();
 function boxNow(){return [...document.querySelectorAll('#modal .modalbox,.modal .modalbox,.modalbox')].find(b=>[...b.querySelectorAll('h1,h2,h3')].some(h=>norm(h.textContent)==='nueva atencion'))||null}
 function gridNow(box){return box?.querySelector('.v492-services-grid')||null}
 function candidateScore(el){
   const t=norm(el.textContent);if(!t.includes('consulta'))return -1;if(t.includes('cistoscopia')||t.includes('consulta nuevamente'))return -1;
   let s=5;if(t.includes('$40')||t.includes('40 fijo')||t.includes('atencion medica'))s+=8;
   if(el.matches('button,label,[role="button"]'))s+=7;if(el.querySelector?.('input[type="checkbox"],input[type="radio"],button'))s+=5;
   if(t.length<180)s+=4;if(el.closest('.v492-services-grid'))s-=4;return s;
 }
 function originalConsult(box){
   const all=[...box.querySelectorAll('button,label,div,section,article,span')].filter(el=>el!==box&&norm(el.textContent).includes('consulta'));
   all.sort((a,b)=>candidateScore(b)-candidateScore(a)||norm(a.textContent).length-norm(b.textContent).length);
   const host=all.find(el=>candidateScore(el)>=9)||null;if(!host)return null;
   let root=host;
   for(let i=0;root&&root!==box&&i<5;i++,root=root.parentElement){
     const t=norm(root.textContent),n=root.querySelectorAll?.('input[type="checkbox"],input[type="radio"]').length||0;
     if(t.includes('consulta')&&!t.includes('cistoscopia')&&t.length<260&&(n===1||root.matches?.('button,label,[role="button"]')))return root;
   }
   return host;
 }
 function actionInside(host){
   if(!host)return null;
   const inp=host.matches?.('input[type="checkbox"],input[type="radio"]')?host:host.querySelector?.('input[type="checkbox"],input[type="radio"]');if(inp)return inp;
   const btn=host.matches?.('button,[role="button"],label')?host:host.querySelector?.('button,[role="button"],label');return btn||host;
 }
 function selected(host){const inp=host?.matches?.('input[type="checkbox"],input[type="radio"]')?host:host?.querySelector?.('input[type="checkbox"],input[type="radio"]');if(inp)return !!inp.checked;return host?.classList?.contains('is-selected')||host?.classList?.contains('selected')||false}
 function triggerOriginal(host){
   const act=actionInside(host);if(!act)return;
   if(act.matches?.('input[type="checkbox"],input[type="radio"]')){act.click();return}
   act.click?.();
 }
 function ensureConsult(box){
   const grid=gridNow(box);if(!grid)return;
   const oldVisible=[...grid.children].find(el=>/\bconsulta\b/.test(norm(el.textContent))&&!norm(el.textContent).includes('cistoscopia'));
   if(oldVisible){oldVisible.classList.add('v493-consult');return}
   const original=originalConsult(box);let proxy=grid.querySelector('.v494-consult-proxy');
   if(!proxy){proxy=document.createElement('div');proxy.className='v494-consult-proxy';proxy.setAttribute('role','button');proxy.setAttribute('tabindex','0');proxy.innerHTML='<span class="v494-consult-mark">+</span><span class="v494-consult-copy"><b>CONSULTA</b><small>Atención médica</small></span><span class="v494-consult-price">$40 fijo</span>';grid.insertBefore(proxy,grid.firstElementChild);proxy.addEventListener('click',e=>{e.preventDefault();const h=originalConsult(box);triggerOriginal(h);setTimeout(()=>syncConsult(box),0);setTimeout(()=>syncConsult(box),80)});proxy.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();proxy.click()}})}
   proxy.classList.toggle('is-selected',selected(original));
 }
 function syncConsult(box){const p=gridNow(box)?.querySelector('.v494-consult-proxy');if(!p)return;const h=originalConsult(box);p.classList.toggle('is-selected',selected(h))}
 function cleanGhosts(box){
   const band=box.querySelector('.v493-alert-band'),grid=gridNow(box);if(!band||!grid)return;
   let el=band.nextElementSibling;let guard=0;
   while(el&&el!==grid&&guard++<12){const next=el.nextElementSibling;const t=norm(el.textContent);const interactive=!!el.querySelector?.('button,input,select,textarea');const structural=el.classList?.contains('v492-selection-head')||el.classList?.contains('v492-empty-source')||el.classList?.contains('v491-attention-title')||el.classList?.contains('v493-old-alert');if((!t&&!interactive)||structural)el.classList.add('v494-ghost-hidden');el=next}
   [...box.querySelectorAll('.v492-empty-source,.v493-old-alert')].forEach(el=>{if(!el.contains(grid)&&!el.contains(band))el.classList.add('v494-ghost-hidden')});
 }
 function enlargeAlert(box){const band=box.querySelector('.v493-alert-band');if(!band)return;const title=band.querySelector('.v493-alert-title');if(title)title.textContent='⚠️ Atención al registro del paciente'}
 function enhance(){const box=boxNow();if(!box)return;ensureConsult(box);enlargeAlert(box);cleanGhosts(box);syncConsult(box)}
 document.addEventListener('click',()=>{setTimeout(enhance,20);setTimeout(enhance,100);setTimeout(enhance,220)},true);
 document.addEventListener('change',()=>setTimeout(enhance,0),true);
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(enhance,250),{once:true});else setTimeout(enhance,250);
})();"""
V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\n" + V494_ATTENTION_CSS
V460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\n" + V494_ATTENTION_JS

V495_ATTENTION_CSS = r"""/* v4.3.95 — CONSULTA enlazada al selector oculto real */
.v495-consult-card{order:-2000!important;position:relative!important;min-height:66px!important;padding:10px 34px 9px 40px!important;border:1.5px solid #79bd94!important;border-radius:12px!important;background:#eaf7ef!important;display:flex!important;align-items:center!important;gap:8px!important;cursor:pointer!important;box-shadow:0 2px 9px rgba(37,110,68,.08)!important;user-select:none!important}
.v495-consult-card:hover{background:#e1f4e8!important;border-color:#55a978!important}.v495-consult-card:active{transform:translateY(1px)}
.v495-consult-icon{position:absolute;left:11px;top:50%;transform:translateY(-50%);width:22px;height:22px;border-radius:7px;background:#d4ecde;color:#267248;display:grid;place-items:center;font-size:15px;font-weight:950}.v495-consult-copy{display:grid;gap:3px;min-width:0}.v495-consult-copy b{font-size:11.5px!important;color:#215d3d!important;line-height:1!important}.v495-consult-copy small{font-size:8.5px!important;color:#557565!important}.v495-consult-price{margin-left:auto;padding:3px 7px;border-radius:999px;background:#d5ecde;color:#246743;font-size:8px;font-weight:950;white-space:nowrap}
.v495-consult-card.is-selected{background:#d9f0e2!important;border-color:#398b5e!important;box-shadow:0 0 0 2px rgba(49,135,86,.11)!important}.v495-consult-card.is-selected .v495-consult-icon{background:#398b5e;color:#fff;font-size:0}.v495-consult-card.is-selected .v495-consult-icon:before{content:'✓';font-size:12px}
.v495-hidden-source{display:none!important;height:0!important;min-height:0!important;margin:0!important;padding:0!important;border:0!important;overflow:hidden!important}
"""
V495_ATTENTION_JS = r""";(()=>{
 if(window.__v495ConsultFix)return;window.__v495ConsultFix=true;
 const norm=v=>String(v||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/\s+/g,' ').trim().toLowerCase();
 function boxNow(){return [...document.querySelectorAll('#modal .modalbox,.modal .modalbox,.modalbox')].find(b=>[...b.querySelectorAll('h1,h2,h3')].some(h=>norm(h.textContent)==='nueva atencion'))||null}
 function gridNow(box){return box?.querySelector('.v492-services-grid')||null}
 function inputText(inp,box){
   let txt=[inp.id,inp.name,inp.value,inp.getAttribute('aria-label'),inp.dataset?.service,inp.dataset?.name].filter(Boolean).join(' ');
   let cur=inp.parentElement;
   for(let i=0;cur&&cur!==box&&i<5;i++,cur=cur.parentElement){const t=norm(cur.textContent);if(t&&t.length<260)txt+=' '+t}
   return norm(txt);
 }
 function hiddenConsultInput(box){
   const grid=gridNow(box);if(!grid)return null;
   const all=[...box.querySelectorAll('input[type="checkbox"],input[type="radio"]')].filter(i=>!i.disabled);
   const outside=all.filter(i=>!grid.contains(i)&&!i.closest('.v492-clinical-head')&&!i.closest('.v493-alert-band'));
   if(!outside.length)return null;
   const scored=outside.map(i=>{const t=inputText(i,box);let s=0;if(t.includes('consulta'))s+=30;if(t.includes('40'))s+=10;if(t.includes('atencion medica'))s+=10;if(t.includes('cisto'))s-=25;if(i.offsetParent===null)s+=6;return [i,s,t]}).sort((a,b)=>b[1]-a[1]);
   if(scored[0][1]>0)return scored[0][0];
   return outside.length===1?outside[0]:null;
 }
 function hideSource(inp,box){
   if(!inp)return;let cur=inp.parentElement;
   for(let i=0;cur&&cur!==box&&i<5;i++,cur=cur.parentElement){const t=norm(cur.textContent);if(t.includes('consulta')&&!t.includes('cistoscopia')&&t.length<280){cur.classList.add('v495-hidden-source');return}}
 }
 function sync(box){const grid=gridNow(box),card=grid?.querySelector('.v495-consult-card'),inp=hiddenConsultInput(box);if(card)card.classList.toggle('is-selected',!!inp?.checked)}
 function ensure(box){
   const grid=gridNow(box);if(!grid)return;
   let card=grid.querySelector('.v495-consult-card');const inp=hiddenConsultInput(box);
   if(!inp)return;
   hideSource(inp,box);
   if(!card){
     card=document.createElement('div');card.className='v495-consult-card';card.setAttribute('role','button');card.setAttribute('tabindex','0');card.innerHTML='<span class="v495-consult-icon">+</span><span class="v495-consult-copy"><b>CONSULTA</b><small>Atención médica</small></span><span class="v495-consult-price">$40 fijo</span>';
     const activate=()=>{inp.click();inp.dispatchEvent(new Event('change',{bubbles:true}));setTimeout(()=>sync(box),0);setTimeout(()=>sync(box),80)};
     card.addEventListener('click',e=>{e.preventDefault();activate()});card.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();activate()}});
     grid.insertBefore(card,grid.firstElementChild);
   } else if(grid.firstElementChild!==card)grid.insertBefore(card,grid.firstElementChild);
   sync(box);
 }
 function cleanup(box){
   const band=box.querySelector('.v493-alert-band'),grid=gridNow(box);if(!band||!grid)return;
   let el=band.nextElementSibling,guard=0;while(el&&el!==grid&&guard++<10){const next=el.nextElementSibling;const t=norm(el.textContent),interactive=!!el.querySelector?.('button,input:not([type="hidden"]),select,textarea');if(!t&&!interactive)el.classList.add('v495-hidden-source');el=next}
 }
 function enhance(){const box=boxNow();if(!box)return;ensure(box);cleanup(box);sync(box)}
 document.addEventListener('click',()=>{setTimeout(enhance,20);setTimeout(enhance,100);setTimeout(enhance,220)},true);
 document.addEventListener('change',()=>setTimeout(enhance,0),true);
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(enhance,240),{once:true});else setTimeout(enhance,240);
})();"""
V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\n" + V495_ATTENTION_CSS
V460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\n" + V495_ATTENTION_JS

V497_ATTENTION_CSS = r"""/* v4.3.97 — CONSULTA nativa visible dentro del remaster */
.v497-native-consult{order:-3000!important;display:grid!important;visibility:visible!important;opacity:1!important;height:auto!important;min-height:62px!important;background:#f2fbf6!important;border-color:#79bd96!important}
.v497-native-consult .service-icon{background:#dcf4e5!important;color:#257249!important}
.v497-native-consult:hover{border-color:#55a978!important;background:#ebf9f0!important}
.v497-native-consult.selected{background:#e3f7eb!important;border-color:#43a66e!important;box-shadow:0 0 0 2px #43a66e22!important}
.v497-native-consult.selected .service-icon{background:#2f925a!important;color:#fff!important}
.v497-native-section-empty{display:none!important;height:0!important;min-height:0!important;margin:0!important;padding:0!important;border:0!important;overflow:hidden!important}
"""
V497_ATTENTION_JS = r""";(()=>{
 if(window.__v497NativeConsult)return;window.__v497NativeConsult=true;
 const norm=v=>String(v||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/\s+/g,' ').trim().toLowerCase();
 function boxNow(){return [...document.querySelectorAll('#modal .modalbox,.modal .modalbox,.modalbox')].find(b=>[...b.querySelectorAll('h1,h2,h3')].some(h=>norm(h.textContent)==='nueva atencion'))||null}
 function nativeConsult(box){return [...box.querySelectorAll('button.service-card[data-service]')].find(b=>norm(b.dataset.service)==='consulta')||null}
 function hideEmptyNativeSections(box){
   for(const sec of box.querySelectorAll('.consultation-service-section,.procedures-service-section')){
     if(!sec.querySelector('.service-card'))sec.classList.add('v497-native-section-empty');
   }
   for(const groups of box.querySelectorAll('.service-groups')){
     if(!groups.querySelector('.service-card'))groups.classList.add('v497-native-section-empty');
   }
 }
 function repairConsult(){
   const box=boxNow();if(!box)return false;
   const card=nativeConsult(box);if(!card)return false;
   const slot=box.querySelector('.v43102-consult-slot');
   if(slot){
     card.classList.remove('v492-empty-source','v493-old-alert','v495-hidden-source','hidden');
     card.style.removeProperty('display');card.style.removeProperty('height');card.style.removeProperty('visibility');
     card.classList.add('v492-service-card','v492-consult','v497-native-consult');
     if(card.parentElement!==slot)slot.appendChild(card);
     card.querySelectorAll('.v492-service-mark').forEach(el=>el.remove());
     hideEmptyNativeSections(box);
     return true;
   }
   const grid=box.querySelector('.v492-services-grid');if(!grid)return false;
   const oldSection=card.closest('.consultation-service-section');
   card.classList.remove('v492-empty-source','v493-old-alert','v495-hidden-source','hidden');
   card.style.removeProperty('display');card.style.removeProperty('height');card.style.removeProperty('visibility');
   card.classList.add('v492-service-card','v492-consult','v497-native-consult');
   grid.querySelectorAll('.v494-consult-proxy,.v495-consult-card').forEach(el=>{if(el!==card)el.remove()});
   if(grid.firstElementChild!==card)grid.insertBefore(card,grid.firstElementChild);
   if(oldSection&&!oldSection.querySelector('.service-card'))oldSection.classList.add('v497-native-section-empty');
   hideEmptyNativeSections(box);
   return true;
 }
 function installFavicon(){
   let link=document.querySelector('link[data-rp-favicon="497"]');
   if(!link){link=document.createElement('link');link.rel='icon';link.type='image/x-icon';link.dataset.rpFavicon='497';document.head.appendChild(link)}
   link.href='/static/doctor_icon.ico?v=4.3.97';
 }
 function enhance(){installFavicon();repairConsult()}
 document.addEventListener('click',()=>{setTimeout(enhance,0);setTimeout(enhance,50);setTimeout(enhance,140);setTimeout(enhance,300)},true);
 document.addEventListener('change',()=>setTimeout(enhance,0),true);
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>{installFavicon();setTimeout(enhance,120)},{once:true});else{installFavicon();setTimeout(enhance,120)}
})();"""
V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\n" + V497_ATTENTION_CSS
V460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\n" + V497_ATTENTION_JS

V43102_ATTENTION_CSS = r"""/* v4.3.102 — Consulta aislada + procedimientos profesionales */
.modalbox.v492-attention{overflow-x:hidden!important}
.v43102-consult-section{display:block;width:100%;box-sizing:border-box;margin:0 0 14px;padding:12px 13px 13px;border:1px solid #cfe0f5;border-radius:14px;background:linear-gradient(180deg,#f6f9ff 0%,#eef5ff 100%);box-shadow:0 2px 9px rgba(39,85,135,.045)}
.v43102-consult-heading{display:flex;align-items:flex-end;justify-content:space-between;gap:12px;margin:0 2px 8px}
.v43102-consult-heading h3{margin:0!important;font-size:14px!important;line-height:1.1!important;letter-spacing:-.01em!important;color:#28425f!important}
.v43102-consult-heading small{font-size:8px!important;color:#6f8197!important;font-weight:700!important}
.v43102-consult-slot{display:block;width:100%;min-width:0;box-sizing:border-box}
.v43102-consult-slot .v492-service-card,.v43102-consult-slot .v497-native-consult{order:initial!important;width:100%!important;max-width:none!important;min-width:0!important;min-height:66px!important;margin:0!important;padding:11px 44px 11px 46px!important;display:flex!important;align-items:center!important;border:1px solid #b9d2ee!important;border-radius:12px!important;background:#fff!important;box-shadow:0 2px 8px rgba(31,72,112,.045)!important;visibility:visible!important;opacity:1!important}
.v43102-consult-slot .v492-service-card:hover,.v43102-consult-slot .v497-native-consult:hover{border-color:#8bb5e1!important;background:#fafdff!important}
.v43102-consult-slot .v492-service-card.selected,.v43102-consult-slot .v492-service-card.is-selected,.v43102-consult-slot .v497-native-consult.selected{border-color:#56a47a!important;background:#eff9f3!important;box-shadow:0 0 0 2px rgba(68,155,105,.10)!important}
.v43102-consult-slot .v492-service-mark{display:none!important}
.v43102-consult-slot .service-icon{background:#e7f1fc!important;color:#316b9f!important}
.v43102-consult-slot .selected .service-icon,.v43102-consult-slot .is-selected .service-icon{background:#3f8f63!important;color:#fff!important}
.v43102-consult-slot strong,.v43102-consult-slot b{font-size:12px!important;letter-spacing:.01em!important;color:#243d59!important}
.v43102-consult-slot .service-price{font-size:9.5px!important;color:#617790!important;font-weight:850!important}
.v43102-procedure-head{display:flex!important;align-items:flex-end!important;justify-content:space-between!important;gap:12px!important;margin:2px 2px 9px!important;width:100%!important;box-sizing:border-box!important}
.v43102-procedure-head>div{min-width:0}
.v43102-procedure-head h3{margin:0!important;font-size:16px!important;line-height:1.1!important;letter-spacing:-.015em!important;color:#263c56!important}
.v43102-procedure-head p{margin:3px 0 0!important;font-size:8.5px!important;line-height:1.2!important;color:#7a899b!important}
.v492-services-grid{width:100%!important;max-width:100%!important;min-width:0!important;box-sizing:border-box!important;display:grid!important;grid-template-columns:repeat(3,minmax(0,1fr))!important;gap:9px!important;margin:0 0 10px!important;padding:0!important;overflow:visible!important}
.v492-services-grid>.v492-service-card{width:100%!important;max-width:100%!important;min-width:0!important;box-sizing:border-box!important;min-height:62px!important;padding:10px 31px 9px 38px!important}
.v492-services-grid>.v492-consult{display:none!important}
.v492-empty-source,.v497-native-section-empty{display:none!important;height:0!important;min-height:0!important;margin:0!important;padding:0!important;border:0!important;overflow:hidden!important}
.v492-sticky-actions{max-width:calc(100% + 34px)!important;box-sizing:border-box!important}
@media(max-width:760px){.v492-services-grid{grid-template-columns:repeat(2,minmax(0,1fr))!important}.v43102-consult-heading{align-items:flex-start;flex-direction:column;gap:2px}}
@media(max-width:470px){.v492-services-grid{grid-template-columns:1fr!important}}
"""
V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\n" + V43102_ATTENTION_CSS

V43103_SERVICES_CSS = r"""/* v4.3.103 — servicios nativos, sin proxies ni reordenamientos */
.modalbox.v492-attention{overflow-x:hidden!important}
.v492-attention .service-title.enhanced{display:none!important}
.v492-attention .service-groups{display:grid!important;grid-template-columns:1fr!important;gap:13px!important;width:100%!important;max-width:100%!important;min-width:0!important;margin:0 0 10px!important;padding:0!important;box-sizing:border-box!important}
.v492-attention .service-section{width:100%!important;max-width:100%!important;min-width:0!important;box-sizing:border-box!important;border-radius:14px!important;box-shadow:0 2px 9px rgba(34,61,91,.035)!important}
.v492-attention .consultation-service-section{padding:12px 13px 13px!important;border:1px solid #c7dcf2!important;background:linear-gradient(180deg,#f6f9ff 0%,#eef5ff 100%)!important}
.v492-attention .consultation-service-section .service-group-heading{margin-bottom:9px!important}
.v492-attention .consultation-service-section .service-group-heading b{font-size:15px!important;color:#274462!important;letter-spacing:-.01em!important}
.v492-attention .consultation-service-section .service-group-heading span{font-size:9px!important;color:#70849a!important}
.v492-attention .consultation-grid{display:grid!important;grid-template-columns:1fr!important;gap:0!important;width:100%!important;max-width:100%!important;min-width:0!important;margin:0!important}
.v492-attention .consultation-card{display:grid!important;grid-template-columns:auto 1fr auto!important;grid-template-areas:'icon title check' 'icon price check'!important;column-gap:10px!important;row-gap:2px!important;align-items:center!important;width:100%!important;max-width:100%!important;min-width:0!important;min-height:66px!important;box-sizing:border-box!important;padding:11px 42px 11px 12px!important;border:1px solid #b8d2ee!important;border-radius:12px!important;background:#fff!important;box-shadow:0 2px 8px rgba(30,68,108,.045)!important;color:#223b58!important}
.v492-attention .consultation-card:hover{border-color:#86b2df!important;background:#fafdff!important}
.v492-attention .consultation-card.selected{border-color:#55a379!important;background:#eff9f3!important;box-shadow:0 0 0 2px rgba(67,150,102,.10)!important}
.v492-attention .consultation-card .service-icon{grid-area:icon!important;background:#e5f0fc!important;color:#2d6ca6!important}
.v492-attention .consultation-card.selected .service-icon{background:#3d8e62!important;color:#fff!important}
.v492-attention .consultation-card strong{grid-area:title!important;font-size:13px!important;line-height:1.05!important;color:#203a56!important}
.v492-attention .consultation-card .service-price{grid-area:price!important;font-size:10.5px!important;font-weight:850!important;color:#58718a!important}
.v492-attention .consultation-card .service-check{grid-area:check!important;right:9px!important;top:50%!important;transform:translateY(-50%)!important}
.v492-attention .procedures-service-section{padding:12px 12px 13px!important;border:1px solid #dfe7f0!important;background:#fbfcfe!important}
.v492-attention .procedures-service-section .service-group-heading{margin-bottom:9px!important}
.v492-attention .procedures-service-section .service-group-heading b{font-size:16px!important;color:#263d57!important;letter-spacing:-.012em!important}
.v492-attention .procedures-service-section .service-group-heading span{font-size:9px!important;color:#7b899a!important}
.v492-attention .procedures-service-section .service-grid{display:grid!important;grid-template-columns:repeat(3,minmax(0,1fr))!important;gap:9px!important;width:100%!important;max-width:100%!important;min-width:0!important;margin:0!important;padding:0!important;box-sizing:border-box!important}
.v492-attention .procedures-service-section .service-card{width:100%!important;max-width:100%!important;min-width:0!important;min-height:62px!important;box-sizing:border-box!important;margin:0!important}
.v492-attention .v43102-consult-section,.v492-attention .v43102-procedure-head,.v492-attention .v492-services-grid,.v492-attention .v495-consult-card,.v492-attention .v494-consult-proxy,.v492-attention .v495-consult-card{display:none!important}
@media(max-width:760px){.v492-attention .procedures-service-section .service-grid{grid-template-columns:repeat(2,minmax(0,1fr))!important}}
@media(max-width:470px){.v492-attention .procedures-service-section .service-grid{grid-template-columns:1fr!important}}
"""
for _legacy_services_js in (globals().get("V493_ATTENTION_JS", ""), globals().get("V494_ATTENTION_JS", ""), globals().get("V495_ATTENTION_JS", ""), globals().get("V497_ATTENTION_JS", "")):
    if _legacy_services_js:
        V460_OVERLAY_JS = (V460_OVERLAY_JS or "").replace(_legacy_services_js, "")
V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\n" + V43103_SERVICES_CSS

V43104_ALERT_CSS = r"""/* v4.3.104 — advertencias de registro independientes de servicios */
.v43104-alert-band{display:grid!important;grid-template-columns:32px minmax(0,1fr) auto!important;gap:12px!important;align-items:center!important;width:100%!important;box-sizing:border-box!important;margin:0 0 13px!important;padding:12px 13px!important;border:1px solid #e6ad19!important;border-radius:14px!important;background:linear-gradient(135deg,#fff3b5 0%,#ffe997 100%)!important;box-shadow:0 3px 10px rgba(143,101,14,.08)!important}
.v43104-alert-icon{display:grid!important;place-items:center!important;width:32px!important;height:32px!important;font-size:25px!important;line-height:1!important;color:#b66e00!important}
.v43104-alert-copy{display:grid!important;gap:3px!important;min-width:0!important}
.v43104-alert-title{font-size:13.5px!important;line-height:1.15!important;font-weight:950!important;color:#694807!important;letter-spacing:.005em!important}
.v43104-alert-lines{display:grid!important;gap:2px!important}
.v43104-alert-line{font-size:11.5px!important;line-height:1.25!important;color:#735719!important}
.v43104-alert-line b{font-weight:950!important;color:#5e4107!important}
.v43104-alert-actions{display:flex!important;align-items:center!important;justify-content:flex-end!important}
.v43104-alert-actions button{min-height:39px!important;padding:8px 14px!important;border-radius:10px!important;border:1px solid #d39b13!important;background:#fffaf0!important;color:#66490d!important;font-size:10.5px!important;font-weight:900!important;white-space:nowrap!important;box-shadow:0 2px 6px rgba(126,88,12,.08)!important}
.v43104-alert-actions button:hover{background:#fff5d4!important}
.v43104-old-warning-source{display:none!important;height:0!important;min-height:0!important;margin:0!important;padding:0!important;border:0!important;overflow:hidden!important}
@media(max-width:700px){.v43104-alert-band{grid-template-columns:28px minmax(0,1fr)!important}.v43104-alert-icon{width:28px!important;height:28px!important;font-size:22px!important}.v43104-alert-actions{grid-column:1/-1!important}.v43104-alert-actions button{width:100%!important}}
"""
V43104_ALERT_JS = r""";(()=>{
 if(window.__v43104PatientWarnings)return;window.__v43104PatientWarnings=true;
 const norm=v=>String(v||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/\s+/g,' ').trim().toLowerCase();
 const leaves=box=>[...box.querySelectorAll('label,span,b,strong,small,p,div,h1,h2,h3')].filter(el=>el.children.length===0);
 function boxNow(){return [...document.querySelectorAll('#modal .modalbox,.modal .modalbox,.modalbox')].find(b=>[...b.querySelectorAll('h1,h2,h3')].some(h=>norm(h.textContent)==='nueva atencion'))||null}
 function patientName(box){
   const root=box.querySelector('.v492-head-main')||box.querySelector('.v492-clinical-head')||box;
   const blocked=/^(paciente|subsecuente|nuevo|fecha de atencion|consulta|procedimientos y servicios)$/i;
   const candidates=[...root.querySelectorAll('h3,strong,b,span,div')]
     .filter(el=>el.children.length===0)
     .map(el=>String(el.textContent||'').replace(/\s+/g,' ').trim())
     .filter(t=>t&&t.length>5&&!blocked.test(t)&&!/^faltan datos/i.test(t)&&!/^ultima atencion/i.test(t));
   candidates.sort((a,b)=>b.length-a.length);return candidates[0]||'';
 }
 function incompleteName(name){const words=String(name||'').trim().split(/\s+/).filter(Boolean);return words.length>0&&words.length<4}
 function originalMissing(box){
   return leaves(box).find(el=>{
     if(el.closest('.v43104-alert-band'))return false;
     const raw=String(el.textContent||'').replace(/^[^A-Za-zÁÉÍÓÚáéíóúÑñ]+/,'');const t=norm(raw);return t.startsWith('faltan datos:')||t==='faltan datos';
   })||null;
 }
 function completeButton(box){return [...box.querySelectorAll('button')].find(b=>!b.closest('.v43104-alert-band')&&norm(b.textContent).includes('completar datos'))||box.querySelector('.v43104-alert-actions button')||null}
 function sourceContainer(missing,complete,box){
   if(!missing)return complete?.parentElement||null;
   let cur=missing;
   for(let i=0;cur&&cur!==box&&i<7;i++,cur=cur.parentElement){
     if(complete&&cur.contains(complete)&&norm(cur.textContent).length<500)return cur;
   }
   return missing.parentElement;
 }
 function ensureAlert(){
   const box=boxNow();if(!box)return false;
   const head=box.querySelector('.v492-clinical-head');if(!head)return false;
   const missing=originalMissing(box);
   let complete=completeButton(box);
   const name=patientName(box),badName=incompleteName(name);
   let band=box.querySelector('.v43104-alert-band');
   if(!missing&&!badName){if(band)band.remove();return false}
   if(!band){
     band=document.createElement('section');band.className='v43104-alert-band';
     band.innerHTML='<div class="v43104-alert-icon" aria-hidden="true">⚠</div><div class="v43104-alert-copy"><div class="v43104-alert-title">Atención al registro del paciente</div><div class="v43104-alert-lines"></div></div><div class="v43104-alert-actions"></div>';
     head.insertAdjacentElement('afterend',band);
   }
   const lines=band.querySelector('.v43104-alert-lines');lines.innerHTML='';
   if(missing){
     const raw=String(missing.textContent||'').replace(/^\s*[⚠️⚠\s]*/,'').trim();
     const colon=raw.indexOf(':');const detail=(colon>=0?raw.slice(colon+1):raw.replace(/^faltan datos\s*/i,'')).trim();
     const line=document.createElement('div');line.className='v43104-alert-line';line.innerHTML='⚠ <b>Faltan datos:</b> '+(detail||'completa la ficha del paciente');lines.appendChild(line);
   }
   if(badName){const line=document.createElement('div');line.className='v43104-alert-line';line.innerHTML='⚠ <b>Nombre incompleto:</b> ideal registrar dos apellidos y dos nombres';lines.appendChild(line)}
   const actions=band.querySelector('.v43104-alert-actions');
   if(complete&&!actions.contains(complete))actions.appendChild(complete);
   const old=sourceContainer(missing,complete,box);
   if(old&&old!==band&&!old.contains(band)&&!band.contains(old))old.classList.add('v43104-old-warning-source');
   if(missing)missing.style.display='none';
   return true;
 }
 function run(){ensureAlert()}
 document.addEventListener('click',()=>{setTimeout(run,0);setTimeout(run,80);setTimeout(run,220)},true);
 document.addEventListener('change',()=>setTimeout(run,0),true);
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(run,180),{once:true});else setTimeout(run,180);
})();"""
V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\n" + V43104_ALERT_CSS
V460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\n" + V43104_ALERT_JS

V440_OPS_CSS = r"""/* v4.4.0 — Centro operativo */
.ops-nav-icon{font-size:16px!important}.ops-page-head{display:flex;align-items:flex-end;justify-content:space-between;gap:14px;margin-bottom:14px}.ops-page-head h1{margin:0 0 3px}.ops-page-head p{margin:0}.ops-tabs{display:flex;gap:7px;margin-bottom:12px}.ops-tabs button{min-height:34px;border-radius:10px;padding:7px 13px}.ops-tabs button.active{background:#203f60;color:#fff;border-color:#203f60}.ops-toolbar{display:flex;align-items:center;gap:8px;margin-bottom:10px}.ops-toolbar input{min-width:260px;max-width:420px}.ops-list{display:grid;gap:8px}.ops-card{display:grid;grid-template-columns:42px minmax(0,1fr) auto;align-items:center;gap:11px;padding:11px 12px;border:1px solid #dfe7ef;border-radius:13px;background:#fff}.ops-card-icon{width:36px;height:36px;border-radius:11px;display:grid;place-items:center;background:#edf3f9;color:#3d6388;font-size:18px}.ops-card-copy{min-width:0;display:grid;gap:2px}.ops-card-copy b{font-size:12px;color:#263e58}.ops-card-copy span{font-size:10px;color:#607287}.ops-card-copy small{font-size:8.5px;color:#8794a3}.ops-card-actions{display:flex;gap:6px;align-items:center}.ops-card-actions button{min-height:32px;font-size:9px;padding:6px 9px;border-radius:9px}.ops-empty{padding:28px;text-align:center;border:1px dashed #ccd8e4;border-radius:14px;color:#78889a;background:#fbfcfe}.ops-origin{font-weight:850;color:#526d88}.ops-toast{position:fixed;right:20px;bottom:20px;z-index:10050;display:flex;align-items:center;gap:12px;max-width:min(520px,calc(100vw - 32px));padding:12px 13px;border-radius:13px;background:#18324b;color:#fff;box-shadow:0 12px 34px rgba(14,35,55,.28)}.ops-toast-copy{display:grid;gap:2px;min-width:0}.ops-toast-copy b{font-size:11px}.ops-toast-copy small{font-size:8.5px;color:#d8e4ef}.ops-toast button{background:#fff;color:#18324b;border:0;font-weight:900;white-space:nowrap}.ops-toast .ops-toast-close{background:transparent;color:#fff;padding:4px 6px;font-size:16px}.ops-diagnostic-panel{margin-bottom:12px}.ops-diagnostic-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px;margin-top:10px}.diag-item{padding:9px 10px;border:1px solid #dfe7ef;border-radius:11px;background:#fff;display:grid;grid-template-columns:10px minmax(0,1fr);gap:7px;align-items:start}.diag-dot{width:9px;height:9px;border-radius:50%;margin-top:3px;background:#9aa7b5}.diag-item.ok .diag-dot{background:#3d9b67}.diag-item.warn .diag-dot{background:#d49a22}.diag-item.bad .diag-dot{background:#ca5656}.diag-copy{display:grid;gap:2px;min-width:0}.diag-copy b{font-size:9px;color:#334c65}.diag-copy span{font-size:8px;color:#718193;line-height:1.25}.diag-actions{display:flex;gap:7px;margin-top:10px}@media(max-width:720px){.ops-card{grid-template-columns:38px 1fr}.ops-card-actions{grid-column:1/-1;justify-content:flex-end}.ops-diagnostic-grid{grid-template-columns:1fr}}
"""
V440_OPS_JS = r""";(()=>{
 if(window.__v440Ops)return;window.__v440Ops=true;
 const opsEsc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
 const opsDateTime=v=>{if(!v)return '';const d=new Date(v);if(Number.isNaN(d.getTime()))return String(v);return `${String(d.getDate()).padStart(2,'0')}/${String(d.getMonth()+1).padStart(2,'0')}/${d.getFullYear()} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`};
 const actionLabels={crear_paciente:'Paciente creado',crear_paciente_offline:'Paciente creado',editar_paciente:'Paciente editado',editar_paciente_offline:'Paciente editado',borrar_paciente:'Paciente eliminado',borrar_paciente_offline:'Paciente eliminado',crear_atencion:'Atención registrada',crear_atencion_offline:'Atención registrada',borrar_atencion:'Atención eliminada',borrar_atencion_offline:'Atención eliminada',eliminar_cita:'Cita eliminada',crear_cita:'Cita creada',editar_cita:'Cita editada',reagendar_cita:'Cita reagendada',restaurar_desde_papelera:'Elemento restaurado',guardar_en_papelera:'Guardado en Papelera',vaciar_elemento_papelera:'Eliminado definitivamente',aprobar_factura:'Factura aprobada',emitir_factura:'Factura emitida',marcar_factura_emitida:'Factura emitida'};
 function actionLabel(a){return actionLabels[a]||String(a||'Actividad').replace(/_/g,' ').replace(/\b\w/g,m=>m.toUpperCase())} function actionIcon(a){const x=String(a||'');if(x.includes('paciente'))return '👤';if(x.includes('atencion'))return '✚';if(x.includes('cita')||x.includes('agenda'))return '▣';if(x.includes('factura')||x.includes('azur'))return '$';if(x.includes('papelera')||x.includes('restaur'))return '↶';return '•'}
 function ensureOpsUI(){const nav=document.querySelector('.side-nav');const configBtn=nav?.querySelector('[data-section="config"]');if(nav&&configBtn&&!nav.querySelector('[data-section="actividad"]'))configBtn.insertAdjacentHTML('beforebegin','<button class="nav-btn" data-section="actividad" onclick="show(\'actividad\')"><span class="nav-icon ops-nav-icon">◷</span><span>Actividad</span></button>');const config=document.querySelector('#config');if(config&&!document.querySelector('#actividad')){const section=document.createElement('section');section.id='actividad';section.className='hidden';section.innerHTML=`<div class="ops-page-head"><div><h1>Actividad</h1><p class="muted">Cambios importantes del consultorio y elementos recuperables.</p></div></div><div class="ops-tabs"><button id="opsActivityTab" class="active" onclick="switchOpsTab('activity')">Actividad</button><button id="opsTrashTab" onclick="switchOpsTab('trash')">Papelera</button></div><div id="opsActivityPane"><div class="ops-toolbar"><input id="opsActivitySearch" class="uppercase-search" placeholder="BUSCAR EN ACTIVIDAD" oninput="scheduleOpsActivitySearch()"><button onclick="loadOpsActivity()">↻ Actualizar</button></div><div id="opsActivityList" class="ops-list"><div class="ops-empty">Cargando actividad…</div></div></div><div id="opsTrashPane" class="hidden"><div class="ops-toolbar"><span class="muted">Los elementos eliminados pueden restaurarse durante 7 días.</span><button onclick="loadOpsTrash()">↻ Actualizar</button></div><div id="opsTrashList" class="ops-list"><div class="ops-empty">Cargando Papelera…</div></div></div>`;config.insertAdjacentElement('beforebegin',section)}ensureDiagnosticsCard()}
 function switchOpsTab(tab){const activity=tab!=='trash';$('#opsActivityTab')?.classList.toggle('active',activity);$('#opsTrashTab')?.classList.toggle('active',!activity);$('#opsActivityPane')?.classList.toggle('hidden',!activity);$('#opsTrashPane')?.classList.toggle('hidden',activity);if(activity)loadOpsActivity();else loadOpsTrash()}window.switchOpsTab=switchOpsTab;
 let opsSearchTimer=null;window.scheduleOpsActivitySearch=()=>{clearTimeout(opsSearchTimer);opsSearchTimer=setTimeout(loadOpsActivity,220)};
 async function loadOpsActivity(){const box=$('#opsActivityList');if(!box)return;box.innerHTML='<div class="ops-empty">Cargando actividad…</div>';try{const q=String($('#opsActivitySearch')?.value||'').trim();const rows=await api('/api/ops/activity?limit=160'+(q?'&q='+encodeURIComponent(q):''));box.innerHTML=rows.map(r=>`<article class="ops-card"><div class="ops-card-icon">${actionIcon(r.action)}</div><div class="ops-card-copy"><b>${opsEsc(actionLabel(r.action))}</b><span>${opsEsc(r.detail||'Sin detalle adicional')}</span><small>${opsEsc(opsDateTime(r.ts))} · <span class="ops-origin">${opsEsc(r.origin||'PC')}</span></small></div><div></div></article>`).join('')||'<div class="ops-empty">Todavía no hay actividad registrada.</div>'}catch(e){box.innerHTML=`<div class="ops-empty">${opsEsc(e.message)}</div>`}}window.loadOpsActivity=loadOpsActivity;
 function trashIcon(t){return t==='patient'?'👤':t==='visit'?'✚':t==='appointment'||t==='staged_appointment'?'▣':'↶'}function trashType(t){return t==='patient'?'Paciente':t==='visit'?'Atención':t==='appointment'||t==='staged_appointment'?'Cita':'Elemento'}
 async function loadOpsTrash(){const box=$('#opsTrashList');if(!box)return;box.innerHTML='<div class="ops-empty">Cargando Papelera…</div>';try{const rows=await api('/api/ops/trash?limit=160');box.innerHTML=rows.map(r=>`<article class="ops-card"><div class="ops-card-icon">${trashIcon(r.entity_type)}</div><div class="ops-card-copy"><b>${opsEsc(trashType(r.entity_type))} · ${opsEsc(r.label)}</b><span>Eliminado ${opsEsc(opsDateTime(r.deleted_at))} · ${opsEsc(r.origin||'PC')}</span><small>${Number(r.days_left||0)} día${Number(r.days_left||0)===1?'':'s'} para recuperación automática</small></div><div class="ops-card-actions"><button class="primary-soft" onclick="restoreTrash(${Number(r.id)})">↶ Restaurar</button><button class="danger ghost" onclick="deleteTrashForever(${Number(r.id)})">Eliminar definitivo</button></div></article>`).join('')||'<div class="ops-empty">La Papelera está vacía.</div>'}catch(e){box.innerHTML=`<div class="ops-empty">${opsEsc(e.message)}</div>`}}window.loadOpsTrash=loadOpsTrash;
 async function restoreTrash(id){try{await singleFlightMutation(`trash:restore:${id}`,async()=>{const d=await api(`/api/ops/trash/${id}/restore`,{method:'POST'});await loadOpsTrash();await loadOpsActivity();try{invalidateAttentionWeekCache()}catch{}try{invalidateAgendaSlotCache()}catch{}try{await refreshVisibleSectionLocal()}catch{}return d},'Restaurando…')}catch(e){alert(e.message)}}window.restoreTrash=restoreTrash;
 async function deleteTrashForever(id){if(!confirm('¿Eliminar definitivamente este elemento de la Papelera? Después ya no podrá recuperarse.'))return;try{await api(`/api/ops/trash/${id}`,{method:'DELETE'});await loadOpsTrash()}catch(e){alert(e.message)}}window.deleteTrashForever=deleteTrashForever;
 function showUndoToast(data){if(!data?.trash_id)return;document.querySelector('.ops-toast')?.remove();const t=document.createElement('div');t.className='ops-toast';t.innerHTML=`<div class="ops-toast-copy"><b>Elemento enviado a Papelera</b><small>${opsEsc(data.trash_label||'Puedes recuperarlo durante 7 días.')}</small></div><button onclick="undoTrashFromToast(${Number(data.trash_id)})">Deshacer</button><button class="ops-toast-close" onclick="this.parentElement.remove()">×</button>`;document.body.appendChild(t);setTimeout(()=>t.remove(),9000)}
 async function undoTrashFromToast(id){try{await api(`/api/ops/trash/${id}/restore`,{method:'POST'});document.querySelector('.ops-toast')?.remove();try{invalidateAttentionWeekCache()}catch{}try{invalidateAgendaSlotCache()}catch{}try{await refreshVisibleSectionLocal()}catch{}if(!$('#agenda')?.classList.contains('hidden'))await loadAgenda()}catch(e){alert(e.message)}}window.undoTrashFromToast=undoTrashFromToast;
 function ensureDiagnosticsCard(){const sys=document.querySelector('[data-config-section="sistema"]'),panel=sys?.querySelector('.system-status-panel');if(!panel||panel.querySelector('#opsDiagnosticControls'))return;panel.querySelector('#opsDiagnosticPanel')?.remove();const head=panel.querySelector('.config-panel-head h3');if(head)head.textContent='Resumen de datos y servicios';const grid=panel.querySelector('#systemStatusGrid');const wrap=document.createElement('div');wrap.id='opsDiagnosticControls';wrap.className='ops-diagnostic-integrated';wrap.innerHTML='<div class="diag-actions"><button class="primary-soft" onclick="runOpsDiagnostics()">🔧 Revisar sistema</button><button id="copyOpsDiagnosticsBtn" class="hidden" onclick="copyOpsDiagnostics()">Copiar diagnóstico</button></div><div id="opsDiagnosticGrid" class="ops-diagnostic-grid hidden"></div>';if(grid)grid.insertAdjacentElement('afterend',wrap);else panel.appendChild(wrap)}let lastSafeDiagnostic='';async function runOpsDiagnostics(){const box=$('#opsDiagnosticGrid');if(!box)return;box.classList.remove('hidden');box.innerHTML='<div class="muted">Comprobando servicios…</div>';try{const d=await api('/api/ops/diagnostics');lastSafeDiagnostic=d.safe_text||'';const order=['local','neon','azur','whatsapp','mensajes','agenda','updates'];box.innerHTML=order.map(k=>{const x=d.services?.[k]||{},state=String(x.status||x.state||'').toUpperCase(),cls=['ONLINE','OK','READY','ACTIVO'].some(v=>state.includes(v))?'ok':['OFFLINE','ERROR','FAILED'].some(v=>state.includes(v))?'bad':'warn';return `<div class="diag-item ${cls}"><span class="diag-dot"></span><div class="diag-copy"><b>${opsEsc(x.name||k)}</b><span>${opsEsc(x.detail||x.message||state||'Sin detalle')}</span></div></div>`}).join('');$('#copyOpsDiagnosticsBtn')?.classList.remove('hidden')}catch(e){box.innerHTML=`<div class="muted">${opsEsc(e.message)}</div>`}}window.runOpsDiagnostics=runOpsDiagnostics;async function copyOpsDiagnostics(){if(!lastSafeDiagnostic)return;try{await navigator.clipboard.writeText(lastSafeDiagnostic);alert('Diagnóstico copiado.')}catch{prompt('Copia este diagnóstico:',lastSafeDiagnostic)}}window.copyOpsDiagnostics=copyOpsDiagnostics;
 window.deletePatient=async function(id,visitCount){const extra=visitCount?` También se eliminarán ${visitCount} atención${visitCount===1?'':'es'} asociada${visitCount===1?'':'s'}.`:'';if(!confirmDeletion(`¿Borrar este paciente?${extra}\n\nPodrás recuperarlo desde Actividad > Papelera durante 7 días.`))return;try{await singleFlightMutation(`patient:delete:${id}`,async()=>{const d=await api('/api/safety/patients/'+id,{method:'DELETE'});closeModal();show('pacientes');await searchPatients();await Promise.all([loadWeek(selectedHomeDate||toISO(new Date())),refreshPendingBadges()]);showUndoToast(d)},'Borrando…')}catch(e){alert(e.message)}};
 window.deleteVisit=async function(visitId,patientId){if(!confirmDeletion('¿Borrar esta atención? Se enviará a Papelera durante 7 días.'))return;try{await singleFlightMutation(`visit:delete:${visitId}`,async()=>{const d=await api('/api/safety/visits/'+visitId,{method:'DELETE'});invalidateAttentionWeekCache();await fullOpenPatient(patientId,'patients');await Promise.all([loadWeek(selectedHomeDate||toISO(new Date())),refreshPendingBadges()]);showUndoToast(d)},'Borrando…')}catch(e){alert(e.message)}};
 window.deleteVisitFromHome=async function(visitId,fecha){if(!confirmDeletion('¿Borrar esta atención? Se enviará a Papelera durante 7 días y se quitará su pre-factura asociada.'))return;try{await singleFlightMutation(`visit:delete:${visitId}`,async()=>{const d=await api('/api/safety/visits/'+visitId,{method:'DELETE'});invalidateAttentionWeekCache();await Promise.all([loadWeek(fecha||selectedHomeDate||toISO(new Date()),fecha||selectedHomeDate),refreshPendingBadges()]);showUndoToast(d)},'Borrando…')}catch(e){alert(e.message)}};
 window.deleteAgendaAppointment=async function(id){if(!confirmDeletion('¿Eliminar esta cita y liberar el horario? La ficha del paciente no se borrará y podrás restaurar la cita durante 7 días.'))return;try{await singleFlightMutation(`appointment:delete:${id}`,async()=>{const d=await api(`/api/safety/appointments/${id}`,{method:'DELETE'});invalidateAgendaSlotCache();invalidateAttentionWeekCache();closeModal();await loadAgenda();showUndoToast(d)},'Eliminando…')}catch(e){alert(e.message)}};
 window.deleteUnlinkedAppointment=async function(itemId){if(!confirmDeletion('¿Eliminar esta cita y liberar el horario? Podrás recuperarla desde Papelera durante 7 días.'))return;try{const d=await api(`/api/safety/unlinked/${Number(itemId)}`,{method:'DELETE'});closeModal();invalidateAgendaSlotCache();invalidateAttentionWeekCache();await loadAgenda();showUndoToast(d)}catch(e){alert(e.message)}};
 const oldShow=window.show;if(typeof oldShow==='function')window.show=function(id,configTab=null){const r=oldShow(id,configTab);if(id==='actividad')setTimeout(()=>switchOpsTab('activity'),0);if(id==='config')setTimeout(ensureDiagnosticsCard,0);return r};
function init(){ensureOpsUI()}if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else setTimeout(init,0);
})();"""
V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\n" + V440_OPS_CSS
V460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\n" + V440_OPS_JS

V441_FIX_CSS = r"""/* v4.4.1 — correcciones operativas y lectura local estricta */
.patient-name-button{appearance:none!important;background:transparent!important;border:0!important;padding:0!important;margin:0!important;color:inherit!important;font:inherit!important;font-weight:inherit!important;text-align:left!important;cursor:pointer!important;box-shadow:none!important;min-height:0!important;line-height:inherit!important}
.patient-name-button:hover{text-decoration:underline!important;color:#245f98!important}
.ops-diagnostic-panel{display:none!important}
.ops-diagnostic-integrated{margin-top:12px!important;padding-top:12px!important;border-top:1px solid #e1e8ef!important}
.ops-diagnostic-integrated .diag-actions{display:flex!important;gap:9px!important;align-items:center!important;margin-top:0!important}
.ops-diagnostic-integrated .diag-actions button{min-height:42px!important;padding:10px 16px!important;font-size:12px!important;font-weight:900!important;border-radius:10px!important}
.ops-diagnostic-integrated .ops-diagnostic-grid{margin-top:11px!important}
.ops-diagnostic-integrated .diag-item{padding:11px 12px!important}
.ops-diagnostic-integrated .diag-copy b{font-size:11px!important}.ops-diagnostic-integrated .diag-copy span{font-size:10px!important;line-height:1.35!important}
"""
V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\n" + V441_FIX_CSS

V442_CLEAN_CSS = r"""/* v4.4.2 — Atender directo desde Agenda */
.attention-agenda-only .modal-form-heading{margin-bottom:12px!important}
.attention-agenda-only .attention-week-block{margin-top:0!important}
"""
V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\n" + V442_CLEAN_CSS

V443_CLEANUP_CSS = r"""/* v4.4.3 — limpia restos visuales de Nueva atención */
.v443-attention-empty-hidden{display:none!important;height:0!important;min-height:0!important;margin:0!important;padding:0!important;border:0!important;overflow:hidden!important}
.v492-attention .attention-form-modal>.v492-selection-head,
.v492-attention .attention-form-modal>.v491-attention-title,
.v492-attention .attention-form-modal>.v491-selection-help{display:none!important;height:0!important;min-height:0!important;margin:0!important;padding:0!important;border:0!important;overflow:hidden!important}
"""
V443_CLEANUP_JS = r""";(()=>{
 if(window.__v443Cleanup)return;window.__v443Cleanup=true;
 function deadHash(a){
   if(!a||a.tagName!=='A'||!a.hasAttribute('href'))return false;
   const raw=String(a.getAttribute('href')||'').trim();
   return raw==='#'||raw==='./#'||raw==='/#';
 }
 function sanitizeHashLinks(root=document){
   root.querySelectorAll?.('a[href]').forEach(a=>{
     if(!deadHash(a))return;
     a.removeAttribute('href');
     if(!a.hasAttribute('role'))a.setAttribute('role','button');
     if(!a.hasAttribute('tabindex'))a.tabIndex=0;
   });
 }
 function cleanAttentionGhostRows(){
   const box=document.querySelector('#modal .modalbox');
   const form=box?.querySelector('.attention-form-modal');
   if(!form||!box.classList.contains('v492-attention'))return;
   if(!box.querySelector('.v492-clinical-head')||!form.querySelector('.service-groups.v43103-native-services,.service-groups'))return;
   const candidates=[
     form.querySelector('#attentionStatus'),
     form.querySelector('.attention-date-card'),
     form.querySelector('.service-title.enhanced'),
     ...form.querySelectorAll('.v492-selection-head,.v491-attention-title,.v491-selection-help,.v492-empty-source,.v493-old-alert,.v494-ghost-hidden')
   ];
   candidates.forEach(el=>{
     if(!el||el.closest('.v492-clinical-head')||el.closest('.service-groups'))return;
     const text=String(el.innerText||'').replace(/\s+/g,' ').trim();
     const live=el.querySelector('input:not([type="hidden"]),select,textarea,button:not([style*="display: none"])');
     if(!text&&!live)el.classList.add('v443-attention-empty-hidden');
     else if(el.matches('.service-title.enhanced,.v492-selection-head,.v491-attention-title,.v491-selection-help'))el.classList.add('v443-attention-empty-hidden');
   });
 }
 function run(){sanitizeHashLinks();cleanAttentionGhostRows()}
 document.addEventListener('pointerover',e=>{const a=e.target?.closest?.('a');if(deadHash(a))sanitizeHashLinks(a.parentElement||document)},true);
 document.addEventListener('focusin',e=>{const a=e.target?.closest?.('a');if(deadHash(a))sanitizeHashLinks(a.parentElement||document)},true);
 document.addEventListener('click',()=>{setTimeout(run,0);setTimeout(run,80);setTimeout(run,220)},true);
 document.addEventListener('change',()=>setTimeout(cleanAttentionGhostRows,0),true);
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(run,120),{once:true});else setTimeout(run,120);
})();"""
V460_OVERLAY_CSS = (V460_OVERLAY_CSS or "") + "\n" + V443_CLEANUP_CSS
V460_OVERLAY_JS = (V460_OVERLAY_JS or "") + "\n" + V443_CLEANUP_JS

@app.get("/v460/overlay.css")
def v460_overlay_css():
    return Response(content=V460_OVERLAY_CSS, media_type="text/css; charset=utf-8", headers={"Cache-Control":"no-store"})

@app.get("/v460/overlay.js")
def v460_overlay_js():
    return Response(content=V460_OVERLAY_JS, media_type="application/javascript; charset=utf-8", headers={"Cache-Control":"no-store"})


@app.get("/api/update/info")
def update_info(user: User = Depends(current_user)):
    return {
        "version": APP_VERSION,
        "mode": "package",
        "message": "Paquetes compatibles pueden aplicarse aquí; siempre se crea un respaldo antes de actualizar.",
    }


@app.post("/api/update/apply")
async def apply_update_package(
    package: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    if user.role != "admin":
        raise HTTPException(403, "Solo el administrador puede actualizar el programa")
    filename = (package.filename or "").lower()
    if not filename.endswith(".zip"):
        raise HTTPException(400, "Selecciona un paquete ZIP de actualización")

    raw = await package.read()
    if len(raw) > 50 * 1024 * 1024:
        raise HTTPException(400, "El paquete de actualización es demasiado grande")

    with tempfile.TemporaryDirectory(prefix="rp_update_") as tmp:
        tmp_path = Path(tmp)
        zip_path = tmp_path / "update.zip"
        zip_path.write_bytes(raw)
        try:
            with zipfile.ZipFile(zip_path) as zf:
                for member in zf.namelist():
                    _safe_update_member_path(tmp_path / "extract", member)
                zf.extractall(tmp_path / "extract")
        except zipfile.BadZipFile:
            raise HTTPException(400, "El archivo ZIP está dañado")

        manifests = list((tmp_path / "extract").rglob("update_manifest.json"))
        if not manifests:
            raise HTTPException(400, "Este ZIP no es un paquete de actualización compatible")
        manifest_path = manifests[0]
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            raise HTTPException(400, "No se pudo leer el manifiesto de actualización")
        if manifest.get("product") != "recepcion-pacientes":
            raise HTTPException(400, "El paquete no corresponde a Recepción de Pacientes")
        new_version = str(manifest.get("version") or "").strip()
        if not new_version:
            raise HTTPException(400, "El paquete no indica su versión")
        if new_version == APP_VERSION:
            raise HTTPException(409, f"La versión {new_version} ya está instalada")

        package_root = manifest_path.parent
        copy_items = manifest.get("copy") or [
            "app.py", "requirements.txt", "ABRIR_RECEPCION.py", "INICIAR.bat",
            "ABRIR_RECEPCION.bat", "CERRAR_RECEPCION.bat", "CREAR_ACCESO_DIRECTO.bat",
            "REPARAR_ACCESO_DIRECTO.bat", "static", "README.md", "MODO_DE_USO.txt", "NUBE_LEEME.txt"
        ]
        prohibited = {".env", "data", ".venv", "BASE DE DATOS 2026.xlsx"}
        for item in copy_items:
            top = Path(item).parts[0] if Path(item).parts else ""
            if top in prohibited:
                raise HTTPException(400, f"El paquete intenta reemplazar un archivo protegido: {top}")
            if not (package_root / item).exists():
                raise HTTPException(400, f"Falta un componente de actualización: {item}")

        backup_path = _app_backup_zip()
        for item in copy_items:
            src = package_root / item
            dst = Path(BASE_DIR) / item
            if src.is_dir():
                dst.mkdir(parents=True, exist_ok=True)
                for child in src.rglob("*"):
                    rel = child.relative_to(src)
                    target = dst / rel
                    if child.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(child, target)
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)

        audit(db, user, "aplicar_actualizacion", f"{APP_VERSION} -> {new_version}; respaldo {Path(backup_path).name}")
        db.commit()

        # Desde v3.9.5 las futuras actualizaciones se reinician solas.
        # El ayudante se inicia con el Python de la instalación, espera a que
        # esta respuesta salga y luego levanta app.py ya reemplazado.
        python_exe = sys.executable
        app_path = os.path.join(BASE_DIR, "app.py")
        helper = (
            "import os,subprocess,time;"
            "time.sleep(2.0);"
            "flags=(getattr(subprocess,'CREATE_NO_WINDOW',0)|getattr(subprocess,'DETACHED_PROCESS',0)) if os.name=='nt' else 0;"
            f"subprocess.Popen([{python_exe!r},{app_path!r}],cwd={BASE_DIR!r},stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=flags,close_fds=True)"
        )
        try:
            subprocess.Popen([python_exe, "-c", helper], cwd=BASE_DIR, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=(getattr(subprocess,'CREATE_NO_WINDOW',0)|getattr(subprocess,'DETACHED_PROCESS',0)) if os.name=='nt' else 0, close_fds=True)
            threading.Timer(0.9, lambda: os._exit(0)).start()
        except Exception:
            pass
        return {
            "ok": True,
            "from_version": APP_VERSION,
            "to_version": new_version,
            "backup": Path(backup_path).name,
            "restart_required": False,
            "restarting": True,
        }


def _downloads_dir() -> Path:
    """Carpeta Descargas del mismo usuario que ejecuta Recepción.

    En WebView2 evitamos depender del gestor de descargas del navegador y
    guardamos el archivo desde el servidor local.
    """
    candidates = []
    profile = (os.getenv("USERPROFILE") or "").strip()
    if profile:
        candidates.append(Path(profile) / "Downloads")
    try:
        candidates.append(Path.home() / "Downloads")
    except Exception:
        pass
    candidates.append(Path(DATA_DIR) / "exports")
    for folder in candidates:
        try:
            folder.mkdir(parents=True, exist_ok=True)
            test = folder / ".recepcion_write_test"
            test.write_text("ok", encoding="utf-8")
            test.unlink(missing_ok=True)
            return folder
        except Exception:
            continue
    raise HTTPException(500, "No se encontró una carpeta donde guardar el Excel")


def _unique_export_path(folder: Path, filename: str) -> Path:
    target = folder / filename
    if not target.exists():
        return target
    stem, suffix = target.stem, target.suffix
    for n in range(2, 1000):
        candidate = folder / f"{stem} ({n}){suffix}"
        if not candidate.exists():
            return candidate
    return folder / f"{stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{suffix}"


@app.post("/api/export.xlsx/save")
def save_xlsx_to_downloads(desde: date, hasta: date, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if hasta < desde:
        raise HTTPException(400, "La fecha Hasta no puede ser anterior a Desde")
    data = build_report_payload(db, desde, hasta)
    content = build_report_xlsx(data, desde, hasta)
    folder = _downloads_dir()
    filename = f"reporte_atenciones_{desde}_{hasta}.xlsx"
    target = _unique_export_path(folder, filename)
    try:
        target.write_bytes(content)
    except Exception as exc:
        raise HTTPException(500, f"No se pudo guardar el Excel: {exc}")
    audit(db, user, "exportar_excel", f"{desde} a {hasta}; guardado en {target}; {data['patients']} pacientes; total {data['total']:.2f}")
    db.commit()
    return {
        "ok": True,
        "filename": target.name,
        "folder": str(target.parent),
        "path": str(target),
        "patients": data["patients"],
        "total": data["total"],
    }


@app.get("/api/export.xlsx")
def export_xlsx(desde: date, hasta: date, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if hasta < desde:
        raise HTTPException(400, "La fecha Hasta no puede ser anterior a Desde")
    data = build_report_payload(db, desde, hasta)
    content = build_report_xlsx(data, desde, hasta)
    audit(db, user, "exportar_excel", f"{desde} a {hasta}; {data['patients']} pacientes; total {data['total']:.2f}")
    db.commit()
    filename = f"reporte_atenciones_{desde}_{hasta}.xlsx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _build_report_csv(db: Session, desde: date, hasta: date) -> str:
    rows = db.execute(
        select(Visit, Patient).join(Patient).where(Visit.fecha >= desde, Visit.fecha <= hasta).order_by(Visit.fecha, Visit.id)
    ).all()
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Fecha", "Cédula", "Nombre", "Nacimiento", "Celular", "Estado", "Procedimiento", "Correo", "Lugar", "Valor", "Observación"])
    for v, p in rows:
        w.writerow([
            v.fecha, p.cedula or "", p.nombre, p.fecha_nacimiento or "", p.celular or "", v.tipo,
            v.procedimiento or "CONSULTA", p.correo or "", p.lugar or "",
            float(v.valor) if v.valor is not None else "", v.observacion or "",
        ])
    return "\ufeff" + out.getvalue()


@app.post("/api/export.csv/save")
def save_csv_to_downloads(desde: date, hasta: date, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if hasta < desde:
        raise HTTPException(400, "La fecha Hasta no puede ser anterior a Desde")
    data = _build_report_csv(db, desde, hasta)
    folder = _downloads_dir()
    target = _unique_export_path(folder, f"atenciones_{desde}_{hasta}.csv")
    try:
        target.write_bytes(data.encode("utf-8"))
    except Exception as exc:
        raise HTTPException(500, f"No se pudo guardar el CSV: {exc}")
    audit(db, user, "exportar_csv", f"{desde} a {hasta}; guardado en {target}")
    db.commit()
    return {"ok": True, "filename": target.name, "folder": str(target.parent), "path": str(target)}


@app.get("/api/export.csv")
def export_csv(desde: date, hasta: date, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if hasta < desde:
        raise HTTPException(400, "La fecha Hasta no puede ser anterior a Desde")
    data = _build_report_csv(db, desde, hasta)
    audit(db, user, "exportar_csv", f"{desde} a {hasta}")
    db.commit()
    return StreamingResponse(
        iter([data.encode("utf-8")]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="atenciones_{desde}_{hasta}.csv"'},
    )




# v4.3.58 — el launcher autocontenido es el único instalador.
@app.post("/api/program/update-now")
def program_update_now():
    """Comprueba el canal sin reemplazar archivos desde el backend en ejecución."""
    try:
        info = _read_update_channel_status()
        if info["update_available"]:
            return {
                "ok": True, "update": True, "current": info["local"], "latest": info["latest"],
                "message": f"Hay una actualización {info['latest']} disponible. Cierra y vuelve a abrir Recepción para que el launcher la instale de forma segura.",
            }
        return {
            "ok": True, "update": False, "current": info["local"], "latest": info["latest"],
            "message": f"Programa actualizado. El paquete {info['local']} coincide con el canal oficial.",
        }
    except Exception as exc:
        return {"ok": False, "update": False, "current": APP_VERSION, "message": f"No se pudo consultar el canal: {str(exc)[:200]}"}


# ---------------------------------------------------------------------------
# v4.4.18 — Bandeja de respuestas de WhatsApp
# ---------------------------------------------------------------------------
# Las respuestas entrantes viven en Neon, dentro de whatsapp_cloud, porque el
# webhook funciona 24/7 aunque la PC esté apagada. La PC solo consulta esta
# bandeja cuando recepción abre Inicio o la sección Respuestas WhatsApp.

def _wa_inbound_table_ready(conn) -> bool:
    try:
        return conn.execute(text("SELECT to_regclass('whatsapp_cloud.inbound_responses')")).scalar() is not None
    except Exception:
        return False


def _wa_cloud_unavailable_payload() -> dict:
    return {
        "available": False,
        "pending": 0,
        "items": [],
        "message": "Las respuestas de WhatsApp necesitan conexión con Neon.",
    }


def _wa_json_row(row) -> dict:
    out = dict(row)
    for key, value in list(out.items()):
        if value is None or isinstance(value, (str, int, float, bool)):
            continue
        try:
            out[key] = value.isoformat()
        except Exception:
            out[key] = str(value)
    return out


def _wa_apply_ok(result: str) -> bool:
    value = str(result or "").strip().upper()
    if not value or value in {"NOT_FOUND", "STALE", "UNKNOWN"}:
        return False
    return not (value.startswith("ERROR") or value.startswith("INVALID"))



WA_TEST_CLEANUP_PHONE_V4424 = "593967841449"
WA_TEST_CLEANUP_CUTOFF_V4424 = datetime(2026, 8, 31, 1, 29, 0)

@app.post("/api/whatsapp-responses/cleanup-old-tests")
def whatsapp_cleanup_old_tests_v4424(user: User = Depends(current_user)):
    if FORCE_OFFLINE or cloud_engine is None:
        return {"available": False, "cleaned": 0}
    try:
        with cloud_engine.begin() as conn:
            if not _wa_inbound_table_ready(conn):
                return {"available": True, "ready": False, "cleaned": 0}
            result = conn.execute(text("""
                UPDATE whatsapp_cloud.inbound_responses
                SET resolved_at = COALESCE(resolved_at, CURRENT_TIMESTAMP),
                    resolved_by = 'cleanup-v4.4.24',
                    resolution = 'RESUELTO'
                WHERE resolved_at IS NULL
                  AND upper(coalesce(interpretation,'')) = 'REVISAR'
                  AND regexp_replace(coalesce(phone,''), '[^0-9]', '', 'g') = :phone
                  AND received_at < :cutoff
            """), {
                "phone": WA_TEST_CLEANUP_PHONE_V4424,
                "cutoff": WA_TEST_CLEANUP_CUTOFF_V4424,
            })
            return {"available": True, "ready": True, "cleaned": max(0, int(result.rowcount or 0))}
    except Exception as exc:
        return {"available": False, "cleaned": 0, "error": str(exc)[:180]}


@app.get("/api/auto-bookings/recent")
def auto_bookings_recent_v4425(db: Session = Depends(get_db), user: User = Depends(current_user)):
    try:
        cutoff = date.today() - timedelta(days=1)
        rows = list(db.scalars(
            select(ConfirmafyAgendaItem)
            .where(
                ConfirmafyAgendaItem.source_hash.like("mobile:autoagenda:%"),
                ConfirmafyAgendaItem.fecha >= cutoff,
            )
            .order_by(ConfirmafyAgendaItem.created_at.desc(), ConfirmafyAgendaItem.id.desc())
            .limit(50)
        ))
        return {
            "items": [
                {
                    "id": int(x.id),
                    "source_hash": str(x.source_hash or ""),
                    "nombre": str(x.nombre or "PACIENTE"),
                    "celular": str(x.celular or ""),
                    "fecha": x.fecha.isoformat() if x.fecha else "",
                    "hora": str(x.hora or "")[:5],
                    "created_at": x.created_at.isoformat() if x.created_at else None,
                }
                for x in rows
            ],
            "source": "sqlite-local",
        }
    except Exception as exc:
        return {"items": [], "source": "sqlite-local", "error": str(exc)[:160]}

@app.get("/api/whatsapp-responses/count")
def whatsapp_responses_count(user: User = Depends(current_user)):
    if FORCE_OFFLINE or cloud_engine is None:
        return _wa_cloud_unavailable_payload()
    try:
        with cloud_engine.connect() as conn:
            if not _wa_inbound_table_ready(conn):
                return {"available": True, "pending": 0, "items": [], "ready": False}
            pending = int(conn.execute(text("""
                SELECT count(*)
                FROM whatsapp_cloud.inbound_responses
                WHERE resolved_at IS NULL AND upper(coalesce(interpretation,''))='REVISAR'
            """)).scalar() or 0)
            return {"available": True, "ready": True, "pending": pending}
    except Exception as exc:
        return {**_wa_cloud_unavailable_payload(), "error": str(exc)[:180]}


@app.get("/api/whatsapp-responses")
def whatsapp_responses_list(scope: str = "review", limit: int = 80, user: User = Depends(current_user)):
    scope = str(scope or "review").strip().lower()
    if scope not in {"review", "all", "resolved"}:
        scope = "review"
    limit = max(1, min(int(limit or 80), 200))
    if FORCE_OFFLINE or cloud_engine is None:
        return _wa_cloud_unavailable_payload()
    try:
        with cloud_engine.connect() as conn:
            if not _wa_inbound_table_ready(conn):
                return {"available": True, "ready": False, "pending": 0, "items": []}
            where = ""
            if scope == "review":
                where = "WHERE resolved_at IS NULL AND upper(coalesce(interpretation,''))='REVISAR'"
            elif scope == "resolved":
                where = "WHERE resolved_at IS NOT NULL"
            rows = conn.execute(text(f"""
                SELECT id,message_id,phone,message_type,raw_text,transcription,media_id,media_mime_type,
                       interpretation,confidence,source_type,source_id,appointment_date,appointment_time,
                       patient_name,match_method,apply_result,received_at,resolved_at,resolved_by,resolution
                FROM whatsapp_cloud.inbound_responses
                {where}
                ORDER BY received_at DESC, id DESC
                LIMIT :limit
            """), {"limit": limit}).mappings().all()
            pending = int(conn.execute(text("""
                SELECT count(*) FROM whatsapp_cloud.inbound_responses
                WHERE resolved_at IS NULL AND upper(coalesce(interpretation,''))='REVISAR'
            """)).scalar() or 0)
            return {"available": True, "ready": True, "pending": pending, "items": [_wa_json_row(r) for r in rows]}
    except Exception as exc:
        return {**_wa_cloud_unavailable_payload(), "error": str(exc)[:180]}


@app.post("/api/whatsapp-responses/{response_id}/resolve")
def whatsapp_response_resolve(response_id: int, payload: dict, user: User = Depends(current_user)):
    if FORCE_OFFLINE or cloud_engine is None:
        raise HTTPException(503, "Se necesita conexión con Neon para resolver esta respuesta")
    action = str((payload or {}).get("action") or "").strip().upper()
    if action not in {"CONFIRMAR", "CANCELAR", "RESUELTO"}:
        raise HTTPException(400, "Acción no válida")
    username = str(getattr(user, "username", "recepcion") or "recepcion")[:80]
    with cloud_engine.begin() as conn:
        if not _wa_inbound_table_ready(conn):
            raise HTTPException(404, "La bandeja de WhatsApp todavía no está disponible")
        row = conn.execute(text("""
            SELECT id,message_id,source_type,source_id,appointment_date,appointment_time,resolved_at
            FROM whatsapp_cloud.inbound_responses
            WHERE id=:id
            FOR UPDATE
        """), {"id": int(response_id)}).mappings().first()
        if not row:
            raise HTTPException(404, "Respuesta no encontrada")
        if action == "RESUELTO":
            conn.execute(text("""
                UPDATE whatsapp_cloud.inbound_responses
                SET resolved_at=COALESCE(resolved_at,now()), resolved_by=:user,
                    resolution='RESUELTO', updated_at=now()
                WHERE id=:id
            """), {"id": int(response_id), "user": username})
            return {"ok": True, "action": "RESUELTO"}
        source_type = str(row.get("source_type") or "").strip().lower()
        source_id = int(row.get("source_id") or 0)
        if source_type not in {"appointment", "staged"} or source_id <= 0:
            raise HTTPException(409, "No pude vincular esta respuesta con una cita. Revísala y usa Marcar como resuelto.")
        if row.get("resolved_at") is not None:
            raise HTTPException(409, "Esta respuesta ya fue resuelta. Actualiza la bandeja antes de continuar.")

        # Seguridad anti-cita-movida: la respuesta quedó ligada a una fecha/hora
        # concreta cuando llegó. Si recepción movió o cambió la cita después, no
        # aplicamos un Sí/No viejo sobre el nuevo turno.
        stored_date = str(row.get("appointment_date") or "")[:10]
        stored_time = str(row.get("appointment_time") or "")[:5]
        if source_type == "staged":
            current_slot = conn.execute(text("""
                SELECT CAST(fecha AS text) AS d, CAST(hora AS text) AS t
                FROM public.confirmafy_agenda_items WHERE id=:id
            """), {"id": source_id}).mappings().first()
        else:
            current_slot = conn.execute(text("""
                SELECT CAST(fecha AS text) AS d, CAST(hora AS text) AS t
                FROM public.appointments WHERE id=:id
            """), {"id": source_id}).mappings().first()
        current_date = str((current_slot or {}).get("d") or "")[:10]
        current_time = str((current_slot or {}).get("t") or "")[:5]
        if not current_slot or current_date != stored_date or current_time != stored_time:
            raise HTTPException(409, "La cita cambió desde que llegó este mensaje. No hice ningún cambio; actualiza y revísala manualmente.")

        message_id = f"manual:{int(response_id)}:{int(time.time())}"
        result = str(conn.execute(text("""
            SELECT public.whatsapp_apply_response(:action,:source_type,:source_id,:message_id,:phone) AS result
        """), {
            "action": action,
            "source_type": source_type,
            "source_id": source_id,
            "message_id": message_id,
            "phone": "manual-recepcion",
        }).scalar() or "UNKNOWN")
        if not _wa_apply_ok(result):
            raise HTTPException(409, f"La cita ya cambió o no pudo actualizarse ({result}). Actualiza la bandeja y revísala manualmente.")
        interpretation = "CONFIRMADO" if action == "CONFIRMAR" else "NO_ASISTIRA"
        conn.execute(text("""
            UPDATE whatsapp_cloud.inbound_responses
            SET interpretation=:interpretation, confidence=100, apply_result=:result,
                resolved_at=now(), resolved_by=:user, resolution=:resolution, updated_at=now()
            WHERE id=:id
        """), {
            "id": int(response_id), "interpretation": interpretation, "result": result,
            "user": username, "resolution": action,
        })
        return {"ok": True, "action": action, "interpretation": interpretation, "result": result}


@app.get("/api/whatsapp-responses/{response_id}/audio")
def whatsapp_response_audio(response_id: int, request: Request, user: User = Depends(current_user)):
    if FORCE_OFFLINE or cloud_engine is None:
        raise HTTPException(503, "Se necesita conexión para escuchar el audio")
    try:
        with cloud_engine.connect() as conn:
            if not _wa_inbound_table_ready(conn):
                raise HTTPException(404, "Audio no disponible")
            row = conn.execute(text("""
                SELECT message_id,media_id,media_mime_type,raw_payload->>'playback_token' AS playback_token
                FROM whatsapp_cloud.inbound_responses WHERE id=:id AND message_type='audio'
            """), {"id": int(response_id)}).mappings().first()
        if not row:
            raise HTTPException(404, "Esta respuesta no tiene un audio disponible")

        # v4.4.20: los audios nuevos se reproducen por el Worker de Cloudflare.
        # La PC nunca necesita conocer el token de Meta y el audio no se guarda en Neon.
        message_id = str(row.get("message_id") or "").strip()
        playback_token = str(row.get("playback_token") or "").strip()
        if message_id and len(message_id) <= 500 and re.fullmatch(r"[A-Fa-f0-9]{64,160}", playback_token):
            target = (
                "https://dr-revelo-whatsapp-cloud.drrevelo.workers.dev/media/audio"
                + "?message_id=" + quote(message_id, safe="")
                + "&token=" + quote(playback_token, safe="")
            )
            # v4.4.21: WebView2 ya no sigue un redirect cross-origin.
            # FastAPI obtiene el audio protegido desde Cloudflare y lo entrega
            # al reproductor como recurso local. También reenvía Range para
            # permitir play/seek correctamente sin cargar más de lo necesario.
            proxy_headers = {
                "User-Agent": "Recepcion-Dr-Revelo/4.4.22",
                "Accept": "audio/*,*/*;q=0.8",
                "Cache-Control": "no-cache",
            }
            range_header = str(request.headers.get("range") or "").strip()
            if range_header and re.fullmatch(r"bytes=\d*-\d*", range_header):
                proxy_headers["Range"] = range_header
            proxy_req = urllib.request.Request(target, headers=proxy_headers)
            try:
                with urllib.request.urlopen(proxy_req, timeout=20) as resp:
                    status_code = int(getattr(resp, "status", 200) or 200)
                    content_type = str(resp.headers.get("content-type") or row.get("media_mime_type") or "audio/ogg").strip()
                    data = resp.read(20 * 1024 * 1024 + 1)
                    response_headers = {
                        "Cache-Control": "private, no-store, max-age=0",
                        "Accept-Ranges": str(resp.headers.get("accept-ranges") or "bytes"),
                    }
                    content_range = str(resp.headers.get("content-range") or "").strip()
                    if content_range:
                        response_headers["Content-Range"] = content_range
                if len(data) > 20 * 1024 * 1024:
                    raise HTTPException(413, "El audio es demasiado grande para reproducirlo aquí")
                return Response(content=data, status_code=status_code, media_type=content_type, headers=response_headers)
            except urllib.error.HTTPError as exc:
                raise HTTPException(502, f"Cloudflare no pudo entregar el audio ({exc.code})")

        # Compatibilidad con audios previos a v2.6.4: si la PC conserva un token
        # válido, mantenemos el método antiguo. Si no, pedimos una nueva prueba.
        if not WHATSAPP_ACCESS_TOKEN:
            raise HTTPException(409, "Este audio fue recibido antes de la mejora de reproducción. Envía una nueva prueba de audio.")
        media_id = str(row.get("media_id") or "").strip()
        if not media_id or not re.fullmatch(r"[A-Za-z0-9._:-]{3,180}", media_id):
            raise HTTPException(404, "Esta respuesta no tiene un audio disponible")
        graph_version = (WHATSAPP_GRAPH_VERSION or "v26.0").strip().lstrip("/")
        meta_req = urllib.request.Request(
            f"https://graph.facebook.com/{graph_version}/{media_id}",
            headers={"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}", "User-Agent": "Recepcion-Dr-Revelo/4.4.20"},
        )
        with urllib.request.urlopen(meta_req, timeout=12) as resp:
            meta = json.loads(resp.read(512000).decode("utf-8"))
        media_url = str(meta.get("url") or "").strip()
        if not media_url.startswith("https://"):
            raise HTTPException(502, "Meta no devolvió la dirección del audio")
        audio_req = urllib.request.Request(media_url, headers={
            "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
            "User-Agent": "Recepcion-Dr-Revelo/4.4.20",
        })
        with urllib.request.urlopen(audio_req, timeout=20) as resp:
            content_type = str(resp.headers.get("content-type") or row.get("media_mime_type") or "audio/ogg").split(";", 1)[0]
            data = resp.read(20 * 1024 * 1024 + 1)
        if len(data) > 20 * 1024 * 1024:
            raise HTTPException(413, "El audio es demasiado grande para reproducirlo aquí")
        return Response(content=data, media_type=content_type, headers={"Cache-Control": "private, no-store, max-age=0"})
    except HTTPException:
        raise
    except urllib.error.HTTPError as exc:
        raise HTTPException(502, f"Meta no permitió descargar el audio ({exc.code})")
    except Exception as exc:
        raise HTTPException(502, f"No se pudo abrir el audio: {str(exc)[:160]}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=LOCAL_HTTP_PORT, reload=False, access_log=False, log_level="warning", workers=1)

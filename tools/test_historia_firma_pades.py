from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID


def _minimal_pdf(path: Path) -> None:
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>",
        b"<< /Length 0 >>\nstream\n\nendstream",
    ]
    data = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for idx, body in enumerate(objects, start=1):
        offsets.append(len(data))
        data.extend(f"{idx} 0 obj\n".encode("ascii"))
        data.extend(body)
        data.extend(b"\nendobj\n")
    xref = len(data)
    data.extend(f"xref\n0 {len(objects)+1}\n".encode("ascii"))
    data.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        data.extend(f"{off:010d} 00000 n \n".encode("ascii"))
    data.extend(
        (
            f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\n"
            f"startxref\n{xref}\n%%EOF\n"
        ).encode("ascii")
    )
    path.write_bytes(bytes(data))


def _test_pkcs12(path: Path, password: bytes) -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "EC"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Historia Clinica CI"),
            x509.NameAttribute(NameOID.COMMON_NAME, "ARMANDO ARTURO REVELO CASTILLO"),
        ]
    )
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    blob = pkcs12.serialize_key_and_certificates(
        name=b"doctor-prueba",
        key=key,
        cert=cert,
        cas=None,
        encryption_algorithm=serialization.BestAvailableEncryption(password),
    )
    path.write_bytes(blob)


def main() -> None:
    import firma_electronica as fe

    with tempfile.TemporaryDirectory(prefix="historia_pades_ci_") as temp:
        root = Path(temp)
        paths = fe._paths(root)
        paths["firma_dir"].mkdir(parents=True, exist_ok=True)
        password = b"Prueba-CI-2026"
        _test_pkcs12(paths["certificate"], password)

        meta = fe._unlock(root, password.decode("ascii"), ttl_seconds=900)
        assert fe._status(root)["unlocked"] is True
        assert meta.get("subject"), meta
        signer = fe._load_signer(root, password)
        assert fe._certificate_legal_name(signer, "Dr. Fallback") == "ARMANDO ARTURO REVELO CASTILLO"
        assert fe._STAMP_BORDER_WIDTH == 0

        source = root / "origen.pdf"
        signed = root / "firmado.pdf"
        _minimal_pdf(source)
        meta_signed = fe._sign_pdf(
            root,
            source,
            signed,
            "Dr. Armando Revelo",
            "certificado",
            "doc-prueba-001",
        )

        raw = signed.read_bytes()
        assert signed.stat().st_size > source.stat().st_size
        assert b"ETSI.CAdES.detached" in raw, "El PDF no declara el subfiltro PAdES esperado"
        assert b"ByteRange" in raw, "El PDF no contiene ByteRange de firma"
        assert b"/Rect" in raw and b"/Widget" in raw, "La firma no tiene apariencia visible"
        code = str(meta_signed.get("verification_code") or "")
        assert len(code.replace("-", "")) == 16, code
        assert fe._signature_stamp_box("receta") != fe._signature_stamp_box("certificado")
        qr_payload = fe._signature_qr_payload(
            "certificado",
            code,
            datetime.now(),
            {
                "not_before": "2026-07-23T15:38:10",
                "not_after": "2027-07-23T15:38:10",
            },
        )
        assert qr_payload.startswith(fe._VERIFICATION_PAGE_URL + "?"), qr_payload
        assert "FIRMASEGURA" not in qr_payload.upper()
        assert "doc-prueba-001" not in qr_payload, "El QR no debe exponer el ID interno"
        assert "c=" in qr_payload and "t=C" in qr_payload
        assert "i=20260723" in qr_payload and "e=20270723" in qr_payload
        assert "patient" not in qr_payload.lower() and "cedula" not in qr_payload.lower()

        fe._session_clear()
        assert fe._status(root)["unlocked"] is False

    print("HISTORIA_PADES_SMOKE_OK")


if __name__ == "__main__":
    main()

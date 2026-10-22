#!/usr/bin/env python3
"""Production R2 S3 presign round-trip with a synthetic PDF, no clinical records.

Uses the exact _r2_url and _upload_r2 implementations from Reception without
importing the application or accessing either clinical database. The credentials
are read from the GitHub Actions process environment only; never logged.
"""
from __future__ import annotations

import ast
import hashlib
import hmac
import http.client
import os
import re
import secrets
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SOURCE = Path("recepcion/app/clinical_delivery.py")
BUCKET = "dr-revelo-clinical-2026"
PREFIX = "clinical-temp/self-test/"
required = ["CLINICAL_R2_ACCOUNT_ID", "CLINICAL_R2_ACCESS_KEY_ID", "CLINICAL_R2_SECRET_ACCESS_KEY"]
for key in required:
    if not os.environ.get(key, "").strip():
        raise SystemExit("R2_S3_SECRET_MISSING: " + key)
if not re.fullmatch(r"[0-9a-fA-F]{32}", os.environ["CLINICAL_R2_ACCOUNT_ID"]):
    raise SystemExit("R2_S3_ACCOUNT_ID_INVALID")
os.environ["CLINICAL_R2_BUCKET"] = BUCKET

# Compile only the two isolated signer/upload functions from deployed source.
# This guarantees no patient data or Neon queries can run inside this job.
tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
extract = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in ("_r2_url", "_upload_r2")]
assert {f.name for f in extract} == {"_r2_url", "_upload_r2"}
namespace = {
    "os": os, "urllib": urllib, "datetime": datetime, "timezone": timezone,
    "hashlib": hashlib, "hmac": hmac, "http": http, "Path": Path,
}
exec(compile(ast.Module(body=extract, type_ignores=[]), str(SOURCE), "exec"), namespace)
presign = namespace["_r2_url"]
upload = namespace["_upload_r2"]


def synthetic_pdf() -> bytes:
    stream = b"BT /F1 22 Tf 35 145 Td (PRUEBA SIN DATOS MEDICOS) Tj ET"
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 550 220] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = [0]
    for i, entry in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + entry + b"\nendobj\n"
    startxref = len(out)
    out += b"xref\n0 6\n0000000000 65535 f \n"
    for offset in offsets[1:]:
        out += f"{offset:010d} 00000 n \n".encode()
    return out + b"trailer\n<< /Root 1 0 R /Size 6 >>\nstartxref\n" + str(startxref).encode() + b"\n%%EOF\n"


def request(method: str, key: str, *, timeout=20) -> bytes:
    # URL never leaves this process or CI logs because it is a bearer credential.
    url = presign(method, key, 180)
    req = urllib.request.Request(url, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(50000)


def run():
    pdf = synthetic_pdf()
    key = PREFIX + secrets.token_hex(20) + ".pdf"
    tmp_path = None
    uploaded = False
    deleted = False
    try:
        with tempfile.NamedTemporaryFile(prefix="revelo_r2_s3_",
                                         suffix=".pdf", delete=False) as f:
            tmp_path = f.name
            f.write(pdf)
        upload(tmp_path, key, "application/pdf")
        uploaded = True
        print("R2_S3_PUT_USING_RECEPTION_SIGNER_OK")
        downloaded = request("GET", key)
        if not hmac.compare_digest(hashlib.sha256(downloaded).digest(),
                                   hashlib.sha256(pdf).digest()):
            raise RuntimeError("R2_S3_GET_PDF_HASH_MISMATCH")
        print("R2_S3_GET_USING_RECEPTION_SIGNER_SHA256_OK")
        request("DELETE", key)
        deleted = True
        print("R2_S3_DELETE_USING_RECEPTION_SIGNER_OK")
        try:
            request("GET", key)
        except urllib.error.HTTPError as exc:
            if exc.code not in (404, 410):
                raise RuntimeError(f"R2_S3_AFTER_DELETE_HTTP_{exc.code}") from None
        else:
            raise RuntimeError("R2_S3_OBJECT_STILL_ACCESSIBLE_AFTER_DELETE")
        print("R2_S3_TEST_OK_NO_PATIENT_DATA")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"R2_S3_HTTP_{exc.code}") from None
    except urllib.error.URLError:
        raise RuntimeError("R2_S3_NETWORK_FAILURE") from None
    finally:
        if uploaded and not deleted:
            try:
                request("DELETE", key)
                print("R2_S3_FAILED_TEST_OBJECT_CLEANED_UP")
            except Exception:
                print("R2_S3_FAILED_TEST_OBJECT_REMAINS_UP_TO_7_DAYS")
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


if __name__ == "__main__":
    run()

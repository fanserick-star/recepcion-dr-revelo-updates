"""Prueba Windows real: CryptProtectData/CryptUnprotectData usando el usuario actual.

No emplea certificado ni contraseña reales; Windows runner efímero en Actions.
"""
import os
import tempfile
from pathlib import Path

import firma_electronica as fe


def main():
    assert os.name == "nt", "Este test solo es válido en Windows."
    with tempfile.TemporaryDirectory(prefix="historia_dpapi_windows_native_") as tmp:
        root = Path(tmp)
        cert = fe._paths(root)["certificate"]
        cert.parent.mkdir(parents=True, exist_ok=True)
        cert.write_bytes(b"PKCS12-ficticio-unicamente-entropia-de-prueba")
        secret = b"PASSWORD_TEST_WINDOWS_UNICAMENTE"
        fe._save_remembered_secret(root, secret)
        saved = fe._remember_file(root)
        blob = saved.read_bytes()
        assert blob.startswith(fe._SAVED_SECRET_MAGIC)
        assert secret not in blob, "Nunca escribir clave sin cifrar."

        unprotected = fe._dpapi_crypt(
            blob[len(fe._SAVED_SECRET_MAGIC):],
            fe._certificate_entropy(root),
            decrypt=True,
        )
        assert unprotected == secret
        cert.write_bytes(b"certificado-diferente")
        failed = False
        try:
            fe._dpapi_crypt(
                blob[len(fe._SAVED_SECRET_MAGIC):],
                fe._certificate_entropy(root),
                decrypt=True,
            )
        except OSError:
            failed = True
        assert failed, "La clave protegida debe estar ligada al P12 actual."

        fe._forget_remembered_secret(root)
        assert not saved.exists()
        assert not fe._status(root)["remembered"]
    print("HISTORIA_DPAPI_WINDOWS_NATIVE_OK")


if __name__ == "__main__":
    main()

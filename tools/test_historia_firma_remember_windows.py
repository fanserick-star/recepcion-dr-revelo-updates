"""Regresiones de la firma recordada: simulación de DPAPI en CI Linux.

Windows CryptProtectData se valida adicionalmente en la PC del consultorio:
esta prueba no afirma que Linux ejecute la API nativa de Windows.
"""
import tempfile
from pathlib import Path
import firma_electronica as fe
from test_historia_firma_pades import _test_pkcs12


def _fake_dpapi(value: bytes, entropy: bytes, *, decrypt: bool) -> bytes:
    """Simula integridad/entropía; NO se usa en producción."""
    from hashlib import sha256
    key = sha256(entropy + b"CI_SIMULADO_NO_PRODUCCION").digest()
    if decrypt:
        assert value.startswith(b"CI_ONLY:")
        value = value[len(b"CI_ONLY:"):]
        return bytes(v ^ key[i % len(key)] for i, v in enumerate(value))
    encoded = bytes(v ^ key[i % len(key)] for i, v in enumerate(value))
    return b"CI_ONLY:" + encoded


def main():
    original_can = fe._can_remember
    original_crypt = fe._dpapi_crypt
    try:
        fe._can_remember = lambda: True
        fe._dpapi_crypt = _fake_dpapi
        with tempfile.TemporaryDirectory(prefix="historia_dpapi_test_") as tmp:
            root = Path(tmp)
            credential = fe._remember_file(root)
            cert = fe._paths(root)["certificate"]
            cert.parent.mkdir(parents=True, exist_ok=True)
            password = "CI_SoloPruebas_2026!"
            _test_pkcs12(cert, password.encode("utf-8"))
            fe._session_clear()
            assert not credential.exists()
            assert not fe._status(root)["unlocked"]

            # Sin aceptación no se guarda. Con opt-in se escribe únicamente
            # una carga cifrada DPAPI, ligada a los bytes del P12 actual.
            fe._unlock(root, password)
            assert not credential.exists()
            fe._save_remembered_secret(root, password.encode("utf-8"))
            raw = credential.read_bytes()
            assert raw.startswith(fe._SAVED_SECRET_MAGIC)
            assert password.encode("utf-8") not in raw

            # Reinicio del proceso => al consultar estado se restaura sola.
            fe._session_clear()
            assert fe._status(root)["unlocked"]
            assert fe._status(root)["remembered"]

            # Bloquear temporalmente NO debe autoreactivar desde DPAPI.
            fe._block_remembered_session()
            assert fe._status(root)["unlocked"] is False
            assert credential.exists()

            # Cambio de P12 invalida contraseña recordada.
            fe._AUTOUNLOCK_DISABLED = False
            fe._session_clear()
            _test_pkcs12(cert, password.encode("utf-8"))
            assert not fe._try_restore_remembered(root)
            assert not fe._status(root)["unlocked"]
            assert fe._AUTOUNLOCK_DISABLED

            # Reconfiguración expresa, olvido local y no auto-descifrado.
            fe._unlock(root, password)
            fe._save_remembered_secret(root, password.encode("utf-8"))
            fe._forget_remembered_secret(root)
            fe._session_clear()
            assert not credential.exists()
            assert not fe._status(root)["unlocked"]
            assert not fe._status(root)["remembered"]
    finally:
        fe._session_clear()
        fe._can_remember = original_can
        fe._dpapi_crypt = original_crypt
        fe._AUTOUNLOCK_DISABLED = False

    import documentos_clinicos as docs
    form = docs._inline_signature_activation_dialog()
    assert 'id="hcs-remember"' in form
    assert "remember:remember.checked" in form
    assert "/api/firma/desbloquear" in form
    assert "localStorage" not in form and "sessionStorage" not in form
    # La preferencia es explícita, no equivale a firmar sin tocar el botón.
    assert "saveCert(" not in form
    assert "saveRest(" not in form
    print("HISTORIA_FIRMA_RECORDAR_PROTEGIDA_OK")


if __name__ == "__main__":
    main()

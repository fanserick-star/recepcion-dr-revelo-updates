#!/usr/bin/env python3
"""No real credentials. Offline sealing regression checks."""
import hashlib
import hmac
from pathlib import Path
import struct
import tempfile
import unittest
from seal_private_installer import MARKER, MAGIC, FOOTER_FORMAT, read_config, seal

class SealTests(unittest.TestCase):
    def test_roundtrip_and_tamper_detection(self):
        data = (
            "DR_REVELO_CONFIG_V2\n"
            "[RECEPTION]\nDATABASE_URL=postgresql://example.invalid/rec\n"
            "AZUR_API_KEY=fake\n"
            "[HISTORIA]\nHISTORIA_DATABASE_URL=postgresql://example.invalid/hist\n"
        ).encode()
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "private.txt"
            p.write_bytes(data)
            self.assertEqual(data, read_config(p))
        base = b"MZ" + b"fake-machine-code" + MARKER + b"none"
        packed = seal(base, data)
        self.assertNotIn(data, packed)
        self.assertNotIn(MARKER, packed)
        size = struct.calcsize(FOOTER_FORMAT)
        magic, version, length, nonce, tag = struct.unpack(FOOTER_FORMAT, packed[-size:])
        self.assertEqual((magic, version, length), (MAGIC, 2, len(data)))
        cipher = packed[-size-length:-size]
        key = packed[2+len(b"fake-machine-code"):2+len(b"fake-machine-code")+64]
        expected = hmac.new(key[32:], struct.pack("<II", 2, length)+nonce+cipher, hashlib.sha256).digest()
        self.assertTrue(hmac.compare_digest(expected, tag))
        restored = bytearray()
        for counter, i in enumerate(range(0, length, 32)):
            stream = hashlib.sha256(key[:32]+nonce+struct.pack("<I",counter)).digest()
            restored.extend(x ^ y for x,y in zip(cipher[i:i+32],stream))
        self.assertEqual(bytes(restored), data)
        self.assertNotEqual(seal(base,data),packed)
        with self.assertRaises(ValueError):
            seal(packed,data)

    def test_reject_duplicate_urls(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "private.txt"
            f.write_text("DR_REVELO_CONFIG_V2\n[RECEPTION]\nDATABASE_URL=same\n[HISTORIA]\nHISTORIA_DATABASE_URL=same\n")
            with self.assertRaises(ValueError):
                read_config(f)
    def test_reject_unsealed_input(self):
        with self.assertRaises(ValueError):
            seal(b"MZ-no-marker",b"anything")

if __name__ == "__main__":
    unittest.main()

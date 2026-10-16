"""Safe negative check of the Cloudflare gateway using Reception's real HTTP identification.

POST body is deliberately INVALID JSON; no token, patient data, alarm,
database lookup or WhatsApp send is possible. Expected HTTP 400 invalid_json.
No application imports or environment access.
"""
from __future__ import annotations
import json
from pathlib import Path
import re
from urllib.error import HTTPError
from urllib.request import Request, urlopen

root = Path(__file__).resolve().parents[1]
src = (root / "recepcion/app/core_runtime.py").read_text(encoding="utf-8")
url = re.search(r'^_WA_GATEWAY_URL\s*=\s*"(https://[^"]+)"', src, flags=re.M)
ua = re.search(r'^_WA_GATEWAY_USER_AGENT\s*=\s*"([^"]+)"', src, flags=re.M)
assert url is not None and ua is not None
assert url.group(1) == "https://dr-revelo-whatsapp-cloud.drrevelo.workers.dev/reception/gateway"
assert ua.group(1).startswith("curl/")
req = Request(
    url.group(1),
    data=b"invalid",
    headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": ua.group(1)},
    method="POST",
)
try:
    with urlopen(req, timeout=12) as resp:
        raise AssertionError(f"Unexpected positive response {resp.status}")
except HTTPError as exc:
    body = exc.read(512)
    assert exc.code == 400, f"Expected Worker 400, got HTTP {exc.code}"
    msg = json.loads(body.decode("utf-8"))
    assert msg == {"ok": False, "error": "invalid_json"}, "Unexpected Worker error"
print("RECEPTION_CLOUDFLARE_1010_UA_NEGATIVE_PROBE_OK_NO_WA_NO_NEON")

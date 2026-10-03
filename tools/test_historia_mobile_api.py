from __future__ import annotations

import json
import urllib.request
from pathlib import Path

AUTH_URL = "https://ep-shiny-scene-a66ta52d.neonauth.us-west-2.aws.neon.tech/neondb/auth/token/anonymous"
API_URL = "https://ep-sweet-mud-arlsk7qa.apirest.c-4.us-west-2.aws.neon.tech/neondb/rest/v1"
ORIGIN = "https://fanserick-star.github.io"
TEST_TOKEN = "historia-mobile-ci-probe-20261003"


def request_json(url: str, *, method: str = "GET", jwt: str = "", body=None):
    headers = {"Accept": "application/json", "Origin": ORIGIN, "Cache-Control": "no-store"}
    data = None
    if jwt:
        headers["Authorization"] = "Bearer " + jwt
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body, separators=(",", ":")).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=25) as response:
        raw = response.read()
        return response.status, dict(response.headers.items()), json.loads(raw.decode("utf-8") or "null")


def main() -> None:
    _, _, auth = request_json(AUTH_URL)
    jwt = str((auth or {}).get("token") or "")
    if jwt.count(".") != 2:
        raise RuntimeError("Reception anonymous JWT was not issued")

    status_http, status_headers, status = request_json(
        API_URL + "/rpc/status",
        method="POST",
        jwt=jwt,
        body={"p_token": TEST_TOKEN},
    )
    search_http, _, search = request_json(
        API_URL + "/rpc/search",
        method="POST",
        jwt=jwt,
        body={"p_token": TEST_TOKEN, "p_query": "KURE BUSTAMANTE"},
    )

    cors = str(status_headers.get("Access-Control-Allow-Origin") or "") == ORIGIN
    ok = (
        status_http == 200
        and search_http == 200
        and isinstance(status, dict)
        and bool(status.get("ok"))
        and status.get("source") == "historia_neon"
        and isinstance(search, list)
        and len(search) >= 1
        and cors
    )
    result = {
        "status_http": status_http,
        "search_http": search_http,
        "status_ok": bool(status.get("ok")) if isinstance(status, dict) else False,
        "source": status.get("source") if isinstance(status, dict) else None,
        "search_count": len(search) if isinstance(search, list) else -1,
        "cors_ok": cors,
        "ok": ok,
    }
    Path("diagnostics").mkdir(exist_ok=True)
    Path("diagnostics/historia-data-api-probe.json").write_text(
        json.dumps(result, ensure_ascii=False), encoding="utf-8"
    )
    if not ok:
        raise SystemExit("Historia mobile direct path failed")
    print("HISTORIA_MOBILE_DIRECT_OK")


if __name__ == "__main__":
    main()

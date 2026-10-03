from __future__ import annotations

import json
import urllib.error
import urllib.request

AUTH_URL="https://ep-shiny-scene-a66ta52d.neonauth.us-west-2.aws.neon.tech/neondb/auth/token/anonymous"
API_URL="https://ep-sweet-mud-arlsk7qa.apirest.c-4.us-west-2.aws.neon.tech/neondb/rest/v1"
ORIGIN="https://fanserick-star.github.io"
PROBE_TOKEN="historia-mobile-safe-probe-20261003"

def request(url, *, method="GET", jwt="", body=None, extra=None):
    headers={"Accept":"application/json","Origin":ORIGIN,"Cache-Control":"no-store"}
    if jwt:
        headers["Authorization"]="Bearer "+jwt
    data=None
    if body is not None:
        headers["Content-Type"]="application/json"
        data=json.dumps(body,separators=(",",":")).encode("utf-8")
    if extra:
        headers.update(extra)
    req=urllib.request.Request(url,data=data,headers=headers,method=method)
    try:
        with urllib.request.urlopen(req,timeout=25) as response:
            return response.status,dict(response.headers.items()),response.read().decode("utf-8","replace")
    except urllib.error.HTTPError as exc:
        return exc.code,dict(exc.headers.items()),exc.read().decode("utf-8","replace")

def allow_origin(headers):
    for key,value in headers.items():
        if key.lower()=="access-control-allow-origin":
            return str(value)
    return ""

def main():
    auth_http,_,raw=request(AUTH_URL)
    auth=json.loads(raw or "{}")
    jwt=str(auth.get("token") or "")
    if auth_http!=200 or jwt.count(".")!=2:
        raise SystemExit("HISTORIA_MOBILE_AUTH_FAILED")

    options_http,options_headers,_=request(
        API_URL+"/rpc/ping",
        method="OPTIONS",
        extra={
            "Access-Control-Request-Method":"POST",
            "Access-Control-Request-Headers":"authorization,content-type",
        },
    )
    ping_http,ping_headers,raw=request(
        API_URL+"/rpc/ping",
        method="POST",
        jwt=jwt,
        body={"p_probe_token":PROBE_TOKEN},
    )
    try:
        ping=json.loads(raw or "{}")
    except Exception:
        ping={}

    origins={allow_origin(options_headers),allow_origin(ping_headers)}
    cors_ok=all(value in {ORIGIN,"*"} for value in origins if value) and bool(origins- {""})
    ok=(
        options_http in (200,204)
        and ping_http==200
        and isinstance(ping,dict)
        and ping.get("ok") is True
        and ping.get("source")=="historia_neon"
        and ping.get("mode")=="read_only"
        and cors_ok
    )
    print(json.dumps({
        "auth_http":auth_http,
        "options_http":options_http,
        "ping_http":ping_http,
        "ping_ok":bool(ping.get("ok")) if isinstance(ping,dict) else False,
        "source":ping.get("source") if isinstance(ping,dict) else None,
        "cors_ok":cors_ok,
        "ok":ok,
    },separators=(",",":")))
    if not ok:
        raise SystemExit("HISTORIA_MOBILE_SAFE_PROBE_FAILED")
    print("HISTORIA_MOBILE_SAFE_PROBE_OK")

if __name__=="__main__":
    main()

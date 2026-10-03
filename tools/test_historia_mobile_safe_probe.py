from __future__ import annotations

import json
import urllib.error
import urllib.request

AUTH_URL="https://ep-sweet-mud-arlsk7qa.neonauth.us-west-2.aws.neon.tech/neondb/auth/token/anonymous"
API_URL="https://ep-sweet-mud-arlsk7qa.apirest.c-4.us-west-2.aws.neon.tech/neondb/rest/v1"
ORIGIN="https://fanserick-star.github.io"
PROBE_TOKEN="historia-mobile-safe-probe-20261003"

def request(url, *, method="GET", body=None, extra=None):
    headers={"Accept":"application/json","Origin":ORIGIN,"Cache-Control":"no-store"}
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
    try:
        auth=json.loads(raw or "{}")
    except Exception:
        auth={}
    jwt=str(auth.get("token") or "")
    auth_ok=(auth_http==200 and jwt.count(".")==2)

    options_http,options_headers,_=request(
        API_URL+"/rpc/status",
        method="OPTIONS",
        extra={
            "Access-Control-Request-Method":"POST",
            "Access-Control-Request-Headers":"authorization,content-type",
        },
    )
    status_http,status_headers,raw=request(
        API_URL+"/rpc/status",
        method="POST",
        jwt=jwt if auth_ok else "",
        body={"p_token":"historia-mobile-invalid-probe"},
    )
    try:
        denied=json.loads(raw or "{}")
    except Exception:
        denied={}

    origins={allow_origin(options_headers),allow_origin(status_headers)}
    cors_ok=all(value in {ORIGIN,"*"} for value in origins if value) and bool(origins- {""})
    denied_message=str(denied.get("message") or "") if isinstance(denied,dict) else ""
    access_guard_ok=(
        status_http in (401,403)
        and "Acceso clínico no autorizado" in denied_message
    )
    ok=(
        auth_ok
        and options_http in (200,204)
        and access_guard_ok
        and cors_ok
    )
    print(json.dumps({
        "auth_http":auth_http,
        "auth_ok":auth_ok,
        "options_http":options_http,
        "guard_http":status_http,
        "guard_code":str(denied.get("code") or "") if isinstance(denied,dict) else "",
        "guard_message":str(denied.get("message") or "")[:180] if isinstance(denied,dict) else "",
        "access_guard_ok":access_guard_ok,
        "cors_ok":cors_ok,
        "ok":ok,
    },separators=(",",":")))
    if not ok:
        raise SystemExit("HISTORIA_MOBILE_SAFE_PROBE_FAILED")
    print("HISTORIA_MOBILE_SAFE_PROBE_OK")

if __name__=="__main__":
    main()

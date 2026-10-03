from __future__ import annotations

import json
import urllib.error
import urllib.request

AUTH_URL="https://ep-shiny-scene-a66ta52d.neonauth.us-west-2.aws.neon.tech/neondb/auth/token/anonymous"
API_URL="https://ep-sweet-mud-arlsk7qa.apirest.c-4.us-west-2.aws.neon.tech/neondb/rest/v1"
ORIGIN="https://fanserick-star.github.io"
TOKEN="historia-mobile-ci-probe-20261003"

def call(url, *, method="GET", jwt="", body=None, extra=None):
    headers={"Accept":"application/json","Origin":ORIGIN,"Cache-Control":"no-store"}
    if jwt:
        headers["Authorization"]="Bearer "+jwt
    if body is not None:
        headers["Content-Type"]="application/json"
        data=json.dumps(body,separators=(",",":")).encode()
    else:
        data=None
    if extra:
        headers.update(extra)
    req=urllib.request.Request(url,data=data,headers=headers,method=method)
    try:
        with urllib.request.urlopen(req,timeout=25) as resp:
            return resp.status,dict(resp.headers.items()),resp.read().decode("utf-8","replace")
    except urllib.error.HTTPError as exc:
        return exc.code,dict(exc.headers.items()),exc.read().decode("utf-8","replace")

def cors_ok(headers):
    value=""
    for k,v in headers.items():
        if k.lower()=="access-control-allow-origin":
            value=str(v)
            break
    return value in {ORIGIN,"*"}

def main():
    auth_http,_,raw=call(AUTH_URL)
    auth=json.loads(raw or "{}")
    jwt=str(auth.get("token") or "")
    if auth_http!=200 or jwt.count(".")!=2:
        raise SystemExit("AUTH_FAILED")

    options_http,options_headers,_=call(
        API_URL+"/rpc/search",
        method="OPTIONS",
        extra={
            "Access-Control-Request-Method":"POST",
            "Access-Control-Request-Headers":"authorization,content-type",
        },
    )
    search_http,search_headers,raw=call(
        API_URL+"/rpc/search",
        method="POST",
        jwt=jwt,
        body={"p_token":TOKEN,"p_query":"KURE BUSTAMANTE"},
    )
    try:
        rows=json.loads(raw or "[]")
    except Exception:
        rows=[]
    patient_id=str(rows[0].get("patient_id") or "") if isinstance(rows,list) and rows else ""

    patient_http=0
    patient_headers={}
    patient={}
    if patient_id:
        patient_http,patient_headers,raw=call(
            API_URL+"/rpc/patient",
            method="POST",
            jwt=jwt,
            body={"p_token":TOKEN,"p_patient_id":patient_id},
        )
        try:
            patient=json.loads(raw or "{}")
        except Exception:
            patient={}

    encounter_count=len(patient.get("encounters") or []) if isinstance(patient,dict) else -1
    ok=(
        auth_http==200
        and options_http in (200,204)
        and search_http==200
        and isinstance(rows,list) and len(rows)>=1
        and patient_http==200
        and isinstance(patient,dict)
        and bool((patient.get("patient") or {}).get("id"))
        and encounter_count>=1
        and cors_ok(options_headers)
        and cors_ok(search_headers)
        and cors_ok(patient_headers)
    )
    result={
        "auth_http":auth_http,
        "options_http":options_http,
        "search_http":search_http,
        "search_count":len(rows) if isinstance(rows,list) else -1,
        "patient_http":patient_http,
        "patient_loaded":bool((patient.get("patient") or {}).get("id")) if isinstance(patient,dict) else False,
        "encounter_count":encounter_count,
        "cors_ok":cors_ok(options_headers) and cors_ok(search_headers) and cors_ok(patient_headers),
        "ok":ok,
    }
    print(json.dumps(result,separators=(",",":")))
    if not ok:
        raise SystemExit("HISTORIA_MOBILE_APP_PATH_FAILED")
    print("HISTORIA_MOBILE_APP_PATH_OK")

if __name__=="__main__":
    main()
